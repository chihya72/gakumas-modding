# Research 文档索引

更新：2026-06-30 · 插件 0.6.0

本目录保留 GakumasMI 从抓帧、逆解蒙皮到透明材质的研究记录。日常以下表「当前有效」
文档为准；已排除路线与逐步实验过程已归档到 [`archive/`](archive/)（保留作避坑证据，不代表
当前实现）。

## 当前有效

| 文档 | 用途 |
|---|---|
| [`current-status-and-roadmap.md`](current-status-and-roadmap.md) | **当前状态、完成度与后续计划的权威来源。** |
| [`transparent-material-status.md`](transparent-material-status.md) | 透明材质当前策略：只保留原生 `m_bdyco` 第二材质段路线，旧自建透明路线仅归档。 |
| [`inverse-skin-matrix-recovery.md`](inverse-skin-matrix-recovery.md) | 逆解每帧骨骼矩阵与任意拓扑导出的数学依据与游戏内验证。 |
| [`pc-il2cpp-gmim-runtime-replacement.md`](pc-il2cpp-gmim-runtime-replacement.md) | PC IL2CPP `.gmim` 运行时换网格研究：真实 Mesh 替换、原生 `m_bdyco` 验证、与 3DMigoto 正式路线对比。 |
| [`theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md`](theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md) | TheHerta4/SSMT4、学马 3DMigoto、学马 IL2CPP 三条路线的层级、能力边界与战略结论。 |
| [`color-scan-20260627-091033.md`](color-scan-20260627-091033.md) | 顶点 COLOR / vb1 扫描：COLOR 是区域/拓扑数据，附描边宽度安全族。 |
| [`blender-plugin-ui-reference.md`](blender-plugin-ui-reference.md) | GIMI/WWMI/EFMI 的 UI / 作者流程参考。 |
| [`baseline/`](baseline/) · [`hunting/`](hunting/) | 基准场景与 Hunting 环境记录。 |

## 已归档（`archive/`，保留证据）

| 文档 | 为何归档 |
|---|---|
| `archive/transparent-pass-status-and-planB-20260628.md` | 透明材质逐步踩坑全程；结论已并入 `transparent-material-status.md`。 |
| `archive/alpha-transparency-frameanalysis-20260628.md` | 透明抓帧原始证据；要点已并入 `transparent-material-status.md`。 |
| `archive/runtime-skinning-bridge.md` | 早期进程内 Runtime 路线边界记录；当前新的 IL2CPP 实验见有效文档中的 `.gmim` 研究。 |
| `archive/reference-framework-comparison.md` | 矩阵恢复成功前的同类工具调查，非当前实现说明。 |
| `archive/ttmr-cstm-0119-body-plan.md` | 早期 TTMR→HSKI 重定向/表面映射路线，已被「Blender 内蒙皮到目标骨架」取代。 |
