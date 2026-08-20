# AB 路线：已坐实事实、实测数据与量测方法（合并版）

日期：2026-08-16

性质：**事实与证据的唯一入口。** 本文合并 2026-08-16 之前所有未提交的 AB 研究文档。

与另两份文档的分工：

| 文档 | 管什么 |
|---|---|
| [`ab-target-rig-route-2026-08-17.md`](ab-target-rig-route-2026-08-17.md) | **做什么、按什么顺序做**（现行路线：target-rig） |
| **本文** | **已知什么、量到多少、哪些结论已作废、怎么量才不出错** |

冲突时：路线与顺序以 `ab-target-rig-route-2026-08-17.md` 为准，事实与数字以本文为准。

> **2026-08-17 路线变更对本文的影响：** §4.13–§4.15（whole-object）**量到的事实全部仍然有效**，
> 作废的只是"该走这条路"这个结论。whole-object 违反「作者只开 Blender」——带组件的 prefab
> UnityPy 造不出来，必须 Unity 出包。现行路线是 **target-rig**：人体主骨架严格使用学马原版
> 70 根，外部网格在 Blender 手动对齐，能对应的骨保留原权重并显式映射。

被本文取代的文档见 §10。原文 2026-08-20 已从 `research/` 删除，取回方式写在那一节。

---

## 1. 状态词

旧文档最大的问题是把「运行时写了接口」「导出器能产数据」「离线测试通过」和「游戏里已验证」
都写成"完成"。本文统一：

| 状态 | 含义 |
|---|---|
| **已实机确认** | 有对应包、日志和画面记录，且验证的是当前所述路径 |
| **已实现，未完整实机** | 代码和离线测试存在，但没有覆盖所需场景的游戏验证 |
| **实验能力** | 只存在于研究工程、孤立脚本或未接入生产的函数中 |
| **规划** | 尚未实现，不能写成当前能力 |

**离线测试通过只证明代码契约没有明显回归**，不证明裙子摆得对、关节不塌或材质和画面一致。
同理，**日志出现「应用成功」只代表代码路径执行了**。

---

## 2. 原版骨架与组件（已实机确认）

### 2.1 基础骨架

530 套原版 body 共有的基础骨架 **70 根**：

```text
52 根  全部 Unity Humanoid 人体骨（一根不缺）
14 根  *_H 关节矫正骨
 1 根  Pelvis      （Hips 和双腿之间多插一层，Unity 没有这个概念）
 1 根  Reference   （根节点）
 2 根  Left/RightBust1_S
```

- 静止姿势 530 套**完全一致**，离标准 T-pose 最大 4.0°，双臂精确 0.0°
- 骨架节点数 78–203；**每套只有 1 个 SkinnedMeshRenderer**
- 19 根必需骨（IDA 得到）；**256 是复杂度预算 warning，不是已证明的硬上限**
- 骨名在 body/face/hair 的**共享命名空间**内唯一；`RegisterBone` 遇到重名**整根跳过**

### 2.2 `*_H` 矫正骨的真实作用

- 全身 **17% 权重质量、38% 顶点**挂在 `*_H` 上
- 关节处人形骨基本不承重：肩 t=0 处 `Arm` **0%** / `Arm_H` **99%**；腕处 `ForeArm` 0% / `Hand_H` 100%
- 位置是中间件常量，1060 条肢体测下来四位小数不变：

```text
*_H 0.000   Arm_Roll_H 0.605   ForeArm_Roll_H 0.581   Hand_H 0.910   UpLeg_Roll_H 0.360
```

- 量化收益：**扭转工况 装 −0.5% / 不装 −8.7%；弯曲工况 0.0%**
- **这个游戏没有肩部摆动矫正骨。** 早期「肩半宽 17.4→12.6cm，需要矫正骨」整套说法**作废**，
  那是错误取样。52 骨缺的是**扭转剪切 + 肘膝硬折**，与静止姿势是 A 还是 T 无关。

### 2.3 组件摆放硬规矩（违反 = 硬崩）

- 一根骨**不能**同时挂 `ActorSwingDynamicBone`/`ActorSwingStaticBone` 和任何 QuartzDriver
  （原版 60 套 327 个裙摆驱动器**零重叠**）。`ActorSwingChain` 是环容器，**允许**与驱动器共骨。
- **静态碰撞体从不挂 `_H` 骨**（原版挂 Hips/Spine/Neck/Arm/ForeArm/Hand/UpLeg/Leg/Foot）
- 一条骨脉至多一个 QuartzDriver
- `CampusActorAnimationInitializeData` 用 `List<组件>` 收集驱动器——**按组件类型，不按骨名**，
  只有 `reference`/`hips`/`head`/`moveReference` 按身份绑

### 2.4 摇物

- **层 0 是锚定层**：单根骨的飘带/裙摆在游戏里不会动，一条链至少两根
- 裙摆面片根部在胯上 **+0.3~+17.4cm**（381 套实测）；方位角分档边界 **56°/89°/124°**
- skirt 档 `collisionMask=1`；落进 cloth 档会变成 −1 去撞半径 0.23m 的胯胶囊 → 裙子发僵不贴腿

### 2.5 驱动器

12 类：`Frill / Furisode / HumanoidArm / HumanoidHand / HumanoidSleeve / HumanoidSleeveSimple /
HumanoidUpLeg / LateRotationSimple / Poncho / Rotation / Skirt / Waist`。
**528/530 套原版带其中 16 个实例。**

---

## 3. 动画与蒙皮机制（已实机确认）

### 3.1 身体动画是纯 Humanoid 肌肉

`data.unity3d` 里的身体 idle clip：**130 条 binding 全是 muscle，零 transform 曲线**
（对照组：脸的 clip 是按骨路径写的，证明读法没问题）。

```text
MotionDefine → AnimationData{clip, mask, footIK} → AnimationClipPlayable → PlayableGraph（无 Controller）
  → Animator(isHuman) 把肌肉值经 Avatar 反解成各骨局部旋转
  → job 层（LookAt / JointLimit / IK / HipCorrector）再改 human stream
  → 摇物/裙摆/头发不在动画数据里，靠 Swing/QuartzDriver 组件自己算
```

Avatar 由 `CampusActorController.BuildAvatar()` 运行时按骨名现建。

### 3.2 重定向吸收方向，**不吸收 roll**

- **骨轴向对身体动画零贡献**——离线台架量到「静止 vs T」和「同一组肌肉值驱动后 vs 参照」
  两列数字**一位小数都不差**，误差 100% 来自静止姿势的 A/T 之差。
- **例外**：头发和脸不是蒙皮到 Head，是挂在 Head 底下当**子物体**，直接继承父骨世界旋转，
  这条路上没有 Avatar。某 Biped rip 的 Head 静止朝向导致头发和脸整个转了 121.7°。
- **roll 不被吸收**：两根指向相同但绕自身轴差 180° 的骨，吃同一个 muscle 会**符号相反**。

### 3.3 运行时的两条蒙皮路径

| 路径 | 触发 | 行为 |
|---|---|---|
| lossless graft（协议 1） | manifest 带 `skeleton` | 用源 bindpose；root/数量/权重索引不符时硬失败 |
| legacy | 没有 `skeleton` | root 同名时用 mod bindpose，否则退回原版，记 `bindposeMode` |

**关键机制**（`ModRuntime.cpp:2855`，`BuildHybridBoneArray`）：

```cpp
if (originalBoneIndexMap.find(sidecarBone.name) != end) {
    hybridBones[index] = originalBones->At(...);   // 同名 → 直接指向原版活体骨
}
```

sidecar 给这根骨写的 `localPosition / localRotation / localScale` **一个字节都不读**。
**源骨架的静止变换被完全丢弃**——这是「lossless 其实不免对齐」的机制根源。

### 3.4 协议 2：来源代理骨架（实验能力）

