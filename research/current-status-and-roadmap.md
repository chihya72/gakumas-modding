# GakumasMI 当前状态与路线

更新：2026-07-27 · Blender 插件：**0.9.0**（分支 `research/ab-route-swing-physics`）

本文只记录当前事实和未完成事项。逐版本变化见 [`../CHANGELOG.md`](../CHANGELOG.md)，
使用方法见 [`../gakumas_mi/README.md`](../gakumas_mi/README.md)。

## 当前交付能力

> **本分支只做 AB bundle（原生蒙皮）路线。** 3DMigoto 逆蒙皮的传权与导出已于 2026-07-27
> 整体移除（不是加开关隐藏）：两条路线并存会让 AB 作者顺着 UI 编号点进传权、用猜的权重盖掉
> 手刷的权重。3DMigoto 保留的唯一角色是**抓帧工具**——做配置档必须用它抓帧。
> 下面带 ~~删除线~~ 的是移除前的能力，留作历史。
>
> ⚠ **2026-07-27 这批改动大部分只过了离线测试，没进游戏。** 实机验证过的只有骨名映射修复
> （`.L/.R` 折叠 / D 骨 / `手捩→ForeArm`）和 t1/t4 纯黑修复；骨骼映射表单、承重关节闸门、
> 装饰骨策略列、移除 3DMigoto 后的三步 UI **都没有人在真 Blender 里用过**，新预设四家更是
> 连模型都没试过。逐项验证等级见
> [universal-mod-automation-plan.md](universal-mod-automation-plan.md) 顶部状态表。

GakumasMI 已打通 Blender → chinosk6 插件 → 游戏的换模闭环：

- 身体与发型任意拓扑网格导入、骨名映射、校验和 bundle 导出打包；`m_bdyco` 是身体包可选段，
  `Geo_HairProp` 是发型包内可选组件，启用时与 `Geo_Hair` 合并发布；
- 作者模型**自带权重原样保留**，插件只把骨名换成游戏骨名，游戏引擎自己蒙皮；
  骨名认不出来时由作者在「骨骼映射表」里点选，覆盖率不取决于插件认识多少种命名规范；
- 导出前查 14 个承重关节有没有拿到权重，缺任一根拒绝导出并点名——防「导出成功、进游戏才废」；
- 从抓帧与 AssetStudio Mesh JSON 一键生成配置档；
- ~~GPU 每帧恢复骨骼矩阵并重蒙皮，动态 VB 实测 RMS 约 `1e-6`~~（随 3DMigoto 路线移除）；
- `t0/t1/t4` 材质烘焙，body 原生 `m_bdyco` 镂空材质；
- hair 的 t0–t7、顶点 COLOR nibble、HHL/coverage/outline pass 已完成 shader+Geo 交叉验证；
  当前产品提供安全 t0/t1/t4 与常量描边默认值；
- 共享基础发型的运行时精确选择：完整发型包只在配套发饰绘制的那一帧替换发型，换成别的
  发饰/发型自动恢复原样（见下方核心结论）；
- manifest、封面、冲突目标与 Mod Manager 完整兼容。

随插件打包的示例配置档三档：

- `profiles/atbm-cstm-0140`：带原生 `bdyco` 的 body；
- `profiles/hmsz-hair-0023-hair`：hair；
- `profiles/ttmr-cstm-0111`：单材质段、无 co 的 body。

## 已冻结的核心结论

- 游戏角色网格使用 CPU 蒙皮；静态结构来自 Mesh JSON。
- ~~逆解与重蒙皮链已实机验证~~（随 3DMigoto 路线移除；不再探索进程注入、手/颈拆件等替代路线）。
- AB 路线的骨架永远是游戏原版那套：不新建骨、不改 bindpose，实测同名骨 bindpose 逐元素偏差 0。
- 骨映射的覆盖率是**数据问题不是算法问题**——支持一种新命名规范＝加一张预设表；认不出来的
  由作者在表单里点选。因此不再靠嗅探"这是哪种模型"。
- 装饰骨的物理归属**命名和位置都决定不了**（源作者常把腰饰绑在胸骨、把裙边花边绑在大腿），
  实测位置匹配 1/3 命中。这一层的目标不是猜准，而是默认选个不会炸的（刚性跟父骨）+ 作者一句话覆盖。
- 材质槽位由运行时地标自动判布局，不维护逐 PS hash 列表。
- body/hair 的 `t1.A` 都门控镜面/间接光；body 常按 AO 使用，hair 原图只在 HHL 区写高。
  当前插件不替换 t6 HHL，因此自定义 hair 的安全预设必须为 0，避免旧 UV 高光泄漏。
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
[`transparent-material-status.md`](transparent-material-status.md)，发型资产/制作流程见
[`hair-replacement.md`](hair-replacement.md)，逐 pass/逐通道逆向见
[`hair-shader-analysis.md`](hair-shader-analysis.md)。

