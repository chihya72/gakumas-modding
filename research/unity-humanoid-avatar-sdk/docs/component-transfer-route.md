# 一条管线，三种源：搬运源自带的 rig，源没有就按几何合成

> 2026-08-14 下午补：管线已扩到「任何模型文件」。三层结构见下方「没有按源游戏分模板这回事」。
> 新增前端 C（FBX）+ Humanoid 骨名桥 + 几何链分类器，实测见文末「外部模型实测」。


> 2026-08-14。这份文档回答两件事：AB 路线现在到哪了，以及**为什么每上一个模型都要手调几小时、怎么让它降到接近零**。

## 一、现状：能跑了，但代价不对

`chs-sucu-00`（偶像荣耀）装在学马 `hmsz-cstm-0059` 上，画面基本正常。已经过门的：

| 项 | 状态 |
|---|---|
| 骨架 / 蒙皮 / bindpose | ✅ |
| 材质 / 贴图 / 顶点 COLOR | ✅ |
| 换装、学园、撮影、live 四个场景都不崩 | ✅ |
| 撮影皮肤发黑 | ✅ 已修（材质每次 `BuildModel` 重克隆） |
| 裙子穿模 | ✅ 已修（`_S_End` 进链 + 按类别分组） |
| 摇物摆动 | ⚠️ 前裙片偏硬（只有 1 根活动骨），其余正常 |
| 回滚 / 泄漏 / 发行形态 | ❌ 未做 |

### 这一轮修掉的六个 bug，以及它们的共同点

| 症状 | 真因 | 类别 |
|---|---|---|
| 进换装/撮影硬崩（AV in UnityPlayer） | 每片裙摆挂了两个 `QuartzDriverSkirtBone`（`_A` 和 `_Repulsion_A` 父子各一个） | 我们凭名字猜宿主 |
| 身上出现亮线高光 | 源 def 图光泽 0.72，越过学马 `_SpecularThreshold` 的 0.6；IP 那边靠材质 `_Smoothness=0.5` 压半，学马没有这个标量 | 我们照搬了源数据 |
| 撮影皮肤全黑 | 克隆材质冻结了按场景重建的 `_RampMap`/`_RampAddMap` | 我们的运行时实现 |
| 裙子穿模 | `_S_End` 被排除出链 → 三片前裙摆一根活动骨都没有 | 我们凭规则重建链 |
| 裙子/翅膀炸开 | `around` 按全库多数取 0（该按被替换那套取 1） | 我们按统计猜参数 |
| 裙子不贴大腿 + 僵硬 | 摇物骨 `collisionMask` 用 -1，撞上了半径 0.23 m 的 `Hips` 胶囊；原版裙摆骨用通道 1 | 我们按统计猜参数 |

**六个里有五个的共同点：我们在「重建」一套 rig，而不是「搬运」源模型已有的 rig。**
每一个参数都要靠"530 套里的中位数"猜，每猜错一个就是一轮出包 + 进游戏 + 看画面。
这就是几个小时的来源，而且换一件衣服要重来一遍——中位数不会因为换了件裙子就变准。

## 二、关键事实：源模型自带完整的 rig

`mdl_chr_chs-sucu-00_body.unity3d`（**原始包**，8.4 MB）里实际有：

| 组件 | 个数 | 序列化字节（中位） | 非 `m_` 字段数 |
|---|---|---|---|
| `ActorSwingDynamicBone` | **42** | 592 | 20 |
| `VLActorExpressionBone` | **22** | 168 | 20 |
| `ActorSwingStaticBone` | 12 | 76 | 1 |
| `IKGoalEffector` / `IKHintEffector` | 4 / 4 | 36 | 1 |
| `ActorSwingBreastBone` | 1 | 480 | 15 |
| `IKBodyEffector` / `LookAtEffector` | 1 / 1 | 32 / 44 | 0 / 3 |

> ⚠️ 别扫 `.cleartree.unity3d` / `.resave.unity3d`——那些是重存过的中间文件，typetree 被清掉了，
> UnityPy 读出来所有字段都是空的，会让人误判"源包里没数据"。**认准原始的 `.unity3d`。**

### 两边是同一套中间件，类名大量重合

| IP 的类 | 学马有没有 | 学马携带率 |
|---|---|---|
| `ActorSwingDynamicBone` | ✅ 同名 | 527/530，每套 91.1 |
| `ActorSwingStaticBone` | ✅ 同名 | 527/530，每套 23.1 |
| `ActorSwingBreastBone` | ✅ 同名 | 527/530，每套 1.0 |
| `IKGoalEffector` / `IKHintEffector` / `IKBodyEffector` / `LookAtEffector` | ✅ 同名（都在 `vl-unity.Runtime`） | 528/530 |
| `VLActorExpressionBone` | ❌ 学马没有 | — 对应 `ActorAnimationQuartzDriver*` 家族 |
| — | `ActorSwingChain` 学马有、IP 没有 | 518/530，每套 3.0 |