`BuildSourceProxyBoneArray()` 已存在：

- sidecar 声明的每根骨都**新建**，不复用学马同名骨
- 原版 Renderer 仍被使用，只把 `bones` 数组换成代理骨
- 网格继续用来源权重和来源 bindpose
- 硬限 `mode: "rest-only"`，日志明写 *animation and physics are intentionally disabled*
- **代理骨带前缀创建**：`"__gmi_sp_" + index + "_" + sourceBone.name`

**前缀的连带后果（重要）**：游戏侧任何「按名字找骨」的机制都够不到代理骨——
`AttachQuartzDriver` 的 `resolveBone(boneName)`、`RegisterBones` 都是按名字。
所以**代理路线下「把源扭转骨接给学马 driver」不成立**，代理侧的一切必须由动画桥或
我们自己的求解器写。

---

## 4. Claymore 全套实测（2026-08-16，最完整的一次外部模型量测）

样本：`Avatar_Girl_Claymore_MarionetteNew.fbx`（miHoYo Biped rip），目标 `mdl_chr_atbm-cstm-0140_body`。

### 4.1 模型盘点

```text
257 骨 / 193 带权重 / 8 个网格 / Body 41645 顶点 / 高 1.6323
biped 预设命中 52/52（人形骨零手工），未覆盖但带权重的骨 142 根
自带扭转骨 6 根：+UpperArmTwist L/R A01/A02、Bone_ForearmTwistA01_L/R
Body 网格含 5 个材质槽，其中 Mat_Hair 那 14615 个面里**连着整条腿**
```

### 4.2 源 vs 游戏的四类差（全部实测）

**镜像**（导入后第一件要判的）：

```text
游戏 LeftArm  X = -0.120        源 Bip001 L UpperArm  X = +0.090
46 根反 / 0 根同（全票）        两边脚尖都朝 +Z ⇒ 纯镜像，不是面朝反向
```

**静止坐标系朝向差**（bindPose 反解，`core._to_unity` 换空间后量）：

```text
LeftShoulder 177.5°   Hips 177.2°   LeftHandThumb1 170.1°
RightUpLeg 138.8°     LeftUpLeg 125.6°   RightShoulder 108.5°   Spine1 7.2°
```

**roll**（Unity 侧在同一副 rip 上量）：

```text
40 根驱动骨里 38 根 >90°；双手 ~174–180°；每根手指 ~172–180°
回放游戏自己录的姿势：510 个爆开的三角形里 280 个在右手，左手 0 个
原因：Biped 两只手用同一个 frame，原版两只手是镜像的
```

**骨长比例**（身高归一后，7/39 段超出 [0.75, 1.35]）：

```text
Spine2→RightShoulder 1.72×    Neck→Head 1.50×    Spine→Spine1 0.66×
中指末节 1.44×                食指末节 1.41×      小指末节 1.33×
```

### 4.3 权重画法差（骨映射和姿势都改不了的那类）

```text
锁骨 1504 顶点   上臂 135 顶点   共享 0 个顶点
跨关节带  肩 4.9% / 原版 13.3%    肘 2.6% / 3.9%    腕 6.2% / 6.2%    膝 8.2% / 9.5%
```

上臂几乎不承重，肩臂之间**完全没有过渡带**。**认领 7 根扭转骨前后这个数字不变**——
证伪了「肩塌和扭转骨缺失是同一个根因」的猜测，与 §2.2 的量化一致（弯曲工况 0.0%）。

### 4.4 混合路线的逐顶点位移（`source-rest-claymore` 三轮）

| 轮次 | 处理 | 平均 | P95 | 最大 |
|---|---|---:|---:|---:|
| A | 原始 A-pose 直接接学马骨 | 37.7 cm | 101.1 cm | 146.6 cm |
| B | Unity Humanoid 烘 T-pose + 重算 bindpose | 21.9 cm | 59.8 cm | 105.4 cm |
| C | 再校正 40 根驱动骨轴向 | 12.8 cm | 44.0 cm | 105.4 cm |

C 轮判定：**人体明显改善，来源专有骨仍不可用，裙摆整片飞离。**

### 4.5 「T-pose Claymore 静态代理实机成功」—— **模型是串的，勿引用**

2026-08-16 晚查实：那个 `claymore-source-proxy-rest.bundle` 里**根本不是 Claymore**。

```text
包里实际是   kth_ss202（学马约定的服装 rig，连根骨都叫 Reference）
             ribbon_L0/R0、OPAI_L0/R0、Bone #56196939、胸.L
             9054 顶点 / 225 蒙皮骨 / 6 材质槽
Claymore 是  Avatar_Girl_Claymore_MarionetteNew / Bip001 / +Breast L A01
             42066 顶点 / 172 蒙皮骨
```

**串包机制**：SDK 每个模型都写同一个 `Build/AssetBundles/mdl_chr_external_body.bundle`。
Claymore 的 T-pose 那次跑（`unity-tpose-report.json`，08-16 06:41，自己报 42066 顶点 /
172 骨）**没产出 bundle**；08-15 07:11 上一个模型留下的 bundle 还在原地，打包脚本照单全收。
产出的 sidecar 完全自洽，进游戏画面也合理——**三类证据里的「自洽」和「渲染对照」都骗得过，
只有拿 Unity 那次跑自己的顶点数/骨数去核才能发现**。这是记忆
`sdk-texture-dir-cross-model-leak`（贴图目录串包）的上一级版本：串的是整个 bundle。

所以那次实机**只能证明协议 2 的路径通**，不能证明「来源身体比例被保留」——
`kth_ss202` 的比例和骨架约定本来就是学马的。

闸门已加（三处，都是"产物要能和产它的那次跑对上"）：

- `build_runtime_test_package.py --unity-report` 必填，拿 Unity 报告的顶点数/骨数对着 bundle 核；
  坏样本报错、真 Claymore 包不误报。
- prefab 路径改成从 bundle 的 container 读，不再靠手敲 `--asset`（敲错 = replacement 静默落空）。
- Unity 侧合成 `ClaymoreBundleExperiment`（`-restPose a-pose|t-pose`），**两种姿势各写自己的
  模型名/prefab/mesh/bundle**，不再共用 `mdl_chr_external_body.bundle`；跑完校验 bundle
  文件真的存在。烘完还校验双臂 ≤1°、权重零改动、顶点与 bindpose 必须一起变
  （只动其一 = 烘焙没落到网格上，就是 §4.6 那个 67cm 的坑）。

**同一天第三次踩贴图串包**：合成后的实验仍然绕过 `BuildSurfaces`，直接
`LoadAssetAtPath("External-Out/m_bdy{N}.mat")` 当「已验证的 Claymore 材质」——实机是
Claymore 的几何穿着上一个 mod 的贴图。**修法不是再打补丁，是别绕过
`ExternalModelImporter.Import()`**：它做模型名限定的贴图重建、写顶点 COLOR（漏了就没描边）、
建 mesh asset、建材质，一步不少。出包前断言每个槽的 `_BaseMap` 名字含本模型名
（**读 `_BaseMap` 不是 `mainTexture`**——`GakumasSdk/BodyPlaceholder` 没有 `_MainTex`，
`mainTexture` 全 null，第一版闸门因此把 5 个正常槽全报成 `<null>`）。

真 Claymore T-pose 包 2026-08-16 已出：烘正 28 根骨 + 双臂滚转，双臂 0.0°、42066 顶点 /
172 蒙皮骨 / 5 子网格，顶点 COLOR 42066 个，5 个 `_BaseMap` 全部来自 Claymore 自己的
`..._Tex_Body/Body01/Hair_Diffuse.png`，包内 15 张贴图零外来；打包后 260 transforms /
172 skinBones、`rootBoneIsSkinBone=false`。

### 4.6 源 rip 的 bindpose 与静止姿势本身就对不上（新）

