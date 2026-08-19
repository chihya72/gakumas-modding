# AB 路线 v2 计划

> 状态：草案（2026-08-15 立）
> 适用：`gakumas_mi`（Blender 插件）+ `gakumas-mod-runtime`（运行时）
> 这份文档是 v2 的**唯一主计划**。阶段推进、删除决定、验收判据都写在这里；
> 运行时自身的缺陷台账不在这里，在 `gakumas-mod-runtime/docs/known-risks.md`（F/R/X/P 编号），
> 本文只引用编号，不复制内容。
>
> **2026-08-15 复核**：本文与 `ab-route-v2-full-record.md` 经独立评审
> （[`ab-sdk-independent-review-2026-08-15.md`](ab-sdk-independent-review-2026-08-15.md)）修正，
> 修正清单见 [`ab-route-v2-full-record.md` §10](ab-route-v2-full-record.md)。路线结论未变。

---

## 1. 目标与非目标

### 目标（按优先级）

1. **排除错误** —— 删掉已证伪的旧结论所留下的代码与 UI，修掉已定位但未修的缺陷。
2. **更新功能** —— 把 SDK 路线上量出来的东西搬进 AB 路线：矫正骨权重、12 种姿势驱动器、闸门套件。
3. **删繁就简** —— 两条子路线（native 补丁 / `unity_route`）职责划清，一件事只有一条通路。

### 非目标（明确不做，避免范围蔓延）

- 不追求"衣物物理全自动分类"。目标是让**调的成本降下来**，不是让分类器更聪明。
- 不追求"任意骨架"。身体动画是纯 humanoid muscle，humanoid 骨名必须是游戏认识的那套，
  这对 AB 和 SDK 一视同仁（见 §2.4）。
- 不改比例/身高。游戏自己有身高系统（`HeightCoefficient`/`CmmnHipsHeight`/`BaseHeight`/
  `MinHeight`/`MaxHeight` + `ApplyActorSwingCmmnHeightCorrection`），跟它对着干得不偿失。
- 不重写 `unity_route` 里已经跑通的部分。

### 一条压倒性约束

> **不能引入新的错误。**

这不是口号，是排序依据：**任何"可能引入新错误"的改动，必须排在"能发现新错误"的改动之后。**
所以 P0（闸门）必须先于 P1（第一个产物改动）。本文所有阶段顺序由这一条推出。

---

## 2. 现状盘点

### 2.1 插件里现在有两条子路线，职责重叠

| | native 补丁路线 | `unity_route` |
|---|---|---|
| 入口 | `operators.py: GMI_OT_export_bundle_source` | `unity_route.py`（适配 / 导出两个按钮）|
| 产物 | geojson + sidecar + PNG → `tools/patch_unity_bundle.py` 打模板补丁 | 调无头 Unity 出包 |
| 宿主 | **原版 prefab**（mesh 塞回原 renderer） | **自建 prefab** |
| 游戏对象侧契约 | **大量继承**（原 prefab / 22 个组件列表 / 原骨上的驱动 / 当前场景活体材质） | 要重新提供对象、组件、引用，让游戏自己重建这些列表 |
| 内容侧契约 | **两条一样多**：坐标空间、骨序、bindpose、权重、submesh↔材质槽、COLOR/UV 语义、服装专属材质参数（见 full-record §3.7） | 同左 |
| 战绩 | 千咲、大国主、fuyuko 飘带、21 号发型、发饰 —— 5 个实机成品 | IP 服装、原神 rip 各 1 次；MMD 0 次 |

> ⚠️ 战绩这一行说明的是**当前 AB 工具链的项目经验更丰富**，不是两条路线的成功率对比 ——
> 模型难度、时间投入、实现成熟度、验收目标都没有控制。别拿它当路线优劣的量化证据。

**v2 的分工决定**：

- **native 补丁是主线。**所有"能在原版宿主上做的"都走它。
- **`unity_route` 降为逃生舱**，只在 native 路线**结构上做不到**时启用。目前唯一确认做不到的是
  「humanoid 关节之间插骨」（如给只有两节脊椎的 MMD 补 `Spine2`），而这一条**尚未验证 native
  路线是否真的做不到**（见 P4-E）。若验通，`unity_route` 的必要性可能归零。

> 分工判据（沿用 `unity_route.py` 自己写的那条，它是对的）：
> **改作者的东西（姿势、权重、贴图）留在 Blender，他看得见；改学马的东西留在自动化里，他不用管。**

### 2.2 删除候选（已证伪 / 从未被走过 / 与新结论冲突）

每一条都要在删之前**再确认一次**（见 §4 变更协议 前置-4）。

| ID | 对象 | 依据 | 处置 |
|---|---|---|---|
| D1 | 摆动**幅度调参** UI 与相关参数 | 2026-08-11 负结果：五个参数只动 ±35%，幅度不由它们决定 | 删 UI，保留字段（sidecar 兼容） |
| D2 | **自动关节对齐** | 两次都产废品；已决定「对齐交给作者，代码只留尺子」 | 删，保留 `report_joint_alignment` 尺子 |
| D3 | `integrate` → `new_source_chain` 通路 | 7 个成品里 `new_source_chain` 计数 **0**，一次都没被成品走过 | **不删**——fuyuko 是画面级成功样本；改为默认不推荐、UI 降级 |
| D4 | "option A：bundle 授权原生组件" 残留 | AB 笔记 §7 已标注「已不需要」 | 删 |
| D5 | 按名字猜链语义的兜底 | 已证伪（`lace` 可能在靴口；Genshin `Hair` 图集里有整条腿） | 删猜测，保留显式声明 + 几何判据 |
| D6 | `patch_unity_bundle.py` 的**合成对象内嵌**路径 | 内嵌 UnityPy 合成对象 = Unity 6 加载崩；已改为运行时从 sidecar 建骨 | 确认已删干净 |
| D7 | `sourceRigRemap` 把 `腕捩*.R` 全折叠成 `RightArm` | 扭转分配整个丢掉，量出来 `*_H` 承重 0.00%（原版 17%） | **改**，见 P1 |

### 2.3 已定位但未修的缺陷

