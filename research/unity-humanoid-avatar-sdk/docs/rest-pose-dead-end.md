# 外部模型的骨架姿势：现状、死胡同，和我的思维误区

> 2026-08-14。这份文档不记录成果，记录一次**方法上的失败**：五次进游戏、三个互相矛盾的
> 结果，全都来自一个从没被验证过的前提。写下来是为了让下一个人（或下一次的我）不要重走。
>
> **2026-08-14 晚补：§5 那个前提已经验掉了，答案在下面 §零。往下读之前先读它——
> §2/§3 的推断有一半是错的，留着是为了记录当时怎么想的。**

## 零、答案：身体是纯 Humanoid 肌肉驱动（离线证据 + 离线台架）

### 证据一：clip 里根本没有按骨路径写的曲线

游戏自带的 `gakumas_Data/data.unity3d` 里就有身体动作 clip，UnityPy 读 typetree 即可：

| clip | binding classID | path | attribute | Rotation/Position/Euler 曲线 |
|---|---|---|---|---|
| `mot_all_chr_cmn_idle-001-add_lp_b`（身体） | **95 = Animator ×130** | 全 0 | **7…136**（root/IK goal/95 条 muscle 的编号空间） | **0 条** |
| `mot_all_chr_cmmn_facial-default-000_in_f`（脸，对照） | 137 = SkinnedMeshRenderer ×84 | 骨路径 hash | 属性名 hash | 0 条 |

对照组存在的意义是证明读法没问题：两类 binding 长得完全不同。
**身体没有一条按骨路径写的曲线，全部走 Avatar 肌肉重定向。**

旁证（dump.cs 3.2.0）：`AnimationData` 带 `AvatarMask` / `applyFootIK` / `applyPlayableIK`；
游戏自己的动画 job 用 `AnimationHumanStream` + `MuscleHandle`（脖/头/脊/眼逐条）+
`AvatarIKGoal` + `HumanPoseHandler` —— 这些在 `isHuman=false` 时根本跑不起来。

所以驱动链是：

```
MotionDefine → AnimationData{clip, mask, footIK} → AnimationClipPlayable → PlayableGraph（无 Controller）
  → Animator(isHuman) 把肌肉值经 Avatar 反解成各骨局部旋转
  → job 层（LookAt / JointLimit / IK / HipCorrector）再改 human stream
  → 摇物/裙摆/头发完全不在动画数据里，靠 Swing/QuartzDriver 组件自己算
Avatar = CampusActorController.BuildAvatar() + GetHumanDescription(HumanBone[], SkeletonBone[])，
         运行时按 HumanBodyBoneMapDictionary（HumanBodyBones→Transform，**按骨名**）现建。
         530 套服装骨架各不相同，SkeletonBone[] 不可能是固定表 → 只能来自我们自己那副骨架。
```

**推论：我们出包时模型摆的什么姿势，就是游戏告诉 Unity 的静止姿势，每条 clip 都相对它播。**

### 证据二：离线台架把实机现象复现出来了

`Editor/AvatarBench.cs`（菜单「台架：离线复现游戏的 Avatar 驱动」，或 batchmode
`-executeMethod GakumasSdk.AvatarBench.RunFromArgs`）。按游戏同一张骨名表
`AvatarBuilder.BuildHumanAvatar`，量两件事：① 出包静止姿势 vs 标准 T-pose；
② 给参照模型和候选模型灌**同一组肌肉值**，比四肢朝向。参照用 `chs-sucu-00`（实机已验证可用）。

Genshin `mdl_chr_external_body` 的结果：

| 探针 | ① 静止 vs T | ② 驱动后 vs 参照 |
|---|---|---|
| 躯干 | 2.6° | 1.6° |
| 左/右大臂 | **69.1° / 67.4°** | **69.1° / 67.4°** |
| 左/右小臂 | **64.7° / 60.2°** | **64.7° / 60.2°** |
| 四条腿骨 | 2.6°–9.3° | 1.9°–8.8° |

**①②两列一位小数都不差**，这一条就把话说完了：

- **骨轴向对动画没有任何贡献** —— 那副 Biped 的 Z-up 轴向被重定向完全吸收了；
- **实机上的全部误差 = 静止姿势的 A/T 之差**，一度不多一度不少；
- 躯干和腿没事、只有手臂坏，是因为只有手臂两边指向不同（原版手臂 ±x 摊平，
  这副垂在身侧）—— 和实机第二版看到的完全一致。

对照组 `chs-sucu-00` 自己的静止姿势是 0.8°–4.0° 的标准 T-pose，这也是「什么叫合格」的标定。

