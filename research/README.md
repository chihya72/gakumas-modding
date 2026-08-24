# Research 文档索引

更新：2026-08-20 · Blender 插件 1.2.0（未发布）

**这个目录只放现在正在用的文档。** 过时的、被推翻的一律删掉，结论和取回方式在
[`lessons-learned.md`](lessons-learned.md) §7（2026-08-20 按这条规矩清了一轮）。

**AB 路线只看两份文档。** 其余是专题记录；与这两份冲突时，以这两份为准。
**作者怎么做 mod 看 [`../docs/wiki/Home.md`](../docs/wiki/Home.md)**，这里是它背后的技术记录。

## AB 路线的两份主文档

| 文档 | 管什么 |
|---|---|
| [`ab-target-rig-route-2026-08-17.md`](ab-target-rig-route-2026-08-17.md) | **做什么、按什么顺序做**：target-rig 架构、P0–P8、**闸门的唯一权威清单**（批次 3 的表，含实现位置）、物理硬规矩、落实顺序、批次 7 实机叉点 |
| [`ab-consolidated-facts-and-evidence-2026-08-16.md`](ab-consolidated-facts-and-evidence-2026-08-16.md) | **已知什么、量到多少、哪些结论已作废、怎么量才不出错**：原版骨架/组件事实、动画与蒙皮机制、Claymore 全套实测、已证伪清单、六个量测坑、工具现状、Unity SDK 可搬清单、作者真实成本、不变量 |

两份冲突时：路线与顺序以第一份为准，事实与数字以第二份为准。

路线文档的两份附件（同一批，跟着它读）：

| 文档 | 管什么 |
|---|---|
| [`ab-target-rig-contract.md`](ab-target-rig-contract.md) | **导出器/闸门/sidecar 的硬约束**：骨架契约、五档状态、尺子与阈值、缺骨怎么补。闸门清单只留指针，不存第二份 |
| [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md) | **离线做不了的那几件事，进游戏一次看什么**：判据全写成"跑哪个命令 / 看哪个数字" |

> 两副骨架桥 / whole-object 那条路的对照组记录（`ab-source-proxy-summary-...-2026-08-16.md`）
> 已于 2026-08-20 删除 —— 它量到的事实全部进了事实文档，作废的路线结论进了
> [`lessons-learned.md`](lessons-learned.md) §7。**代码没删**，双骨架 bridge 仍是特殊兼容模式。

## 专题记录（仍然有效）

| 文档 | 权威范围 |
|---|---|
| [`ab-route-notes.md`](ab-route-notes.md) | AB 路线：三段契约、运行时换网格机制、新增物理骨规范、无损边界、原生 `m_bdyco` 透明边界 |
| [`hair-pipeline.md`](hair-pipeline.md) | 发型/发饰：资产结构、制作流程、踩坑总表 + shader 逐通道逆向证据 |
| [`lessons-learned.md`](lessons-learned.md) | **反面教训汇总**：已排除的路线、作废的做法、被推翻的结论 |
| [`unity-humanoid-avatar-sdk/`](unity-humanoid-avatar-sdk/) | **Unity 实验台**：`HANDOFF.md`、`docs/corrective-helper-rig.md`、`docs/rest-pose-dead-end.md` 是大量原版数字的原始出处，必须跟代码放在一起，**不归档** |

## 不在这个目录里的东西

| 内容 | 在哪 |
|---|---|
| 半透明材质研究（938 行，路线暂停） | **分支 `research/transparent-material`**。主分支不留：路线停着，留在这里只会被当成现役 |
| 9 份被合并版取代的 AB 研究文档 + 3 份过时文档 | git 历史，标签 `archive/research-2026-08-20`。逐份结论与取回命令见 [`lessons-learned.md`](lessons-learned.md) §7；每份里还值得查的原始数据列在事实文档 §10 |
| 已放弃路线的旧记录（3DMigoto 逆蒙皮、PC IL2CPP、照搬 GIMI） | [`lessons-learned.md`](lessons-learned.md) §1 —— 只留结论，不留过程 |

---

2026-08-20 的清理：删 3 份过时主文档 + `archive-2026-08-16/`（9 份）+ 两个过期数据目录，
半透明研究移到自己的分支。结论表见 `lessons-learned.md` §7。

2026-08-16 的合并：9 份 AB 研究文档 → `ab-consolidated-facts-and-evidence-2026-08-16.md`。

2026-08-02 的一轮合并：4 份退役路线文档 → `retired-routes.md`（2026-08-03 再并入
`lessons-learned.md` 并删除）；3 份发型文档 → `hair-pipeline.md`；`ab-route-handoff/docs/`
5 份 → `ab-route-notes.md`（数据侧脚本移入 `../tools/`）；删除 3 份纯本地过程史。

抓帧操作已并入 [`../3dmigoto_gkms/README.md`](../3dmigoto_gkms/README.md)（产品文档跟产品走）。