用两条独立推导（bundle 的 Transform 树 / Unity 自己的 metadata，彼此差 2.8e-06）核出来：

```text
未烘焙的 Claymore A-pose 包  W·B 偏离单位阵 max = 0.9217（指尖最坏，深链递增）
                             蒙皮自洽位移 mean 3.32cm / p95 9.33cm / max 18.97cm
烘焙后的 T-pose 包           W·B 偏离单位阵 max = 5.4e-07，自洽位移 max 0.00003cm
```

也就是说**这副 rip 的顶点不住在它节点静止姿势里**。A-pose 包即使补上完整 transform 树，
进游戏也会渲染成它的 bind 姿势，不是作者在 DCC 里看到的静止姿势。
`TPoseBaker.BakeSkin` 把新静止直接当新 bind（`bindposes[i] = bone.worldToLocalMatrix * rendererLtw`），
顺手修好了这个。

**对 T-pose 硬闸门的要求**：只量节点静止姿势的角度不够，必须同时查
`bindpose · 静止世界矩阵 ≈ I`。前者过、后者不过的包，闸门全绿而画面是另一个姿势。

### 4.7 T-pose 烘焙的形变量化（新，2026-08-16）

`measure_tpose_package.py`，Claymore 42066 顶点 / 66681 条边：

```text
蒙皮自洽     max 0.00003cm，权重和 1.000000
边长变化     绝对 mean 0.115mm / p95 0.54mm；相对 mean 1.20% / p95 5.06%
单骨回摆     80/81 根骨精确(<1e-4)；唯一例外 Head = AlignHeadAxes 重新表达坐标系(渲染上抵消)
尾部         718 条边(1.08%) 变化 >2mm，136 条 >5mm，最坏 1.36mm→15.0mm
尾部位置     LeftShoulder / RightShoulder / +UpperArmTwist L,R A01 / +PelvisTwist CF A01
```

**这是 §9.1 作者痛点「A→T 之后肩膀变小崩坏」第一次被量出来。**
根因是源自己的权重（§4.3：锁骨 1504 顶点 / 上臂 135 顶点 / 共享 0 个，跨肩带 4.9% vs 原版 13.3%），
不是烘焙算法——`BakeSkin` 用的是双四元数混合，本来就是防塌陷的那一版。
要改善只能补肩部过渡权重，属作者 DCC 侧。

### 4.8 头身接口的实测差（Claymore vs `atbm-cstm-0140`，新）

两副骨架放同一空间（原版取自 `libraries/assetstudio-body-json/…/Geo_Body.skeleton.json`）：

```text
骨            原版 Y      来源 Y     差
Head         1.4599     1.3298   -13.01cm      ← 游戏的脸/头发挂在这里
Neck         1.4037     1.2545   -14.93cm
LeftShoulder 1.3466     1.2433   -10.33cm
Hips         0.9981     0.8764   -12.17cm
LeftFoot     0.1025     0.0608    -4.17cm
半肩宽       11.95cm     9.48cm

Neck→Head            ×1.360        Spine2→Neck        ×1.117
Hips→Spine2          ×0.832        LeftShoulder→Arm   ×0.815
LeftArm→ForeArm      ×0.926        LeftUpLeg→Leg      ×1.013
```

**游戏的脸和头发不是蒙皮到 Head，是挂在 Head 底下当子物体**（§3.2），而代理路线只换了
body renderer 的骨数组，游戏骨架一根没动。所以游戏的头仍然吊在原版 `Head`（Y=1.4599），
而来源身体的脖子只到 Y=1.2545 —— **头悬在身体上方约 13cm**，这是路线图第 7 步
`HeadSocket` 存在的原因，rest-only 阶段日志里 `headSocket=-1` 就是明写没接。

注意差的不只是 `Neck→Head` 一个比值：躯干、肩宽、上臂各自不同向
（0.815× 到 1.360× 都有），**没有一个统一缩放能同时对上**。保留这些差异正是代理路线的目的，
让头对上必须把游戏头部件挪到来源的头节点上并做位置/旋转/缩放校准。

> 量测坑：`Geo_Body.skeleton.json` 的 `nodes[].parent` 是**数组下标**，不是 `pathId`。
> 按 pathId 查会 151 个节点全部落成根，量出 `Hips→Spine 92cm` 这种明显不对的数。

### 4.9 2026-08-16 那次 A/B 对照 —— **结果无效，勿引用**

```text
A 不烘  自洽位移 22.61cm   B "烘"  自洽位移 6.96cm
```

**B 的烘焙实现是错的**：只设了骨的世界旋转当姿势，位置被父骨旋转拖走，网格跟着定型。
量出来 **B 的网格相对原始源网格位移平均 67.72cm**。而当时的尺子只量「自洽性」，
一个被烘烂但自洽的包照样得高分。**这组数不能用来回答「要不要烘 T-pose」。**

### 4.10 最小动画桥实机通过（2026-08-16 夜，Claymore 真外来模型）

`mode=animation-bridge-minimal`，驱动 20 根（Hips、脊椎×3、颈、头、双侧肩/臂/前臂/手、
双侧大腿/小腿/脚），不含手指、Hips 位移、物理。**来源身体跟着游戏动画动了**，比例是来源自己的。
公式和四个决定见 `gakumas-mod-runtime/docs/manifest-v2.md`。

**坑一（贵，且骗过了两类证据）：换装钩子改的是 prefab 资产，不是活体。**
`ReplaceLocalModAssetIfNeeded` 挂在 `AssetBundle.LoadAsset(Async)` / `AssetBundleRequest.get_asset`
上，拿到的 `originalResult` 是加载出来的 **prefab**，游戏渲染的是它的 `Instantiate()` 副本。
第一版桥在建桥时把游戏骨和代理骨的 **Transform 指针**存了下来——那些指针全属于资产，
每帧照写，画面纹丝不动，日志却是 `armed driven=20 unmatched=0` 加 tick 正常。

- 为什么前几个阶段没暴露：Mesh、材质、骨数组这类改动**随实例化被复制**，rest-only 就是
  这么渲染出来的。**只有逐帧写某个具体 Transform 才依赖对象身份。**
- 同一个 prefab 被第二个 actor 复用时会被二次 patch，那一遍 `originalBones` 已经是我们
  自己的骨，按原版骨名找会全 miss 刷一屏 warning——**那是同一件事的第二个症状，不是根因**。
- 修法：桥只存 `(游戏骨名, 代理骨名, correction)`，每个 actor 第一次 `LateUpdate` 在自己
  子树里按名字解析一次并缓存；`RegisterBones` 清缓存。correction 是两个静止的比值，
  actor 朝向自己抵消，**在资产上算、在实例上用是同一个值**。
- 判据：`armed` 只证明模板算出来了；`Animation bridge bound to live actor: scope=actor driven=20/20`
  才是活体绑定的证据。

**坑二：装机的 DLL 比源码旧一版。**「编译通过」不等于「装机的是它」。
`grep <新加的日志字符串> <部署的 dll>` 是零成本的核对，日志比对之前先跑。

**头已接（第 7 步的位置部分）：** 每帧把原版 `Head` 的**世界位置**吸到来源头骨上，
脸和头发骑着这根骨，跟着走。只写位置不写旋转——旋转本来就对
（`游戏骨世界旋转 = 代理骨世界旋转 · correction⁻¹` 是恒等式），且留着游戏自己的
点头/视线修正继续驱动脸。写的是绝对目标不是增量，所以 Animator 不重写这根骨的局部位置时
重复写也只是幂等。`headSocket` 缺省 `-1` 时退回 `semanticMap` 的 `Head`。

