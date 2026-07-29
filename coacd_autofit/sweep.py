"""制表阶段：对一个视觉网格扫一遍 threshold，量化每档的真实精度和片数，
落盘成 json(机读，供生成阶段反查) + markdown 表 + csv。

自变量 = CoACD 输入 threshold；因变量 = 凸包片数(hull 数) 和真实 Hausdorff 精度。
每算完一档立刻落盘 json，中途中断也不丢已算的档，重跑接着算。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import decompose
from .fit import fit_error_mm
from .meshio import bbox_diag_mm, clean_and_merge_solid, load_mesh

DEFAULT_THRESHOLDS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2]


def sweep_mesh(
    mesh_path,
    out_dir,
    thresholds=None,
    unit: str = "m",
    mcts_nodes: int = decompose.DEFAULT_MCTS_NODES,
    mcts_iterations: int = decompose.DEFAULT_MCTS_ITERATIONS,
    merge_solid: bool = True,
) -> dict:
    """扫描单个网格。返回 {"name", "bbox_diag_mm", "rows": [...]}，并把 json/md/csv
    写到 out_dir。可重复调用续算(已算过的 threshold 会跳过)。"""
    mesh_path = Path(mesh_path)
    name = mesh_path.stem
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    thresholds = list(thresholds) if thresholds else list(DEFAULT_THRESHOLDS)

    visual_mesh = load_mesh(mesh_path, unit=unit)
    src_mesh = clean_and_merge_solid(visual_mesh) if merge_solid else visual_mesh
    diag_mm = bbox_diag_mm(visual_mesh)

    json_path = out_dir / f"{name}.json"
    prev = json.loads(json_path.read_text()) if json_path.exists() else {}
    rows = prev.get("rows", []) if isinstance(prev, dict) else prev  # 兼容旧纯列表格式
    done = {r["threshold"] for r in rows}

    print(f"\n########## {name} (包围盒对角线 {diag_mm:.1f}mm) ##########", flush=True)
    for threshold in thresholds:
        if threshold in done:
            print(f"  threshold={threshold} 已有结果，跳过", flush=True)
            continue
        print(f"  === threshold={threshold} ===", flush=True)
        parts, gen_time = decompose.run(
            src_mesh, threshold=threshold, mcts_nodes=mcts_nodes, mcts_iterations=mcts_iterations
        )
        print(f"    CoACD: {len(parts)} 片, {gen_time:.1f}s", flush=True)
        m = fit_error_mm(parts, visual_mesh)
        row = {
            "threshold": threshold,
            "gen_time_s": gen_time,
            "relative_unit": m["hausdorff_mm"] / diag_mm,
            "n_parts": m["n_parts"],
            "hausdorff_mm": m["hausdorff_mm"],
            "gap_max_mm": m["gap_max_mm"],
            "gap_p5_mm": m["gap_p5_mm"],
            "gap_p95_mm": m["gap_p95_mm"],
            "bulge_max_mm": m["bulge_max_mm"],
            "bulge_p5_mm": m["bulge_p5_mm"],
            "bulge_p95_mm": m["bulge_p95_mm"],
        }
        print(
            f"    片数={row['n_parts']}  Hausdorff={row['hausdorff_mm']:.3f}mm  "
            f"相对单位={row['relative_unit']:.4f}",
            flush=True,
        )
        rows.append(row)
        result = {
            "name": name,
            "bbox_diag_mm": diag_mm,
            "unit": unit,
            "mcts_nodes": mcts_nodes,
            "mcts_iterations": mcts_iterations,
            "rows": sorted(rows, key=lambda r: r["threshold"]),
        }
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    result = {
        "name": name,
        "bbox_diag_mm": diag_mm,
        "unit": unit,
        "mcts_nodes": mcts_nodes,
        "mcts_iterations": mcts_iterations,
        "rows": sorted(rows, key=lambda r: r["threshold"]),
    }
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    _write_markdown(result, out_dir / f"{name}.md")
    _write_csv(result, out_dir / f"{name}.csv")
    print(f"  已写: {json_path.name}, {name}.md, {name}.csv", flush=True)
    return result


def _write_markdown(result: dict, path: Path):
    rows = sorted(result["rows"], key=lambda r: r["n_parts"])
    lines = [
        f"### {result['name']}  (包围盒对角线 {result['bbox_diag_mm']:.1f}mm，"
        f"mcts={result['mcts_nodes']}/{result['mcts_iterations']})",
        "",
        "| 输入threshold | 片数(凸包数) | 相对单位 | Hausdorff(mm) | gap p5~p95 (mm) | bulge p5~p95 (mm) | 生成耗时(s) |",
        "|---:|---:|---:|---:|---|---|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['threshold']} | {r['n_parts']} | {r['relative_unit']:.4f} | "
            f"{r['hausdorff_mm']:.3f} | {r['gap_p5_mm']:.3f} ~ {r['gap_p95_mm']:.3f} | "
            f"{r['bulge_p5_mm']:.3f} ~ {r['bulge_p95_mm']:.3f} | {r['gen_time_s']:.1f} |"
        )
    lines.append("")
    path.write_text("\n".join(lines))


def _write_csv(result: dict, path: Path):
    rows = sorted(result["rows"], key=lambda r: r["threshold"])
    if not rows:
        return
    cols = ["threshold", "n_parts", "hausdorff_mm", "relative_unit", "gap_p5_mm",
            "gap_p95_mm", "bulge_p5_mm", "bulge_p95_mm", "gen_time_s"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
