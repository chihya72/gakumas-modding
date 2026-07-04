# Research 文档索引

更新：2026-07-04 · 插件 0.7.2

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

> Mod 包管理器的规划与 GUI 开发文档随产品代码放在
> [`../mod-manager/docs/`](../mod-manager/docs/)（`plan.md`、`gui-development-flow.md`）。

## 已归档（`archive/`，保留证据）

| 文档 | 为何归档 |
|---|---|
| `archive/roadmap-early-draft.md` | 早期产品愿景/分阶段草案；状态以 `current-status-and-roadmap.md` 为准，定位/边界已并入根 README。 |
| `archive/session-20260704-gmi-global-layout-and-mirror.md` | 运行时全局布局探测的会话复盘；结论已进 0.7.2 与 CHANGELOG。 |
| `archive/session-20260701-dress2609-t1-material-summary.md` | dress2609 t1 材质会话记录；要点已并入材质结论。 |
| `archive/dress2219-foreign-rip-and-smart-transfer.md` | dress2219 外部 rip 与智能转权会话记录。 |
| `archive/selfbuilt-cutout-and-blend-removed-20260630.md` | 自建镂空/半透明路线移除记录；透明只保留原生 `m_bdyco`。 |
| `archive/transparent-pass-status-and-planB-20260628.md` | 透明材质逐步踩坑全程；结论已并入 `transparent-material-status.md`。 |
| `archive/alpha-transparency-frameanalysis-20260628.md` | 透明抓帧原始证据；要点已并入 `transparent-material-status.md`。 |
| `archive/runtime-skinning-bridge.md` | 已放弃的进程内 Runtime 路线边界记录（代码已删）。 |
| `archive/reference-framework-comparison.md` | 矩阵恢复成功前的同类工具调查，非当前实现说明。 |
| `archive/ttmr-cstm-0119-body-plan.md` | 早期 TTMR→HSKI 重定向/表面映射路线，已被「Blender 内蒙皮到目标骨架」取代。 |
