"""量化碰撞凸包跟视觉网格的真实贴合精度。

核心是双向误差(缺一个方向都会漏一类问题)：
  1. 缝隙(gap)：视觉网格表面 -> 最近碰撞体表面，查"碰撞体有没有盖到"。
  2. 鼓出(bulge)：碰撞凸包表面 -> 视觉网格的带符号距离，查"碰撞体有没有跑到
     视觉网格外面"。只测方向1的话鼓出来的凸包测不出来——视觉网格表面本来就离
     那坨鼓出去的碰撞体很近，方向1误差看起来反而很小。

精度阈值就一个数：Hausdorff 距离 = max(缝隙方向最大值, 鼓出方向最大值)，即两个
形状"最坏情况下差多远"。5/95 分位是辅助细节，判断最坏偏差是个例还是普遍现象。

(逻辑照搬自原 coacd_threshold_sweep_batch.fit_error_with_bounds，已验证)
"""
from __future__ import annotations

import numpy as np
import trimesh

CollisionPart = tuple  # (vertices ndarray, faces ndarray)，即 coacd.run_coacd 的返回元素


def fit_error_mm(collision_parts, visual_mesh: trimesh.Trimesh, n_samples: int = 20000) -> dict:
    """返回缝隙/鼓出的 max/mean/p5/p95(mm)、片数、Hausdorff(mm)。"""
    hulls = [
        trimesh.Trimesh(vertices=v, faces=f, process=True).convex_hull
        for v, f in collision_parts
    ]

    # 方向 1：缝隙——所有凸包拼成一个 mesh 只建一次空间索引、只查一次(避免按片
    # 循环把查询次数放大到 O(片数))。trimesh 的空间索引自己会处理"点离拼接体
    # 哪部分最近"。
    combined = trimesh.util.concatenate(hulls)
    sample_pts, _ = trimesh.sample.sample_surface(visual_mesh, n_samples)
    combined_pq = trimesh.proximity.ProximityQuery(combined)
    gap_dist = np.abs(combined_pq.signed_distance(sample_pts))

    # 方向 2：鼓出——每片凸包表面采样点相对视觉网格的带符号距离，正值=跑到外面。
    # 总采样预算固定，片数越多单片分到越少，避免片数线性拖慢。
    per_part_samples = max(20, min(500, 50000 // max(len(hulls), 1)))
    visual_pq = trimesh.proximity.ProximityQuery(visual_mesh)
    bulge_per_part = []
    for hull in hulls:
        hull_pts, _ = trimesh.sample.sample_surface(hull, per_part_samples)
        signed = visual_pq.signed_distance(hull_pts)  # 视觉网格内部为正(trimesh 约定)
        bulge_per_part.append(float((-signed).max()))
    bulge_arr = np.array(bulge_per_part)

    gap_max_mm = float(gap_dist.max() * 1000)
    bulge_max_mm = float(bulge_arr.max() * 1000)

    return {
        "n_parts": len(collision_parts),
        "gap_max_mm": gap_max_mm,
        "gap_mean_mm": float(gap_dist.mean() * 1000),
        "gap_p5_mm": float(np.percentile(gap_dist, 5) * 1000),
        "gap_p95_mm": float(np.percentile(gap_dist, 95) * 1000),
        "bulge_max_mm": bulge_max_mm,
        "bulge_mean_mm": float(bulge_arr.mean() * 1000),
        "bulge_p5_mm": float(np.percentile(bulge_arr, 5) * 1000),
        "bulge_p95_mm": float(np.percentile(bulge_arr, 95) * 1000),
        "bulge_worst_part": int(bulge_arr.argmax()),
        "bulge_per_part_mm": [float(b) for b in bulge_arr],
        "hausdorff_mm": max(gap_max_mm, bulge_max_mm),
    }