| ID | 现象 | 根因 | 阶段 |
|---|---|---|---|
| B1 | 肩/肘关节剪切 | mod mesh 在 16 根 `*_H` 上承重 **0.00%**，原版 ~17% | P1 |
| B2 | 新建骨没有姿势驱动器 | 12 种 driver 一种都没往新骨上装过 | P3 |
| B3 | 静止姿势不规范 | 无强制、无尺子 | P2 |
| X1 等 | 见 `gakumas-mod-runtime/docs/known-risks.md` | — | 不在本文范围 |

### 2.4 不可动摇的游戏侧事实（读 il2cpp 3.2.3 得出）

这些是设计约束，不是可选项：

- 身体动画是**纯 humanoid muscle**（idle clip 130 条 binding 全 muscle，零 transform 曲线）。
- muscle 需要 Avatar；Avatar 在 `BuildAvatar()` 里从骨架层级建，humanoid 映射走游戏自己的
  `VLActorDefine.boneToAvatarMap : Dictionary<string, HumanBodyBones>`，`IsValidHumanDescription()` 把关。
- → **任何骨要拿到身体动画，必须叫游戏那张表认识的名字。**新建骨拿不到 muscle，只能靠
  ①跟父骨刚性走 ②`ActorSwing` 物理 ③我们挂的 `QuartzDriver`。
- 组件不是 `GetComponentsInChildren` 收的，是 `CampusActorModelParts.OnRegisterBone(boneName, bone)`
  **逐骨**收进 22 个 `List<>`。什么算骨由 `VLActorDefine.IsBone(Transform)` 决定（判据未读，P5）。
- `VLActorModelParts.TransformCapacity = 256`，`RendererCapacity = 16`。
- 骨进 `BoneNameToTransformDictionary`，body/face/hair 三部件靠 `InitializeBones(allBoneNameToTransformMap)`
  **按名字**互连 → 重名会互相覆盖。

---

## 3. 不变量（INV）

**任何一步都不能破。**每条都来自真实事故，括号里是事故。

| ID | 不变量 | 来源事故 |
|---|---|---|
| INV-1 | **一根骨只能有一个写它的求解器。** QuartzDriver 不得重复；摇物骨不得再挂 QuartzDriver；静态碰撞体不挂 `_H` 骨 | 2026-08-15 双驱动器 → loading 崩；此前静态碰撞体挂 `_H` → 硬崩 |
| INV-2 | **不得向 `CampusActorAnimationInitializeData` 的列表追加。** `initialTransforms`(0xB0) 与 `swingDynamicBones`(0xD8) 是按下标并行的两张表 | 2026-08-11 `RegisterBones` 越界夭折，日志全绿 |
| INV-3 | 节点数预算 **warning**：超 `TransformCapacity`(256) 报复杂度风险，**不阻止出包** | 尚未撞到，但 SDK 侧已到 243。`RegisterBone` 没有 256 边界检查 → 是容量提示不是硬上限，早前写成硬不变量是错的 |
| INV-4 | **骨名在 body+face+hair 合集内唯一** | `_boneMap` 是 name→Transform 字典 |
| INV-5 | **bindpose 与骨架自洽，且在 renderer 空间比较** | 2026-08-15 闸门假设 renderer 是单位阵，原神那版靠 wrapper 碰巧抵消才过 |
| INV-6 | **日志所述 = 实际所做。** 任何"报告做了 X"的日志行，必须能被离线复验 | 材质命名、贴图串包两次都是日志说谎 |
| INV-7 | **破坏性改写必须 per-job 开关、默认关，且在 report 里量化**（移了多少权重、改了多少顶点） | 「转换器只做加法」契约本会期已破两次 |
| INV-8 | **闸门必须双向验证：在坏包上验过会报，在原版上验过不报** | 只验一半的闸门 = 假安全 |
| INV-9 | **一次只改一个变量。**实机一次成本高，作者只看得到画面 | 混变量 → 无法归因 |
| INV-10 | **共享容器必须按模型限定作用域** | 贴图目录跨模型串包（`*_bdy_sdw*.png` glob 到别的模型） |

---

## 4. 变更协议

> 你要的"每操作一步都要检查是否引入新漏洞"就是这一节。**每个 commit 走一遍，不许跳。**

### 前置（动手之前）

- **前置-1｜新存在性检查。** 这个改动会让什么"以前不存在的名字 / 类型 / 文件 / 字段"开始存在？
  然后 **grep 所有按名字或类型查找的地方**，确认没有第二个消费者会因此被激活。
  *(这一条直接来自双驱动器事故：`stockJointRig` 让 `LeftArm_Roll_H` 这个名字开始存在，
  另一个按名字查的装配器就跟着装了第二个驱动器。)*
- **前置-2｜共享容器检查。** 它会往哪个共享容器写？逐个点名：贴图目录、`_boneMap`、
  `renderer.bones[]`、`CampusActorAnimationInitializeData` 的列表、材质槽、sidecar 字段。
  写入是否按模型/按部件限定了作用域（INV-10）？
- **前置-3｜归属检查。** 改的是作者的东西还是学马的东西？改作者的必须可见、可关、可量化（INV-7）。
- **前置-4｜删除确认。** 若是删除：**再验一次它真的没用**（grep 引用 + 查成品数据里的实际计数），
  不能只凭文档里的一句"已废弃"。
- **前置-5｜不变量点名。** 列出这个改动可能触碰的 INV 编号。没有就写"无"。

### 后置（改完之后，进游戏之前）

- **后置-1｜闸门双向验证**（INV-8）。新闸门：坏包会报 + 原版不报，两条都要有输出为证。
- **后置-2｜日志复验**（INV-6）。日志声称做了的事，用离线脚本独立量一遍。
- **后置-3｜原版不回归。** 拿一个已出货成品跑全套闸门，结果与改动前逐条对比。
- **后置-4｜回滚路径。** report / 配置里写清楚怎么退回上一版（路径 + 开关）。
- **后置-5｜单变量确认**（INV-9）。本次实机验证只包含一个变量？若否，拆开。

### 实机验证协议

实机一次成本高，所以：