`ActorSwingDynamicBone` 的字段对比（学马 18 个 / IP 20 个）：

- **同名同结构，可直搬（8 个）**：`damping`、`stiffness`、`spring`、`mass`、`limitInfo`（`useLimit`/`axisX`/`axisY`/`axisZ` 结构一致）、`referenceLimitInfo`、`dynamicCollider`（`type`/`collisionMask`/`vector3_A`/`vector3_B`/`float_A`/`float_B` 结构一致）、`useWindGlobalForce`
- **学马有、IP 没有（需用原版常量补）**：`dynamicType`、`pendulum`、`pendulumRange`、`resetType`、`rootWeight`、`wind`、`modelingTransform`、`axisAddXToY`、`axisAddXToZ`、`seatDynamicCorrection`
- **IP 有、学马没有（丢弃）**：`jobDynamicBone`（运行时 job 缓存）

作者调的东西**全在可直搬的那 8 个里**。对比一下差距有多大（IP 的 `LeftFrontSkirtAccessory2_S` vs 我们按中位数给它的值）：

| | damping | stiffness | spring | mass | limitX | 碰撞半径 |
|---|---|---|---|---|---|---|
| **IP 作者调的** | 0.6 | 0.003 | 0.8 | 0.1 | (-3, 3) | 0.10 |
| 我们的中位数 | 0.5 | 0.008 | 0.3 | 0.7 | (0, 0) | 0.018 |

`mass` 差 7 倍、`spring` 差 2.7 倍、碰撞半径差 5.5 倍，`limitX` 更是被我们锁死成 0。
**这不是"调得不够细"，是根本没在用作者的数据。**

### `VLActorExpressionBone` 就是我们手推了几小时的那个东西

它挂在 `*_Repulsion_A` 上（22 个），字段是一个通用的姿势驱动器：

```json
{"_referenceBone": <骨>, "_axisType": 0, "_rotationOrder": 0,
 "_axisData": [{"coefficient": 0.0,  "min": -180, "max": 180, "outputAxisType": 0},
               {"coefficient": -1.0, "min": -180, "max": 15,  "outputAxisType": 1},
               {"coefficient": -0.9, "min": -20,  "max": 55,  "outputAxisType": 2}]}
```

「跟随某根参考骨旋转，逐轴给系数和上下限」——正是学马 `ActorAnimationQuartzDriverSkirtBone` /
`RotationBone` 的语义（`referenceBone` + `coefficient` + `limitMin`/`limitMax` + `rotationOrder`）。
我们这一轮靠 379/530 的统计、手工把驱动器挂到 `_A` 上、再靠实机把重复的那个删掉——
**而源包里本来就写着每一片跟哪根骨、系数多少、限位多少。**

## 三、已实施（2026-08-14）

搬运器已落地并出包，离线校验 **559 个字段、0 处不符**。

| 件 | 位置 |
|---|---|
| 导出器 | `tools/export_source_components.py` → `components.json`（强类型，给 Unity `JsonUtility` 直读） |
| 搬运器 | `Editor/ComponentTransfer.cs`，在 `SdkPipeline.Shape()` 末尾运行 |
| 校验器 | `tools/verify_transfer.py`，读回成品 AB 逐字段比对源清单，不符则非零退出 |

**设计：先按原版中位数合成，再用源覆盖。** 一条代码路径，没有 if/else 分支：
源没提到的骨保留合成值，目标独有的字段（`wind`/`rootWeight`/`pendulum`/`resetType`/`modelingTransform`）
保持原版表的值。源模型没有 rig 时（MMD/VRM）就没有清单，一切照旧。

实际搬运结果（`chs-sucu-00`）：

```
摇物骨 42（源 42 全部命中）
静态碰撞体 12（拆掉我们合成的 30 个，换成源自带的一整套）
姿势驱动器 14（拆掉合成的 7 个 SkirtBone，换成源的 RotationBone）
胸部驱动 1
```

### 没有「按源游戏分模板」这回事

管线只有一条，三层，**任何源都走同一条**：

