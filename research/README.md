# Research 文档索引

状态：GakumasMI 1.3.0。

这个目录只保留现行开发仍会读取的技术文档和可复现实证。完成后的
计划、会话日志与重复说明，在结论并入权威文档后删除；历史由 Git 和
[`lessons-learned.md`](lessons-learned.md) 保存。作者制作 mod 请看
[`../docs/wiki/Home.md`](../docs/wiki/Home.md)，不要从研究记录反推操作流程。

## 当前 AB 发布路线

| 文档 | 权威范围 | 类型 |
|---|---|---|
| [`ab-target-rig-architecture.md`](ab-target-rig-architecture.md) | 现行架构、制作/运行流程、导出闸门与明确非目标 | 必须保留的活文档 |
| [`ab-target-rig-contract.md`](ab-target-rig-contract.md) | 骨架、五档映射、sidecar、阈值与导出硬约束 | 必须保留的契约 |
| [`ab-consolidated-facts-and-evidence-2026-08-16.md`](ab-consolidated-facts-and-evidence-2026-08-16.md) | 原版事实、量测数据、证伪结论与量法 | 必须保留的历史证据 |
| [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md) | 离线无法替代的实机验收判据 | 开发/发布验证必用 |
| [`ab-route-notes.md`](ab-route-notes.md) | AB 加载、换网格、新增物理骨、无损和材质边界 | 维护实现时使用 |
| [`hair-pipeline.md`](hair-pipeline.md) | 发型/发饰资产结构、制作流程与 shader 通道证据 | 发型开发必用 |
| [`lessons-learned.md`](lessons-learned.md) | 已排除路线、失败做法、历史文档取回入口 | 必须保留的防复发记录 |

分工原则：流程与产品边界以架构文档为准；格式与导出约束以契约为准；事实和数字以合并事实文档
为准；产品面向用户的状态以根 [`README.md`](../README.md) 为准。不要在多份文档复制进度表。

## 已归档内容

| 内容 | 取回位置 |
|---|---|
| 2026-08-20 合并前的 AB 文档、旧数据目录 | Git 标签 `archive/research-2026-08-20`；逐份结论见 [`lessons-learned.md`](lessons-learned.md) §7 |
| 半透明材质研究 | 分支 `research/transparent-material` |
| 已证伪的 Unity Humanoid / whole-object SDK 路线 | 有效量测和方法已并入合并事实文档 §2、§3、§8，否决结论与 Git 取回方式见 [`lessons-learned.md`](lessons-learned.md) §1、§7 |
| 3DMigoto 逆蒙皮、PC IL2CPP、照搬 GIMI 等退役路线 | [`lessons-learned.md`](lessons-learned.md) |

抓帧操作属于产品文档，见 [`../3dmigoto_gkms/README.md`](../3dmigoto_gkms/README.md)。