1. 每次实机只带**一个**变量。
2. 出发前把"要看什么"写成不超过 3 条，写进 `swap-experiment.txt` 的注释。
3. 带回来的证据优先级：`mod-plugin.log` > 截图 > 口述。
4. 失败先读日志核时间戳，确认跑的是新包不是旧包。

---

## 5. 阶段

### P0 — 闸门（零产物风险，必须最先做）

**做什么**：把 SDK 侧已验证的检查搬成 AB 侧出包前闸门，输入是 geojson + sidecar（+ 打好补丁的 bundle）。

| 闸门 | 判据 | 坏包样本 | 原版样本 |
|---|---|---|---|
| G1 `*_H` 承重 | 原版 ~17%；现成品 0.00% | 千咲 / 大国主成品 | 原版 body |
| G2 跨关节混合带 | 原版 肩 13.3% / 肘 3.9% / 腕 6.2% | 同上 | 同上 |
| G3 一根骨一个驱动器 | 原版 16 个在 16 根不同骨上 | SDK `mmd-final` 包 | atbm-0140 |
| G4 摇物骨/驱动器/碰撞体互斥 | 原版 327 个裙摆驱动器零重叠 | 待造 | 全 530 套 |
| G5 骨名唯一（含跨部件） | — | 待造 | 全 530 套 |
| G6 节点数 ≤ 256 | `TransformCapacity` | 待造 | 全 530 套 |
| G7 bindpose 自洽（renderer 空间） | 0 根偏 >1mm | 原神旧包 | 原版 sucu 标定 4/98、28.7mm |
| G8 顶点 COLOR 语义 | 皮肤 `(81,0,15,144)` 逐字节 | — | atbm-0140 |
| G9 贴图归属 | 每个槽的贴图名必须含本模型名 | SDK 串包那版 | — |

**验收**：每条闸门交出两份输出——坏包报了什么、原版报了什么。缺一条不算完成。
**风险**：无产物改动。唯一风险是闸门误报导致以后被无视 → 由 INV-8 兜。

---

### P1 — 矫正骨权重（第一个产物改动）

**做什么**
1. geojson 权重按原版剖面重分配到**已经存在**的 16 根 `*_H`（表来自 `measure_helper_rig.py`，1060 条肢体）。
2. 修 D7：`sourceRigRemap` 里 `腕捩*.R → RightArm` 改成 `→ RightArm_Roll_H`（左同）。

**为什么第一个**：靶子已量化（0.00% vs 17%）；骨已存在，不新建、不碰 prefab、不开 Unity；纯权重数学。

**触碰的不变量**：INV-7（破坏性，必须开关+量化）、INV-9（单变量）。
**前置-1 检查**：不产生任何新名字 —— `*_H` 本来就在原版骨表里，所以**不会**触发 INV-1 那类连锁。
**验收**：拿已出货的**千咲泳装**（同一件 atbm-0140），只改这一项。
- 离线：`probe_joint_collapse --motion=twist` 三方对照（改前 / 改后 / 原版）
- 实机：同一动作看肩肘
**证否条件**：若扭转塌陷无改善 → 说明对 `PatchModMeshSkinningToOriginalOrder` 的理解有错，**停下重读运行时**，不要继续往下推。

---

### P2 — 静止姿势规范化（变换外包，我们只出尺子）

**做什么**：不写 retarget。作者侧用成熟方案（CATS `Pose → Rest Pose` / Auto-Rig Pro）。我们出验收：

- 静止姿势偏差（原版量级 4°）
- **滚转对称性** —— 现有工具与 `AvatarBench` 都对它瞎（左右差 6.4° 时报 0.0°），按 thumb→pinky 掌横向量量
- 手指 0° / 拇指 45°
- 烘焙后 bindpose 自洽（复用 G7）

**为什么不自己写**：`TPoseBaker` 只是 28 根骨的瞄准表 + 单样本标定的滚转常量，不通用。
**触碰的不变量**：无（只加检查）。

---

### P3 — 12 种姿势驱动器上运行时（最大的功能增量）

**前提（已确认，不需要 IDA）**：`reference/body-component-inventory.json` 是 530 套原版全扫、0 失败，
每种 driver 的宿主骨名约定与 setting 实值都在里面。**宿主是按命名约定认的**：
`*_H` = 挂 humanoid 骨的矫正，`*_A` = 衣物面板锚点。

**做什么**：sidecar 增加 `drivers: [{bone, type, setting}]`；运行时按类型 `il2cpp_object_new` 建组件、
写 setting、挂到骨上（机制与现有 `ActorSwingChain`/`Collider`/`LimitInfo` 建法相同）。

**setting 的内存布局（读自 il2cpp 3.2.3，实现直接照抄）**

关键事实：`setting` 是**引用字段**（`public class ...Setting`，不是 struct），所以走的是运行时
已有的 `EnsureReferenceField` 那条路——和 `dynamicCollider`/`limitInfo` 完全一样，
`SetDefaultValues` 不会建它，必须自己 `il2cpp_object_new` 再写。

非 Simple 版驱动器的 `setting` 一律在组件的 **0x28**（Simple 版在 0x20，我们不用 Simple 版）。

| Setting 类 | 实例字段偏移 |
|---|---|
| `HumanoidArmSetting` / `HumanoidHandSetting` / `HumanoidUpLegSetting` | `humanPartDof` int **@0x10**，`coefficient` float **@0x14** |
| `RotationSetting` | `rotationOrder` int @0x10，`limitMin` float3 @0x14，`limitMax` float3 @0x20，`coefficient` float3 @0x2C，`connectionAxis` int @0x38，`decomposeType` int @0x3C，`composeType` int @0x40，`referenceBone` GameObject* **@0x48** |
| `SkirtSetting` | `rotationOrder` int @0x10，`innerCoefficient` float3 @0x14，`outerCoefficient` float3 @0x20，`limitMin` float3 @0x2C，`limitMax` float3 @0x38，`connectionAxis` int @0x44，`referenceBone` GameObject* **@0x48** |
| `WaistSetting` | `weight` float @0x10，`referenceWaistOffsetBone` GameObject* **@0x18**，`referenceThighOffsetBone` GameObject* **@0x20** |

