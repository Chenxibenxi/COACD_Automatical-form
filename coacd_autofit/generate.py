"""生成阶段：按用户给的精度要求，反查最优 threshold，跑 CoACD 生成碰撞片，
导出 obj + 可直接粘进 MJCF 的片段，并回报实际达到的精度。

三种要求(择一)：
  --target-mm X   真实精度：要求 Hausdorff <= X mm。从制表结果里挑"满足精度的
                  前提下片数最少"的那一档(即最大的、还满足要求的 threshold)。
  --max-parts N   片数预算：碰撞体最多 N 片。挑"不超预算的前提下精度最好"的那档。
  --threshold T   直接给 CoACD threshold，跳过反查，不需要制表结果。

前两种需要该网格的制表结果(sweep json)。没有就现场先扫一遍(用 --thresholds 控
制档位)。选定 threshold 后用同一套"最优情况"默认参数跑出碰撞片。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import trimesh

from . import decompose
from .fit import fit_error_mm
from .meshio import clean_and_merge_solid, load_mesh
from .sweep import sweep_mesh

# 跟原 coacd_fit_check 渲染用的碰撞几何属性一致，方便直接进物理仿真
GEOM_ATTRS = {
    "solimp": "0.998 0.998 0.001",
    "solref": "0.001 1",
    "density": "100",
    "friction": "0.95 0.3 0.1",
}


def _pick_threshold(rows, target_mm, max_parts):
    """从制表结果里按要求挑 threshold，返回 (threshold, 选中行, 提示语)。"""
    rows = sorted(rows, key=lambda r: r["threshold"])
    if target_mm is not None:
        ok = [r for r in rows if r["hausdorff_mm"] <= target_mm]
        if ok:
            # 满足精度的前提下片数最少 = threshold 最大的那一档
            best = max(ok, key=lambda r: r["threshold"])
            return best["threshold"], best, (
                f"满足 Hausdorff<={target_mm}mm 的最省片数档：threshold={best['threshold']}"
                f"，预计 {best['n_parts']} 片 / {best['hausdorff_mm']:.2f}mm"
            )
        best = min(rows, key=lambda r: r["hausdorff_mm"])  # 都不满足，退回最精确的
        return best["threshold"], best, (
            f"⚠ 制表结果里没有任何一档能达到 {target_mm}mm，最精确的是 threshold="
            f"{best['threshold']}({best['hausdorff_mm']:.2f}mm / {best['n_parts']} 片)，"
            f"用它。要更细可减小 --thresholds 下限重扫。"
        )
    if max_parts is not None:
        ok = [r for r in rows if r["n_parts"] <= max_parts]
        if ok:
            # 不超预算的前提下精度最好 = Hausdorff 最小
            best = min(ok, key=lambda r: r["hausdorff_mm"])
            return best["threshold"], best, (
                f"不超 {max_parts} 片预算里精度最好的档：threshold={best['threshold']}"
                f"，{best['n_parts']} 片 / {best['hausdorff_mm']:.2f}mm"
            )
        best = min(rows, key=lambda r: r["n_parts"])  # 都超预算，退回片数最少的
        return best["threshold"], best, (
            f"⚠ 制表结果里最省的一档也有 {best['n_parts']} 片，超过预算 {max_parts}，"
            f"用它(threshold={best['threshold']})。要更少片可加大 --thresholds 上限重扫。"
        )
    raise ValueError("需要 --target-mm / --max-parts / --threshold 三者之一")


def _export_mjcf_snippet(name, part_paths, out_path, group="3"):
    """写一段 <asset>+<geom> 的 MJCF 片段，用户粘进自己的 body 里即可用。"""
    asset = ET.Element("asset")
    geoms = []
    for i, p in enumerate(part_paths):
        mesh_name = f"{name}_col_{i:02d}"
        ET.SubElement(asset, "mesh", {"name": mesh_name, "file": str(p)})
        g = ET.Element("geom", dict(GEOM_ATTRS))
        g.set("type", "mesh")
        g.set("mesh", mesh_name)
        g.set("group", group)
        geoms.append(g)
    root = ET.Element("mujoco_collision_snippet")
    root.append(asset)
    body_hint = ET.SubElement(root, "body_geoms_把下面这些_geom_放进你的_body_")
    for g in geoms:
        body_hint.append(g)
    ET.indent(root, space="  ")
    Path(out_path).write_text(ET.tostring(root, encoding="unicode"))


def generate(
    mesh_path,
    out_dir,
    target_mm=None,
    max_parts=None,
    threshold=None,
    unit="m",
    thresholds=None,
    mcts_nodes=decompose.DEFAULT_MCTS_NODES,
    mcts_iterations=decompose.DEFAULT_MCTS_ITERATIONS,
    merge_solid=True,
) -> dict:
    given = [x is not None for x in (target_mm, max_parts, threshold)]
    if sum(given) != 1:
        raise ValueError("--target-mm / --max-parts / --threshold 必须且只能给一个")

    mesh_path = Path(mesh_path)
    name = mesh_path.stem
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 选 threshold
    if threshold is not None:
        chosen, note = threshold, f"直接使用给定 threshold={threshold}"
    else:
        json_path = out_dir / f"{name}.json"
        if json_path.exists():
            import json as _json

            table = _json.loads(json_path.read_text())
            print(f"用已有制表结果: {json_path}", flush=True)
        else:
            print("没有制表结果，现场先扫一遍...", flush=True)
            table = sweep_mesh(
                mesh_path, out_dir=out_dir, thresholds=thresholds, unit=unit,
                mcts_nodes=mcts_nodes, mcts_iterations=mcts_iterations, merge_solid=merge_solid,
            )
        chosen, _row, note = _pick_threshold(table["rows"], target_mm, max_parts)
    print(f"选档: {note}", flush=True)

    # 用选定 threshold 生成碰撞片
    visual_mesh = load_mesh(mesh_path, unit=unit)
    src_mesh = clean_and_merge_solid(visual_mesh) if merge_solid else visual_mesh
    print(f"用 threshold={chosen} 生成碰撞片...", flush=True)
    parts, gen_time = decompose.run(
        src_mesh, threshold=chosen, mcts_nodes=mcts_nodes, mcts_iterations=mcts_iterations
    )
    print(f"CoACD: {len(parts)} 片, {gen_time:.1f}s", flush=True)

    # 导出每片 obj
    parts_dir = out_dir / f"{name}_collision"
    parts_dir.mkdir(exist_ok=True)
    part_paths = []
    for i, (v, f) in enumerate(parts):
        p = parts_dir / f"part_{i:02d}.obj"
        trimesh.Trimesh(vertices=v, faces=f, process=False).export(str(p))
        part_paths.append(p)

    snippet_path = out_dir / f"{name}_collision.xml"
    _export_mjcf_snippet(name, part_paths, snippet_path)

    # 回报实际精度
    err = fit_error_mm(parts, visual_mesh)
    print(f"\n{'='*56}")
    print(f"生成完成: {len(parts)} 片，实际 Hausdorff = {err['hausdorff_mm']:.3f} mm")
    print(f"  碰撞片: {parts_dir}/part_*.obj ({len(part_paths)} 个)")
    print(f"  MJCF 片段: {snippet_path}")
    print(f"{'='*56}")
    return {
        "name": name, "threshold": chosen, "n_parts": len(parts),
        "hausdorff_mm": err["hausdorff_mm"], "gen_time_s": gen_time,
        "parts_dir": str(parts_dir), "snippet": str(snippet_path),
    }


# ---- CLI 挂载 ----

def add_generate_parser(sub):
    p = sub.add_parser("generate", help="按精度要求生成碰撞模型(obj + MJCF 片段)")
    p.add_argument("mesh", help="视觉网格文件")
    p.add_argument("--out-dir", default="./coacd_autofit_out")
    p.add_argument("--unit", choices=["m", "cm", "mm"], default="m")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target-mm", type=float, help="要求真实 Hausdorff <= 这么多毫米")
    g.add_argument("--max-parts", type=int, help="碰撞体最多几片")
    g.add_argument("--threshold", type=float, help="直接给 CoACD threshold")
    p.add_argument("--thresholds", help="现场制表时的档位(逗号分隔)")
    p.add_argument("--mcts-nodes", type=int, default=decompose.DEFAULT_MCTS_NODES)
    p.add_argument("--mcts-iterations", type=int, default=decompose.DEFAULT_MCTS_ITERATIONS)
    p.add_argument("--no-merge-solid", action="store_true")


def run_generate(args):
    thresholds = [float(x) for x in args.thresholds.split(",")] if args.thresholds else None
    generate(
        args.mesh, out_dir=args.out_dir, target_mm=args.target_mm, max_parts=args.max_parts,
        threshold=args.threshold, unit=args.unit, thresholds=thresholds,
        mcts_nodes=args.mcts_nodes, mcts_iterations=args.mcts_iterations,
        merge_solid=not args.no_merge_solid,
    )