**近景发糊 —— ⚠️ 下面这段结论是错的，2026-08-16 夜由实机推翻，保留作反面教材。**
换上游戏材质（§4.11 的材质采用）之后**糊立刻消失**。真正的原因是身体一直用 SDK 占位
着色器渲染（单 pass、只采样 `_BaseMap`、无描边无 ramp），不是下面推的几何深度差。
**教训：把"相机按骨骼算"这个正确机制，和"所以糊是几何差"这个跳跃结论混为一谈了。**
相机机制本身（`CharacterOrbitCinemachine` / `FocusTargetType` 全按骨骼）仍然成立且有用——
它解释的是**点击判定和取景**，不是模糊。

~~不是 bug，已定性：拉近后衣服糊、脸清楚。~~
换装间的相机是 `Campus.OutGame.CharacterOrbitCinemachine`，它的
`_centerTarget/_finalTarget/_focusPoint`、`GetEyeDistance()`、`UpdateFocalLength()`、
`SetDefault(float humanScale)` **全部基于骨骼和 humanScale，不读渲染器包围盒**；
对焦目标枚举 `FocusTargetType = {FocusedEye, Head, Spine2, Hips, 双手, 双脚}` 也全是骨。
脸清楚说明焦平面正确落在眼睛上（眼睛在对的位置，正是因为头已接）。衣服糊是几何真的离焦平面远：

```text
50 根映射骨静止位置差   平均 31.6mm  最大 71.7mm   （Spine2 71mm / Spine1 64mm）
皮肤顶点位移            平均 52mm    p95 148mm
身体正面深度（对比同一件衣服贴合原版体型） 深出约 13cm
出处：unity-tpose-frames-source-rest-comparison-report.json
```

近距离景深只有几厘米厚，胸腔差 7cm 直接出景深；原版不糊是因为景深参数本来就是照着
原版体型调的。**这是「保住来源比例」的固有代价，不是缺陷。**
连带挡掉一个自然但无效的修法：把 `Spine2` 等原版骨也吸到代理骨上**不会**让衣服变清楚——
衣服跟代理骨走，焦平面还在眼睛上，画面一点不变。头那次有效是因为脸和头发**真的骑在**
那根原版骨上。

**改名不是原因（已排查）：** runtime 里 `grep set_name` 零命中，原版骨架一根没改名，
代理骨是**加**出来的、带 `__gmi_sp_<下标>_` 前缀。前缀是必须的：body/face/hair 共用一张
`BoneNameToTransformDictionary`，重名抛 `ArgumentException` 打断建模。
后果是游戏按名字找骨**全部成功**，找到的是原版那根——不报错，只是那根骨不再代表可见的身体。
改名真正会咬人的地方是 `AttachQuartzDriver` 的 `resolveBone`、`RegisterBones`、IK 目标、
道具挂点，症状是**不动/挂错位置**，不是模糊。

### 4.11 全 52 根（mode 2）实机：拇指、材质、接地（2026-08-16 夜）

**拇指恒定翘起 = 游戏骨静止取错了源，只错在拇指。**
桥原来把游戏骨的静止从原版 bindpose 反解。拿 `atbm-cstm-0140` 真值量 52 根：

```text
最小桥那 20 根        bindpose 静止 == 节点静止   最大 0.00°（复现了 mode 1 上线前那次校验）
52 根里不一致的 6 根  Left/RightHandThumb1/2/3    全部 33.46°
其余 46 根（含所有其他手指、脚趾）                 0.00°
```

bindpose 静止差多少，桥就给那根骨恒定偏多少——「大拇指一直向上翘」就是这 33.46°。
**已改成两边的静止都从 transform 读**：换装钩子跑在 prefab 上（§4.10），prefab 的 transform
永远不被动画驱动，所以当初「actor 可能已经在动」那个顾虑在这条路径上根本不成立。
bindpose 降级为尺子，不一致就打日志并计入 `restDisagreements=N`；这个数变成一大片，
就说明有人在已摆姿势的活体上建桥。
离线尺子：`check_game_bindpose_rest.py`（自检=20 根全 0°）、`compare_rest_hand.py`（自检=复现 §4.8 的 13.01cm）。

> 顺带证伪：**不是「来源 rip 的手静止是翘的」**。来源手指方向与原版差 0.0°，
> 拇指相对手掌两边都是 45.0°。别再往源模型上找这个锅。

**身体一直在用 SDK 占位着色器渲染（根因，解释全部渲染异常）。**
`GakumasSdk/BodyPlaceholder` 是**贴图载体，不是用来渲染的**（它自己的文件头就这么写）。
它把属性起名 `_BaseMap`/`_DefMap`/`_ShadeMap`，和 `Campus/Actor/Default` 逐字同名，
就是为了让运行时把贴图搬到游戏材质上——**C++ runtime 从来没实现这一步**，
`replaceMaterials:true` 直接把占位壳拍到渲染器上。后果：

- 单 pass、只采样 `_BaseMap` → 没有描边、没有 ramp、没有游戏的任何渲染状态；
- 默认 `Cull Back` + 来源那几段是零厚度单片 → **正面看不见、背面看得见**；
- 深度/队列不按游戏约定 → 「深度计算有问题」；
- 想用 `materialFloats` 写 `_Cull` 也写不进去（占位壳没这属性）——
  **日志靠「一条 `Applied material float` 都没有」诚实地说了这件事**，`floats=5` 只证明配置解析了。

修法（2026-08-16 装机）：每个 mod submesh 克隆游戏的 `m_bdy`，搬那三张贴图过去。
两条硬规矩：**一律采用槽 0 的不透明材质**（按下标对应会让某段几何拿到槽 1 那个不写深度的
`co`）；**每次应用都重新克隆**（见 [[ab-cloned-material-loses-per-scene-ramps]]）。
日志：`Adopted game material for mod submeshes: ... carried=[m_bdy:3, ...]`。

**零厚度单片 vs 闭合壳（画法差，量法有坑）。** 按**顶点位置**数开放边：

```text
原版 Geo_Body  sub0  0.2%     ← 有厚度的闭合壳
来源           sub0 5.6% / sub1 1.3% / sub2 11.7% / sub3 1.4% / sub4 17.1%
```

> 量测坑：按**顶点下标**数开放边是错的——UV 缝把顶点拆开，原版都会报 24.1%，
> 看着像"原版也是单片"。必须按位置（量化到 0.1mm）合并。
> 另：两边都没有「反向绕序的孪生三角形」，所以**双面几何这条假设是错的**，
> 原版靠的是厚度不是双面。

**鞋子入地 4.1cm = 模型没站在自己原点上。**

```text
原版网格  minY = -0.0000 m    ← 正好在地面
来源网格  minY = -0.0410 m    ← 最低点在自己原点下方 4.1cm
```

与 §4.8 独立量到的「来源 LeftFoot 比原版低 4.17cm」互相印证。游戏把 body 根放在地面上，
模型如实渲染 → 鞋底进地 4.1cm。**这是出包侧缺陷，不是运行时 bug**；运行时偷偷抬高会把
4.1cm 写成常量（路线图明令禁止）并让作者永远看不见它。正确落点是构建脚本量 minY 后拒收。

**材质槽这条假设被否掉了（留个记录防止重走）：** 一度怀疑「5 段网格 vs 原版 2 个材质槽 →
多出来的段没人画」。日志否掉了：`submeshes=5 slots=5 unpainted=0`。

### 4.12 冷路径与热应用是两套前提（2026-08-17，第 5 步实机）

同一段替换代码有两条入口，**前提相反**，凡是「读当前状态当真值」的地方都会在其中一条上翻车：

| | 冷路径（资源加载） | 热应用（mod 开关 ON） |
|---|---|---|
| patch 对象 | 刚加载的 **prefab** | **活体 actor** |
| 骨架状态 | 永不被动画驱动 = 静止 | **正在播动画 = 摆着姿势** |
| 材质 | 资产原件 | 游戏已做 **per-actor 副本** |

