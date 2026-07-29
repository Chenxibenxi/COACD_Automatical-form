"""通用网格加载与清理。

跟原来 LIBERO 工具链最大的区别：不再依赖 MjModel 去解 .msh 二进制视觉网格，
直接用 trimesh 读用户给的原始网格文件(.obj/.stl/.ply/.glb/.off ...)。所以也
不需要再补惯性主轴坐标系那套 mesh_quat/mesh_pos 旋转——那是 MuJoCo 编译产物
特有的坑，原始文件里的顶点本来就在自己的坐标系下。

单位处理：CoACD 内部无量纲，但我们汇报的精度是 mm，所以要知道输入网格的单位。
默认按"米"处理(机器人仿真资产常见)，可用 unit=mm/cm/m 显式指定，内部统一换算
到米，再乘 1000 报成 mm。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

UNIT_TO_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}


def load_mesh(path: str | Path, unit: str = "m") -> trimesh.Trimesh:
    """读任意网格文件，合并重复/极近顶点，换算到米。返回单一 Trimesh。

    有的格式(glb/obj 带多个 group)读进来是 Scene，dump 合并成一个 mesh。
    """
    path = Path(path)
    if unit not in UNIT_TO_M:
        raise ValueError(f"unit 只支持 {list(UNIT_TO_M)}，收到 {unit!r}")

    loaded = trimesh.load(str(path), force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        loaded = trimesh.util.concatenate(
            [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        )
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"{path} 读出来不是有面的三角网格")

    mesh = loaded
    before_v = len(mesh.vertices)
    mesh.merge_vertices()
    scale = UNIT_TO_M[unit]
    if scale != 1.0:
        mesh.vertices = mesh.vertices * scale
    print(
        f"加载 {path.name}: 顶点={len(mesh.vertices)}(合并掉 {before_v - len(mesh.vertices)} "
        f"个重复/极近顶点)  面={len(mesh.faces)}  单位={unit}  watertight={mesh.is_watertight}",
        flush=True,
    )
    return mesh


def clean_and_merge_solid(mesh: trimesh.Trimesh, junk_extent_mm: float = 1.0) -> trimesh.Trimesh:
    """把一个可能由多个连通分量组成的网格处理成单一真实体，供 CoACD 使用。

    (逻辑照搬自原 coacd_fit_check.clean_and_merge_solid，已在多个 LIBERO 资产上验证)

    - 好几个各自封闭、互相嵌入/贴合拼出来的实体(比如柱子插进底板)：网格里从没被
      布尔合并过，CoACD 面对这种"同一块空间被两个实体重复声明为内部"的无效拓扑
      搜索会显著变慢，先 manifold 布尔并集合成一个实体。
    - 近零体积的垃圾碎片(扫描/导出噪声，几个顶点的退化三角形)：跟主体既不重叠也
      不接触，直接按最长边阈值丢弃。

    只有一块干净分量的(多数物体)原样返回。
    """
    parts = mesh.split(only_watertight=False)
    if len(parts) == 1:
        return mesh

    junk_extent_m = junk_extent_mm / 1000
    kept = [p for p in parts if p.extents.max() >= junk_extent_m]
    dropped = len(parts) - len(kept)
    if dropped:
        print(f"    丢弃 {dropped} 个近零体积的垃圾碎片(最长边 < {junk_extent_mm}mm)", flush=True)
    if not kept:
        return mesh
    if len(kept) == 1:
        return kept[0]

    print(f"    布尔合并 {len(kept)} 个连通分量为一个实体...", flush=True)
    return trimesh.boolean.union(kept, engine="manifold")


def bbox_diag_mm(mesh: trimesh.Trimesh) -> float:
    """包围盒对角线长度(mm)——相对单位的归一化分母。"""
    return float(np.linalg.norm(mesh.extents) * 1000)
