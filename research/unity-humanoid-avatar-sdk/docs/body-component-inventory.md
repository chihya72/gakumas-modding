# body 部件组件全清查

> 2026-08-14。取代"发现一个坑查一个坑"的做法：把学马 body 部件**可能携带的组件**一次穷举完，
> 和 SDK 实际产出逐项对账。三个数据源交叉，结论是闭合的（无未知项）。

## 方法

| 轴 | 数据源 | 脚本 |
|---|---|---|
| A 游戏**要什么** | `CampusActorAnimationInitializeData` 的字段 + `CampusActorAnimationRig` 消费的列表 + il2cpp 里 `ActorAnimation.Runtime`（Image 30，TypeDefIndex 39668-39831，157 个类型）全枚举 | `il2cpp.cs` 直接读 |
| B 原版**给什么** | **全部 530 套 body bundle**，逐个 MonoBehaviour 记类名 / 程序集 / 宿主骨 / 字段集 / 样例值 | `scratchpad/inventory_body_components.py` → `body-component-inventory.json` |
| C 我们**给什么** | SDK 产出的 AB 包 | UnityPy 读回 |

530 套全部解析成功，0 失败，共 **23 个组件类**。唯一的 `?unresolved`（2 套 / 436 个）按字段集
认出来是 `ActorSwingDynamicBone` 和一个 driver，只是那两个包里 MonoScript 名字表没带上 —— 不是新类型。

## 对账表（按携带率排序）

| 携带率 | 每套 | 组件 | SDK | 备注 |
|---|---|---|---|---|
| 528/530 | 4.2 | `ActorAnimationQuartzDriverRotationBone` | ✅ 2026-08-14 | 前臂/小腿 helper 跟随真骨旋转 |
| 528/530 | 4.0 | `ActorAnimationQuartzDriverHumanoidArmBone` | ✅ 2026-08-14 | 手臂扭转分配 |
| 528/530 | 4.0 | `ActorAnimationQuartzDriverHumanoidUpLegBone` | ✅ 2026-08-14 | 大腿扭转分配 |
| 528/530 | 4.0 | `ActorAnimationQuartzDriverHumanoidHandBone` | ✅ 2026-08-14 | 手/前臂扭转分配 |
| 528/530 | 4/4/1/1 | `IKGoalEffector` / `IKHintEffector` / `IKBodyEffector` / `LookAtEffector` | ✅ | 都在 `vl-unity.Runtime` |
| 527/530 | 91.1 | `ActorSwingDynamicBone` | ✅ | |
| 527/530 | 23.1 | `ActorSwingStaticBone` | ✅ | 我们给 32（全身并集，原版均 23，各套只笼自己够得着的） |
| 527/530 | 1.0 | `ActorSwingBreastBone` | ✅ 2026-08-14 | 挂 Spine2，接线 79/79 套一致；**它拥有的 Bust 骨在原版从不挂摇物骨（0/79），摇物必须让开** |
| 518/530 | 3.0 | `ActorSwingChain` | ✅ | |
| 486/530 | 2.0 / 1.0 | `ActorAnimationIKCorrectionGoal` / `Collider` | ✅ | 缺 Goal 会硬崩，见 P0-STATUS |
| 379/530 | 8.1 | `ActorAnimationQuartzDriverSkirtBone` | ✅ 2026-08-14 | 裙摆避让大腿 |
| 230/530 | 2.0 | `ActorAnimationQuartzDriverWaistBone` | ❌ | `Left/RightWaist_H` |
| 78/530 | 3.7 | `ActorAnimationQuartzDriverFrillBone` | ❌ | |
| 39/530 | 3.4 | `ActorAnimationQuartzDriverPonchoBone` | ❌ | |
| 33/530 | 3.1 | `ActorAnimationQuartzDriverLateRotationSimpleBone` | ❌ | |
| 26/530 · 9/530 | 2.8 · 4.0 | `HumanoidSleeveSimpleBone` · `HumanoidSleeveBone` | ❌ | |
| 25/530 | 2.8 | `ActorAnimationQuartzDriverFurisodeBone` | ❌ | |