前三个各只有两个标量字段 —— 这是 P3a 便宜的原因。带 `GameObject*` 的（Rotation / Skirt / Waist）
要在 graft 时按骨名解引用并写指针，是 P3b 的主要风险（V3）。

**分批**

> **2026-08-15 范围修正（前置-1 检查的产物，动手前抓到）**
>
> **P3a 在 AB 路线上不需要做。** AB 路线的宿主是**原版 prefab**，16 根 `*_H` 上的
> `HumanoidArm/Hand/UpLeg` + `Rotation` 驱动器**本来就在**（audit 实测 atbm-0140 有 24 根驱动器骨，
> 原版 528/530 套都带）。缺的从来只是**落在这些骨上的权重** —— 那是 P1，已经做了。
>
> 我原先把 SDK 路线的缺口（自建 prefab，什么都得重装）直接搬到 AB 上，是**错的**。
> 这条修正让 P3 既变小又变准。

| 批 | 类型 | 覆盖 | 备注 |
|---|---|---|---|
| ~~P3a~~ | ~~`HumanoidArm` `HumanoidHand` `HumanoidUpLeg` `Rotation`（humanoid 肢体）~~ | — | **取消**：原版 prefab 自带，见上 |
| P3b | `Skirt`(379) `Waist`(230) | 多数带裙服装 | 只对**新建的衣物骨**；`Waist` 的 setting 带 `GameObject*`，要按骨名解引用后写指针（V3） |
| P3c | `Frill`(78) `Poncho`(39) `LateRotationSimple`(33) `HumanoidSleeve`(26+9) `Furisode`(25) | 长尾 | 同上 |

**重新表述后的 P3**：给**运行时新建的衣物骨**装上学马自己的布料驱动器，作为"自建摇物链
（`integrate`）"之外的第二条路 —— 原版的裙摆/荷叶边/振袖本来就不靠 `ActorSwing`，靠这些驱动器。

### P3 运行时侧已完成（2026-08-15）

`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`：

- `LocalQuartzDriver` + `parseDriver`：sidecar 的骨记录多一个 `driver` 字段
  （`bones[]` 和 `newBones[]`/`extraSwingBones[]` 都收）。
- `AttachQuartzDriver`：按类名 `ActorAnimationQuartzDriver{type}Bone` 建组件，
  `EnsureReferenceField` 建 setting，**按字段名**写值。
- `GetComponentByClass`：新增，INV-1 闸门要它。

**两个设计决定，都不是随手定的**：

1. **字段按名字写，不按偏移。** 12 种 setting 各有各的字段，硬编码偏移等于把 il2cpp 布局钉死在
   运行时里，游戏一更新就集体错位；「别猜偏移」也是这个项目付过学费的规矩。名字由导出器从原版
   bundle 的内嵌 typetree 抄，运行时只负责找槽写值。类型不靠猜 —— sidecar 分
   `ints` / `floats` / `vectors` / `bones` 四张表明说。（JSON 的 `0` 既可能是 int 也可能是 float，
   按形状猜会把 `rotationOrder` 写成浮点、把枚举写坏，而且这种错在日志里看不出来。）
2. **摇物与驱动器二选一。** `createBone` 原本**无条件**给每根新骨挂 `ActorSwingDynamicBone`，
   所以 INV-1 闸门会把驱动器全挡掉 —— 这是接线时才暴露的。改成：声明了 `driver` 就不挂摇物。
   依据是原版 530 套里 327 个裙摆驱动器与 ActorSwing 组件**零重叠**。

**验证**：`xinput1_3.dll` 构建通过；`mod_runtime_catalog_tests` / `mod_presentation_tests` 通过；
Python 全套 54 项通过。

**顺带修正一个测试 fixture**：`test_verify_ab_package_passes_minimal_contract` 原本声明了
`LeftArm_Roll_H` 却不给它任何权重 —— G1 一上就报了。这不是误报：那份 "最小契约" 描述的是一个
**肩肘会剪切的包**。已把 fixture 改成矫正骨真的承重，并加了一条 `weightShare > 0` 的断言。
（改测试让它通过是很容易掩盖回归的做法，所以理由必须写清楚：fixture 的意图是打包契约，
但它同时也是"什么叫合格的包"的样板，这一条本来就该在里面。）

**触碰的不变量**：INV-1（**最高危**）、INV-2、INV-3、INV-6。
**前置-1 检查（必做）**：装 driver 会让 `LeftArm_Roll_H` 这类名字在 mod 侧"开始有组件"。
必须 grep 运行时里所有按名字/类型找骨或找组件的地方，确认不会有第二个装配器跟着装。
**验收**：每批装完后**活体读回 setting 逐字段等于 sidecar**（这套读回验证在 swing 上已跑通）。
**注意**：P3a 应紧跟 P1。分开上会得到"有权重没人驱动"的假阴性 —— 但这与 INV-9 冲突，
所以 **P1 与 P3a 各自单独实机一次**，先 P1 再 P3a，不合并。

---

### P4 — 命名规范 + 分类器改造

P3 做完后，"给装饰件加物理"变成一个**命名问题**：叫 `LeftFrontSkirt_A` 就吃 Skirt driver，
叫 `LeftArmCloth_Front_H` 就吃 Frill。

**做什么**
- `ChainClassifier` 判据从"这条链建几层"改成"**这条链该叫什么名字**"。几何判据（垂到胯下、
  链长 <2cm 是体内辅助骨、分叉、父骨是谁）可复用。
- Blender 里让作者**看见每条链被判成了什么**、一键改档。
- report 明说"这条我不确定"。
- 翘起/穿模在出包时报，而不是进游戏才发现。
- **P4-E（独立实验）**：验证 native 路线能否在 humanoid 关节之间插骨（给 MMD 补 `Spine2`）。
  做法：graft 阶段在 `Spine1` 与 `{LeftShoulder, Neck, RightShoulder}` 之间插一个保世界变换的节点，
  看角色能否正常初始化并播动画。**这个实验的结果决定 `unity_route` 是否还有存在必要。**

**这一层永远做不到全自动**（裙 / 缎带 / 披挂的语义），目标是把调的成本降下来。

---

### P5 — IDA（只在这几处，且都不是卡点）

P0–P4 **一次都不需要 IDA**（真值全在 530 套原版的内嵌 typetree 里）。