## 完成度评估（0.7.8 时点，对照 TheHerta4；未按 0.9.0 重评）

参照目标是 [TheHerta4](https://github.com/StarBobis/TheHerta4)（GIMI/WWMI 家族的 SSMT4
Blender 插件，v4.1.37 · 2026-07，10+ 游戏）提供的作者体验。注意两者前提不同：它支持的游戏
是 GPU 蒙皮（权重可从 VB 直接抓），学马是 CPU 蒙皮——GakumasMI 的逆蒙皮链、自动传权、
运行时布局探测都是参照目标**没有**的能力；反之它有我们**暂不开展**的 ShapeKey 与蓝图树批量导出。

> 表中「GPU 核心」「蒙皮转权」两行对应的功能已于 2026-07-27 随 3DMigoto 路线**整体删除**，
> 保留行文仅为记录当时评估。0.9.0 的骨映射覆盖率账见
> [universal-mod-automation-plan.md](universal-mod-automation-plan.md) 的 2026-07-27 进度。

| 模块 | 完成度 | 相对 0.7.2 评估的变化 |
|---|---:|---|
| ~~GPU 核心（逆解矩阵 + 重蒙皮 + 注入）~~（已删除） | ~95% | 冻结无变化。RMS ≈ 1e-6，参照目标无对应能力（其游戏不需要）。 |
| 配置档生成（一键：注入 + 结构 + 逆算子） | ~90% | 新增 hair+hairprop 双组件一键提取；共享基础发型多候选按同帧发饰顶点数消歧。 |
| ~~蒙皮转权（作者模型 → 配置档骨架）~~（已删除） | ~85% | 无变化。参照目标无自动传权（数字顶点组 + 手工笔刷），此项仍领先。 |
| 贴图 / 材质 | ~90% | hair t0–t7、coverage/HHL、COLOR nibble 与 outline 已逆向闭环；当前三图安全路线已校正。剩余是把可选 t6+t1.A 和 HairProp section 语义产品化。参照目标用逐游戏静态槽位映射，我们是运行时地标探测。 |
| 透明材质（cutout 边界内） | ~85% | 无变化；真半透明仍在边界外。 |
| 健壮性 / 回归测试 | ~90% | 7 组纯 Python 回归进入 CI；Blender 4.2.7/4.5.3 矩阵各跑安装、UI、材质烘焙、合成逆蒙皮导出 4 个闭环。测试不再依赖本机绝对路径、gitignored 抓帧或旧版 zip。 |
| 产品化（完整发型包 / Mod Manager / 发布） | ~85% | **交付边界从"单 body 换装"扩至 body + 完整发型包**：hair+hairprop 合并单包、运行时精确选择（0.7.6 实机验证）、管理器显示组件组合、tag 触发自动发布。 |

**相对参照目标的差距**（均在「暂不开展」清单内，有可复现需求再评估）：
ShapeKey/表情、蓝图树批量出 mod、多游戏架构。脸部等其余组件同前暂缓。

## 当前维护项

| 优先级 | 事项 | 完成条件 |
|---|---|---|
| P0 | 回归与发布维护 | 5 组纯 Python + Blender 4.2/4.5 四段闭环持续通过（移除 3DMigoto 后 mod.ini/传权两组测试已删） |
| P0 | 装饰骨默认策略翻转 | 位置匹配退出默认路径、改为跟源父骨 + `胸`→`Bust*_S` 名字规则；属行为变更，需确认后再做 |
| P1 | hair 高保真材质 | t6 HHL 与 t1.A mask 成对导出；无 t6 时继续安全归零 A |
| P2 | HairProp section 语义 | 显式保留 hair-like / `hirco` cutout 的 t0.A、材质段与 outline pass |
| P3 | packed COLOR 高级模式 | 常量档保持默认；另提供保留/绘制 outline RGB、G低、B低、A高的路径与合约测试 |
| P4 | 作者体验 | 仅处理会阻断主流程的 UI、报错和兼容问题 |

排序依据：测试闭环已修完，当前最大可见质量缺口是 hair t6 HHL；HairProp 分段若不先明确，
继续堆通用透明/材质抽象会把 cutout 与普通 hair 段混在一起。ShapeKey、蓝图树和多游戏支持
仍不是下一步，它们不会改善当前学马 hair 的正确性。

## 暂不开展

- 连续半透明、Shape Key/表情、脸部替换、LOD/多 drawcall 自动编排；
- 自建 shader/state 透明路线；
- 为单个样本增加通用抽象或长期维护的 PS 枚举。

这些需求只有在出现可复现样本和明确用户需求时再恢复。
