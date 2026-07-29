"""coacd_autofit —— 把"给视觉网格自动制表 + 按精度要求生成碰撞模型"这两件事
打包成一个可复用工具。

两个阶段：
  1. 制表(table)：对任意视觉网格扫一遍 CoACD threshold，量化每档的
     真实贴合精度(Hausdorff, mm) 和 凸包片数，产出表格(md/csv/json)+图。
  2. 生成(generate)：给定精度要求(真实 mm / 最多片数 / 原始 threshold 三选一)，
     从表里反查最省片数的 threshold，跑出碰撞片并导出 obj + MJCF 片段。
"""

__version__ = "0.1.0"