| 问题 | 为什么要 | 优先级 |
|---|---|---|
| `ActorSwingChain.UpdateChainInfo`（`sub_1316A88`, 0xa20） | 层数 / `radius` / `smoothing` / `active` 现在靠反推，且已知"它根本不算，新层拿默认值" | 高 |
| 各 driver 的 `Calc()` 读哪条 muscle / 哪根参考骨 | 抄值能用，但不知语义就只能抄不能推 | 中 |
| `VLActorDefine.IsBone(Transform)` | 决定组件挂哪里才会被 `OnRegisterBone` 收 | 中 |
| `boneToAvatarMap` + `IsValidHumanDescription()` | 骨名桥现在是猜的 | 中 |
| `CorrectSkeleton(partsId, instance)` | 完全不知道它改什么 | 低 |
| `RegisterBone(bone, layer)` 的 layer / 256 是软是硬 | 决定 G6 是警告还是红线 | 低 |

**操作纪律**（2026-08-15 事故）：IDA 反编译会因为弹窗或自动分析未完成而**长时间阻塞**。
- 先用便宜调用探（`get_function_by_address`），确认响应再 `decompile_function`。
- 必须先给 `ida-pro-mcp` 配 per-server `timeout`（建议 120000 ms）。
- **一旦超时，立刻停下来报告，不许原地重试。**

---

## 6. 风险登记

| ID | 风险 | 阶段 | 缓解 |
|---|---|---|---|
| V1 | P1 改作者权重，作者不认可 | P1 | 默认关 + report 量化 + 可退回 |
| V2 | P3 装 driver 触发第二个装配器 → 崩（重演 2026-08-15） | P3 | 前置-1 强制 grep + G3 闸门 |
| V3 | `Waist` 的对象引用接线错 → 空指针 | P3b | 单独一批，活体读回验证 |
| V4 | 新骨 + 新 driver 把节点数推过 256 | P3/P4 | G6 |
| V5 | 闸门误报 → 以后被无视 | P0 | INV-8 双向验证 |
| V6 | 删除误伤（D1–D6） | P0/P1 | 前置-4 二次确认 |
| V7 | 热重载不补建新骨/链 → 测试结论失真 | 全程 | 每次改 sidecar 结构必须重进场景 |

---

## 7. 版本与发布

- `gakumas_mi` 当前 `1.1.0` → v2 目标 `2.0.0`（有删除，是破坏性变更）。
- 运行时协议：`sidecar schemaVersion 4 / runtimeProtocol 1`。P3 增加 `drivers` 字段：
  **优先两种都收，不升协议号**（旧包不带 `drivers` 也能加载）。
- 契约变更必须同时改 `gakumas-mod-runtime/docs/manifest-v2.md` —— 只查插件仓会漏。
- Release tag 用前缀（`gakumas-mi-vX`），两条产品线版本号绝不同步。
- 打包输出到项目 `dist/`。

---

## 8. 进度

| 阶段 | 状态 | 证据 |
|---|---|---|
| P0 | G1/G5/G6 已落地并双向验证 | 见下 |
| P1a 捩骨落点（非破坏性） | 已完成 | 37 项单测通过（35 旧 + 2 新），无回归 |
| P1b 权重重分配（破坏性） | 未开始 | — |
| P2 | 已完成（G10） | 判据在原版上标定 0.00°；扰动 bindpose 后报 33.8° |
| P3 运行时侧 | 已完成并编译通过 | 54 项 py 测试 + 2 个 C++ 测试全过；`xinput1_3.dll` 构建成功 |
| P3 导出器侧 | 已完成 | 530 套扫出 12 种驱动器预设；60 项测试通过 |
| P4 | 部分完成 | 命名/类别映射已定；P4-E 需实机 |
| P5 | 部分完成 | `IsBone` 已反编译定性；其余待续 |
| P4 | 未开始 | — |
| P5 | 未开始 | IDA 连通已验（`0x1316A88` → `sub_1316A88`, 0xa20） |

### P0 已完成部分（2026-08-15）

落在 `tools/verify_ab_package.py`（沿用它的 stdlib-only 契约，没有新建工具）：

- **G1 `*_H` 承重** —— `helper_rig_share()` 抽成纯函数，好让同一个判据能直接喂原版数据做反证。
- **G5 骨名唯一** / **G6 节点数 ≤ 256** —— `_check_skeleton_budget()`。

**INV-8 双向验证结果**

| 侧 | 结果 |
|---|---|
| 坏包会报 | 6 个已出货成品里 4 个触发：chisaki / daikokushu / hmsz-fuyuko / mltd-stage 全是 **0.00%**；madoka(8.88%)、miku 正确不报 |
| 原版不报 | 49 套原版 body **误报 0** |

**过程中抓到一个我自己的标定错误**（这正是 INV-8 存在的意义）：第一版把下限定在 8%，理由是
文档里的"原版 ~17%"。实测 49 套原版的分布是 **min 6.02% / P5 7.43% / 中位 11.28% / max 21.00%**，
8% 会误报 13 套（27% 的原版）。已改为下限 4%（低于观测最小值且有余量），硬错误只留在**恰好为 0**
——原版没有一套是 0。"17%" 来自 `measure_helper_rig.py` 的另一种分母，**不能在这里复用**。

**G2/G3/G4** 落在新增的 `tools/audit_ab_rig.py`（要 UnityPy + 原版对照，所以不能塞进
stdlib-only 的 `verify_ab_package.py`），共用新的 `tools/vanilla_body.py` 读原版骨架/组件。

> **阈值策略改了**：能和"被替换的那一件原版"逐关节对比，就不用总体阈值。
> `*_H` 那次标定错（8% 会误报 27% 的原版）之后，G2 改成 mod 与它自己的目标逐关节比，
> 低于原版同关节 40% 才报 —— 这类错误从此不可能再犯。

| 闸门 | 坏包会报 | 原版不报 |
|---|---|---|
| G1 `*_H` 承重 | 6 个成品中 4 个（0.00%） | 49 套误报 0 |
| G2 跨关节带 | madoka（肩 4.5% vs 原版 16.5%） | 22 套自比，误报 0 |
| G3 一骨一驱动器 | 造的违规 sidecar 报了 | 4 个成品全不报 |
| G4 摇物/驱动器/碰撞体互斥 | 同上，3 条全中 | 同上 |
| G5 骨名唯一 / G6 ≤256 | — | 全不报 |

