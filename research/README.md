# Research 文档索引

更新：2026-08-02 · Blender 插件 0.9.0

本目录只保留仍承担独立事实来源的文档。历史过程、已完成计划和重复说明由 Git 历史保存，
不在工作树维护副本。

| 文档 | 权威范围 |
|---|---|
| [`current-status-and-roadmap.md`](current-status-and-roadmap.md) | 当前能力、边界和维护事项 |
| [`inverse-skin-matrix-recovery.md`](inverse-skin-matrix-recovery.md) | 逆解矩阵的数学依据与实机误差 |
| [`transparent-material-status.md`](transparent-material-status.md) | 原生 `m_bdyco` 镂空路线与透明边界 |
| [`hair-replacement.md`](hair-replacement.md) | hair/hairprop 资产结构、材质和顶点色语义 |
| [`hair-shader-analysis.md`](hair-shader-analysis.md) | hair/hairprop 各 pass、t0–t7、COLOR nibble 与描边的逆向证据 |
| [`step3-hair-texture-improvement.md`](step3-hair-texture-improvement.md) | Blender 步骤③的 hair t0.A、HHL 与 HairProp 贴图改进方案 |
| [`step3-texture-input-guide.md`](step3-texture-input-guide.md) | 步骤③ Body / Hair / HairProp 需要准备的图像路径、通道和必填规则 |
| [`hunting/README.md`](hunting/README.md) | 3DMigoto Hunting / Frame Analysis 操作 |
| [`3dmigoto-vs-ab-route.md`](3dmigoto-vs-ab-route.md) | 两条路线的拦截点对比与取舍依据 |
| [`pc-il2cpp-gmim-runtime-replacement.md`](pc-il2cpp-gmim-runtime-replacement.md) | 已放弃的 PC IL2CPP 注入路线：Unity 层换 Mesh 的实测结论与透明避坑记录 |
| [`universal-mod-automation-plan.md`](universal-mod-automation-plan.md) | 任意外部模型 → AB mod 的自动化边界与逐项验证等级 |
| [`workspace-consolidation-plan.md`](workspace-consolidation-plan.md) | IP、SCSP、DLL 与 Blender 工作区的归并、清理和验收流程 |
| [`migration-p0-snapshot.md`](migration-p0-snapshot.md) | 工作区归并前的 P0 备份快照与校验记录 |
| [`rc1-evidence-20260727.md`](rc1-evidence-20260727.md) | RC1 验收的一次性证据快照（哈希与命令记录） |

产品安装与操作说明分别位于 [`gakumas_mi/`](../gakumas_mi/README.md)、
[`3dmigoto-gkms/`](../3dmigoto-gkms/README.md) 和 [`mod-manager/`](../mod-manager/README.md)。