> **2026-08-14 晚再补：§零「骨轴向零贡献」只对*身体*成立，有一个例外。**
> 头发和脸不是蒙皮到 Head 的，是 actor build 把它们**挂在 Head 底下当子物体**
> （`.../Neck/Head/Head_Hair/...`）。子物体直接继承父骨的世界旋转，这条路上没有 Avatar，
> 重定向管不着。那副 Biped 的 Head 静止朝向是 +Y 朝前 / +Z 朝左，实机量出头发和脸整个
> 转了 **121.7°**（三个原版角色彼此只差 3°），离线从包里量出 121.5°，同一个数。
> 修法不是把 `RestPoseNormalizer` 请回来，只需要 `TPoseBaker.AlignHeadAxes()`：单转 Head
> 一根，子骨保世界变换、只重算 Head 的 bindpose，网格零位移（bindpose 体检仍是 0/172）。
> 闸门在 `audit_body_bundle.py`：Head 静止朝向偏 >15° 判不合格。

### 这推翻了什么

- **`RestPoseNormalizer` 那条路（把骨的静止旋转数值对齐原版）整个是错的。**
  重定向存在的意义就是抹平轴向；作者最早那句「能映射成 Humanoid 就不该有 Y/Z 基准问题」是对的。
- 唯一要做的是**把模型烘成真 T-pose 再出包**（摆姿势 → 应用为 rest → 重算 bindpose），
  §3 结尾猜的「A→T 姿势匹配后重新绑定」方向对，但理由不是「游戏直写局部旋转」，
  而是「Avatar 拿我们的静止姿势当基准」。

### 已实施（同日）：烘 T-pose，删归一化

`Editor/TPoseBaker.cs`：把四肢摆到标准 T（`FromToRotation` 逐骨对准，父先子后），
然后**把蒙皮一起烘上去**——顶点按 `Σ wᵢ·(rendererW2L · boneᵢ.LTW_new · bindposeᵢ_old)` 重算，
bindpose 换成新静止姿势。只做后半（重算 bindpose）是陷阱：骨架站成 T、网格留在 A，
而且离线全绿——这正是当初「体检绿了三次实机坏了三次」的同一个坑。

外部模型实测（`Import()` 里替掉原 `RestPoseNormalizer.Apply`，在写 mesh 资产之前）：

| | 台架① 静止 vs 标准 T | 台架② 同肌肉值 vs 参照 |
|---|---|---|
| 烘之前 | 大臂 69.1°/67.4°，小臂 64.7°/60.2° | 同左，一位小数不差 |
| **烘之后** | **手臂腿全 0.0°，整体 2.6°（脊椎弧度）** | **手臂 0.0°**，膝 3.7°（比例差异），整体 3.7° |

顺带把「带不带归一化」的对照做了：**同一副模型，带 `RestPoseNormalizer` 与不带，
台架两列读数完全一致**。所以已删除
`Editor/RestPoseNormalizer.cs`、`tools/export_target_rest_pose.py`、`reference/target-rest-pose.json`，
`SdkPipeline.Shape()` 的 `normalizeRestPose` 参数也一并去掉。
`tools/audit_body_bundle.py` 里那条「静止朝向对照原版旋转值」换成了「静止姿势是不是 T-pose」——
旧判据不但没意义，还会把**修好之后**的模型判成坏的（它轴向仍是 Biped）。

### 还没验的两件事（别当成已知）

1. **第一版为什么是躺倒悬空**，没有实测。台架显示轴向不影响驱动，所以「Avatar 建失败 →
   一帧动画都吃不到 → 停在包里的 Z-up 静止姿势」只是最省事的解释，没有证据。
   真要查：把那一版拿来跑台架，看 `isValid/isHuman`。
   —— 修完 T-pose 之后如果不再出现，就不必查了。
2. **只查了 data.unity3d 里的两条通用 idle**，live/舞蹈 clip 在下载包里没查过。
   拿到解密的 motion bundle 用同一段脚本复查一次即可（判据：binding 的 classID 是不是 95）。
3. 台架现在拿 `chs-sucu-00` 当参照（实机验证过，但仍是我们造的包）。
   把一套原版 body 导进工程当参照会更硬。

## 一、现状

外部模型（Genshin `Avatar_Girl_Claymore_MarionetteNew`，Biped 骨架、零 rig）除了**骨架姿势**
这一环，其余都通了：

| 环节 | 状态 |
|---|---|
| 骨名桥（Unity Humanoid 映射 → 学马命名） | ✅ 52 根映射，补 Pelvis，去重 |
| 几何链分类（不看名字判裙/袖/饰品） | ✅ 12 条链，实测判对 |
| 贴图（源只有 Diffuse → 合成 t1/t4） | ✅ |
| 顶点 COLOR / 材质 / 组件 / 打包 | ✅ 离线体检全过 |
| **骨架姿势 / 骨轴向** | ❌ **卡住** |

试过的三版，三种坏法：

| 版本 | 结果 |
|---|---|
| 不做归一化 | 整个人躺倒 + 悬空 |
| 52 根身体骨全部对齐到原版静止朝向 | 躯干**完全正常**，手臂往后拧，腿废掉 |
| 只对齐 Hips | 回到躺倒 + 悬空 |

## 二、思维误区之一：从没验证「游戏怎么驱动身体」

作者的推理是对的，而且是这份工作本该有的起点：

> 只要能正常映射成 Unity Humanoid，就不该出现 Y 基准 / Z 基准的问题。