**G7（bindpose）已证伪并撤掉。** 原判据假设"所有承重骨共享同一个 mod→renderer 空间校正"。
拿**原版自己的** bindpose 反证：原样 最大离散 1088.6mm / 中位 261.3mm，转置 748.2mm / 6.7mm ——
两种矩阵约定都不成立。真因是 bindpose 编码的是**绑定时**的骨世界变换，与 bundle 里 Transform 的
**当前静止**变换不必相等（原版静止姿势本就有量级 4° 偏差）。三个已出货成品全被判 ~1000mm 就是
这个错误前提的产物。**上一个在原版上也报的闸门比没有闸门更坏（V5）**，所以撤掉，理由写进源码注释，
防止再走同一条错路。要重做就照 SDK 侧那条已验证的：在 renderer 空间比 bindpose 推出的骨位置与实际骨位置。

**G9 不适用 AB 路线**：贴图串包是 SDK 侧共享目录 glob 造成的；AB 路线的贴图由 `mod.json`
逐槽显式声明，没有隐式查找，不存在这个洞。

**顺带修掉一个静默洞**：`vanilla_body.resolve()` 早期版本在名字为空时会 glob 成 `*`，
**静默拿库里第一套 body 当对照**，报告照样打印得像模像样。已改成硬失败（空名字、或匹配数 ≠ 1）。

### P1a 已完成（2026-08-15）：捩骨落点

**P1 拆成了两半**，这是动手时才看清楚的：

- **P1a 换落点** —— 源模型**自带**捩骨时（MMD 的 `腕捩/手捩`、原神的 `+UpperArmTwist`、
  多数 rip 都有），只要把映射目标从 `LeftArm` 改成 `LeftArm_Roll_H`，权重就落到矫正骨上。
  **这是纯换落点，作者的权重数值一个都没动** —— 不触碰 INV-7，不需要开关。
- **P1b 重分配** —— 源模型**没有**捩骨时才需要按剖面搬权重。破坏性，按 INV-7 走开关。

P1a 的实现：预设表的值现在可以是**按优先级排的候选列表**（`gakumas_mi/core.py:
_resolve_preset_value`），16 条捩骨规则改成 `["LeftArm_Roll_H", "LeftArm"]`。
目标骨架没有 `*_Roll_H` 时退回 humanoid 骨 —— **绝不能让它掉进 `unmapped` 把权重丢掉**，
这是改这版时差点造出来的新洞（`mapped_name` 原本要求 `candidate in target`，
直接写死 `*_Roll_H` 会让整根骨消失）。

验证：`tests/test_bundle_source_contract.py` 加了 2 个用例（正常落点 + 无矫正骨退化），
全套 **37 项通过（35 旧 + 2 新），无回归**。

**还没验的**：实际能把 `*_H` 承重从 0.00% 抬到多少 —— geojson 里只有最终骨序，
无法从已导出的成品反推，必须**从 .blend 重新导出一次**才能量。这是 P1a 的验收缺口，
不能当作已完成。

---

## 9. P3 导出器侧 / P4 / P5 落地记录（2026-08-15）

### P3 导出器侧

`tools/scan_vanilla_drivers.py` 扫 **530 套原版、0 套读不出**，得到 12 种驱动器的 setting 实值
（标量取众数不取平均 —— `rotationOrder` 是枚举，平均出来的 0.37 是个不存在的值；向量逐轴取中位数），
装到 `gakumas_mi/driver_presets.json`。**形状就是 sidecar 里 `driver` 块的形状**，两边都只认字段名。

**只支持三种，这是证据决定的，不是偷懒。**扫描把 setting 里的对象引用当场解成了骨名：

| 驱动器 | 参考骨 | 能否装到任意目标 |
|---|---|---|
| `Skirt` | `Left/RightUpLeg`（1536 / 1525 次） | ✅ 通用身体骨 |
| `Frill` | `Left/RightArm` | ✅ |
| `HumanoidSleeve` | `Left/RightHand` | ✅ |
| `Waist` | `LeftWaist_O` / `LeftThigh_O` | ❌ 每套服装自己的偏移骨 |
| `Furisode` | `LeftFurisodeA_O`、`Spine`、`LeftHand`… | ❌ 四个引用里有两个是 `*_O` |
| `Poncho` | `RightBackPoncho_move_in_O` … **六个引用全是 `*_O`** | ❌ |

后三种装到别的服装上只会得到一串空引用 —— 表现是"这块布不动"，**日志还全绿**。
那正是这一版要消灭的静默洞，所以宁可不支持。`ribbon` 也不给驱动器：原版的蝴蝶结/飘带
就是裸的 `ActorSwingDynamicBone`，本来就该走摇物。

**默认不改变任何现有行为**：`build_source_extra_bones(..., driver_categories=None)`，
作者不点名类别就完全不走这条路径，现有成品重导逐字节一样。点名了才把该类别的骨改成
`driver` 并**去掉 `swing`**（二选一，与运行时一致）。

**接线时抓到一个假阳性**：`bone_side()` 第一版按子串匹配 `_r`，`Cloth_Ribbon` 会被判成右侧，
于是袖子绑到另一条胳膊上，而且离线完全看不出来。已改成边界正则，并加了用例。

### P4（部分）

类别 → 驱动器 → 参考骨的映射表已经定死在 `_DRIVER_BY_CATEGORY`，等于把"这条链该怎么动"
从"建几层摇物"改成"归哪一类"。剩下三件需要 Blender UI / 实机：

- Blender 里让作者看见每条链被判成了什么、一键改档
- report 明说"这条我不确定"
- **P4-E**：native 路线能否在 humanoid 关节之间插骨（给 MMD 补 `Spine2`）—— 决定
  `unity_route` 是否还有存在必要。**必须实机**，离线没法回答。

### P5（部分）

IDA 可用（`ida-pro-mcp`，`UnityFramework` 3.2.3，地址与 `il2cpp.cs` 1:1）。

