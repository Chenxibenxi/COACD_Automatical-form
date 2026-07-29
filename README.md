# coacd-autofit

给一个**视觉网格**，自动搞清楚"CoACD 简化参数 ↔ 碰撞体片数 ↔ 真实贴合精度"三者
的关系，再按你的精度要求生成对应的碰撞模型。

两个阶段：

1. **制表 (`table`)** —— 对视觉网格扫一遍 CoACD `threshold`，每一档都独立量化：
   - 生成了多少片凸包 (hull 数)；
   - 碰撞体跟视觉网格的**真实** Hausdorff 贴合误差 (mm)，不是 CoACD 自己报的
     那个内部相对 `threshold`；
   - 相对单位 (Hausdorff / 包围盒对角线)、gap/bulge 的 5~95 分位。

   产出 `<name>.json`(机读) + `<name>.md`(表) + `<name>.csv` + 一张扫描曲线图。

2. **生成 (`generate`)** —— 给一个精度要求，自动反查最优 `threshold` 并导出碰撞
   模型（每片一个 `.obj` + 可直接粘进 MJCF 的 `<asset>`/`<geom>` 片段），生成完
   再实测一遍实际达到的 Hausdorff 回报给你。

> 精度阈值只有一个数：**Hausdorff 距离 = max(缝隙最大值, 鼓出最大值)**，即碰撞体
> 和视觉网格"最坏情况下差多远"。缝隙 = 碰撞体没盖到的地方；鼓出 = 碰撞体跑到视觉
> 网格外面的地方。只测单方向会漏掉鼓出，所以两个方向都算。

## 安装

```bash
pip install -e .
# 或者： pip install -r requirements.txt
```

依赖 `coacd`、`trimesh`、`numpy`、`matplotlib`；清理"多个实体拼在一起"的网格时
用到 `trimesh.boolean.union(engine="manifold")`，需要额外装 `manifold3d`。

## 用法

### 制表

```bash
coacd-autofit table bowl.obj --out-dir ./out
# 网格单位不是米时显式指定（内部统一换算到米再报 mm）
coacd-autofit table bowl.stl --unit mm
# 自定义扫描档位
coacd-autofit table bowl.obj --thresholds 0.01,0.03,0.05,0.1
```

- 支持 `.obj/.stl/.ply/.glb/.off` 等 trimesh 能读的格式。
- 每算完一档立刻落盘，中途中断/崩溃不丢已算的档，重跑接着算。
- `--no-merge-solid` 跳过多连通分量的清理/布尔合并（默认开，能显著加速那种
  "柱子插进底板"式的拼接网格）。

### 只重新画图

```bash
coacd-autofit plot ./out/bowl.json
```

### 生成碰撞模型

三种精度要求择一（`--target-mm` / `--max-parts` / `--threshold`）：

```bash
# 要求真实贴合误差 <= 4mm，自动挑满足要求里片数最少的那档
coacd-autofit generate bowl.obj --out-dir ./out --target-mm 4

# 碰撞体最多 20 片，自动挑不超预算里精度最好的那档
coacd-autofit generate bowl.obj --out-dir ./out --max-parts 20

# 直接指定 CoACD threshold，跳过反查
coacd-autofit generate bowl.obj --out-dir ./out --threshold 0.05
```

- `--target-mm` / `--max-parts` 需要该网格的制表结果；`--out-dir` 下没有
  `<name>.json` 时会**自动先扫一遍**（用 `--thresholds` 控制档位），再反查。
- 产出：`<name>_collision/part_*.obj`（每片凸包一个）+ `<name>_collision.xml`
  （MJCF 片段，把里面的 `<mesh>` 放进 `<asset>`、`<geom>` 放进你的 `<body>`）。
- 生成后会实测实际 Hausdorff 并打印，跟制表预估对得上。

## 表格字段

| 列 | 含义 |
|---|---|
| 输入threshold | 喂给 CoACD 的凹度容差（内部相对单位，不是物理距离） |
| 片数(凸包数) | 分解出的凸包数量，直接决定物理仿真开销 |
| 相对单位 | Hausdorff / 包围盒对角线，跨物体可比 |
| Hausdorff(mm) | 真实最坏贴合误差 |
| gap p5~p95 | 缝隙方向的分位区间 |
| bulge p5~p95 | 鼓出方向的分位区间 |
| 生成耗时(s) | 该档 CoACD 分解耗时 |

## 结构

```
coacd_autofit/
  meshio.py     通用网格加载 + 多连通分量清理/合并
  fit.py        双向 Hausdorff 贴合误差
  decompose.py  CoACD 分解薄封装(共用"最优情况"默认参数)
  sweep.py      制表主逻辑
  plot.py       扫描曲线图
  generate.py   按精度要求反查 threshold + 导出碰撞模型
  cli.py        命令行入口
```