**坑一：静止姿势的来源不能一刀切。** §4.11 把游戏骨的静止从 bindpose 改成读 transform，
理由是「prefab 永不被驱动」——对冷路径成立，**对热应用不成立**。实机表现：mod 从 OFF 打开后
回主页，身体定死在某个姿势，进一次换装（走冷路径重建）才好。日志里两次建桥的差别就是答案：

```text
热应用   restDisagreements=52   ← 52 根全部与 bindpose 不一致 = 骨架在摆姿势
冷路径   restDisagreements=6    ← 只有 6 根拇指 = 骨架在静止
```

两个来源各有各的坏：transform 在静止时**完全正确**、在摆姿势时是垃圾；bindpose 与姿势无关、
但这副骨架上 6 根拇指差 33.46°。所以**按每次建桥判一次**（不是每根骨）：分歧超过 1/4 就判定
「活体在摆姿势」，整体退回 bindpose；否则用 transform。两种情形是 6/52 与 52/52，
离得足够远，不需要精细阈值。日志打 `restSource=transform` / `restSource=bindpose(actor was posed)`。

> 这个坑是**尺子先于结论**的一次实例：`restDisagreements` 是上一轮当"报警器"加的，
> 加的时候并不知道会用来抓什么，结果它直接把根因指出来了。

**坑二：材质还原不能靠指针身份。** `replaceMaterials` 换整个数组，而还原只在
`renderer == patch->patchedRenderer && !patchedMaterialKeys.empty()` 时才做——两个条件在这条路上
**同时为假**：patch 注册的是当初那次的渲染器（actor 早被重建），而**游戏会给它找到的材质再做一份
per-actor 副本**（`m_bdy(Clone) (Instance)`），指针对不上。实测 `slots=5 expectedSlots=2`。
活下来的信号是**槽位数量**：游戏从不改渲染器的槽位数，只有我们改。
（同数量替换 + per-actor 副本仍无解，那种情况要靠 `_BaseMap` 贴图引用匹配——引用能穿过副本。）

**坑三：销毁共享资源要看还有谁引用。** 代理容器建在被 patch 的那一侧，OFF 释放网格克隆时
prefab 可能还攥着它。修法统一成**先换、后销毁**：容器在渲染器骨数组换完之后才退休
（提前销毁会让游戏在自己的 LateUpdate 里走到已销毁 transform，**直接硬崩**，
Player.log 栈顶是游戏自己的 LateUpdate，我们的帧只是调用原函数那一层）。

### 4.13 一副骨架路线实机走通（2026-08-17，whole-object）

> ⚠️ **§4.13–§4.15 是对照组记录。** 下面量到的数字、机制和坑**全部仍然有效**，且其中几条
> （socket 从被替换资产照搬、`_H` 名字是工具链契约、"先证明在被解算再谈参数"）直接被
> target-rig 路线复用。作废的只有一条：**"该走 whole-object"这个路线结论**——它要求作者装
> Unity，违反基调。见 [`ab-target-rig-route-2026-08-17.md`](ab-target-rig-route-2026-08-17.md) §2。

**结论先行：`replaceWholeObject` + SDK 的 `IkRigger` = 动画、跳舞全部由 Unity 自己的 Humanoid
重定向负责，不需要任何手写桥。** 今晚为两副骨架写的桥、头挂点、Hips 位移、静止来源选择，
在这条路线下全部不需要。

**运行时零改动就走到了 IK 装配。** `replaceWholeObject` 是 manifest 里本来就有的能力：
加载钩子直接 `return modAsset`，游戏拿到的就是我们的 prefab，`BuildModel` 用它建 Avatar。
**不需要钩 `BuildModel`**——实测钩了也没用：override 在泛型 `VLDefaultActorController\`3` 上，
钩泛型定义的函数指针**零触发**（装上了 ≠ 会被调用，又一次）。

**第一次失败点是有名有姓的缺件，不是路线不通：**

```text
ArgumentNullException: Value cannot be null. Parameter name: transform
  at ActorAnimationFullBodyIKMovePart..ctor(animator, reference, target, skeleton)
  at CampusActorAnimationJob.CreateFullBodyIK → CampusActorAnimation.Initialize
```

而 SDK 的 `IkRigger.cs` **文件头注释逐字预言了这条报错**——它就是为解决这个而写的。
契约在 `CampusActorAnimationInitializeData`：`reference` / `hips` / `head` / `moveReference`
四个按身份绑的 transform + 左右手 `ActorAnimationIKCorrectionGoal` + `iKCorrectionColliders`。
出包时加 `-withGameRig` 跑 `IkRigger.Rig(root)` 即可，日志：

```text
[SDK] 补了 Reference 节点：root → Reference → Hips（原版结构）
[SDK] 1 根有权重的骨掉在 Reference 子树外面，已认领回去：+PelvisTwist CF A01 → Pelvis
[SDK] IK 装配完成: 4 goal + 4 hint + IKBody + LookAt + Move
weightsPreserved: True     ← 现有闸门顺带证明了这一步是纯加法
```

**whole-object 路径不走网格补丁，所以材质采用也不会跟过来**——身体会穿着
`GakumasSdk/BodyPlaceholder` 渲染（单 pass、只采 `_BaseMap`），表现是「近看糊、没描边」。
已在该路径补上同样的材质采用。

**「糊的时候颜色正常、不糊之后偏灰」不是 bug**：占位着色器只采 base，那是源模型原始贴图；
游戏着色器要按 t4(sdw) 混阴影、t1(def) 控 toon/smooth，而**源模型没有这两张图**，SDK 只能合成：
t4 = base × darken、t1 = 常量。全部 5 个材质都标成 `Cloth`（darken 0.45）→ 统一压暗、零变化 =
整体偏灰。旋钮在 `<model>.labels.asset`，属**作者侧调色**（Skin 0.78 / Metal 0.32 /
LeatherPlastic 0.59 各不同），改标注重出包即可。

**层：读到 `layer=12` 但 `moved=0`** —— 包里静态值是 0，Unity 导入时已经改过，所以运行时那次
抄层**什么也没做**，身体能显示不是它的功劳。记在这里防止把功劳记错。

**仍未解决：道具（麦克风 + 换装门帘）。** 两者都是 `mdl_prp_*`（`PropCurtain =
"mdl_prp_dresscurtain-normal-00_dresscurtain"`），**是同一个问题不是两个**。
> ⚠️ 一次不成立的排除：我用 `Geo_Body.skeleton.json` 的 151 个节点 diff 出「缺的只有 14 根
> `*_H` + 2 根 `Skirt_*_O`，没有道具挂点」——**这个结论无效**。那份 json 是**蒙皮骨列表**，
> 不是完整 prefab 层级；不参与蒙皮的挂点节点根本不会出现在里面。要用运行时把
> `originalResult` 的完整子树名字打出来再 diff。

### 4.14 whole-object 逐项收口实录（2026-08-17 凌晨）

接 §4.13。这一节记每一项**是什么坏了、真因是什么、修在哪一侧**，因为其中一半的真因
和两副骨架时期的直觉相反。

**道具（麦克风 + 换装门帘）= body prefab 上的 socket 节点，不是"场景物件受影响"。**
运行时探针 `LogWholeObjectContractGap` 把被替换资产的完整子树减去我们的，缺口是 8 个裸节点：

```text
RightHand1_E  LeftHand1_E            双手各一个
RightHand1_I  RightHand2_I           双手各两个
LeftHand1_I   LeftHand2_I
Reference1_I  Reference2_I           身体根部两个 ← 门帘挂这里
```

> ⚠️ **离线的骨架 json 结构上量不到它们**：`grep RightHand1_E Geo_Body.skeleton.json` = 0。
> 那份文件是**蒙皮骨列表**，socket 不带权重所以根本不在里面。用它得出"没有缺挂点"是
> 拿一把量不到的尺子说"量不到就是没有"。