**`VLActorDefine.IsBone(Transform)` 已定性**（`0x0A845DF4`）：

```c
return (unsigned int)sub_450BAD8(t, &out, qword_D6AC9D8) ^ 1;
//  sub_450BAD8(t, out, dict): name = Object.get_name(t); return dict.TryGetValue(name, out)
```

→ **`IsBone(t) == !<某张静态表>.ContainsKey(t.name)`**。也就是说它是一张**排除表**：
名字命中表里就不算骨。表的内容（静态字段 `qword_D6AC9D8`）要读 `VLActorDefine..cctor`
（`0x0A8463C8`，5620 字节）才知道，il2cpp 的字符串走 metadata 索引，反编译里看不到字面量，
得另想办法（metadata.json 里按索引查）。

**操作纪律（2026-08-15 事故）**：反编译会因为弹窗或自动分析未完成长时间阻塞。
先用 `get_function_by_address` 探，确认响应再 `decompile_function`；小函数（几百字节）秒回，
大函数要留意。**一旦超时立刻停下报告，不许原地重试。**

### P5 补齐（2026-08-15 第二轮，IDA 6 次调用）

**`IsValidHumanDescription()` 已完全定性 —— 这是本轮最有价值的一条。**

| 函数 | 地址 | 结论 |
|---|---|---|
| `ClearRequiredDescriptionFlags` | `0x0A845FF4` | 分配 `bool[19]` 并清零 |
| `AddRequiredDescriptionFlag(hbb)` | `0x0A846130` | `arr[(int)hbb] = 1` —— **索引就是 `HumanBodyBones` 枚举值** |
| `IsValidHumanDescription()` | `0x0A846228` | 这 19 位的**全 AND**（向量化）；数组长 ≤0 时返回 true |

→ **必备集合 = `HumanBodyBones` 0–18**：Hips / 双 UpperLeg / 双 LowerLeg / 双 Foot / Spine /
**Chest** / **Neck** / Head / **双 Shoulder** / 双 UpperArm / 双 LowerArm / 双 Hand。

**Unity 自己的必备集只有 15 根，不含 Chest、Neck、两个 Shoulder。这四根在本作是硬要求**，
缺一根 Avatar 就无效 → 动画一帧都不播。已落成闸门 **G11**（`REQUIRED_HUMANOID_BONES`，
存在性检查而非承重检查 —— Head/Neck 在 body 网格上完全可以零权重，脸是另一个部件）。
双向验证：造的缺 3 根的骨架会报；6 个已出货成品全不报。
顺带发现原有的 `CRITICAL_BONES` 只有 14 根，**正好漏掉这 5 根**。

**`VLActorDefine.IsBone(Transform)`**（`0x0A845DF4`）—— **上一版的"名字排除表"是我读错了，已订正。**

追进 helper 才看清：`sub_46A55F8` 是 `GameObject.TryGetComponent(Type, out)`
（`sub_A3EDDCC` = `Component.get_gameObject`，`sub_A3F2EA8` = 注入的 TryGetComponent），所以

```
IsBone(t) == !t.gameObject.TryGetComponent(<qword_D6AC9D8>, out _)
```

而那个类型由 `RegisterBone` 反推出来了：带该组件的节点被塞进 `v5[11]/v5[12]/v5[13]`，
按字段偏移正是 `renderers`(0x58) / `rendererGameObjects`(0x60) / `skinRenderers`(0x68)。
→ **`qword_D6AC9D8` = `Renderer`**。

**一个 Transform 是"骨"当且仅当它身上没有 `Renderer`。**
可执行结论：**组件不能挂到带 Renderer 的节点上** —— 那不算骨，`OnRegisterBone` 永远不会收它，
表现是"组件明明在包里却完全不生效"。

**`ActorSwingChain.UpdateChainInfo()`**（`0x1316A88`，`sub_1316A88`）：

- `this+32` = `rootBones`，`this+40` = `chains`；它**重建**一份 ChainInfo 再赋回 `this+40`。
- 沿链逐层走，对每一层：
  - 老 `chains` 里**已有对应层** → `layer[16] = old[16]`、`*(u64*)(layer+20) = *(u64*)(old+20)`
    —— 即 **`active`(@16) 与 `radius`/`smoothing`(@20/@24) 原样继承**。
  - 老 `chains` 里**没有** → 新层只写死 `*(u32*)(layer+20) = 1028443341`
    = `0x3D4CCCCD` = **float 0.05f**，其余留默认。

→ 坐实了两件事：① 它**确实不计算** `radius`/`smoothing`，新层拿到的就是 0.05f 常量；
② **但只要 graft 时先把 `chains` 填好，它会原样保留我们的值**。这条对自建摇物链是可用的
——不是"参数会被冲掉"，而是"没预填才会被冲成默认"。

**还没读**：`IsBone` 排除表的内容、各 driver 的 `Calc()` 语义、`CorrectSkeleton`、
`RegisterBone(bone, layer)` 的 layer 用途（决定 G6 的 256 是警告还是红线）。

### P5 收尾（第三轮，IDA 再 4 次）

**`VLActorModelParts.RegisterBone(Transform bone, int layer)`**（`0x0A8840E0`）—— 一次读出三个答案：

```c
name = bone.name;
if (_boneMap.ContainsKey(name)) return false;          // ← 重名直接退出
if (layer >= 0) bone.gameObject.layer = layer;         // ← layer 参数就是 Unity 层
if (bone.gameObject.TryGetComponent<Renderer>(out r))  // 带 Renderer → 当渲染器登记
    { renderers.Add(r); if (isSkinned) skinRenderers.Add(r); rendererGameObjects.Add(go); }
else                                                    // 不带 → 当骨登记
    { _boneInfos.Add(new DefaultBoneInfo(name, bone)); _boneMap[name] = bone; … }
OnRegisterBone(name, bone);                             // ← 22 个组件列表在这里被收
return true;
```

1. **重名的后果比"覆盖"更狠：整根骨被跳过，`OnRegisterBone` 根本不被调用。**
   → 那根骨上的摇物 / 驱动器 / 碰撞体**一个都不会被收**，包里明明有、就是不生效，日志全绿。
   这给 INV-4 和闸门 G5 补上了硬证据（此前只是"字典会覆盖"的推测）。