**Humanoid 重定向的全部意义**就是抹平骨名、骨轴向、静止姿势三者的差异：动画作者在任意一副
humanoid 骨架上做的动作，可以播到任意另一副上。如果这条路成立，我对骨轴做的一切都是白费功夫，
而且不该有任何效果。

但实测三版互相矛盾：不归一化会躺倒（说明骨轴**有**影响），全归一化又让手臂拧掉
（说明它不是简单的轴向问题）。**两个现象都和"纯 Humanoid 重定向"不相容。**

合理的解释是：这个游戏（至少部分地）**把动画曲线按骨路径直接写进骨的局部旋转**，而不是走
肌肉空间重定向 —— 旁证是它的动画走 PlayableGraph、没有 Animator Controller
（见 [[gakumas-actor-runtime-structure]]）。若如此，模型必须和原版**同一套静止姿势**，
不只是同一套轴向。

**但这仍然是推断。我在没有验证机制的情况下，凭症状来回改了三版，让作者跑了五次游戏。**
这才是真正的错误：症状驱动，正是这个项目几周前就明确放弃过的做法。

## 三、思维误区之二：把「轴向」和「静止姿势」当成一回事

它们是两件事，而且实测数据把这点戳得很清楚（我们的模型 vs `hmsz-cstm-0059`，
骨指向其子骨的方向夹角）：

| 骨 | 我们的朝向 | 原版朝向 | 夹角 |
|---|---|---|---|
| Hips / Spine / Spine1 / Spine2 / Neck | 竖直向上 | 竖直向上 | 2°–14° |
| 双肩 | 侧向 | 侧向 | 17°–21° |
| **双腿全部（UpLeg/Leg/Foot）** | 向下 | 向下 | **2°–20°** |
| **大臂 / 小臂 ×2** | **垂在身侧**（y −0.92） | **向两侧张开**（x ±1.00） | **60°–69°** |

一根骨的静止旋转，**只有和它实际指向配在一起才有意义**。把一根指着下方的手臂骨赋予"指着侧方"
那套轴向，就是让骨的指向和它的轴脱节 —— 动画一旋转就拧成麻花。这解释了为什么
「全对齐」会坏手臂，也解释了为什么躯干和腿在同一版里毫发无损（它们两边指向一致）。

所以「全部对齐」和「只对齐 Hips」都不可能对。真正需要的若是姿势层面的对齐，那就是
**A-pose → T-pose 姿势匹配后重新绑定蒙皮**，不是改几个旋转数值。
[[mmd-ab-oneclick-remap-route]] 里早就写过「全骨架 A→T retarget 才是主工作量」——
我有这条记忆，却没在这里想起来。

## 四、思维误区之三：把「sucu 能成」当成管线通了

IP 的 `chs-sucu-00` 一路顺利，我把它当成"管线打通"的证据。其实它只是**恰好绕过了这个问题**：
它和学马同属一套中间件，静止姿势本来就一样。真正的外部模型一进来，这一环立刻暴露。

一个只在"源和目标碰巧同构"时成立的管线，不算通用管线。

## 五、下一步：先测机制，不要再出包

> **已办（见 §零）**：机制是**肌肉重定向**，而且离线就测出来了，一次游戏都没跑。
> 按这一节自己写的分叉，走这条就意味着「`RestPoseNormalizer` 应当整个删掉」。
> 下面保留原文。

在弄清楚下面这件事之前，任何对骨架的改动都是碰运气：

**游戏播身体动画时，走的是 Humanoid 肌肉重定向，还是按骨路径写局部旋转？**

可测，而且只要一次运行：

1. 探针 dump 当前播放的 clip 是否 `isHumanMotion`（humanoid clip 走肌肉，generic clip 走曲线）；
2. 或者更直接：运行时读一个**原版**角色的 `Animator.avatar` 与某根身体骨的局部旋转，
   和它在包里的静止值比对——再对我们的模型做同样的事，看两者的差异模式是否一致；
3. 附带确认 `BuildAvatar` 是用我们骨架的静止姿势建的，还是用一份固定的 HumanDescription。

结果决定走哪条路，而且两条路互斥：

- **走 Humanoid 重定向** → 骨轴向根本不用管，该查的是 Avatar 建得对不对
  （T-pose 配置、`isHuman`、55 根骨是否全映射）。**RestPoseNormalizer 应当整个删掉。**
- **走曲线直写** → 必须做真正的姿势匹配（把模型摆成原版静止姿势 + 重算 bindpose），
  改轴向数值这条路彻底放弃。

## 六、给下一个人的教训

- **症状驱动会让你在三个都错的版本之间来回跳。** 三版三种坏法，看起来像"接近了"，
  其实是同一个未验证前提的三个投影。
- **"我们这版能跑"不等于"管线通了"** —— 先问它是不是碰巧绕过了问题。
- 离线体检能挡住的只是"文件里看得见的错"。这一轮体检从"全绿"到实机躺倒发生了两次
  （先漏旋转，后漏位置），第三次全绿又是手臂拧掉 —— **体检绿不代表对，只代表我还没想到该查什么。**
