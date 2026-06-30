# dress_2219 异游戏 rip 鉴定 + 智能转权方案

更新：2026-06-29 · 触发：探索「能否把自有 mod 模型权重带进 Gakumas」

## 0. 一句话结论

`dress_2219_full` 是**从别的游戏抓的模型**，骨架/bindpose/权重对 Gakumas **完全不可用**；
直接带它的权重 = 路线图记录的「全屏爆炸」。**只有服装几何可用**，权重必须从 Gakumas
body 重新生成。抓帧目标已识别为 **`ttmr-cstm-0136`**（月村手毬）。

## 1. 异游戏 rip 的硬证据（dress_2219 vs Gakumas ttmr 目标骨架）

| 证据 | dress_2219 | Gakumas | 判定 |
|---|---|---|---|
| 骨名覆盖 | 仅 50/72 在 Gakumas 骨架中存在 | — | 22 根对不上 |
| 缺失骨命名 | `OPAI_L0/R0`、`*_rot`(LeftArm1_rot…)、`LeftRing/Clavicle/Toe` | **无 OPAI、无 _rot** | 异 rig 命名体系 |
| Hips bindpose row0 | `[~0, 1, ~0, -0.905]` | `[1, 0, 0, 0]` | 完全不同 rest pose |
| 核心骨 bindpose 差 | median 1.36，最大 2.0，**最好的也差 1.0** | — | 没有一根兼容 |
| 几何 | 双 body 网格(BodySkin 6278 + bodyskin 3591)、T-pose、脚在原点(Y:0.02→1.34) | A-pose、髋在原点(Y:-0.95→0.45) | 不同坐标约定 |

复现：`_intermediate.pkl` 解出 BodySkin 的 `bone_list`(72)/`bindpose`(72,4,4)，对 Gakumas
`Geo_Body.skeleton.json` 的 `name→weightedIndex` 与 `Geo_Body.json` 的 `m_BindPose` 逐骨比对。

→ 这与历史失败路线一致（路线图 §4「保留 TTMR 与 HSKI 同名骨权重 → 全屏爆炸」「外部
权重属外部 bind rig」）。**结论：异游戏 rip 不能带权重进游戏。**

## 2. 抓帧目标识别

三个 `FrameAnalysis-2026-06-29-06xxxx` 的 body draw：VS `436f9c16af3b54cf` / PS
`a04da6e49886b206`，VB0 stride 40。最大 body draw = **19678 顶点 / 77643 索引(IB e5995e2b)**，
按索引数+顶点数精确匹配库里 **`mdl_chr_ttmr-cstm-0136_body`**（同计数还有 0137，成对）。

## 3. 正确管线（异 rip 服装 → Gakumas）

1. **只保留服装几何**：dress(15681)、coat_BS_b(8357)、mizugi_option(833)、
   wingopacity(2319)/_BS_b(73)、neckless(224)、acce(18)、InBack(414)。丢弃 BodySkin/bodyskin
   及其权重，body 用游戏自身的。
2. **贴合到 ttmr body**：把服装几何对齐到 `ttmr-cstm-0136` 的 rest body（形状+姿态+尺度+
   原点都不同，需作者在 Blender 拟合——异 rip 的主要人工成本）。
3. **从 ttmr body 几何转权**：用 §4 的智能转权（法线闸门 + inpaint）从 Geo_Body 的
   rest body + `m_Skin` 传权重到服装。
4. **inverse-skin 导出**：经现有管线，按 ttmr profile 注入（需先从抓帧抽 ttmr profile，
   现有 profile 只有 hski-cstm-0000）。

## 4. 智能转权方案（已落地为代码 + 测试）

新增 `gakumas_mi/weight_transfer.py`（纯 numpy，无 bpy/scipy，Blender 与 CI 都能跑），
替代朴素 `POLYINTERP_NEAREST` 的两个硬伤（跨薄缝串权重、前后面污染）：

- **法线一致里取最近**（不是「先取最近再判法线」）：在 `dot(法线) >= 阈值` 的 source 里
  找最近的，距离 <= `max_distance` 才算置信，直接抄权重。
- **Laplacian inpaint**（零依赖 Jacobi 迭代）：未置信顶点以置信顶点为 Dirichlet 边界，
  沿网格边反复取邻居均值，收敛到调和解——权重**沿表面流动、不跨缝**。
- top-4 截断 + 归一；孤立顶点兜底最近 source。

回归测试 `tests/weight_transfer_smart.py`：合成「薄缝跨面 + 远点空洞」。证明朴素最近把
属于 A 面的目标错抄成法线相反的 B 面骨（>90%），而智能转权靠闸门改写回 A(>95%)，并把
远离所有 source 的塔尖顶点 inpaint 出正确骨、无零权重。

### 待办（本次未做）
- 把 `smart_weight_transfer` 接进 `GMI_OT_transfer_profile_weights`（Blender 端从 bpy 网格
  抽 pos/normal/faces/源权重 → 调核心 → 写回顶点组），替换/可选 DATA_TRANSFER。
- 抽取 `ttmr-cstm-0136` profile；服装贴合后跑通整条导出并实机验证形变。