## 确认**不需要**的（530 套里一个都没有，可以永久划掉）

`ActorAnimationConstraintTransformBone`、`ActorAnimationFullBodyIKPullPartSetting`、
`ActorAnimationIKBodyEffectorLocator` / `IKGoalEffectorLocator` / `IKHintEffectorLocator` /
`LookAtEffectorLocator`、`ActorSwingGroup`、以及全部 `*SimpleBone` 变体（除 LateRotation / Sleeve 两个）。

IK 走的是 `vl-unity.Runtime` 的 `*Effector`，不是 `ActorAnimation.Runtime` 的 `*EffectorLocator`。

## 两套独立系统，别混

- **摇物（Swing）**：弹簧模拟，输入是时间 / 速度 / 风 / 碰撞。`DynamicBone` + `Chain` + `StaticBone`。
- **姿势驱动（QuartzDriver）**：读**另一根骨的旋转**做代数修正，和时间无关。
  `Calc(initialReferenceRotation, currentReferenceRotation, …)` 的签名就说明了这点。

只搬摇物、不搬驱动器 → 裙子必穿大腿，而且**碰撞体调多大都没用**（实测放大 5 倍仍穿模，
同时原版头发被撞飞，证明碰撞路径本身是活的）。IP 的 `*Skirt_Repulsion_A` 就是同一套 rig。

## 值表（每根宿主骨在 120 套里 100% 一致，是硬表不是启发式）

### 必备 16 个

| 组件 | 宿主骨 | setting |
|---|---|---|
| HumanoidArmBone | `LeftArm_H` / `LeftArm_Roll_H` | dof 4，coef −0.8 / −0.3 |
| HumanoidArmBone | `RightArm_H` / `RightArm_Roll_H` | dof 5，coef −0.8 / −0.3 |
| HumanoidHandBone | `LeftHand_H` / `LeftForeArm_Roll_H` | dof 4，coef 0.9 / 0.5 |
| HumanoidHandBone | `RightHand_H` / `RightForeArm_Roll_H` | dof 5，coef 0.9 / 0.5 |
| HumanoidUpLegBone | `LeftUpLeg_H` / `LeftUpLeg_Roll_H` | dof 2，coef −1.0 / −0.6 |
| HumanoidUpLegBone | `RightUpLeg_H` / `RightUpLeg_Roll_H` | dof 3，coef −1.0 / −0.6 |
| RotationBone | `Left/RightForeArm_H` | rotationOrder 1，coef (0,−0.4,0)，compose 3，referenceBone = 同侧 `ForeArm` |
| RotationBone | `Left/RightLeg_H` | rotationOrder 0，coef (0,0,−0.5)，compose 3，referenceBone = 同侧 `Leg` |

`humanPartDof` 是 `UnityEngine.HumanPartDof`：LeftLeg 2 / RightLeg 3 / LeftArm 4 / RightArm 5。

### 裙摆驱动器（每片一个，8 片；9 套之间完全一致）

公共项：`rotationOrder 0`、`connectionAxis 0`、`innerCoefficient (0, 0.1, 0.1)`、
`outerCoefficient (1,1,1)`、`referenceBone` = **同侧 `UpLeg` 的 GameObject**（不是 Transform）。

| 裙片 | limitMin | limitMax |
|---|---|---|
| `*FrontSkirt_A` | (−180,−180,−180) | (180, 40, 20) |
| `*FrontSideSkirt_A` | (−180,−180,−180) | (180, 50, 50) |
| `*BackSideSkirt_A` | (−180,−180,−78) | (180, 50, 83) |
| `*BackSkirt_A` | (−180,−180,−58) | (180, 60, 180) |

## 材质 / 颜色路径清查（同样 530 套全扫）