1. **合成兜底** —— 按目标游戏 530 套的表把该有的组件都装上（源什么都没带时，比如 MMD/VRM，就只有这层）。
2. **同名搬运** —— 源包里凡是和目标**同名**的组件，逐实例覆盖参数。这条规则不认识"IP"，
   只认识类名；换个源游戏只要它也是这套中间件就自动生效。
   目标没有的类走一张极小的「类名 → 目标类」表（目前只有一行：
   `VLActorExpressionBone` → `QuartzDriverRotationBone`），加一个新源游戏最多加一行，不是加一个模板。
3. **目标规矩修正** —— 属于目标游戏、与源无关的规则，最后统一施加：
   - **取值域夹取**：同名不等于同量纲。源值若超出目标游戏**自己从没出现过**的范围，
     就是两边解算器对该字段语义不一致的信号，夹回目标域。范围由
     `tools/inventory_target_ranges.py` 扫全库生成到 `reference/target-value-ranges.json`，
     SDK 和校验器共用一份。实测这条规则的锋利程度刚刚好：
     源那 42 根摇物骨 **0 个越界**（一动不动），胸部驱动 **2 个越界**
     （damping 0.15→0.20、stiffness 0.03→0.06，目标 529 个胸驱只用 0.20~0.35 / 0.06~0.12），
     而那正是唯一实机表现异常的组件（一直乱抖 = 欠阻尼）。
   - `collisionMask` 按目标的通道表（裙摆 = 1），不管源写的是什么；
   - **一条骨脉至多一个 QuartzDriver**，嵌套会硬崩（`UnityPlayer+0x143EF86`，栽过两次：
     一次是合成器给 `_A` 和 `_Repulsion_A` 各挂一个，一次是把源的两级设计原样搬过来）。
     多级驱动按「系数相加、限位取最内层、宿主取最外层」合并 —— 一阶近似，但这是能跑和崩进程的区别；
   - `*_H` 上的驱动、IK effector 用目标自己的约定。

**三样刻意不搬**，都写在 `ComponentTransfer.cs` 头部：

- `collisionMask` —— 通道约定不是数值。两边源数据都是 -1，但目标的笼子分了真实通道，
  -1 会让裙摆撞上 0.23 m 的 `Hips` 胶囊。成品包实测：裙摆骨 27 根全是通道 1，其余 15 根 -1。
- IK effector ×10 —— 两边是同一张固定表，合成的就够。
- `*_H` 上的 8 个 VL 驱动 —— 目标游戏自己的 humanoid 约定（528/530），且源那 8 个系数基本是 0。

## 四、原方案（存档）：组件搬运器（一次性写，之后每件衣服零调参）

把 SDK 的装配阶段从「按类别查中位数表」改成「按源组件逐个转换」：

```
源 prefab 组件 ──映射表──> 目标组件
   命中     → 直搬同名字段 + 用原版常量补目标独有字段
   源没有   → 才回退到现在的合成（ActorSwingChain、IKCorrection*）
   目标没有 → 按语义映射（VLActorExpressionBone → QuartzDriver*）
```

**成本结构完全变了**：映射表是**按源游戏写一次**（IP→学马一张表），
之后同一个源游戏的每一件衣服都是零调参。现在的方案是每件衣服一轮轮试。

### 分四步，每步都能单独验

1. **搬运可直搬的（收益最大、风险最低）**：`ActorSwingDynamicBone` 的 8 个同名字段 +
   `ActorSwingStaticBone` + `ActorSwingBreastBone` + 4 类 IK effector。
   目标独有字段用现在预设表里的常量补（`wind=1`/`rootWeight=0.3` 这些本来就是全库常量）。
   验收：日志打「搬运 N 个组件 / 合成 M 个」，摆动应当立刻接近源游戏观感。
2. **`VLActorExpressionBone` → `QuartzDriver*` 语义映射**：`_axisData` 三轴 → `coefficient`/`limitMin`/`limitMax`，
   `_referenceBone` 直接指过去。做完就不用再按骨名猜哪片裙摆跟哪条腿。
3. **只对源缺的做合成**：`ActorSwingChain`（IP 没有，规则已实测：矩形层、层 0 锚定、
   最后一层是 `_S_End`、`around` 按被替换那套取）、`ActorAnimationIKCorrectionGoal/Collider`。
4. **导出器补上**：现在 `export/full/*.json` 每个组件类只导了一个实例
   （`ActorSwingDynamicBone.json` 只有 28 字节），搬运器需要**逐实例 + 宿主骨名**的导出。
   这一步是前置，先做。

### 什么东西搬不过来，必须仍然按目标游戏来

- **贴图 / 材质数值**：两边 shader 不同族（`Campus/Actor/Default` vs URP Lit 系），
  源的 def 图光泽、顶点 COLOR 语义都不通用——这部分保持现在的"按学马预设重写"。
