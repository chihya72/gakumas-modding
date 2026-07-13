# GakumasMI 当前状态与路线

更新：2026-07-13 · Blender 插件：**0.7.6**

本文只记录当前事实和未完成事项。逐版本变化见 [`../CHANGELOG.md`](../CHANGELOG.md)，
使用方法见 [`../gakumas_mi/README.md`](../gakumas_mi/README.md)。

## 当前交付能力

GakumasMI 已打通 Blender → 3DMigoto → 游戏的换模闭环：

- 身体与发型任意拓扑网格导入、转权、校验和导出；`m_bdyco` 是身体包可选段，`Geo_HairProp`
  是发型包内可选组件，启用时与 `Geo_Hair` 合并发布；
- 从抓帧与 AssetStudio Mesh JSON 一键生成配置档和逆蒙皮算子；
- GPU 每帧恢复骨骼矩阵并重蒙皮，动态 VB 实测 RMS 约 `1e-6`；
- `t0/t1/t4` 材质烘焙，body 原生 `m_bdyco` 镂空材质；
- hair 专用 t1/t4 与顶点 COLOR 语义，hairprop 按材质类型生成描边；
- 共享基础发型的运行时精确选择：完整发型包只在配套发饰绘制的那一帧替换发型，换成别的
  发饰/发型自动恢复原样（见下方核心结论）；
- manifest、封面、冲突目标与 Mod Manager 完整兼容。

默认示例只保留两档：

- `profiles/atbm-cstm-0140`：带原生 `bdyco` 的 body；
- `profiles/hmsz-hair-0023-hair`：hair。

## 已冻结的核心结论

- 游戏角色网格使用 CPU 蒙皮；静态结构来自 Mesh JSON，动画矩阵从实时 VB0 反解。
- 逆解与重蒙皮链已实机验证，不再探索进程注入、手/颈拆件等替代路线。
- 材质槽位由运行时地标自动判布局，不维护逐 PS hash 列表。
- body 的 `t1.A` 是 AO/间接光；hair 的 `t1.A` 必须为 0，二者不可混用。
- `m_bdyco` 是 cutout/alpha-test，不是连续半透明；薄纱和玻璃不在正式支持范围。
- hair 与 hairprop 是同一发型道具的两个独立 drawcall，由同一发型 profile 和 UI 流程管理。
- 多套发型常共用同一 `Geo_Hair` IB，故完整发型包用配套发饰的 `IB hash + firstIndex` 作为
  帧内 latch（`$..._hairprop_match`），发型只在该发饰绘制时替换。游戏所用 3DMigoto 分支的
  **TextureOverride 不支持 `allow_duplicate_hash`**（仅 ShaderOverride 支持），故合并单包时把
  latch 置位注入发饰自身的同 hash override（不另开会互相覆盖的 selector），每帧末由 `[Present]`
  清零——**不能在 body landmark 处清零**，它夹在发饰与发型 draw 之间会让主 pass 漏替换。
  已知边界：某场景若不渲染该发饰（部分剧情/降级 pass），发型在该场景不替换（gate 设计使然）；
  两发型若基础发型与发饰运行时特征均相同则无法区分。

数学验证见 [`inverse-skin-matrix-recovery.md`](inverse-skin-matrix-recovery.md)，材质边界见
[`transparent-material-status.md`](transparent-material-status.md)，发型语义见
[`hair-replacement.md`](hair-replacement.md)。

## 完成度评估（0.7.6，对照 TheHerta4）

参照目标是 [TheHerta4](https://github.com/StarBobis/TheHerta4)（GIMI/WWMI 家族的 SSMT4
Blender 插件，v4.1.37 · 2026-07，10+ 游戏）提供的作者体验。注意两者前提不同：它支持的游戏
是 GPU 蒙皮（权重可从 VB 直接抓），学马是 CPU 蒙皮——GakumasMI 的逆蒙皮链、自动传权、
运行时布局探测都是参照目标**没有**的能力；反之它有我们**暂不开展**的 ShapeKey 与蓝图树批量导出。

| 模块 | 完成度 | 相对 0.7.2 评估的变化 |
|---|---:|---|
| GPU 核心（逆解矩阵 + 重蒙皮 + 注入） | ~95% | 冻结无变化。RMS ≈ 1e-6，参照目标无对应能力（其游戏不需要）。 |
| 配置档生成（一键：注入 + 结构 + 逆算子） | ~90% | 新增 hair+hairprop 双组件一键提取；共享基础发型多候选按同帧发饰顶点数消歧。 |
| 蒙皮转权（作者模型 → 配置档骨架） | ~85% | 无变化。参照目标无自动传权（数字顶点组 + 手工笔刷），此项仍领先。 |
| 贴图 / 材质 | ~88% | hair 专属 t1/t4 与 COLOR 语义 0.7.4 转正；hairprop 按材质类型生成描边。参照目标用逐游戏静态槽位映射，我们是运行时地标探测。 |
| 透明材质（cutout 边界内） | ~85% | 无变化；真半透明仍在边界外。 |
| 健壮性 / 回归测试 | ~80% | 合约测试 6 → 12（新增发型选择器注入、hair/hairprop 合并、布局探测回归）；发布流水线校验 tag/版本一致。 |
| 产品化（完整发型包 / Mod Manager / 发布） | ~85% | **交付边界从"单 body 换装"扩至 body + 完整发型包**：hair+hairprop 合并单包、运行时精确选择（0.7.6 实机验证）、管理器显示组件组合、tag 触发自动发布。 |

**相对参照目标的差距**（均在「暂不开展」清单内，有可复现需求再评估）：
ShapeKey/表情、蓝图树批量出 mod、多游戏架构。脸部等其余组件同前暂缓。

## 当前维护项

| 优先级 | 事项 | 完成条件 |
|---|---|---|
| P0 | 回归与发布维护 | 现有 smoke、契约测试和打包流程持续通过 |
| P1 | 材质实机校准 | 遇到新组件语义时补最小预设与回归用例 |
| P2 | 作者体验 | 仅处理会阻断主流程的 UI、报错和兼容问题 |

## 暂不开展

- 连续半透明、Shape Key/表情、脸部替换、LOD/多 drawcall 自动编排；
- 自建 shader/state 透明路线；
- 为单个样本增加通用抽象或长期维护的 PS 枚举。

这些需求只有在出现可复现样本和明确用户需求时再恢复。