`tools/inventory_body_materials.py` → `reference/body-material-inventory.json`。
材质名只有三个：`m_bdy`(530 套) · `m_bdyco`(341) · `m_bdytrs`(21)。

### 贴图槽：4 张随服装 + 1 张随角色，530/530 全绑

| 槽 | 目标 | 随什么 | SDK |
|---|---|---|---|
| `_BaseMap` | `<本套>_bdy_col` | 服装 | ✅ |
| `_DefMap` | `<本套>_bdy_def` | 服装 | ✅ 改写 |
| `_ShadeMap` | `<本套>_bdy_sdw` | 服装 | ✅ 改写 |
| **`_RampAddMap`** | **`<本套>_bdy_rma`** | **服装** | ❌ **沿用被替换角色的** |
| `_RampMap` | `<本角色>-base-0000_rmp` | 角色 | 沿用（正确） |

`m_bdyco` 的 `_RampAddMap` 指向的是 **body 的** `<本套>_bdy_rma`，不是自己的一张。

`_bdy_rma` 是 **128×16 的 ramp 条**：16 行由顶点 COLOR 的 **G 低 nibble** 选，行内 128 px 是一条渐变。
hmsz-cstm-0059 的行编排（PIL 自上而下）：`(49,56,79)` 冷蓝 ×2 行 → 灰 ×3 → 灰 ×3 → 暖橙 ×3 →
深灰 ×3 → **纯黑 ×2**。UV 的 V=0 在底部，所以 **G_lo=0 取到的是纯黑那行 = 不加色**。

**这解释了 live / 撮影场景整体偏暗**：RampAdd 是加色项，弱光场景看不出差别，舞台光下占主导。
我们既没产出自己的 rma，cloth 的 COLOR 又取了不加色的那行 —— 双重缺失。

### 随服装变的标量 / 颜色（沿用即错，需作者产出）

| 属性 | 取值种数 | 主流值 | 少数值 |
|---|---|---|---|
| `_RampAddColor` | 10 | `(1,1,1,1)` ×498 | `(3.816, 3.199, 1.202, 1)` ×12 —— HDR 乘数 |
| `_DefValue` | 8 | `(0.5,0,1,0)` ×500 | `(0.5,0,0,0)` ×17 |
| `_Glossiness` / `_Smoothness` | 3 | 0.0 / 0.5 ×526 | |
| `_SrcBlend` / `_DstBlend` | 2 | 1 / 0 ×519 | 5 / 10 ×11（半透明款） |

其余 71 个 float、21 个 color 在 530 套里都是常量 → 沿用克隆材质安全。

## 顶点 COLOR 清查（第三轴，2026-08-14）

410/530 套读出（120 套的 mesh 数据在 UnityPy 下解不开，已记进 `missing`），共 706 万顶点。
字段语义见 `GakumasVertexColor`；下表是**顶点占比**。

| 字段 | 分布 | 说明 |
|---|---|---|
| rim（A 高位） | **9 → 65.9%**、0 → 31.4%，其余合计 2.7% | 只有两个主流档。24 套 hmsz 里 23 套的主值是 9 |
| 描边宽（B 低位） | 15 → 49.5%、0 → 22.1%（关描边），其余分散 | 字节写 15，不是 255 |
| LUT 行（G 低位） | 0 → 36.7%、3 → 16.4%、6 → 14.9%、9 → 11.8%、12 → 10.0%、15 → 9.5% | **只用 0/3/6/9/12/15 六行**，随服装 |
| 描边色（R 高/低、G 高） | 分散，逐服装art | 黑（全 0）是安全默认 |

最常见的单值是 `(81,0,15,144)`（占 8.0%，117 套的主值）—— 就是皮肤：描边(5,1,0)、LUT 0、宽 15、rim 9。

被替换那套 `hmsz-cstm-0059` 的真值（`libraries/assetstudio-body-json` 的 dump，逐 submesh）：

