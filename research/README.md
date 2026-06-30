# Research 文档索引

更新：2026-06-28 · 插件 0.6.0

本目录保留 GakumasMI 从抓帧、逆解蒙皮到透明材质的研究记录。日常以下表「当前有效」
文档为准；已排除路线与逐步实验过程已归档到 [`archive/`](archive/)（保留作避坑证据，不代表
当前实现）。

## 当前有效

| 文档 | 用途 |
|---|---|
| [`current-status-and-roadmap.md`](current-status-and-roadmap.md) | **当前状态、完成度与后续计划的权威来源。** |
| [`transparent-material-status.md`](transparent-material-status.md) | 透明材质当前策略、架构结论与抓帧证据（整合自归档的两份过程记录）。 |
| [`inverse-skin-matrix-recovery.md`](inverse-skin-matrix-recovery.md) | 逆解每帧骨骼矩阵与任意拓扑导出的数学依据与游戏内验证。 |
| [`pc-il2cpp-gmim-runtime-replacement.md`](pc-il2cpp-gmim-runtime-replacement.md) | PC IL2CPP `.gmim` 运行时换网格研究：骨名权重重映射、`ttmr-cstm-0003` AssetStudio 解包、材质属性结论。 |
| [`color-scan-20260627-091033.md`](color-scan-20260627-091033.md) | 顶点 COLOR / vb1 扫描：COLOR 是区域/拓扑数据，附描边宽度安全族。 |
| [`blender-plugin-ui-reference.md`](blender-plugin-ui-reference.md) | GIMI/WWMI/EFMI 的 UI / 作者流程参考。 |
| [`baseline/`](baseline/) · [`hunting/`](hunting/) | 基准场景与 Hunting 环境记录。 |

## 已归档（`archive/`，保留证据）

| 文档 | 为何归档 |
|---|---|
| `archive/transparent-pass-status-and-planB-20260628.md` | 透明材质逐步踩坑全程；结论已并入 `transparent-material-status.md`。 |
| `archive/alpha-transparency-frameanalysis-20260628.md` | 透明抓帧原始证据；要点已并入 `transparent-material-status.md`。 |
| `archive/runtime-skinning-bridge.md` | 已放弃的进程内 Runtime 路线边界记录（代码已删）。 |
| `archive/reference-framework-comparison.md` | 矩阵恢复成功前的同类工具调查，非当前实现说明。 |
| `archive/ttmr-cstm-0119-body-plan.md` | 早期 TTMR→HSKI 重定向/表面映射路线，已被「Blender 内蒙皮到目标骨架」取代。 |