修法是运行时**从被替换的资产上照搬**（名字不写进代码，位置是那具身体的）：原版有、我们没有、
且是**裸叶子**（只有一个 Transform 组件、无子节点）→ 按名字找父级、照搬 TRS 建出来。
"裸叶子"这条把服装摇物骨挡在外面。两个额外的坑：

- **根节点必须按"对应"而不是按名字匹配**：两边根名不同（`mdl_chr_atbm-cstm-0140_body` vs
  `mdl_chr_external_tpose_body`），所以父级是根的那两个 socket 全被跳过 → 门帘一直没修好。
  改成"源父级 == 原版根 ⇒ 宿主 = 我们的根"之后 `count=7→9`，门帘可拉动。
- socket 的局部位姿是照**原版宿主骨的坐标系**写的，直接抄会带上两边静止朝向差。

**手骨静止差 173–178°，而一副骨架下没有人吸收它。**

```text
hostRestDelta=[LeftHand1_E:178deg, RightHand1_E:173deg, ...]
```

两副骨架时期这个差**完全无害**——桥每帧用 correction 吸收，源模型的手歪 180° 也没人看得出来。
所以出包路径把 `AlignDrivenBoneAxes`（改网格+bindpose，属破坏性步骤）**写死为不跑**。
一副骨架下我们的手骨**就是**游戏的手骨，道具/IK/碰撞体直接读它的坐标系，178° 原样长在麦克风上。
开启后 `driven frames aligned: 40`，麦克风位置与朝向基本正确（仍有肉眼可见的残差待查）。

> **这是本轮最值得记住的一条**：同一个属性（源骨轴向）在两条路线上的定价**相反**。
> 凡是"两副骨架时期决定不做"的步骤，转到一副骨架都要**重新定价一遍**，不能沿用结论。

**物理：SDK 的三个 Rigger 一开就有，但姿势驱动器装了 0 个。**

```text
[SDK] 摇物装配完成: 27 条链 / 78 根骨（sleeve 4, ribbon 24, skirt 50）/ 3 chain / 30 静态碰撞体
[SDK] 胸部骨认领 2 根（改名 + 补尖端骨，网格权重不动）：+Breast L A01→LeftBust1_S
[SDK] 补了 Pelvis 节点：Hips → Pelvis → 双腿
[SDK] 骨架缺这些骨，对应姿势驱动器跳过: LeftArm_H, LeftArm_Roll_H, ..., LeftHand_H, ...
[SDK] 姿势驱动器装配完成: 0 个（原版每套 16 个必备 + 每片裙摆 1 个）
```

**`TwistAdopter` 与 `QuartzDriverRigger` 对同一批 `*_H` 的处理方式不一致**：前者"认领源模型
自带的扭转骨、**不改名**"（因为游戏运行时按**组件类型**收集），后者**按名字**找 `LeftArm_H`
再挂驱动器，于是一个都找不到。**运行时按类型、SDK 装配器按名字**——两边都没错，但拼在一起
就漏了 16 个必备驱动器。这正是"我们自己造的骨架要满足学马 70 根基础骨"这个判断的落点：
对游戏是"功能不能少"，**对工具链是"名字不能少"**。

摇物已能动但"很丑很突兀"——参数是按几何分类合成的，不是原版真值。
参考 [[buildmodel-hook-own-skeleton]]：同一角色不同衣服的 stiffness/pendulum 能差 100 倍，
参数不能跨服装抄。

**颜色偏灰 = 源模型缺 sdw/def 通道时的合成兜底，属作者侧调色。** 见 §4.13。

### 4.15 摇物：合成的摇物**根本没在被模拟**（2026-08-17，三轮参数全部作废）

**结论**：whole-object 的包里有 78 根 `ActorSwingDynamicBone` + 3 条 `ActorSwingChain`，游戏也把链收走了
（`native ActorSwing chain layers: object=Pelvis stats=3layers/24bones` 正是我们那三条），
但抽样的摇物骨**局部旋转 300 帧峰值 0.00°**——它没有被解算，只是被父骨带着走。

```text
Swing motion over 300 frames: bone=Bone_SleeveSA01_L peakLocalRotation=0.00deg — NOT SIMULATED
```

**在此之前做的三轮参数工作全部无效，且都不该做**：

| 轮次 | 改了什么 | 画面 |
|---|---|---|
| 1 | 530 套中位数 → atbm 自己的 106 根真值 | 无变化 |
| 2 | 锚点 Spine→Pelvis、逐层环半径、collisionMask | 无变化 |
| 3 | 角色缺格回退（76/78 根真正拿到真值和掩码） | 无变化 |

**三组实质不同的输入产生像素级相同的输出——这个模式本身就是「输入没被读」的证据**，
而我连着三轮在调输入。诊断顺序错了：**先证明系统在跑，再谈它跑得对不对**。

> 探针缺陷也记一下：第一版只盯 `bones.front()`，恰好是一根**袖子**骨，而按 atbm 真值袖子
> `chainHost=None` 本来就没有链——用一个样本给系统下了全局结论。已改成铺开采样 24 根、
> 报「几根动了 + 动得最多的是哪根」。

**为什么这个盲区能存在三轮**：运行时本来有一把 `LogSwingRegistrationCoverage` 专门量
「我们的骨有没有进游戏的 `swingDynamicBones`」，但它被 `HasModBonesUnder()` 挡着——那个判据
问的是「骨是不是**运行时创建**的」。whole-object 下骨在包里，**这把尺子一次都没触发过**。
已补一条无条件日志（`swingDynamicBones=` / `initialTransforms=`）。

**顺带一个硬崩，值得单独记**：那条无条件日志第一版顺手读了 `swingChainLayers`，
而这个字段**不在** `CampusActorAnimationInitializeData` 上（它在 `IActorAnimationRigData` 上）。
`GetValue` 按名字取不到时不报错、返回垃圾指针，解引用 → **游戏 loading 直接崩**。
教训：**按名字取字段前先对着 dump 核字段表**，这类调用没有失败信号。

**路线评价（重要，防止误判）**：物理不佳**不是 whole-object 的问题**，四条路线在这件事上是这样的：

| 路线 | 物理 |
|---|---|
| 老 AB（千咲） | 源模型**自带**摇物骨和链，改名保留即可 → 有效 |
| 双骨架代理 | **从未实现**（每次 armed 日志都写着 `physics=0`） |
| Unity+BepInEx | 同一个 `SwingRigger` → **同样不佳** |
| whole-object | 同一个 `SwingRigger` → 同样不佳 |

**这副 Claymore rip 没有任何物理元数据**（源目录只有 FBX + PNG，Genshin 导出时就丢了）。
所以这是「**给一个不带物理的源模型合成摇物**」这道独立的题，**换路线不会改善它**，
而退回双骨架或老 AB 会同时丢掉 whole-object 已经拿到的动画重定向、根位移、碰撞体、
道具挂点、相机取景、§12 量化验收。

**下一次碰这个问题时的正确起点**（不是参数）：

1. 读那条无条件日志的 `swingDynamicBones=N`。atbm 自己注册 106 根。
   ≈0 → 游戏没收我们的骨，查注册链路；≈178 → 收了但不解算，查 `active`/层结构/`initialTransform`。
2. 只有在确认「有骨真的在动」之后，参数、碰撞笼、限位才有讨论意义。

---

## 5. 已证伪 / 已作废的结论（防止重犯）