2. **`layer` 参数就是 Unity 的 GameObject layer**（对上插件日志的 `layer: 243 个节点设为 12`）。
3. **`TransformCapacity = 256` 是容量提示，不是硬上限**：`RegisterBone` 全程没有对 256 的边界检查，
   列表靠 `List.Add` 自行扩容。→ **G6 保持 warning 是对的，不该升成 error。**

**驱动器 `Calc()` 语义**（以 `HumanoidArmBone.Calc` `0x01312B84` 为例）：

```c
float Calc(muscleValue, muscleConvertCoefficient, rotateCoefficient)
    { return muscleValue * muscleConvertCoefficient * rotateCoefficient; }
```

纯标量连乘 —— setting 里的 `coefficient` 就是一个**线性增益**，没有曲线、没有钳位。
所以新部件的系数**可以推**（按目标幅度线性缩放），不是只能照抄原版。

**唯一没读的**：`CorrectSkeleton(partsId, instance)` —— 它在泛型
`VLActorController<TModelParts,TDescriptor,TIDescriptor>` 上，dump 里没有具体地址，
要先找到实例化后的具体方法才能反编译。**不是卡点**（AB 路线继承原版 prefab，这一步对我们透明）。

---

## 10. 复审（2026-08-15，自查"有没有没做全"）

**结论：查出 3 个真缺口，其中 1 个是我这轮自己引入的新 bug。全部已修。**

### 缺口 1 —— P3 导出器**根本接不通**（我却报成"完成"）

`build_source_extra_bones(..., driver_categories=None)` 加了参数，但**没有任何调用方传它**
（`operators.py:766` 原样没传）。也就是说整个 P3 导出器侧对作者是**不可达的死代码**。

已接通：
- 策略枚举加 `native_driver`（"原版布料驱动器"），说明里写清只支持 Skirt/Frill/HumanoidSleeve
  以及为什么不支持 Waist/Furisode/Poncho。
- `_form_driver_categories(scene)` 收集点名的类别（`swing_category` 为 auto 时按骨名判）。
- 调用点真正传 `driver_categories=`。
- `ui.py` 的部件类型下拉原本只对 `integrate` 可用，现在 `native_driver` 也可用
  —— 否则作者选了新策略却无法选类型。
- JSON 导入的策略校验走 `enum_ids("strategy")` 动态取值，新枚举自动被接受，无需改。

### 缺口 2 —— G8（顶点 COLOR 语义）**从头到尾没做，汇总里也没提**

之前只列了 G1–G7/G9/G10/G11，G8 被静默跳过了。已实现：

判据取自 22 套原版实测 —— **纯白顶点 0 个**（RampAdd 行用到 {0,1,2,3,6,9,12,15}；
rim 以 9 为主但 0 也占约三分之一，**所以 rim 不能当判据**，纯白才是干净的红线）。
一个没有顶点色的网格导进来会拿到 (255,255,255,255)，描边宽/rim/行号全读错，
画面上就是"换完模型没描边"。双向验证：造的全白包会报；4 个成品全不报。

### 缺口 3 —— 我引入的新 bug：`GetComponentByClass` 可能拿错重载

`FindMethodByNameAndArgCount` 只比名字 + 参数**个数**，而 `GameObject.GetComponent` 有
`(Type)` 和 `(string)` 两个单参重载，遍历顺序不确定。拿错就是把 `Il2CppReflectionType*`
当 `System.String*` 传 —— 而这个函数正是 INV-1 闸门的判据，**一个静默失效的闸门比没有闸门更糟**。

已修：新增 `FindMethodByArgType(klass, name, argTypeName)` 按参数类型名匹配；
且解析不出正确重载时**返回"已占用"而不是 nullptr**，让调用方拒绝挂载（fail-closed）。
运行时重新构建通过。

> 遗留（未改，因为是既有生产代码、动它有回归风险）：`AddComponentByClass` 用的还是
> 只比个数的旧 helper。它在生产里一直工作，说明当前解析顺序恰好正确，但这是**碰运气**，
> 游戏更新后可能翻车。建议后续统一换成 `FindMethodByArgType`。

### 一个反复出现的信号

`test_verify_ab_package_passes_minimal_contract` 这份 fixture 被**三条不同的闸门**先后打回：
缺矫正骨权重 → 缺 5 根 Avatar 必备骨 → 顶点色是纯白。
三次都不是误报，是那份"最小契约"一直在描述一个**进游戏跑不起来的包**。
每次都是补齐 fixture 而不是放宽闸门，理由都写在测试注释里。

---

## 11. 从 SDK 再取五项（2026-08-15 第二轮）

详细记录见 [`ab-route-v2-full-record.md` §11](ab-route-v2-full-record.md)。摘要：

| # | 目标 | 结果 |
|---|---|---|
| ① 摇物层 `around` | ③ 动态 | **已改**。IDA 读出 `UpdateChainInfo` 不拷贝 `around`(@0x11)；`smoothing` 量完发现原版中位数全 0、不用写 |
| ② 顶点 COLOR 合成 | ② 显示 | **已整条撤回** —— AB 已有且更强（BASECOLOR 逐顶点采样 t0） |
| ③ 结构化 report | ① 操作 | **已改**。`findings[{level,message,action}]`；顺带修了 action 在子报告汇总时被丢掉的洞 |
| ④ 链分类几何判据 | ③ 动态 | **已改**。锚点 + 同锚点条数 + 垂向；名字降为兜底 |
| ⑤ 出包预览图 | ① 操作 | **已改**。`--preview`，边界写在注释里：只抓粗错误 |

**新增不变量候选（还没进正式表，因为只栽过一次）**：

> **INV-11｜判断"AB 有没有某功能"时，必须查"它有没有被消费"，不能只查数据/属性是否存在。**
> 本会期四次提出搬运 AB 已有的东西：P3a 驱动器（原版 prefab 自带）、t1/t4 合成、摇物基准表、
> 顶点 COLOR。前三次栽在只看数据存在，第四次栽在 grep 用字面量而消费点是变量传递
> （`_preset_color_float(presets.get(key))`）。
