# Research 文档索引

更新：2026-08-02 · Blender 插件 0.9.0

本目录只保留仍承担独立事实来源的文档。历史过程、已完成计划和重复说明由 Git 历史保存，
不在工作树维护副本。**作者怎么做 mod 看 [`../docs/wiki/Home.md`](../docs/wiki/Home.md)，
这里是它背后的技术记录。**

| 文档 | 权威范围 |
|---|---|
| [`current-status-and-roadmap.md`](current-status-and-roadmap.md) | 当前能力、边界和维护事项（**进度只有这一个出处**） |
| [`ab-route-notes.md`](ab-route-notes.md) | AB 路线：三段契约、运行时换网格机制、新增物理骨规范、无损边界 |
| [`universal-mod-automation-plan.md`](universal-mod-automation-plan.md) | 通用化的问题模型、架构、算法规格与诚实边界 |
| [`hair-pipeline.md`](hair-pipeline.md) | 发型/发饰：资产结构、制作流程、踩坑总表 + shader 逐通道逆向证据 |
| [`transparent-material-status.md`](transparent-material-status.md) | 原生 `m_bdyco` 镂空路线与透明边界 |
| [`step3-texture-input-guide.md`](step3-texture-input-guide.md) | Body / Hair / HairProp 贴图路径、通道和必填规则 |
| [`retired-routes.md`](retired-routes.md) | 已排除的三条路线（3DMigoto 逆蒙皮 / PC IL2CPP 注入 / 照搬 GIMI）及其原因 |

抓帧操作已并入 [`../3dmigoto_gkms/README.md`](../3dmigoto_gkms/README.md)（产品文档跟产品走）。

2026-08-02 的一轮合并：4 份退役路线文档 → `retired-routes.md`；3 份发型文档 →
`hair-pipeline.md`；`ab-route-handoff/docs/` 5 份 → `ab-route-notes.md`（数据侧脚本移入
`../tools/`）；删除 3 份纯本地过程史（工作区归并计划、P0 迁移快照、RC1 证据快照）。