- **`_RampMap`/`_RampAddMap`**：运行时按场景赋值，谁都不能提前烘进包。
- **骨名不一致的源**：搬运器按名字对齐宿主骨，骨名重映射仍然是独立问题。

## 四、风险与未知

- IP 的 `ActorSwingDynamicBone` 有 20 个字段，这里只对了前 8 个的名字和结构，
  **剩下 12 个（含 `jobDynamicBone` 内部结构）还没逐字段核**——第 1 步实施前要把整表打出来对完。
- 两边同名字段的**单位/量纲**假定一致（都是 VL 中间件），未验证。第 1 步的实机结果就是验证。
- IP 的 `dynamicCollider.collisionMask` 也是 -1（见上表），说明**通道约定两边不同**，
  搬运时这个字段要按目标游戏的类别表覆盖，不能直搬。
- 源没有 `ActorSwingChain`，说明 IP 的裙摆约束机制和学马不同（可能就靠 `VLActorExpressionBone`）。
  搬过去之后仍然需要合成链，两套机制叠加的效果未知。

## 五、外部模型实测（2026-08-14，Genshin `Avatar_Girl_Claymore_MarionetteNew`）

一个**完全外部**的 FBX：257 根骨、`Bip001` Biped 命名、8 个网格、只有 Diffuse 贴图、零 rig。
按用户要求只留 body（丢掉 face/hair/eye/brow/pupil/effect），替换 `atbm-cstm-0140`。

三块新东西各自解决一个「以前根本进不来」的问题：

| 新增 | 解决 | 实测结果 |
|---|---|---|
| `Editor/HumanoidBridge.cs` | 骨名。用 Unity 自己的 Humanoid 映射当桥，`Bip001 L Thigh` → `LeftUpLeg` | 映射 52 根；顺带补 `Pelvis`（Humanoid 没有这个概念，而原版 758/1537 条链锚在它上面）、去重 1 处 |
| `Editor/ChainClassifier.cs` | 摇物。按**挂在哪根 Humanoid 骨 + 朝向 + 链长 + 同锚点条数**分类，完全不看名字 | 12 条链 / 42 根骨。名字只用来事后验证：`Bone_SkirtB/C/G`→skirt、`Bone_SleeveSA`→sleeve、头纱和侧发→ribbon，**全对** |
| `TextureRewriter` 合成路径 | 贴图。源只有 Diffuse，没有 def/sdw | 4 段各合成 t4（base×0.45）与常量 t1（toon 0.38/smooth 0.40） |
| `Editor/ExternalModelImporter.cs` | 前端 C：FBX → 分段 → 贴图 → 顶点 COLOR → prefab → 包 | 顶点 42066、子网格 4、蒙皮骨 172 |

### 分类器的准确率（`tools/measure_chain_classifier.py`，120 套原版当标注集）

| 真值 | 召回 | 说明 |
|---|---|---|
| skirt | 82% | |
| **skin** | **83%** | 最关键的一类：`*Skin*` 是身体形变辅助骨，判错会给**身体本身**挂摇物 |
| sleeve | 59% | 掉的那部分被判成 skin（钉死）——那些袖链本身长度就是 0，摆不起来，钉住是安全侧 |
| ribbon | 54% | 手感偏差，不致命 |
| cloth | ~0% | 落进 skirt/ribbon 行，只影响软硬 |
| **总体** | **64.1%**（3615 条链） | 第一版只有 57%，skin 召回是 0% |

64% 不是好成绩，但要看错在哪：**有害的那一类（skin）已经从 0% 拉到 83%**，其余的错分只改变软硬手感。
分歧里还有一部分不是「错」——名字说是袖子、几何说这条链零长度动不了，按几何钉住其实更对。

**因此设计上必须配的两样，都已就位**：每条链的判定连证据一起打日志（锚点/朝向/骨数/链长），
以及作者一行覆盖（`GakumasBodyLabels` 同款标注资产）。

### 离线体检（`tools/audit_body_bundle.py`）

进游戏之前把能在文件里看出来的问题全查掉：必备节点、骨名重复、顶点 COLOR 是否还是默认白、
蒙皮骨与 bindpose 数量、材质三张图是否都绑上、组件齐不齐、Hips/Head 高度。
外部模型这一版：**全部通过**，顶点 COLOR 主值 `(0,15,15,144)` 95% + 皮肤 `(81,0,15,144)` 4%，
朝向 +z、左手 −x（与已验证的 sucu 一致），Head 高 1.330（原版 1.248，高 7%）。

### 实机连败三版 —— 真因是静止姿势，不是骨轴向

