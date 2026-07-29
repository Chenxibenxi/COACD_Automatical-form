"""把 sweep 产出的 json 画成图：每个物体一张(两个子图——相对单位 vs 片数、
Hausdorff 精度 vs 片数)，标注每个点对应的输入 threshold。

字体：优先用系统里的 Noto CJK(中文标签好看)，找不到就退回 matplotlib 默认字体，
不因为缺字体报错(打包给别人用时机器上不一定装了 CJK 字体)。
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

INK, INK_SOFT, GRID, LINE, MARKER_FACE = "#1A2424", "#5A6666", "#D8DEDD", "#0E7A74", "#F6F8F7"

_CJK_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _setup_style():
    for p in _CJK_CANDIDATES:
        if Path(p).exists():
            try:
                fm.fontManager.addfont(p)
                plt.rcParams["font.family"] = "Noto Sans CJK JP"
                break
            except Exception:
                pass
    plt.rcParams.update({
        "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK,
        "text.color": INK, "xtick.color": INK_SOFT, "ytick.color": INK_SOFT,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    })


def plot_result(result: dict, out_path) -> Path:
    """result 是 sweep_mesh 的返回(或它写出的 json)。画一张图存到 out_path。"""
    _setup_style()
    name = result["name"]
    data = sorted(result["rows"], key=lambda r: r["n_parts"])
    n_parts = [r["n_parts"] for r in data]
    rel_unit = [r["relative_unit"] for r in data]
    hausdorff = [r["hausdorff_mm"] for r in data]
    thresholds = [r["threshold"] for r in data]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    fig.patch.set_facecolor("white")

    for ax, ys, ylabel, title in [
        (axes[0], rel_unit, "近似相对单位 (Hausdorff / 包围盒对角线)", "相对单位 vs 片数"),
        (axes[1], hausdorff, "真实精度差距 Hausdorff 距离 (mm)", "真实精度差距 vs 片数"),
    ]:
        ax.plot(n_parts, ys, color=LINE, linewidth=2, marker="o", markersize=6,
                markerfacecolor=MARKER_FACE, markeredgecolor=LINE, markeredgewidth=2)
        for x, y, t in zip(n_parts, ys, thresholds):
            ax.annotate(f"th={t}", (x, y), textcoords="offset points", xytext=(6, 6),
                        fontsize=8, color=INK_SOFT)
        ax.set_xlabel("片数 (凸包数)")
        ax.set_ylabel(ylabel)
        ax.set_title(title, color=INK, fontsize=12, fontweight="bold")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    fig.suptitle(
        f"{name}: CoACD threshold 扫描 "
        f"(mcts={result.get('mcts_nodes', '?')}/{result.get('mcts_iterations', '?')}, "
        f"{len(data)} 个点)\n自变量=凸包片数, 因变量=相对单位 / Hausdorff 精度差距",
        fontsize=10, color=INK_SOFT, y=1.08,
    )
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def plot_json(json_path, out_path=None) -> Path:
    json_path = Path(json_path)
    result = json.loads(json_path.read_text())
    if isinstance(result, list):  # 兼容旧纯列表格式
        result = {"name": json_path.stem, "rows": result}
    if out_path is None:
        out_path = json_path.with_name(f"threshold_sweep_{result['name']}.png")
    return plot_result(result, out_path)