| 结论 | 判定 | 依据 |
|---|---|---|
| lossless AB 免对齐，作者不必逐根对齐 | **错**。免的是**位置**，**静止朝向必须一致** | §3.3 的机制 + §4.4 的位移 |
| `RestPoseNormalizer`（把骨静止旋转对齐原版） | **作废** | 重定向本来就抹平轴向 |
| 「肩半宽 17.4→12.6cm，需要肩部摆动矫正骨」 | **作废**，错误取样 | §2.2 |
| 认领扭转骨能改善肩塌 | **错**，前后 4.9% 不变 | §4.3 |
| 几何分类器已进入生产 | **错**，`swing_category_by_geometry` 只有测试调 | 生产走 `swing_category(name)` |
| 12 种驱动器作者侧已完成 | **错**，只接通 Skirt/Frill/HumanoidSleeve 三种 | |
| `audit_ab_rig` 的 G10 能证明 AB 动画角度 1:1 残差 | **错**，那是 SDK Avatar 的结论 | |
| `audit_ab_rig` 的「绑定姿势偏差」能挡姿势问题 | **错**，上臂实差 90.6° 时它报 0.0° | 实测 |
| 「workspace 54 个候选 blend」 | **错**，可证明的是 9 个归档条目，`B054` 是编号 | |
| 「SDK 侧 ChainClassifier 在 381 套原版上量过」 | **无对应实验记录** | |
| 「SDK 只写 3/32 材质属性，AB 全对」 | **删除** | |
| 代理路线下可以「认领源扭转骨接学马 driver」 | **错**，代理骨带前缀，游戏按名字找不到 | §3.4 |
| A-pose 协议 2 包失败 = A-pose 被游戏拒绝 | **错**，是 sidecar 只存蒙皮骨数组、`Hips` 不在其中 | `meshApplied=0`；协议 2 拆分后已修，A 包 `rootBoneIsSkinBone=false` 仍能解析 |
| 「T-pose Claymore 静态代理实机成功，来源比例被保留」 | **错**，包里是 `kth_ss202`（学马约定 rig），不是 Claymore | §4.5，Unity 报告 42066/172 vs bundle 9054/225 |
| 自洽 + 渲染对照两项过 = 测的是你以为的那个模型 | **错**，串包时两项都过 | §4.5；第三条尺子是「产物与产它的那次跑对得上」 |
| whole-object 是发布路线（§4.13 的转向结论） | **作废**，它要求作者装 Unity（带组件的 prefab UnityPy 造不出）——违反「作者只开 Blender」 | 2026-08-17；`unitypy-monobehaviour-layout-wall` |
| 双骨架 bridge 可以作为默认路线 | **错**，代理骨前缀是结构性的，游戏一切按名字找骨的机制都够不到它 → 物理与挂点要从零造。保留为特殊兼容模式 | §3.4；§4.15 四路线表 |
| 「补齐 70 根基础骨」能治麦克风 / 抖动 / 着色 | **错**，三者真因分别是 socket 位移未按骨长校准、接地 4.1cm + IK 常量按原版体型、源模型缺 t1/t4 通道 | §4.11/§4.14；均与骨数无关 |

---

## 6. 量测方法与已知的坑（今天最贵的一课）

### 6.1 验收必须三类证据，缺一不可

```text
自洽性    Σw · 运行时骨矩阵 · 来源 bindpose · 顶点   与  包内静止顶点   的位移
形状保真  最终出包网格  与  作者原始网格   同一世界空间下的位移
渲染对照  同相机/同焦距/同帧/同缩放的正面 + 侧面，与基准同帧对照
```

只做自洽性会被**烘烂但自洽**的包骗过（§4.5，67cm 的错误拿了 6.96cm 的分）。
形状保真遇到 Unity 拆点时不能按顶点序号硬比，要用 Unity 导入基准、稳定来源编号或表面距离。

### 6.2 六个会给出「看似合理的错数字」的坑

1. **游戏骨静止位置不能按层级累加 `localPosition`** —— 151 个节点里 57 个带非单位
   `localRotation`，累加会让任何带旋转的关节以下全错（把腿烘成劈叉）。
   **用 `bindPose` 求逆**，精确且不碰四元数手性。
2. **不能用 Blender 骨的 head→tail 当朝向** —— Biped 的 tail 约定会给出反向（Spine1 报 172.9°）。
   两边都用「本骨 → 人形子骨」的位移。
3. **Blender(Z-up) 的向量不能直接比 Unity(Y-up)** —— 过 `core._to_unity`（脊椎报 82.8°）。
4. **算游戏骨朝向别把全部子骨平均** —— 脊椎下面挂着一堆下垂的衣物骨会把方向拽反（报 154°）。
   只取人形子骨。
5. **`Quaternion.angle` 在 w<0 时给出 >180°** —— 必须折回 [0,180]（报过 269.6°）。
6. **对象缩放必须 apply** —— 不 apply 则每根新骨 `localScale=1.1` 沿链累乘（5 节 1.61 倍），
   实机是从身上射出去的长尖刺。

### 6.3 导出侧两条必守

- **交换左右之后，必须把全部人形骨映射显式写进 `bone-remap.json`。** 插件的
  `build_bone_remap()` 自己去读预设文件，不知道外部脚本做过交换；只写扭转认领会两边打架，
  装饰骨的 `parentName` 跟着算错（袖口新骨飞 0.78m）。
- **不要按材质名丢网格段。** miHoYo 的 `Mat_Hair` 图集里连着整条腿，删完 UpLeg 零权重。
  可用判据是结构的：主导骨属于 Head 锚点装饰组 → 直接删；主导骨是 Head 本体 → 只删材质属于
  发图集的面。

---

## 7. 工具与代码现状

### 7.1 已修

- `tools/verify_ab_package.py:241` **新骨被数了两遍**：顶层 `extraSwingBones` 与
  `sourceRigRemap.newBones` 是同一批骨的两份视图。任何带新骨的包都被判「骨名重复」、
  节点数虚高——**已发布的 `hmsz-fuyuko-icu` 成品也 FAIL**（报 292，实际 192）。
  违反项目自己「坏样本会报、正常样本不误报」的不变量。已改，6 个单测全绿。

### 7.2 缺陷与缺口（按性价比排）

| 项 | 状态 |
|---|---|
| 运行时空引用只 warn 后继续（`ModRuntime.cpp:779/756`），且 `AddComponent` 在 743 早于引用循环，748 已有半初始化组件泄漏 | 必须改成 **AddComponent 之前预检、缺任一必需引用整体拒绝** |
| 映射没有 `via` 来源标注 | 72 根静默塌 Hips 的骨和真映射长得一模一样，排错要靠 dump JSON |
| 表单按「有没有填目标」报警 | 装饰骨没有目标是**正常状态**，57 行全在喊 |
| 结构分组（锚点 + 链）未进生产 | `group_key()` 仍按名字剥 left/right，日语/中文/乱码全废 |
| `swing_category_by_geometry()` 未进生产 | 只有测试调 |
| `simulate_ab_skinning.py` 用旧路径数学 | 验不了 lossless |
| `native_driver` / `_form_driver_categories()` | 作者不知道其存在、从没用过；且把选择压成全局类别集合（一行选 skirt，全模型 skirt 骨跟着走）。建议**删除** |
| `material_presets.json` 的 `metal` 行 metallic 0.75 | 来自**头饰**；原版 **body 实测 t1.B = 0.000**，金属 body 室内混暗环境探针**渲成黑**。Unity 侧已修正，AB 侧未改 |
| `bone_remap_presets.json` 的 `*_Roll_H` 目标 | 只有 mmd-standard 有 16 条（未提交）；其余 7 张全 0；**SCSP 预设还显式把 18 根扭转/锁骨骨塌进人形骨** |

---

## 8. 从 Unity SDK 能搬什么

Unity 侧 `SdkPipeline.Shape()` 的八步（有序）：

```text
1  TPoseBaker.AlignDrivenBoneAxes   无条件。40 根驱动骨转到原版静止坐标系
2  HelperBoneRigger (stockJointRig)  默认关（破坏性，重画权重）
3  SwingRigger                       先找 `_S` 命名，没有才用 ChainClassifier 几何兜底
4  IkRigger                          10 个 IK 锚点（CreateFullBodyIK 缺了会挂死）
5  TwistAdopter                      扭转骨认领
6  QuartzDriverRigger                姿势驱动器
7  BreastRigger                      胸部驱动
8  ComponentTransfer                 源组件搬运
```

