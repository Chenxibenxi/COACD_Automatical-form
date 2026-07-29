#!/usr/bin/env python3
"""coacd_autofit 命令行入口。

    coacd-autofit table  <mesh> [选项]   # 制表：扫 threshold，产表格+图
    coacd-autofit plot   <sweep.json>    # 只把已有扫描结果重新画图
    coacd-autofit generate <mesh> [选项] # 生成：按精度要求产碰撞模型 (Phase 2)

也可以 python -m coacd_autofit.cli ...
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _add_table(sub):
    p = sub.add_parser("table", help="制表：对视觉网格扫 threshold，量化片数/真实精度")
    p.add_argument("mesh", help="视觉网格文件 (.obj/.stl/.ply/.glb ...)")
    p.add_argument("--out-dir", default="./coacd_autofit_out", help="表格/图/json 输出目录")
    p.add_argument("--unit", choices=["m", "cm", "mm"], default="m", help="输入网格单位 (默认米)")
    p.add_argument("--thresholds", help="逗号分隔的 threshold 列表，默认 0.005~0.2 八档")
    p.add_argument("--mcts-nodes", type=int, default=None)
    p.add_argument("--mcts-iterations", type=int, default=None)
    p.add_argument("--no-merge-solid", action="store_true", help="跳过多连通分量的清理/布尔合并")
    p.add_argument("--no-plot", action="store_true", help="只出表格，不画图")


def _add_plot(sub):
    p = sub.add_parser("plot", help="把已有的扫描结果 json 重新画图")
    p.add_argument("json", help="sweep 产出的 <name>.json")
    p.add_argument("--out", default=None, help="输出 png 路径")


def _run_table(args):
    from . import decompose
    from .sweep import sweep_mesh

    thresholds = [float(x) for x in args.thresholds.split(",")] if args.thresholds else None
    result = sweep_mesh(
        args.mesh,
        out_dir=args.out_dir,
        thresholds=thresholds,
        unit=args.unit,
        mcts_nodes=args.mcts_nodes if args.mcts_nodes is not None else decompose.DEFAULT_MCTS_NODES,
        mcts_iterations=(
            args.mcts_iterations if args.mcts_iterations is not None
            else decompose.DEFAULT_MCTS_ITERATIONS
        ),
        merge_solid=not args.no_merge_solid,
    )
    if not args.no_plot:
        from .plot import plot_result

        out_png = Path(args.out_dir) / f"threshold_sweep_{result['name']}.png"
        plot_result(result, out_png)
        print(f"图已写: {out_png}")


def _run_plot(args):
    from .plot import plot_json

    out = plot_json(args.json, args.out)
    print(f"图已写: {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="coacd-autofit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    _add_table(sub)
    _add_plot(sub)
    # generate 子命令在 Phase 2 注册
    try:
        from .generate import add_generate_parser, run_generate  # noqa: F401
        add_generate_parser(sub)
    except ImportError:
        pass

    args = ap.parse_args(argv)
    if args.cmd == "table":
        _run_table(args)
    elif args.cmd == "plot":
        _run_plot(args)
    elif args.cmd == "generate":
        from .generate import run_generate
        run_generate(args)


if __name__ == "__main__":
    main()
