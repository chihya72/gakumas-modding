# AB 包路线 v2：完整记录

> 立档：2026-08-15
> 覆盖：AB 包路线与 Unity SDK 路线的对比、游戏侧逆向所得、v2 的修改计划与执行、遗留项
> 配套：[`ab-v2-plan.md`](ab-v2-plan.md) 是**工作计划**（不变量、变更协议、阶段清单）；
> 本文是**完整记录**（为什么这么定、探索过程、改了什么、还剩什么）。两份都要看的话，先看本文。
> 运行时自身的缺陷台账在 `gakumas-mod-runtime/docs/known-risks.md`（F/R/X/P 编号），本文不复制。
>
> **2026-08-15 复核**：本文与 `ab-v2-plan.md` 被独立评审
> （[`ab-sdk-independent-review-2026-08-15.md`](ab-sdk-independent-review-2026-08-15.md)）查出 4 处硬错、
> 若干措辞过强，已就地改正，见 [§10 本轮复核修正](#10-本轮复核修正2026-08-15)。
> **路线结论未变**（AB 仍是主线），变的是理由的准确度。

---

## 目录

1. [两条路线是什么](#1-两条路线是什么)
2. [游戏侧硬事实（逆向所得）](#2-游戏侧硬事实逆向所得)
3. [两条路线的完整对比](#3-两条路线的完整对比)（含 §3.6 **AB 的真实人工成本**）
4. [探索过程与被证伪的结论](#4-探索过程与被证伪的结论)
5. [v2 修改计划：为什么这么排](#5-v2-修改计划为什么这么排)
6. [改了什么（逐条 + 验证证据）](#6-改了什么逐条--验证证据)
7. [还有什么没做](#7-还有什么没做)
8. [实测数据附录](#8-实测数据附录)
9. [复现命令](#9-复现命令)
10. [本轮复核修正（2026-08-15）](#10-本轮复核修正2026-08-15)

---

## 1. 两条路线是什么

### 1.1 AB 包路线（native 补丁）

**不换 prefab。** 插件 hook `AssetBundle.LoadAsset`，把我们的 Mesh `set_sharedMesh` 塞回
**原版活体 renderer**；原 `bones[]`、原材质、原组件全部留着，只按 `mod.json` 逐槽换贴图。

```
[数据] geojson + bones sidecar + PNG + mod.json        ← 全部可无 Unity 产出
   ↓
[打包] tools/patch_unity_bundle.py 给 R32 模板打补丁    ← 作者侧不开 Unity
   ↓
[运行时] xinput1_3.dll hook AssetBundle.LoadAsset
         · 按【骨名】匹配 mod 骨 → 原 renderer 活体骨
         · mesh 落到【原 renderer】，保留原材质，只按属性换贴图
         · 缺失骨按 sidecar 运行时新建 GameObject + 组件
```

蒙皮公式：`skinnedV = Σ wᵢ · 学马活体骨ᵢ · mod_bindposeᵢ · v`

这个乘积**只自动解决比例**（把网格映射到目标骨长），**不解决静止姿势**：
`mod_bindposeᵢ` 就是源绑定时的姿势，源是 A-pose 就会带着 A-pose 的偏移进游戏。
早期笔记里"不需要 Blender 预烘对齐"那句的前提是**源与学马同 QualiArts 骨架、静止姿势本来就一致**
（IP 服装那种），对 MMD / 游戏 rip 不成立。

三条决定难度的事实（读插件源码得出）：

1. 插件按**骨名字符串**认骨（`BuildBoneNameIndexMap`），不看 `m_BoneNameHashes`。
   → bundle 里 prefab 的骨 Transform 只要名字对、顺序对，TRS 无所谓。
2. mesh 被 clone 后设到原 body 的 renderer 上，`replaceMaterials:false` 保留原材质。
3. 顶点**空间**（坐标系/原点）由插件的空间修正处理 → mesh 可以在自己空间里。
   **注意别把这条读成"姿势也不用对"** —— 它说的是坐标系，不是静止姿势。
   蒙皮公式里 `mod_bindposeᵢ` 编码的是**源模型绑定时的姿势**，
   源在 A-pose、目标静止在 T-pose，胳膊就整体差那个角度。**A→T 对齐照做不误。**

**Unity 版本 6000.0.67f1**（bundle 头写死，必须匹配游戏运行时）。

### 1.2 Unity SDK 路线

**换整个 prefab。** 我们自己的骨架、组件、材质，走游戏的 `BuildModel` 正常加载。
作者在 Unity 里（或由 `unity_route.py` 调无头 Unity）产出完整 prefab 再打包。

### 1.3 一个盘点时才发现的事

`gakumas_mi/unity_route.py` **已经存在**，就是"作者只开 Blender，背后调无头 Unity 完成学马那一侧
全部规矩"的桥。也就是说插件里**本来就有两条子路线，职责重叠**。这是 v2 "删繁就简" 的第一个靶子。

`unity_route.py` 自己写的分工判据是对的，v2 沿用：

> **改作者的东西（姿势、权重、贴图）留在 Blender，他看得见；改学马的东西留在自动化里，他不用管。**

---

## 2. 游戏侧硬事实（逆向所得）

两个来源：`il2cpp.cs` 签名 dump（`D:\GIT\gkms-localify-ios\workspace\3.2.3\inspector\cs\`）
与 IDA（`ida-pro-mcp`，`UnityFramework` 3.2.3，地址与 dump 1:1）。
**dump 只有签名没有方法体**，能给"有什么、要什么、字段叫什么、常量多少"，
给不了"具体怎么判" —— 后者靠 IDA。

### 2.1 模型加载全路径

```
CampusActorManager
└ CampusActorController : VLDefaultActorController<CampusActorModelParts, CampusActorDescriptor, …>
   │  ActorLoadAsync   b__71_2/5/6/7 —— 按 partsIndex 过滤 prefab
   ├→ VLActorController.BuildModel(IEnumerable<GameObject> resources)   ← hook 点①
   │     CheckResourceObjects(resources)
   │     每个 resource 实例化 → CampusActorModelParts.Initialize(partsId, assetName)
   │        └ VLActorModelParts.Initialize
   │             ProcessBones() → RegisterBone(Transform bone, int layer)
   │                            → OnRegisterBone(in string boneName, Transform bone)  ← 组件在这里被收
   │             UpdateSkinnedMeshRenderers()
   │             InitializeMaterials() → InitializeCampusMaterials()
   │                                   → AddCombinedOpaqueSubMesh(...)   不透明段合批
   │             ProcessSkinningBones(bones, aabbHashSet)
   │     CorrectSkeleton(partsId, instance)
   │     InitializeBones(BoneNameToTransformDictionary allBoneNameToTransformMap)  ← 跨部件按名字连骨
   │     UpdateRootBoneLinkList(...)
   ├→ BuildAvatar()                                                     ← hook 点②
   │     GetSkeleton(...) → SkeletonBone[]
   │     VLActorDefine.TryGetHumanBodyBone(name) → HumanBone[]
   │     VLActorDefine.IsValidHumanDescription()                        ← 必备骨闸门
   │     GetHumanDescription(human, skeleton) → AvatarBuilder
   └→ OnBuildModelSuccess() → OnBuildModelSuccessAsync(ct)
         InitializeExpression        b__80_0
         InitializeActorAnimation    b__81_0 … b__81_21   ← 22 个 SelectMany 合并各部件的 List
            → new CampusActorAnimationInitializeData(…35 个参数…)
            → CampusActorAnimation.Setup(rootTransform, initializeData)
            → CampusActorAnimationRig.RegisterBones(initialData)
            → CampusActorAnimationBuilder.Build(animator, graph, rig)
                 Job.CreateConstraint / CreateQuartzDriver / CreateFullBodyIK /
                 CreateSwingSkeleton / CreateRoot
                 每帧 ProcessAnimation → Constraint → QuartzDriver → SwingSkeleton →
                       FullBodyIK → LookAtLimit → JointLimit → Root
```

### 2.2 从签名 dump 读到的

| 事实 | 出处 |
|---|---|
| **组件不是 `GetComponentsInChildren` 收的**，是 `OnRegisterBone` 逐骨收进 `CampusActorModelParts` 的 22 个 `List<>` | `VLActorModelParts:988786-988789`、`CampusActorModelParts:91562-91585,91595` |
| **`TransformCapacity = 256`**、`RendererCapacity = 16` | `988744-988745` |
| 骨存进 `BoneNameToTransformDictionary _boneMap`，**按名字** | `988751` |
| body/face/hair 三部件靠 `InitializeBones(allBoneNameToTransformMap)` **按名字**互连 | `988790` |
| Humanoid 映射走游戏自己的 `boneToAvatarMap : Dictionary<string, HumanBodyBones>`，**不是 Unity 的自动映射器** | `987708,987721` |
| **QuartzDriver 一共 12 种** | `CampusActorAnimationInitializeData:90013-90024` |
| Shader 属性一共 **32 个** | `CampusActorShader.Property:91794-91826` |
| `ShaderType` 枚举 10 种（Opaque/Cutout/Transparent/EyeBase/Eye/EyeHighlight/FaceParts/FacialParts/Hair/Face） | `91777-91789` |
| 每种 Driver 都有 `*SimpleBone` 双胞胎（12 对） | `24349-25229` |
| 碰撞体 4 型：Sphere/Capsule/Line/Plane | `27408-27415` |
| `ActorSwingDynamicBone : IComparable<>` —— **顺序有语义** | `27447` |
| 不透明段会被**合批**：`AddCombinedOpaqueSubMesh` | `91593` |
| 运行时只碰 6 个 shader ID：`_BaseMap/_ShadeMap/_DefMap/_LayerWeight/_BaseMap_ST/_UseLastFramePositions` | `90604-90609` |
| 身体动画是**纯 humanoid muscle**（idle clip 130 条 binding 全 muscle，零 transform 曲线） | 早期 `scan_clip_bindings` |
| 游戏自带身高系统：`HeightCoefficient/CmmnHipsHeight/BaseHeight/MinHeight/MaxHeight` + `ApplyActorSwingCmmnHeightCorrection` | `90559-90563` |

### 2.3 从 IDA 读到的（10 次调用）

#### ① `IsValidHumanDescription()` —— 必备骨是 **19 根**，不是 Unity 的 15 根

| 函数 | 地址 | 结论 |
|---|---|---|
| `ClearRequiredDescriptionFlags` | `0x0A845FF4` | 分配 `bool[19]` 并清零 |
| `AddRequiredDescriptionFlag(hbb)` | `0x0A846130` | `arr[(int)hbb] = 1` —— **索引就是 `HumanBodyBones` 枚举值** |
| `IsValidHumanDescription()` | `0x0A846228` | 这 19 位的**全 AND**（向量化）；数组长 ≤0 时返回 true |

→ 必备集合 = `HumanBodyBones` **0–18**：
Hips / 双 UpperLeg / 双 LowerLeg / 双 Foot / Spine / **Chest** / **Neck** / Head /
**双 Shoulder** / 双 UpperArm / 双 LowerArm / 双 Hand。

**Unity 自己的必备集只有 15 根，不含 Chest、Neck、两个 Shoulder。这四根在本作是硬要求**，
缺一根 Avatar 无效 → 动画一帧都不播。

#### ② `VLActorDefine.IsBone(Transform)` —— 判据是"身上有没有 Renderer"

`0x0A845DF4`。**第一版我读成了"名字排除表"，是错的，已订正。**追进 helper：
`sub_46A55F8` = `GameObject.TryGetComponent(Type, out)`
（`sub_A3EDDCC` = `Component.get_gameObject`，`sub_A3F2EA8` = 注入的 TryGetComponent）。

```
IsBone(t) == !t.gameObject.TryGetComponent(<qword_D6AC9D8>, out _)
```

那个类型由 `RegisterBone` 反推出来：带它的节点被塞进 `v5[11]/v5[12]/v5[13]`，
按字段偏移正是 `renderers`(0x58) / `rendererGameObjects`(0x60) / `skinRenderers`(0x68)
→ **`qword_D6AC9D8` = `Renderer`**。

**一个 Transform 是"骨"当且仅当它身上没有 `Renderer`。**
可执行结论：**组件不能挂到带 Renderer 的节点上** —— 那不算骨，`OnRegisterBone` 永远不收它，
表现是"组件明明在包里却完全不生效"。

#### ③ `VLActorModelParts.RegisterBone(Transform, int layer)` —— 一次读出三个答案

`0x0A8840E0`：

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
2. **`layer` 参数就是 Unity 的 GameObject layer**（对上插件日志 `layer: 243 个节点设为 12`）。
3. **`TransformCapacity = 256` 是容量提示，不是硬上限** —— 全程没有对 256 的边界检查，
   列表靠 `List.Add` 扩容。**→ 闸门 G6 保持 warning 是对的，不该升成 error。**

#### ④ `ActorSwingChain.UpdateChainInfo()` —— 不是"会冲掉参数"，是"没预填才冲"

`0x1316A88`（`sub_1316A88`，0xa20 字节）。`this+32` = `rootBones`，`this+40` = `chains`；
它**重建**一份 ChainInfo 再赋回。沿链逐层：

- 老 `chains` 里**已有对应层** → `layer[16] = old[16]`、`*(u64*)(layer+20) = *(u64*)(old+20)`
  —— 即 **`active`(@16) 与 `radius`/`smoothing`(@20/@24) 原样继承**。
- 老 `chains` 里**没有** → 新层只写死 `*(u32*)(layer+20) = 1028443341`
  = `0x3D4CCCCD` = **float 0.05f**。

→ 坐实两件事：① 它**确实不计算** `radius`/`smoothing`；
② **只要 graft 时先把 `chains` 填好，它会原样保留我们的值** —— 这条对自建摇物链是可用路径，不是死路。

#### ⑤ 驱动器 `Calc()` 是纯标量连乘

`HumanoidArmBone.Calc` `0x01312B84`：

```c
float Calc(muscleValue, muscleConvertCoefficient, rotateCoefficient)
    { return muscleValue * muscleConvertCoefficient * rotateCoefficient; }
```

没有曲线、没有钳位 → setting 里的 `coefficient` 就是**线性增益**，
新部件的系数**可以推**（按目标幅度线性缩放），不是只能照抄原版。

#### ⑥ 没读的：`CorrectSkeleton(partsId, instance)`

在泛型 `VLActorController<TModelParts,TDescriptor,TIDescriptor>` 上，dump 里没有具体地址，
要先定位实例化后的具体方法。**非卡点**：AB 路线继承原版 prefab，这一步对我们透明。

### 2.4 12 种 QuartzDriver 的原版分布（530 套全扫，0 套读不出）

| Driver | 服装数 | 每套 | 宿主骨命名约定 |
|---|---|---|---|
| `Rotation` | 528 | 4.2 | `*ForeArm_H` `*Leg_H` + `*_Receive_A`(53) |
| `HumanoidHand` | 528 | 4.0 | `*ForeArm_Roll_H` `*Hand_H` |
| `HumanoidUpLeg` | 528 | 4.0 | `*UpLeg_H` `*UpLeg_Roll_H` |
| `HumanoidArm` | 528 | 4.0 | `*Arm_H` `*Arm_Roll_H` |
| `Skirt` | 379 | 8.1 | `*FrontSkirt_A` `*FrontSideSkirt_A` … |
| `Waist` | 230 | 2.0 | `LeftWaist_H` `RightWaist_H` |
| `Frill` | 78 | 3.7 | `*ArmCloth_Front_H` `*ArmCloth_Back_H` |
| `Poncho` | 39 | 3.4 | `*BackPoncho_H` `*FrontPoncho_H` |
| `LateRotationSimple` | 33 | 3.1 | `*Foot_H` `*ToeBase_H` |
| `HumanoidSleeveSimple` | 26 | 2.8 | `*Sleeve_Up_H` `*Sleeve_Down_H` |
| `Furisode` | 25 | 2.8 | `*FurisodeA_A` `*FurisodeB_A` |
| `HumanoidSleeve` | 9 | 4.0 | `*Sleeve_Up_H` `*Sleeve_Down_H` |

**宿主按命名约定认**：`*_H` = 挂 humanoid 骨的矫正，`*_A` = 衣物面板锚点。

**setting 是引用字段**（`public class ...Setting`，不是 struct），
`SetDefaultValues` 不建它 —— 和 `dynamicCollider`/`limitInfo` 一样得自己 new 完再写。
非 Simple 版的 `setting` 一律在组件的 **0x28**（Simple 版在 0x20）。

| Setting 类 | 实例字段偏移 |
|---|---|
| `HumanoidArm/Hand/UpLegSetting` | `humanPartDof` int **@0x10**，`coefficient` float **@0x14** |
| `RotationSetting` | `rotationOrder`@0x10，`limitMin`f3@0x14，`limitMax`f3@0x20，`coefficient`f3@0x2C，`connectionAxis`@0x38，`decomposeType`@0x3C，`composeType`@0x40，`referenceBone`**@0x48** |
| `SkirtSetting` | `rotationOrder`@0x10，`innerCoefficient`f3@0x14，`outerCoefficient`f3@0x20，`limitMin`f3@0x2C，`limitMax`f3@0x38，`connectionAxis`@0x44，`referenceBone`**@0x48** |
| `WaistSetting` | `weight`f@0x10，`referenceWaistOffsetBone`**@0x18**，`referenceThighOffsetBone`**@0x20** |

**关键：把 setting 里的对象引用解成骨名之后，可移植性一目了然**

| 驱动器 | 参考骨 | 能否装到任意目标 |
|---|---|---|
| `Skirt` | `Left/RightUpLeg`（1536 / 1525 次） | ✅ 通用身体骨 |
| `Frill` | `Left/RightArm` | ✅ |
| `HumanoidSleeve` | `Left/RightHand` | ✅ |
| `Waist` | `LeftWaist_O` / `LeftThigh_O` | ❌ 每套服装自己的偏移骨 |
| `Furisode` | `LeftFurisodeA_O`、`Spine`、`LeftHand`… | ❌ 四个引用里两个是 `*_O` |
| `Poncho` | `RightBackPoncho_move_in_O` … **六个引用全是 `*_O`** | ❌ |

后三种装到别的服装上只会得到一串空引用 —— 表现是"这块布不动"，**日志还全绿**。
所以 v2 **只支持前三种**。

---

## 3. 两条路线的完整对比

### 3.1 决定性差异：要满足的契约面

| 游戏侧要求 | AB 路线 | SDK 路线 |
|---|---|---|
| `CampusActorModelParts` 的 **22 个 `List<>`** | 原版的，原封不动 | 不用手工填 —— 但**必须提供让游戏能填满它们的对象/组件/引用** |
| **12 种 QuartzDriver** | 原版的，齐全 | 只做了 5 种 |
| `boneToAvatarMap` + `IsValidHumanDescription()`（19 根） | 原版骨名，必过 | 靠我们的骨名桥 |
| **`TransformCapacity = 256`** | 原版计数 + 少量新建骨 | SDK 侧已到 243，余量 13 |
| **32 个 shader 属性** | 原版材质，只覆盖 3 张贴图 | **也是克隆原版材质**再覆盖同样 3 张（见 §3.2 材质行） |
| `AddCombinedOpaqueSubMesh` 合批 | 原版路径 | 没碰过 |
| `_boneMap` / 跨部件 `InitializeBones` 按名字 | 原版名字，天然不撞 | MMD 自动名/`HAIR`/`目.L` 全带进来 |
| `initialTransforms` ↔ `swingDynamicBones` 并行表 | 原版同步构建 | 我们构建 |
| `decalProjectors` | 原版的 | 空 |

**AB 大量继承游戏对象侧契约；SDK 必须重新提供让游戏重建这些契约的对象、组件和引用。**
这不是"哪条做得好"，是结构性的。

> ⚠️ 早前写的是"AB 要满足的项数 ≈ 0"。**这句只在"原 prefab 已存在的游戏对象侧组件与初始化关系"
> 这个严格限定下才近似成立**。AB 自己仍要满足一整套内容侧契约：mesh 坐标空间、骨名/骨序/parentIndex、
> bindpose 与 renderer 空间、boneWeights 索引范围、submesh↔材质槽、COLOR/UV/法线/切线语义、
> sidecar 与运行时协议、新骨上 driver/swing/collider 的互斥与引用完整性。别把"≈0"读成"没有契约"。

### 3.2 逐项对比

| | AB 包路线 | SDK 路线 |
|---|---|---|
| **骨架** | 原版骨架 + **运行时任意新建骨**（已画面级跑通） | 模型自己的 |
| **网格** | **UV/COLOR/submesh 不碰**；顶点/法线/切线**每次都会被运行时变换到原 renderer 空间**（`ModRuntime.cpp:3048-3088`，无 identity 快路径），bindpose 另乘空间修正 | T-pose 烘焙**会重写顶点和 bindpose** |
| **权重** | **不做破坏性重分配**（插件只 remap 骨序，不丢合法的四权重数据） | 矫正骨**搬走 6.3%、截断 184 顶点** |
| **动画** | 原版编舞，`活体骨ᵢ × mod_bindposeᵢ` 自动 retarget 到学马体型 | 原版 muscle 驱动我们的骨架 |
| **比例 / 骨长映射** | 数学上自动（`活体骨ᵢ × mod_bindposeᵢ`）。**但这不等于工作量免费** —— 衣服合不合身、有没有穿模，仍然全是手工，见 §3.6 | 我们的骨长，同样要自己对 |
| **静止姿势对齐（A→T）** | ⚠️ **2026-08-16 收紧**：源 rest 只通过 bindpose 参与重定向，Avatar 是游戏自己的 —— 「整体差那个角度」对当前 lossless 路径**未经证明**，G10 的前提同样未证明。真实风险是大角度 A→T 的**混合带塌陷**，不是全局角度残差。见 [`ab-author-cost-reduction-2026-08-16.md` §2/§3](ab-author-cost-reduction-2026-08-16.md) | 同样不免费；且我们的静止姿势就是 muscle 零点，必须≈原版（**这条对 SDK 成立**，因为 Avatar 是拿源骨架建的） |
| **物理** | 复用原版骨=免费；自建骨=运行时建 + 手调 | 组件离线挂好，但 12 种驱动只做 5 种 |
| **材质** | 复用**当前场景活体**材质，逐槽换贴图 —— shader、共享 ramp、逐场景绑定天然对；**服装专属参数拿到的是宿主那件的值，不是新服装的**（见 §3.7） | 克隆**原版模板**材质再搬同样 3 张贴图，其余 29 项同样继承 —— 与 AB 同机制，差别只在克隆时机（冻结 vs 活体） |
| **作者要装 Unity** | ❌ 不用 | ✅ 要（约 6GB） |
| **需要运行时插件** | ✅ 必须 | ✅ 也要 |
| **新组件类型** | 只能运行时 `il2cpp_object_new` | Unity 里直接挂 |
| **换脸/换发** | 已跑通（发型、发饰独立路线） | 没做 |
| **透明件** | 只有原生 `m_bdyco` 一条路，且实测是 cutout | 没碰过 |
| **游戏对象侧契约** | 大量继承（原 prefab / 原 `CampusActorModelParts` / 原初始化时序 / 原骨组件） | 必须重新提供对象、组件和引用，让游戏自己重建 |
| **内容侧契约** | **两条一样多**：坐标空间、骨序、bindpose、权重、submesh↔材质、COLOR/UV 语义 | 同左 |

### 3.3 一个我立错又推翻的对比轴

我曾把差异表述成"AB 只能用原版骨架 / SDK 能用任意骨架"。**这是错的。**

- AB 路线**已经能任意建骨**（`ModRuntime.cpp` 有 `SkinnedMeshRenderer_set_bones`、
  `Transform_SetParent`、`il2cpp_object_new`；2026-08-11 fuyuko 飘带画面级跑通）。
  "固定 146 根" 是插件早期 "没同名就 fallback Hips" 时代的描述，早就不是现状。
- 真正受限的是**被动画驱动的那部分**，而且**对两条路线一视同仁**：
  身体动画是纯 humanoid muscle → muscle 要 Avatar → Avatar 按 `boneToAvatarMap` 用**名字**建。
  所以任何骨要拿到身体动画，就必须叫游戏认识的名字。
  SDK 路线的"自建骨架"最后也得过 `HumanoidBridge` 改名成 `Hips`/`Spine`/`LeftArm`。

**修正后 SDK 真正独占的只剩三条**，而且都在缩水：

1. **humanoid 关节之间插骨**（如给只有两节脊椎的 MMD 补 `Spine2`）
   —— AB 应该也能做，**没验过**（见 P4-E）。
2. **比例 / 骨长** —— AB 强制学马体型。但游戏自带身高系统，跟它对着干得不偿失，
   **这个自由度多半不该要**。
3. **离线挂任意组件** —— 真实，但运行时已经证明能建那些真正要紧的类型。

→ 若 P4-E 验通，**SDK 路线的必要性可能归零**。

### 3.6 AB 路线的真实人工成本（`mod-workspace` 实测）

**这一节是为了纠正上表可能给人的错觉。**"契约面 ≈ 0" 说的是**我们不用重建游戏侧那套东西**，
**不是**"做一个 mod 很省事"。模型侧的调整对齐是巨大工作量，AB 路线一点没省。

2026-08-15 盘点 `mod-workspace/`：

| 证据 | 数字 |
|---|---|
| workspace 总体积 | **26.6 GB** |
| 8 个工作项目的 blend / 工作文件 | **1.2 GB** |
| 最重的单项（chisaki 泳装） | 工作目录 **461 MB**、`authoring.blend` **102.7 MB**、41 个文件 |
| dress-2219 | **104 个文件**、198 MB |
| `backups/blend-originals` 已归档条目 | **9 条**（B005/007/010/015/019/027/036/053/054）—— `B054` 是**编号不是数量** |
| 最终成品 | **7 个** |
| 整体废弃的项目 | 2 个（`rui-nurs-hmsz-0000`、`hair-21-hmsz-mod`） |
| 收敛掉的并行候选 | mltd-stage 的 B053/B054；Miku 的 `ab-aligned` / `weighted` 两条路线 |
| 发布后返工 | 2 轮（`backups/release-fixes/`） |

> **9 个已归档原始/候选 blend → 7 个最终 authoring blend。**
>
> ~~54 个候选 → 7 个成品~~ —— **这是本文出过的最硬的一个错**：我把目录里最大的编号 `B054`
> 当成了数量，`ls | wc -l` 一次就能证伪，而上一行的证据自己写的就是"编号跨度"。
> 如果确实存在过 54 个候选，需要补目录清单或迁移记录，不能靠编号推。

每个成品都要过 `manual-validation.md` 的 8 条回归标准，**每一条都要人眼看**：

- 主模型朝向、原点、缩放和**镜像**合理，骨架与网格关系清楚
- **蒙皮姿态、关节弯曲**、裙摆/头发/饰品等高风险区域没有明显破面或飞点
- 材质槽对应正确，贴图实际显示，透明材质与普通材质没有混用
- 打包贴图可用；旧外部路径不成为导出的必要条件
- 要作为成品来源，**另做一次目标格式导出和游戏实测**

所以两条路线在"模型侧"的成本是**同一个量级**，差别只在"游戏侧契约"：

| | 模型侧（作者的活） | 游戏侧（契约） |
|---|---|---|
| AB | **巨大**：镜像、A→T retarget、合身、权重、破面、材质、透明、反复试错 | 大量继承原版对象侧状态 |
| SDK | **同样巨大**，且额外要满足 Humanoid 规矩 | 要重新提供对象/组件/引用，让游戏重建 22 列表；12 驱动只做了 5 种；19 必备骨、256 预算自己负责 |

**AB 相对 SDK 省下来的是"游戏侧"那一栏，不是"模型侧"那一栏。**
把它读成"AB 做 mod 更轻松"是误读 —— 我在早期版本的对比表里就是这么写的，是错的。

> ⚠️ "模型侧同一量级"是**工程判断，不是统计结论**。现有证据只证明了 AB 侧的模型成本很高，
> 没有做过"同一模型、同一验收目标"下 AB/SDK 的受控工时对比。同理，"AB 5 个成品 / SDK 2 个 / MMD 0 个"
> 说明的是**当前 AB 工具链的项目经验更丰富**，不能推出两条路线的理论成功率 —— 模型难度、
> 时间投入、实现成熟度都没有控制。

---

### 3.7 材质：两条路线共有的缺口（服装专属参数）

**本文原先写"AB 复用原版材质所以 32 个属性全对"，这句是错的。** 正确的分层是三层：

| 层 | 内容 | 谁负责 | 现状 |
|---|---|---|---|
| 游戏/角色**公共**状态 | shader、共享 ramp、公共 float | 从当前活体材质继承 | ✅ 天然对 |
| **逐场景动态绑定** | `_RampMap`/`_RampAddMap` 的场景侧覆盖 | 必须每次从当前场景模板取，**不得提前冻结** | ✅ AB 用活体材质天然避开；SDK 踩过（撮影皮肤全黑） |
| **服装专属**状态 | 见下表 | **无人负责** | ❌ 缺口 |

服装专属、530 套扫描证实随服装变化的项：

- `_RampAddMap`（服装专属的 `*_bdy_rma`）
- `_RampAddColor`
- `_DefValue`
- `_Glossiness` / `_Smoothness`
- `_SrcBlend` / `_DstBlend`、alpha test/cutout 对应参数

**后果**：把 A 服装的 mesh 塞进 B 服装的宿主 renderer，这些项拿到的是 **B 的值**，不是 A 的。
AB 和 SDK 都一样，只覆盖 Base/Def/Shade 三张贴图救不了。

**待办**：manifest 支持显式覆盖这几项 + audit 出一条"mod 服装与宿主服装这 6 项不一致"的 warning。
在做出来之前，这是一条**已知会影响画面、但目前静默**的缺口。

---

### 3.4 战绩（事实，带日期）

**AB 路线**：千咲 MMD 泳装、大国主→`fktn-othr-0002`、fuyuko 飘带自建摇物（画面级，2026-08-11）、
21 号波波头发型、发饰更换 —— **5 个实机成品**；rui-nurs→hmsz-0000 数据侧跑通。

**SDK 路线**：IP 服装装到学马身上（2026-08-13，剩顶点 COLOR 拍平导致肤色偏灰）、
原神 rip 实机通过；**kth_qinye MMD 三次进游戏全失败**（两次画面错、一次 loading 崩）。

值得单说：**MMD 这一类模型，AB 路线已经出过成品了**（千咲）。
kth_qinye 走 SDK 路线，7 个洞里至少 5 个在 AB 上根本不会出现。

### 3.5 v2 的分工决定

- **native 补丁是主线。**所有"能在原版宿主上做的"都走它。
- **`unity_route` 降为逃生舱**，只在 native 结构上做不到时启用。
  目前唯一确认做不到的是关节间插骨 —— 而这一条**尚未验证**。

---

## 4. 探索过程与被证伪的结论

按时间顺序，含我自己犯的错。**这一节是本文最该留的部分** —— 结论会过时，踩坑的方式不会。

### 4.1 起因：kth_qinye（MMD）走 SDK 路线，肩肘关节坏、颜色阴影错

作者报了两张截图。查下来两个根因：

1. **关节**：上一轮我把 `stockJointRig` 关掉了，理由是"收益只在扭转，且已由扭转骨认领拿到"。
   那个结论是在**原版服装**上量的，原版权重本来就好。三方对照（上臂扭转 67°）：

   | | 最严重塌陷 |
   |---|---|
   | 只认领 MMD 自己的 腕捩/手捩 | **−12.1%** |
   | 开 `stockJointRig` 合成 16 根 | **−4.6%** |
   | 原版 atbm-0140 | −3.3% |

   而且 `ForeArm_H`/`Leg_H`（肘膝半角）根本不在认领表里，认领路线永远补不上肘膝。

2. **颜色/阴影**：`TextureRewriter` 用 `*_bdy_sdw*.png` 去**共享目录**里 glob 找 t4，
   匹配到了上一个实验模型（`mdl_chr_bad_scale`）留下的 sdw，然后就地改写它 ——
   **日志照样打「t4 已改写」**。6 个槽里 5 个在用别的模型的阴影贴图。

修完 1 之后引入了新崩溃：`TwistAdopter`（按角色认领）和 `QuartzDriverRigger`（按骨名查）
摸到同一根骨 → 12 根 `*_H` 各挂 2 个驱动器（24 个，原版 16 个）→ 走到 `BuildAvatar` 就停。

**这一串是 v2 全部不变量的来源。**

### 4.2 被证伪的结论清单

| # | 我曾经的结论 | 怎么被推翻 | 现在的结论 |
|---|---|---|---|
| 1 | `stockJointRig` 该默认关，认领就够了 | 在 rip 上量出 −12.1% vs 原版 −3.3% | 外部模型默认应该开；认领只适合本来就按本作 rig 布骨的源 |
| 2 | `*_H` 承重下限 8%（依据"原版 ~17%"） | 实测 49 套原版 min **6.02%**，8% 会误报 13 套（27%） | 下限 4%，硬错误只留"恰好为 0"；17% 来自另一种分母，不能复用 |
| 3 | bindpose 闸门：所有承重骨共享同一个空间校正 | 拿**原版自己的** bindpose 反证：原样中位 261mm、转置中位 6.7mm 但最大仍 748mm | **前提本身错**（bindpose 编码的是绑定时姿势，与当前静止姿势不必相等）；整条撤掉 |
| 4 | `IsBone` 是按名字的排除表 | 追进 `sub_46A55F8` = `TryGetComponent(Type,out)` | `IsBone(t) = !t.gameObject.有Renderer` |
| 5 | AB 骨架固定 146 根 | 读 `ModRuntime.cpp`：`set_bones` + `il2cpp_object_new` 俱在，且 fuyuko 已画面级跑通 | AB 能任意建骨；受限的是"能不能拿到 muscle" |
| 6 | AB / SDK 的差异是"原版骨架 vs 任意骨架" | 见 §3.3 | 差异是契约面，不是骨架自由度 |
| 7 | P3a（humanoid 肢体驱动器）也要在 AB 上做 | 原版 prefab 自带 24 根驱动器骨 | AB 上取消；缺的只是权重 |
| 8 | `TPoseBaker` 是可移植资产 | 只覆盖 28 根骨的瞄准表 + 单样本标定的滚转常量，Shoulder/Spine/Neck/Head/Foot 全不碰 | 变换外包给 CATS/ARP，我们只留尺子 |
| 9 | `UpdateChainInfo` 会冲掉参数 | IDA 读出：老层存在就继承，不存在才写 0.05f | 只要 graft 时预填 `chains`，值会活下来 |
| 10 | `TransformCapacity=256` 可能是硬上限 | `RegisterBone` 全程没有 256 的边界检查 | 是容量提示；G6 保持 warning |

### 4.3 关于"能不能万能"

用可证伪的方式问过一次：拿第三个模型跑一遍，数管线级问题有多少。
**实际数出来 7 个，不是接近零。**其中 2 个是**静默的**（日志说做了、实际没做）。

诚实的划分：

- **代码级万能**：接近成立。三个模型没有一行"为这个模型写的代码"，
  7 个洞全是格式/约定/作用域这类一次性问题。
- **配置级万能**：不成立。`job.json` 里的网格名、丢哪些材质槽、每段 skin/cloth
  是量出来的，成本只是从作者转移到了开发者。
- **验证级万能**：完全不成立，**这是真正的瓶颈**。静默洞离线看不见，
  第 5 个（贴图串包）是靠 grep 游戏运行日志的贴图名才发现的。

所以 v2 的排序依据是：
> **任何"可能引入新错误"的改动，必须排在"能发现新错误"的改动之后。**

---

## 5. v2 修改计划：为什么这么排

### 5.1 目标（按优先级）

1. **排除错误** —— 删掉已证伪结论留下的代码与 UI，修掉已定位未修的缺陷。
2. **更新功能** —— 把 SDK 上量出来的搬进 AB：矫正骨权重、姿势驱动器、闸门套件。
3. **删繁就简** —— native / `unity_route` 两条子路线职责划清。

### 5.2 非目标

- 不追求"衣物物理全自动分类"。目标是**让调的成本降下来**。
- 不追求"任意骨架"（§3.3 已说明为何这是伪命题）。
- 不改比例/身高（游戏自带身高系统）。
- 不重写 `unity_route` 里已跑通的部分。

### 5.3 十条不变量（每条都来自真实事故）

| ID | 不变量 | 来源事故 |
|---|---|---|
| INV-1 | **一根骨只能有一个写它的求解器** | 双驱动器 → loading 崩；静态碰撞体挂 `_H` → 硬崩 |
| INV-2 | 不得向 `CampusActorAnimationInitializeData` 的并行表追加 | `RegisterBones` 越界夭折，日志全绿 |
| INV-3 | 节点数预算 **warning**（超 256 报复杂度风险，**不阻止出包**） | SDK 侧已到 243。`RegisterBone` 全程没有 256 边界检查，内部列表会正常扩容 —— 早前把它写成硬不变量，与 §4.2 #3 和 G6 自相矛盾 |
| INV-4 | 骨名在 body+face+hair 合集内唯一 | 重名整根骨被跳过，组件收不到 |
| INV-5 | bindpose 与骨架自洽，且在 renderer 空间比较 | 闸门曾假设 renderer 是单位阵 |
| INV-6 | **日志所述 = 实际所做** | 材质命名、贴图串包两次都是日志说谎 |
| INV-7 | 破坏性改写必须 per-job 开关、默认关、report 量化 | "只做加法"契约已破两次 |
| INV-8 | **闸门必须双向验证：坏包会报 + 原版不报** | 只验一半 = 假安全 |
| INV-9 | 一次只改一个变量 | 混变量 → 无法归因 |
| INV-10 | 共享容器必须按模型限定作用域 | 贴图目录跨模型串包 |

### 5.4 变更协议

**前置**：① 新存在性检查（这个改动让什么名字/类型开始存在？grep 所有按名字查找的地方）
② 共享容器检查 ③ 归属检查（改作者的还是学马的）④ 删除确认（再验一次真没用）
⑤ 不变量点名。

**后置**：① 闸门双向验证 ② 日志复验 ③ 原版不回归 ④ 回滚路径 ⑤ 单变量确认。

---

## 6. 改了什么（逐条 + 验证证据）

### 6.1 P0 —— 闸门套件（零产物风险，必须最先）

| 闸门 | 判据 | 坏包会报 | 原版不报 |
|---|---|---|---|
| **G1** `*_H` 承重 | 硬错误=恰好 0；warning<4% | 6 个成品中 4 个是 **0.00%** | **49 套误报 0** |
| **G2** 跨关节混合带 | 与**被替换的那一件**逐关节比，<40% 报 | madoka 双肩 4.5%（原版 16.5%） | **22 套自比误报 0** |
| **G3** 一骨一驱动器 | 原版 16 个在 16 根不同骨上 | 造的违规 sidecar 报了 | 4 个成品全不报 |
| **G4** 摇物/驱动器/碰撞体互斥 | 原版 327 个裙摆驱动器零重叠 | 同上，3 条全中 | 同上 |
| **G5** 骨名唯一 | `_boneMap` 重名整根被跳过 | — | 全不报 |
| **G6** 节点数 ≤ 256 | `TransformCapacity`（warning） | — | 全不报 |
| **G8** 顶点 COLOR 语义 | **纯白顶点 = 0**（22 套原版实测 0 个） | 造的全白包会报 | 4 个成品全不报 |
| **G10** 绑定姿势偏差 | 与目标静止姿势比，≥15° 报 | 扰动 bindpose 后报 **33.8°** | 成品全 **0.0°** |
| **G11** 19 根 Avatar 必备骨 | `HumanBodyBones` 0–18 存在性 | 造的缺 3 根会报 | 6 个成品全不报 |
| ~~G7~~ | ~~bindpose 空间校正~~ | **已证伪撤除**（见 §4.2 #3） | — |
| ~~G9~~ | ~~贴图归属~~ | **不适用 AB**（贴图由 mod.json 显式声明，无隐式查找） | — |

**阈值策略的转变**：`*_H` 那次标定错之后，能和"被替换的那一件原版"逐项比就不用总体阈值。
G2 就是这么做的 —— 这类错误从此不可能再犯。

**顺带修掉一个静默洞**：`vanilla_body.resolve()` 早期版本名字为空时会 glob 成 `*`，
**静默拿库里第一套 body 当对照**，报告照样打印得像模像样。已改成硬失败（空名字或匹配数 ≠ 1）。

### 6.2 P1 —— 矫正骨权重（拆成 a/b，这是动手时才看清的）

**P1a 换落点（非破坏性）** —— 源模型**自带**捩骨时（MMD `腕捩/手捩`、原神 `+UpperArmTwist`，
多数 rip 都有），把映射目标从 `LeftArm` 改成 `LeftArm_Roll_H`，权重自然落到矫正骨上。
**作者的权重数值一个都没动**，不触碰 INV-7、不需要开关。

实现：预设表的值现在可以是**按优先级排的候选列表**（`core._resolve_preset_value`），
16 条捩骨规则改成 `["LeftArm_Roll_H", "LeftArm"]`。目标骨架没有 `*_Roll_H` 时退回 humanoid 骨
—— **绝不能让它掉进 `unmapped` 把权重丢掉**，这是改这版时差点造出来的新洞
（`mapped_name` 原本要求 `candidate in target`，直接写死 `*_Roll_H` 会让整根骨消失）。

**P1b 重分配（破坏性）** —— 源模型**没有**捩骨时才需要。剖面来自 `measure_helper_rig.py`
（1060 条肢体中位数），与 SDK 侧 `HelperBoneRigger.cs` 同一张表。默认试跑，`--write` 才落盘。

实测（chisaki-swimsuit）：`*_H` 承重 **0.00% → 17.85%**（原版范围 6.02–21.00%），
权重和无异常，4329 个顶点因超过 4 骨被截断（已报数）。

### 6.3 P2 —— 静止姿势（变换外包，我们只出尺子）

不写 retarget（`TPoseBaker` 已被证伪为不通用）。作者侧用 CATS `Pose → Rest Pose` / Auto-Rig Pro。
我们出 **G10**：由 bindpose 反推的肢体方向 vs 目标静止方向。

**判据在原版上标定过**：原版 atbm-0140 逐根 **0.00°**。
前提是矩阵按**转置**读 —— 导出的 `M<行><列>` 名字是转置过的，原样读会退化成无效向量。
（这也坐实了旧笔记里"AssetStudio 的 bindpose 名字转置了"那一句。）

### 6.4 P3 —— 姿势驱动器

**范围修正（前置-1 检查的产物，动手前抓到）**：
**P3a 在 AB 上不需要做** —— 原版 prefab 自带那 16 个驱动器。缺的只是权重（P1）。
我原先把 SDK 的缺口直接搬过来，是错的。

**运行时侧**（`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`）：

- `LocalQuartzDriver` + `parseDriver`：sidecar 的骨记录多一个 `driver` 字段。
- `AttachQuartzDriver`：按类名建组件、`EnsureReferenceField` 建 setting、**按字段名**写值。
- `GetComponentByClass` + `FindMethodByArgType`：INV-1 闸门。

两个设计决定：

1. **字段按名字写，不按偏移。**12 种 setting 各有各的字段，硬编码偏移等于把 il2cpp 布局
   钉死在运行时里，游戏一更新就集体错位。类型不靠猜 —— sidecar 分
   `ints`/`floats`/`vectors`/`bones` 四张表明说（JSON 的 `0` 既可能是枚举也可能是浮点，
   按形状猜会把 `rotationOrder` 写成浮点，而且这种错在日志里看不出来）。
2. **摇物与驱动器二选一。**`createBone` 原本**无条件**给每根新骨挂 `ActorSwingDynamicBone`，
   所以 INV-1 闸门会把驱动器全挡掉 —— 接线时才暴露。依据是原版 327 个裙摆驱动器与
   ActorSwing 零重叠。

**导出器侧**：`tools/scan_vanilla_drivers.py` 扫 530 套产出 `gakumas_mi/driver_presets.json`
（标量取**众数**不取平均 —— `rotationOrder` 是枚举，平均出来的 0.37 是个不存在的值）。
`core.build_driver_block(category, side)` + 策略枚举 `native_driver` + UI 放开。

**只支持 Skirt / Frill / HumanoidSleeve**，理由见 §2.4 的参考骨表。

**默认不改变任何现有行为**：`driver_categories` 空集时完全不走这条路径，现有成品重导逐字节一样。

### 6.5 P5 —— IDA（10 次调用，6 问答 5）

见 §2.3。产出两条直接改了代码的结论：G11（19 根必备骨）、G6 保持 warning。

### 6.6 复审时查出的 3 个缺口（含我自己引入的新 bug）

| # | 缺口 | 严重度 | 已修 |
|---|---|---|---|
| 1 | **P3 导出器根本接不通** —— `driver_categories` 没有任何调用方，整个功能对作者不可达，我却报成"完成" | 高 | 策略枚举 `native_driver` + `_form_driver_categories` + 真正传参 + UI 放开 |
| 2 | **G8 从头到尾没做，汇总里也没提** | 中 | 已实现并双向验证 |
| 3 | **`GetComponentByClass` 可能拿错重载** —— `FindMethodByNameAndArgCount` 只比参数个数，而 `GetComponent` 有 `(Type)`/`(string)` 两个单参重载；这是 INV-1 闸门的判据，**静默失效的闸门比没有闸门更糟** | 高（我引入的） | 新增 `FindMethodByArgType` 按参数类型名匹配；解析失败时**返回"已占用"而非 nullptr**（fail-closed） |

**一个反复出现的信号**：`test_verify_ab_package_passes_minimal_contract` 这份 fixture
被**三条不同闸门先后打回**（缺矫正骨权重 → 缺 5 根必备骨 → 顶点色纯白）。
三次都不是误报 —— 那份"最小契约"一直在描述一个**进游戏跑不起来的包**。
每次都补齐 fixture 而不是放宽闸门，理由写在测试注释里。

### 6.7 文件清单

**新增**（`gakumas-modding`）

| 文件 | 行数 | 作用 |
|---|---|---|
| `tools/vanilla_body.py` | 149 | 读原版 body 的骨架拓扑/静止变换/每骨组件 |
| `tools/audit_ab_rig.py` | 300 | G2/G3/G4/G10（对照原版） |
| `tools/redistribute_helper_weights.py` | 158 | P1b 权重重分配（默认试跑） |
| `tools/scan_vanilla_drivers.py` | 163 | 扫 530 套产出驱动器预设 |
| `gakumas_mi/driver_presets.json` | — | 12 种驱动器 setting 基准 |
| `reference/vanilla-driver-presets.json` | — | 扫描全量结果（查证用） |
| `tests/test_driver_blocks.py` | 59 | P3 导出器单测 |
| `tests/test_helper_weight_redistribution.py` | 74 | P1b 单测 |
| `research/ab-v2-plan.md` | 642 | 工作计划 |
| `research/ab-route-v2-full-record.md` | 本文 | 完整记录 |

**修改**

| 文件 | 改了什么 |
|---|---|
| `tools/verify_ab_package.py` | +G1 +G5 +G6 +G8 +G11 |
| `gakumas_mi/core.py` | `_resolve_preset_value` / `load_driver_presets` / `build_driver_block` / `bone_side` / `build_source_extra_bones(driver_categories=)` |
| `gakumas_mi/bone_remap_presets.json` | 16 条捩骨规则 → 候选列表 |
| `gakumas_mi/operators.py` | 策略枚举 `native_driver`、`_form_driver_categories`、传参 |
| `gakumas_mi/ui.py` | 部件类型下拉对 `native_driver` 放开 |
| `tests/test_bundle_source_contract.py` | +2 个捩骨用例 |
| `tests/test_verify_ab_package.py` | fixture 补齐（三次） |
| `gakumas-mod-runtime/src/runtime/ModRuntime.cpp` | `LocalQuartzDriver` / `parseDriver` / `AttachQuartzDriver` / `GetComponentByClass` / `FindMethodByArgType` / `createBone` 二选一 |

**验证**：`xinput1_3.dll` 构建通过 · C++ 测试 2/2 · Python **60/60**

---

## 7. 还有什么没做

### 7.1 只能实机做的

| 项 | 为什么重要 |
|---|---|
| **P4-E：关节间插骨实验** | 在 `Spine1` 与 `{LeftShoulder, Neck, RightShoulder}` 之间插一个保世界变换的节点，看角色能否正常初始化并播动画。**这个结果决定 `unity_route` 还有没有存在必要**（§3.3） |
| **P1a 实际抬升多少** | geojson 只有最终骨序，无法从已导出成品反推，**必须从 .blend 重导一次**才能量 |
| **`native_driver` 端到端** | 单测覆盖了 `build_driver_block`，但从 Blender 点按钮 → sidecar 落盘 → 运行时装配这条链**一次都没跑过真实数据** |

> **P3 现在是"代码通、单测通、构建通"，但没有一个真实的包走过这条路。**

### 7.2 需要你点头的

**删除候选 D1–D6 全部没执行** —— 变更协议前置-4 要求"删之前再验一次它真的没用"，
而且牵涉作者现有工作流。删东西的账我不替你签。

| ID | 对象 | 依据 | 建议处置 |
|---|---|---|---|
| D1 | 摆动**幅度调参** UI 与参数 | 2026-08-11 负结果：五参数只动 ±35% | 删 UI，保留字段（sidecar 兼容） |
| D2 | **自动关节对齐** | 两次都产废品 | 删，保留 `report_joint_alignment` 尺子 |
| D3 | `integrate` → `new_source_chain` | 7 个成品里计数 **0**，一次没被走过 | **不删**（fuyuko 是画面级成功样本），改为默认不推荐、UI 降级 |
| D4 | "option A：bundle 授权原生组件" 残留 | 笔记已标注"已不需要" | 删 |
| D5 | 按名字猜链语义的兜底 | 已证伪（`lace` 可能在靴口） | 删猜测，保留显式声明 + 几何判据 |
| D6 | `patch_unity_bundle.py` 的合成对象内嵌路径 | 内嵌 = Unity 6 加载崩 | 确认已删干净 |

### 7.3 非卡点的遗留

| 项 | 状态 |
|---|---|
| `CorrectSkeleton(partsId, instance)` | 泛型方法，dump 无具体地址；AB 继承原版 prefab，对我们透明 |
| `IsBone` 排除表的**具体类型确认** | 已由 `RegisterBone` 反推为 `Renderer`，但没有直接从 metadata 验字符串 |
| **`AddComponentByClass` 的重载隐患** | 用的还是只比个数的旧 helper。生产里一直工作 = 当前解析顺序恰好正确，但这是**碰运气**。建议后续统一换成 `FindMethodByArgType`，**我没动它因为怕回归** |
| P4 的 Blender 可视化 / report 明说"这条不确定" | 需要 UI 工作 + 实机对照才知道有没有用 |
| 12 种驱动器里的 Waist/Furisode/Poncho | 参考骨是每套服装自己的 `*_O`，**结构上不可移植**，除非连 `*_O` 一起建 |
| `unity_route` 与 native 的最终合并 | 等 P4-E 结果 |

### 7.4 我不打算做的（明确放弃）

- **衣物物理的自动语义分类**（裙 vs 缎带 vs 披挂）。目标是让调的成本降下来，不是猜得更准。
- **改身高/比例**去对抗游戏自带的身高系统。
- **自己写 A→T retarget**。外包给成熟工具，我们只出尺子。

---

## 8. 实测数据附录

### 8.1 `*_H` 矫正骨承重（49 套原版）

```
min 6.02% (amao-cstm-0062) · P5 7.43% · 中位 11.28% · max 21.00% (atbm-othr-0002)
低于 8% 的 13 套（27%）  低于 4% 的 0 套  等于 0 的 0 套
```

→ 闸门下限 **4%**，硬错误只留"恰好为 0"。
**"17%" 来自 `measure_helper_rig.py` 的另一种分母，换场景不能复用。**

已出货成品：chisaki / daikokushu / hmsz-fuyuko / mltd-stage 全是 **0.00%**；
madoka 8.88%、miku 有权重（正确不报）。

### 8.2 跨关节权重混合带（atbm-0140 原版 vs chisaki）

| 关节 | chisaki | 原版 |
|---|---|---|
| 左肩 | 12.1% | 13.3% |
| 左肘 | 6.4% | 3.9% |
| 左腕 | 8.3% | 6.2% |
| 右肩 | 6.8% | 13.2% |
| 左膝 | 6.0% | 9.5% |

madoka 双肩 4.5% / 4.9%（原版 16.5% / 16.7%）→ **G2 报出**。

### 8.3 顶点 COLOR 语义（22 套原版）

```
RampAdd 行 (G 低 nibble) 用到的:  {0, 1, 2, 3, 6, 9, 12, 15}
rim (A 高 nibble) 分布:           9→245184  0→131778  5→4049  3→3100  4→1344
纯白顶点 (255,255,255,255):       0
```

→ **rim 不能当判据**（0 占约三分之一）；**纯白才是干净的红线**。
原版皮肤实测值：`(81, 0, 15, 144)`。

### 8.4 上臂扭转 67° 塌陷（SDK 侧三方对照）

```
只认领源模型自己的捩骨   −12.1%
开 stockJointRig 补 16 根 −4.6%
原版 atbm-0140            −3.3%
弯曲工况（对照）          ours −8.5% / 原版 −10.9%   ← 矫正骨是扭转装置，对纯弯曲按设计 0 收益
```

### 8.5 P1b 重分配效果（chisaki-swimsuit）

```
*_H 承重  0.00% → 17.85%（原版范围 6.02–21.00%）
触及 56836 个顶点，搬走 17.9% 的全身权重
截断顶点 4329，权重和异常 0 个
```

---

## 9. 复现命令

```bash
# 源目录契约 + G1/G5/G6/G8/G11（stdlib，不依赖 UnityPy）
python tools/verify_ab_package.py <mod目录> [--json]

# rig 级闸门 G2/G3/G4/G10（要 UnityPy + 原版对照）
python tools/audit_ab_rig.py <mod目录> [--vanilla <名字或路径>]

# P1b 权重重分配（默认试跑，--write 才落盘）
python tools/redistribute_helper_weights.py <mod目录> [--write]

# 重扫原版驱动器预设（530 套，几分钟）
python tools/scan_vanilla_drivers.py --install

# 全套单测
python -m pytest tests/ -q --ignore=tests/blender_smoke.py --ignore=tests/blender_ui_smoke.py \
  --ignore=tests/blender_install_smoke.py --ignore=tests/material_bake_blender_smoke.py
```

运行时构建：

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" `
  "D:\GIT\gakumas-modding\gakumas-mod-runtime\build\gakumas_mod_runtime.sln" `
  /p:Configuration=Release /p:Platform=x64 /m
```

### IDA 操作纪律（2026-08-15 事故）

反编译会因为**弹窗**或自动分析未完成**长时间阻塞**（那次卡了很久，是作者按停止才拦下的）。

1. 先用 `get_function_by_address` 便宜探测，确认响应再 `decompile_function`。
2. 小函数（几百字节）秒回；`UpdateChainInfo` 那个 2.5 KB 的也没卡。
3. **一旦超时立刻停下报告，不许原地重试。**
4. 建议给 `ida-pro-mcp` 配 per-server `timeout`（120000 ms）—— **目前还没配**。

---

## 11. 从 SDK 再取五项（2026-08-15 第二轮）

按「① 简化开发者操作 ② 提升游戏内显示效果 ③ 新增骨更好还原动态」重新评估后定的五项。
**五项里有一项做完发现是重复的，已整条撤回** —— 记在这里，因为撤回的理由比做的过程更值钱。

### ① 摇物链层的 `around`（目标③，已改）

IDA 读 `UpdateChainInfo`（`sub_1316A88`）拿到 `ChainLayerInfo` 的精确拷贝范围，对照 il2cpp 布局
（`active`@0x10 `around`@0x11 `radius`@0x14 `smoothing`@0x18）：

```
layer[16] = old[16]                  ← 1 字节，只有 active
*(u64*)(layer+20) = *(u64*)(old+20)  ← 8 字节，radius + smoothing
```

三条结论：

1. 现有代码在 `UpdateChainInfo` **之后**写 active/radius 是对的，而且**重入安全** ——
   再调一次会把它们当老值继承回来。
2. **`smoothing` 不用写**：174 条原版链逐层实测中位数**全是 0.0000**，等于默认值。
   （本来打算加，量完发现是白加 —— 负结果同样记账。）
   **样本出处**：这 174 条是当时的抽样，不是全量。2026-08-15 重扫全部 530 套复核：
   0 失败 / 48,292 骨记录 / **1,539 chain** / 5,223 layer，各层 smoothing 中位数**仍然全是 0**，
   结论成立。（同批复核：排除 layer 0 后 `around=1` 占 1,334/3,684 = **36.21%**，即正文说的"约四成"。）
3. **`around`(@0x11) 不在拷贝范围内**，重跑 `UpdateChainInfo` 会被打回 false。原版 40% 的层
   开着它（环形碰撞），但逐链手调无规律，所以**不猜默认值**，改成 sidecar 可显式指定
   （`chains[].around`），不指定就保持现状。

### ② 顶点 COLOR 合成（目标②）—— **做完发现重复，已整条撤回**

我判断 AB 的 `m_Colors` 是作者手工准备的，依据是 grep 不到 `material_presets.json` 里
`color.rgba` 的消费点。**这个判断是错的**：它通过
`_material_slot_color_map()` → `_preset_color_float(presets.get(key))` 被消费，
我 grep 的是 `"color"` 字面量，没匹配到就下了结论。

AB 实际已有的比 SDK **更强**：`gmi_vertex_color_mode` 三档，其中 `BASECOLOR` 逐顶点从 t0 采样、
按抓帧实测的编码系数（相关性 0.94/0.77/0.24）算描边 nibble，ramp 行/宽度/光照按材质预设；
SDK 那套是每子网格一个扁平预设 + 皮肤 mask。

已把加的算子、UI 按钮、材质属性、core 函数、测试文件**全部删除**。留着就是第二条更弱的通路，
正是 v2 「删繁就简」要消灭的东西。

> **这是本会期第四次提出"搬一个 AB 已经有的东西"**（前三次：P3a 驱动器、t1/t4 合成、摇物基准表）。
> 教训不是"要先查"——每次我都查了——而是**查"有没有这个数据/属性"不够，必须查"它有没有被消费"**。
> 前三次栽在只看数据存在，这次栽在 grep 用了字面量而消费点是变量传递。

### ③ 结构化 report（目标①，已改）

`verify_ab_package.py` 的 `_record()` 多一个 `action`，报告里多一个 `findings` 数组
（`{level, message, action}`）。四条高频结论配了修法：`*_H` 零承重、纯白 COLOR、骨名重复、
缺 Avatar 必备骨。

`action` 为空表示"没有已知的通用修法"，那本身也是信息，不拿空话填。

**接线时抓到一个洞**：逐 geometry 的结论在汇总到主报告时只搬了 `message`，
**`action` 被静默丢掉** —— 而 G1/G8 这两条最高频的恰好都走这条路径。已修。

### ④ 链分类改几何判据（目标③，已改）

AB 原本按骨名词表分类（`_SWING_CATEGORY_RULES`）。按名字判的硬伤是**只对恰好用本作命名习惯的
源有效**：原神 rip 把裙摆叫 `Bone_HemA01_L`、MMD 叫 `スカート`，词表两个都不认 → 整条链没有物理。

新增 `core.swing_category_by_geometry(anchor, direction, siblings, fallback_name)`，
判据与 SDK 侧 `ChainClassifier` 同源（381 套原版量过）：

| 信号 | 用法 |
|---|---|
| **挂在哪根身体骨上** | 原版 1537 条链的锚点：Pelvis 758 / Spine2 86 / Spine 82 / UpLeg_H 80 / Shoulder 50 |
| **同锚点几条** | 裙摆是一圈（原版 4–8 片）；只挂一两条的是围裙/尾巴/腰带 → cloth |
| **往哪垂** | 只用来拆胸口一族：向下=披挂，朝前=胸，朝后/朝外=翅膀/披肩 |

**匹配方式不是随手定的**：手臂/腿那两行用子串（`LeftForeArm`、`RightUpLeg_H` 都要命中），
头颈和胯部那两行用**精确相等** —— `Spine2` 必须落不进 `Spine`，否则胸口一族全被判成裙摆。
第一版我全用了子串，测试当场抓出来。名字保留为兜底（几何信息拿不全时总比不判强）。

### ⑤ 出包预览图（目标①，已改）

`audit_ab_rig.py --preview <目录>`：从 geojson 直接出一张正交剪影 PNG，按子网格上色，不用开 Blender。

**明确写在源码注释里的边界**：只能抓粗错误（丢了半身、整体错位、镜像反了），
**抓不到合身/破面/飞点** —— 那些仍然只能人眼看。别拿它当验收。

接线时踩了两个：
- PNG 字节转义在写文件时被解成了真实控制字符 → 改成显式 `bytes([...])`。
- 子网格用 `firstByte`（**字节**偏移）不是 `firstIndex`，且**索引是 uint16 不是 uint32**
  （chisaki 实测 firstByte 338826，除以 4 不是整数、除以 2 正好等于前一段的 indexCount）。
  第一版按 firstIndex 取永远落在 0，整个模型一个颜色，分段图是假的。
  现在步长从数据自推，推不出就退回不分色 —— **宁可少一个颜色，不要画一张假的分段图**。

### 本轮验证

`xinput1_3.dll` 构建通过 · C++ 测试 2/2 · Python **65/65**（新增 5 个几何分类用例）

---

## 10. 本轮复核修正（2026-08-15）

来源：[`ab-sdk-independent-review-2026-08-15.md`](ab-sdk-independent-review-2026-08-15.md)。
下面每条我都独立复核过（不是照抄评审）。

### 10.1 硬错，已就地改正

| # | 原文 | 事实 | 证据 | 改到哪 |
|---|---|---|---|---|
| 1 | "54 个候选 → 7 个成品" | `blend-originals/` **9 个目录 / manifest 9 条**。`B054` 是编号不是计数 | `ls -d .../B* \| wc -l` → 9 | §3.6 |
| 2 | "SDK 只写 3/32，AB 32 个属性全对" | **两条都是克隆原版材质再搬同样 3 张贴图**，其余 29 项都继承 | `AvatarProbePlugin.cs:949-1026` 用 `Material` 拷贝构造，注释原话 `_RampMap/_RampAddMap stay as the game authored them`；`BodyImporter.cs:273-302` 只是 placeholder | §3.1 / §3.2 / **新 §3.7** |
| 3 | 网格/权重"100% 无损（顶点/法线都不碰）" | 运行时**每次**把顶点、法线、切线变换到原 renderer 空间，**无 identity 快路径**；bindpose 另乘空间修正。真正成立的是"不做破坏性权重重分配"，UV/COLOR/submesh 确实没碰 | `ModRuntime.cpp:3048-3088`（vertices/normals/tangents 三个循环 + `SetMesh*`）、`:3171-3178`（`bindposeSpaceAdjustment`） | §3.2 |
| 4 | INV-3 "节点总数 ≤ 256" 写成硬不变量 | `RegisterBone` 全程无 256 边界检查，内部列表正常扩容 → 是容量提示。同一份文档 §4.2 #3 和 G6 早就写了它是 warning，**自相矛盾** | 见 §4.2 #3 | §5.3 INV-3、`ab-v2-plan.md` INV-3 |

### 10.2 措辞过强，已收紧（结论方向不变）

- "AB 契约面 ≈0 / SDK 全部重建" → **AB 大量继承游戏对象侧契约；内容侧契约两条一样多**（§3.1）。
- "SDK 全部重建 22 个 List" → **不用手工填**，游戏的 `Initialize/ProcessBones/UpdateSkinnedMeshRenderers`
  自己填；SDK 的负担是**提供让它填得起来的对象/组件/引用**
  （`AvatarProbePlugin.cs:833-848` 注释原话："组件只要存在"）。
- "模型侧同一量级" / "AB 5 个成品 vs SDK 2 个" → 标为**工程判断与项目经验**，不是受控对比或成功率（§3.6、plan §2.1）。
- 174 条链的样本出处 → 补上：那是抽样；530 套全量重扫（1,539 chain）后中位数仍全 0，结论成立（§6.2 ②）。

### 10.3 不构成实质错误

- workspace "26.6 GB" vs 复核的 26.0 GiB —— 十进制/二进制单位差，同一个数。
- `UpdateChainInfo` 函数大小记 `0xA20`，当前 IDA 是 `0xA34` —— 范围标注陈旧，**行为结论不变**，不改。
- 19 根必备骨、`RegisterBone` 重名早退、256 是软容量 —— 评审是**独立证实**本文，不是推翻。

### 10.4 新增的待办（唯一有画面后果的一条）

**服装专属材质参数缺口**，见 §3.7。manifest 显式覆盖 + audit warning，两样都还没做。

### 10.5 为什么这些错当时没被发现

不是运气问题，是四个可复现的写作习惯：

1. **数字从标签推，没数过。** `B054` 当成 54 个。一条 `ls | wc -l` 就能证伪，而上一行的证据自己写的
   就是"编号跨度"。→ **凡是数量，必须来自一次真实的计数命令，且命令要写进文档。**
2. **读代码的深度不对称。** SDK 侧只读了 editor 的 `BodyImporter.cs`（写 3 个属性）就下结论，
   runtime 的 `RebuildMaterials`（克隆原版材质）没读；AB 侧读到底。
   **支持既定结论的一侧读得深，不支持的一侧读得浅** —— 对比表因此天然倾斜。
   → **对比表的每一格，两侧必须读同一层（都读 runtime，或都读 editor）。**
3. **写的是设计意图，不是代码实况。** "100% 无损"是 lossless graft 那条路径的**契约**，
   被当成了整个 mesh 的事实。→ **形容词（无损/全对/齐全）必须挂一个 `file:line`。**
4. **只追加不回改。** 256 是软的这个发现写进了 §4.2 和 G6，但前面的 INV-3 表没回头改；
   §3.6 是给 §3.2 对比表打的补丁，却留着错的表格在上面。
   → **新结论推翻旧表述时，改旧表述，不是在下面另写一节说"上表可能给人错觉"。**

第 2 条是根子：**这两份文档是在结论已定之后写的论证，不是查证。**
本文自己的记忆库里就存着"`_RampAddMap` 随服装"，写"32 个属性全对"时压根没去比对。