### 8.1 能搬的（代码/常量/实测数据）

| 内容 | 要点 |
|---|---|
| **`TPoseBaker.Turn()`** | 换骨的表达坐标系：**子骨保世界变换、网格零位移、只重算这根骨的 bindpose**。这是 additive 操作，和「烘 T-pose」（会改几何）是**两件事**，混淆会把网格搞歪 67cm |
| **`DrivenFrames`** | 40 根驱动骨的 (forward, up) 常量表，60 套服装实测 spread ±0.000；手指跟自己那条手臂的 frame，拇指自己一套、绕掌心滚 45° |
| **`TwistAdopter`** | 纯加法、不改名不改权重。**注意代理路线下失效**（§3.4） |
| **`BreastRigger`** | 胸骨接 `*Bust1_S` |
| **`SwingColliderCage`** | 两条规矩：**never blend**（每行照抄某套真实服装的真碰撞体，不混参数）+ **cover all**（哪些骨有碰撞体跨服装取并集） |
| **`IkRigger`** | 10 个锚点的布局。AB 复用原版 prefab 时不需要；**新增 Renderer 或换 prefab 时必需** |
| **`ChainClassifier`** | 三信号几何分类，按可信度排序，一个骨名不读 |
| **`SurfacePresets` 的修正** | 见 §7.2 的 metal 行 |
| **`GakumasVertexColor`** | COLOR 四通道高低 nibble 语义（描边色/宽度/t7 行/rim） |

### 8.2 方法论（比代码值钱）

1. **`PreviewRenderer` 的那句注释**：
   > 闸门全绿而画面不对，是因为我一直在看数字。作者更是——度数、权重占比、骨数对他没有意义，**一张图有**。

   AB 侧至今只有黑白正交剪影。2026-08-16 那轮六次进游戏，根因就在这。
2. **`AvatarBench`：进游戏前先离线量死。** Unity 靠它一次量死 69°。
3. **`ComponentTransfer` 的教训**：源自带 rig 就搬源的，别用中位数猜——
   > Six of this route's bugs came from guessing values the source already had.

   中位数与源作者调好的值差最多 **7 倍**（mass 0.1 vs 0.7、spring 0.8 vs 0.3、limitX ±3 vs 锁死 0）。
4. **前端/后端分离**：后端是产品（游戏要什么），前端是作者碰巧有什么源。
5. **每步幂等 + 默认加法**：`Shape()` 每步「输入已带就跳过」；唯一破坏性的那步默认关，
   注释写清楚为什么。
6. **翻案顶在文件开头**：`corrective-helper-rig.md` 第一行就写「先读这段，下面的前提是错的」；
   `rest-pose-dead-end.md` 整篇记的是一次**方法失败**。AB 侧文档缺这个习惯。

### 8.3 不搬

`HelperBoneRigger` 合成矫正骨（破坏性，属作者 DCC）、`HumanoidBridge` 的实现（依赖 Unity）、
`RestPoseNormalizer`（已证伪）、12 类 driver 自动安装、独立 Avatar/prefab/bundle。

---

## 9. 作者的真实成本（唯一作者，2026-08-16 逐条核对）

痛点排序（作者原话）：

1. **权重最麻烦**——手部调参手指变长/扭曲；**A→T 之后肩膀变小崩坏**
2. 贴图/描边/光照/材质已有一整套自建模拟流程「大体是对的」，但想要真实的外部贴图→学马贴图转换
3. 骨架几乎每个 mod 一开始都绑错，但很明显，调几次就对

两条关键事实：

- **A→T 是作者手工在 Blender 里转的，肩膀崩坏在 Blender 里就看得见**，不是导出/游戏侧问题。
- **作者不是用源权重，是从原版身体转移权重**，所以必须先在 Blender 世界坐标里把网格贴合
  （手工挪 + 缩放）。手指的骨映射本身是对的，问题在贴合精度。

**这解释了为什么作者一直在做「对齐」**：当前发布路线（§3.3）确实要求它。
代理路线（路线图 §3.3）如果成立，才能免掉全身贴合，只留头颈接口。

装饰骨的真实体验：fuyuko 表单底部「还有 57 个骨没指定目标」；chisaki 的 MMD 裙子
**作者手动点了几十次「跟裙摆」**。而且骨名可能是日语、中文或乱码——**任何基于名字的方案都不接受**。

作者不知道 `native_driver` / `_form_driver_categories` 的存在。

---

## 10. 被本文取代的文档

以下 9 份 2026-08-16 先移入 `archive-2026-08-16/`、**2026-08-20 从工作树删除** —— 结论早已收进
本文和路线文档，留在目录里只会让人以为它们还管事。**里面的原始数据仍然可取**，逐份从标签
`archive/research-2026-08-20` 拿：

```bash
git show archive/research-2026-08-20:research/archive-2026-08-16/ab-route-v2-full-record.md > /tmp/x.md
git checkout archive/research-2026-08-20 -- research/archive-2026-08-16/   # 整批取回
```

结论一律以本文和路线图为准；下表是每份里**还值得查的原始数据**：

| 文档 | 里面还值得查的 |
|---|---|
| `ab-current-truth-and-generalization-plan-2026-08-16.md` | 状态词表（已并入 §1）、旧文档逐份取舍 |
| `ab-plan-review-conversation-2026-08-16.md` | 评审过程、作者澄清原文 |
| `ab-route-v2-full-record.md` | **IDA 逆向地址、原版扫描数据、失败样本、复现命令** |
| `ab-v2-plan.md` | P0–P5 的历史落地记录、不变量的推导过程 |
| `ab-sdk-independent-review-2026-08-15.md` | 19 根必需骨、driver 引用依赖差异的原始推导 |
| `ab-bindpose-component-transfer-classifier-review-2026-08-16.md` | bindpose 重定向数学的推导 |
| `ab-author-cost-reduction-2026-08-16.md` | 作者成本的原始访谈记录 |
| `source-rest-claymore-experiment-2026-08-16.md` | **三轮受控实验的完整数字、逐材质逐骨误差、可交互 blend** |
| `source-proxy-runtime-test-2026-08-16.md` | 协议 2 的实现细节与安全边界 |

`unity-humanoid-avatar-sdk/` **不归档**——它是一个在用的 Unity 工程，其 `HANDOFF.md`、
`docs/corrective-helper-rig.md`、`docs/rest-pose-dead-end.md` 是 §2、§3、§8 大量数字的原始出处，
必须跟代码放在一起。

---

## 11. 当前仍然有效的不变量

1. 一根骨只能有一个主要求解器（同一个 Transform 每帧只能有一个最终写入者）
2. 不向游戏的并行初始化列表随意追加
3. body / face / hair 的骨名在共享命名空间内唯一
4. 256 是复杂度预算 warning，不是已证明的硬上限
5. bindpose、骨序、权重索引和 Renderer 空间必须自洽
6. 日志声称做过的事必须能从实际产物或活体读回验证
7. 破坏性改名、改姿势、改权重必须可见、可关、可量化、可撤销
8. 新检查必须同时证明「坏样本会报」和「正常样本不误报」
9. **实机验证一次只改变一个主要变量**（2026-08-16 违反过，导致三轮结果不可归因）
10. 共享文件、贴图、骨名和缓存必须按模型/部件限定作用域
11. 低可信推断不得自动变成已确认事实
12. 源数据、推断结果和作者覆盖必须能够区分和追溯
13. **动手前先 grep `research/` 和记忆索引**：源模型名、目标资源名、机制关键词。
    已有量化结论的不要重新用实机去测