> **2026-08-14 晚更正**：下面这一小节（连同 `RestPoseNormalizer`）是**错的**，留作记录。
> 离线证据表明身体是**纯 Humanoid 肌肉重定向**驱动，骨轴向被重定向完全吸收、对动画零贡献；
> 真正要紧的是**静止姿势必须是 T-pose**，因为 Avatar 是运行时照我们的骨架建的。
> 完整证据与台架见 [`rest-pose-dead-end.md` §零](rest-pose-dead-end.md)。当前实现：
>
> | 件 | 位置 | 作用 |
> |---|---|---|
> | 烘焙 | `Editor/TPoseBaker.cs` | 把四肢摆到标准 T（外部模型实测大臂 69.1°/67.4°、小臂 15.9°），**顶点和 bindpose 一起重算**——只重算 bindpose 会让骨架站成 T 而网格留在 A，且离线全绿 |
> | 闸门 | `Editor/AvatarBench.cs` | 按游戏的方式建 Avatar，量 ①静止 vs 标准 T ②同肌肉值 vs 参照模型 |
> | 体检 | `tools/audit_body_bundle.py` | 「静止朝向对照原版旋转值」已换成「静止姿势是不是 T-pose」 |
> | 已删 | `RestPoseNormalizer.cs`、`export_target_rest_pose.py`、`reference/target-rest-pose.json` | 带与不带，台架读数一位小数都不差 |
>
> 烘焙后：静止姿势 69.1° → **0.0°**，同肌肉值下与参照模型手臂差 **0.0°**（膝 3.7°，属比例差异）。

第一版外部模型包**通过了当时的全部离线检查**，进游戏却是躺在半空的。当时归因于**旋转**：

| 骨 | 本游戏（已验证的 sucu） | Biped（Genshin） |
|---|---|---|
| Hips | (0, 0, 0) | (83.9, 2.6, −85.4) |
| Spine2 | (0, 0, 0) | (90.0, −16.0, −91.8) |
| Head | (0, 0, 0) | (90.8, 2.1, −89.6) |

本游戏的骨架是 **Y-up、整条脊椎静止旋转为单位阵**，动画就是按这个写的；3ds Max 的 Biped 是 **Z-up**
（每个 Genshin rip、多数游戏 rip 都是）。位置一模一样，轴向差 90°，**所有只看位置的检查都发现不了**。

修法 `Editor/RestPoseNormalizer.cs`：把身体骨的世界旋转设成目标约定（基准由
`tools/export_target_rest_pose.py` 从原版导出到 `reference/target-rest-pose.json`），
饰品骨旋转按原样放回，最后**按新静止姿势重算 bindpose**。
蒙皮是 `骨矩阵 × bindpose × 顶点`，重算后静止姿势逐像素不变，而之后施加的旋转含义就对了。

实测：改了 52 根骨（最大 177.5° 在 LeftShoulder），重算 172 个 bindpose，
**网格 0/172 根骨偏移 >1mm（最大 0.0mm）**——一毫米没动。

`tools/audit_body_bundle.py` 补了两条把这个漏洞堵死：
- **静止朝向**对照 `reference/target-rest-pose.json`（只比身体骨——饰品骨和 IK 锚点随服装不同，
  拿别套当基准会误报，已验证好用的 sucu 就差 20 处）；
- **bindpose 与骨架**是否吻合（UnityPy 的 Matrix4x4 字段是转置的，读的时候要 `.T`；
  判据用 sucu 标定过：它 4/90 根偏 >1mm、最大 28.7mm，和 SDK 自己的 `CheckBindPoses` 报的完全一致）。

#### 归一化本身踩的坑：只保旋转会把骨架打散

第二次实机是炸成尖刺的一团。原因是 `RestPoseNormalizer` 的第一版**只保了旋转**：
改父骨的世界旋转，会把每个子骨的局部偏移一起转走，于是世界位置全变了 ——
Head 挪了 63cm，两只手叠到同一点（右手偏 114cm）。

**而 bindpose 是照这副打散的骨架重算的**，所以绑定姿势自洽、体检全绿、`0/172 根偏 >1mm`
——只有动画一上来才暴露。修法：逐骨在设完旋转后把**世界位置也放回原值**（父骨此时已定稿，
放回世界位置得到的就是正确的局部偏移）。实测 6 根关键骨位移 ≤0.6mm。

体检因此又补两条形状不变量（一个包内部就能查，不需要"之前那版"作对照）：
**左右对称**（LeftHand/RightHand 的 x 必须异号且量级相当 —— 打散那版两只手 x 都是 −0.869）、
**Hips→Head 高度**在人体比例区间内。