| submesh | 主值 | 解码 |
|---|---|---|
| 0（18918 顶点） | `(51,79,15,144)` 10.1% | 描边(3,3,4) LUT **15** 宽 15 **rim 9** |
| 0 | `(81,0,15,144)` 8.3% | 皮肤 |
| 1（522 顶点） | `(0,3,0,144)` 48.7% | 描边黑 LUT 3 宽 0 rim 9 |

→ 我们布料预设的 LUT 15 **是对的**（配的就是这套的 rma），rim 0 **是错的**（该 9）。已改，见 `SurfacePresets`。

## 摇物链结构真值（2026-08-14，UnityPy 直读 `all_body`）

| 事实 | 数据 |
|---|---|
| 每套 chain 数 | 3.0（518/530 套有） |
| 宿主骨 | **`Pelvis` 758 / 1537 实例**，其次 Spine2 86、Spine 82、`*UpLeg_H` 80+ |
| 每链 strand 数 | 4–8（裙子典型 8 = 八片裙摆） |
| 层结构 | **严格矩形**：每层骨数 = rootBones 数，无长短不齐 |
| 层 0 | 恒为 `active=0 around=0 radius=0.05`（锚定层，不动） |
| `around` | **每链一个选择，链内从不混用**：223 条有活动层的链中 138 条全 0、85 条全 1。**别按多数取 0** —— 实机试过，裙子/翅膀/摆带全炸；环是这里唯一约束横向位移的东西。按**被替换那套**取（0059 的裙链是 1） |
| **最后一层** | **就是 `_S_End` 尾骨**，`active=1`，半径最大 |

`hmsz-cstm-0059` 的裙链逐层实测：

```
层0 active=0 around=0 r=0.05  : RightBackSkirt1_S,     RightBackSideSkirt1_S,     ... (8 条)
层1 active=1 around=1 r=0.015 : RightBackSkirt2_S,     RightBackSideSkirt2_S,     ...
层2 active=1 around=1 r=0.02  : RightBackSkirt3_S,     ...
层3 active=1 around=1 r=0.03  : RightBackSkirt4_S,     ...
层4 active=1 around=1 r=0.04  : RightBackSkirt5_S_End, RightBackSideSkirt5_S_End, ...
```

由此改掉 `SwingRigger` 两处：① `IsSwing` 收 `_S_End`（原先排除 → 每片少一层活动层，单骨片直接一层不剩、完全不动）；
② 分组键从"直接父骨 + 深度"改成"类别 + 深度"、宿主取共同祖先（落在 Pelvis）——
原先每片裙摆各自成链、每链 1 条 strand，`around` 环形碰撞无邻居可依。

### 摇物骨的 `collisionMask`（60 套抽样，按类别）

| 类别 | 骨数 | 主流 mask | 次多 |
|---|---|---|---|
| skirt | 2493 | **1**（51%） | -1 13%、2 11%、64 9% |
| cloth | 466 | 64（48%） | 128 10%、-1 9% |
| ribbon | 700 | 256（28%） | -1 20%、64 19% |
| sleeve | 506 | 0（42%） | -1 19%、128 14% |
| skin | 672 | 0（63%） | -1 36% |

**`-1`（Everything）不是安全默认值。** 笼子里 `Hips` 是半径 **0.23 m** 的胶囊、通道 192(=64|128)；
原版裙摆骨用通道 1 碰不到它，而 -1 会碰到 —— 整条裙子被顶到离胯 23 cm 外，表现为"不贴大腿 + 僵硬"。
通道 1 对应的正是 `Pelvis` / `Leg` / `Foot` / `UpLeg` 这几个下半身碰撞体。

## 复现

```bash
python tools/inventory_body_components.py    # 组件轴，全 530 套，约 3 分钟
python tools/inventory_body_materials.py     # 材质/颜色轴，全 530 套
python tools/inventory_body_colors.py        # 顶点 COLOR 轴，410/530 套可读
python scratchpad/driver_tables.py                # 每宿主骨的 setting 真值
```

换游戏版本后应重跑：组件类的增减和字段布局都可能变。
