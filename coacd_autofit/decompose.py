"""CoACD 分解的薄封装，让制表和生成两个阶段共用同一套"最优情况"默认参数。

"最优情况"(原始需求里的说法)指的是：给足 MCTS 搜索预算，让 CoACD 在相同
threshold 下尽量用更少的片数达到同等精度——所以 mcts_nodes / mcts_iterations
默认给到 1000/1000(实测对普通桌面物体安全)。threshold 是唯一主旋钮。
"""
from __future__ import annotations

import time

import coacd
import trimesh

# 制表全物体报告里验证过的"最优情况"默认档
DEFAULT_MCTS_NODES = 1000
DEFAULT_MCTS_ITERATIONS = 1000


def run(
    mesh: trimesh.Trimesh,
    threshold: float,
    mcts_nodes: int = DEFAULT_MCTS_NODES,
    mcts_iterations: int = DEFAULT_MCTS_ITERATIONS,
    pca: bool = True,
    quiet: bool = True,
):
    """跑一次 CoACD，返回 (parts, 耗时秒)。parts 是 [(verts, faces), ...]。"""
    if quiet:
        coacd.set_log_level("error")
    cm = coacd.Mesh(mesh.vertices, mesh.faces)
    t0 = time.time()
    parts = coacd.run_coacd(
        cm,
        threshold=threshold,
        mcts_nodes=mcts_nodes,
        mcts_iterations=mcts_iterations,
        pca=pca,
    )
    return parts, time.time() - t0
