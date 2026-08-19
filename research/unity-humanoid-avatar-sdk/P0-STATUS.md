# P0 status — Windows Unity/BepInEx Avatar route

> **接手先读 [HANDOFF.md](HANDOFF.md)** —— 那份是自足的交接文档（架构、目标侧事实、代码在哪、
> 怎么跑、闸门清单、已证伪的结论、没做的部分）。本文件是时间序的会话记录，用来查"某件事是哪天
> 怎么定下来的"。

更新时间：2026-08-14 深夜（会话交接）

## 结论翻案：`*_H` 骨是扭转分配，不是防肩塌（读 il2cpp 定的）

`D:\GIT\gkms-localify-ios\workspace\3.2.3\inspector\cs\il2cpp.cs`：

| 骨 | 驱动器读什么 | 作用 |
|---|---|---|
| `Arm_H` −0.8 / `Arm_Roll_H` −0.3 | MuscleHandle **41/50 = Arm Twist In-Out** | 上臂扭转分配 |
| `ForeArm_Roll_H` 0.5 / `Hand_H` 0.9 | **43/52 = Forearm Twist In-Out** | 小臂/腕扭转分配 |
| `UpLeg_H` −1.0 / `UpLeg_Roll_H` −0.6 | **23/31 = Upper Leg Twist In-Out** | 大腿扭转分配 |
| `ForeArm_H` / `Leg_H` | RotationBone，参考同侧 ForeArm / Leg | 肘/膝半角 |

**这个游戏没有肩部摆动矫正骨。**「肩半宽 17.4→12.6cm、需要矫正骨」整套说法作废，
那是用错误取样量出来的。52 骨缺的是**扭转剪切 + 肘膝硬折**，与静止姿势是 A 还是 T 无关。

另外 `CampusActorAnimationInitializeData` 用 `List<组件>` 收集驱动器——**按组件类型，不按骨名**，
只有 `reference`/`hips`/`head`/`moveReference` 是按身份绑的。所以认领源模型自带的扭转骨
**不需要改名**，挂上组件即可，是纯加法。

## 路线修正：管线改成「加法层」，破坏性步骤全部退成可选

作者的判断（对的）：一直在打补丁，是因为管线在**破坏性改写源模型**。按这个轴重新划过：

| 步骤 | 性质 | 现状 |
|---|---|---|
| 名字桥 / 必需节点 / 材质贴图 / 摇物几何分类 | **加法**（只加节点和组件） | 保留，默认开 |
| T-pose 烘焙 | 改写网格 + bindpose | **改成先校验**：源本来就是 T 就一个字节都不动 |
| 骨坐标系对齐（40 根） | 改写骨的表达系 | **退成可选**，跟矫正 rig 绑定 |
| 关节矫正 rig（建 `*_H` + 重分配权重） | 改写作者权重、截断到 4 骨 | **退成可选，默认关** |

后两条是绑定的：矫正骨要有权重才有用 → 必须重分配权重；驱动器系数按骨自身轴写 → 必须对齐坐标系。
拆掉矫正 rig，坐标系对齐就失去全部意义（重定向本来就吸收轴向，台架早证过）。
入口：`SdkPipeline.Shape(..., stockJointRig: true)` / 菜单「前端 C：…+ 关节矫正 rig（会改权重）」。

代价说清楚：大角度关节按线性蒙皮塌陷（肩半宽 17.4→12.6cm）。那是**绑定权重的活**，
属于作者在 DCC 里做的事，不该由转换器猜着改。

**与源模型的契约**：给一副 T-pose 的 FBX，管线对网格的改动是**零**。
这副 Genshin rip 是 A-pose，所以烘焙仍会跑（摆正 28 根骨）。

## 最新一轮：装上原版的关节矫正骨，删掉反解补偿

外部模型（Genshin rip）的肩塌、手腕折、裙子破皮是同一个东西的三个投影：
`TPoseBaker` 里那个按姿势预畸变的反解补偿，以及它必须切的部位边界。
**真正的根因是缺件**：原版 530/530 套 body 都把关节权重挂在 `*_H` 矫正骨上（全身 17% 权重），
我们一根都没装。详见 [`docs/corrective-helper-rig.md`](docs/corrective-helper-rig.md)。

- 新增 `Editor/HelperBoneRigger.cs`（建骨 + 折回源扭转骨 + 按原版剖面重分配权重）+
  `tools/measure_helper_rig.py`（尺子，530 套现测）；补偿已从 `TPoseBaker` 删除。
- 闸门加在 `audit_body_bundle.py`：矫正骨必须在、必须承重、肩/胯关节人形骨占比 ≤ 20%。
- 两个包都已重打并通过体检；台架不变（静止 2.6°／驱动后 3.7°）。
- 这条闸门顺手抓到 `chs-sucu-00` 的胯 100% 压在人形骨上（IP 的 rig 没有 `UpLeg_*_H`），已补装。
- 第一版实机**一条胳膊拧了过去**：驱动器系数按骨自身轴写，原版左右能共用同一系数是因为
  原版左右骨架本身镜像，而这副 rip 两侧同坐标系（实测右侧正好差 180°）。已加
  `TPoseBaker.AlignDrivenBoneAxes()`（8 根骨转到原版坐标系，零位移）+ 对应闸门。
- 裙子**整个前片和后片一直是焊死的**：`ChainClassifier` 只在「父骨不是衣物骨」处起链，
  于是挂在衣物骨下的**分叉被整支孤立**（前片挂 `Bone_SpineTwist01_M`，后片挂 `Bone_BowknotC01_M`），
  19% 的全身权重没有任何摇物组件。修 `Continues()` 后链数 12 → 26、摇物骨 42 → 76。
  同时补了两件：腰高向下垂的链一律判 skirt（否则 collisionMask −1 去撞 23cm 的胯胶囊），
  裙摆驱动器改为按几何挂（原版按 `*Skirt_A` 命名，任何 rip 都不匹配）0 → 16 个。
- 闸门加了「垂到胯下、没人驱动的衣物链权重」（原版 0.00%），**已在坏包上验过会报 4.4%**。
- **那一版实机硬崩了（21:42，换装后 2.6 秒，无 dump 无托管栈）**，两处都是这版新造的重叠：
  ① 按几何挂的 16 个裙摆驱动器落在链的第 0 根骨上，而那根骨同时是摇物骨——
  原版 60 套 327 个裙摆驱动器**零重叠**（驱动器在 `_A` 锚点，摇物链从 `1_S` 起）；
  ② 矫正骨改到摇物之前建以后，`SwingColliderCage` 里那两条写着 `LeftArm_H`/`RightArm_H` 的
  碰撞体第一次真的挂上去了，正好压在手臂驱动器上——原版静态碰撞体挂在人形骨上，`_H` 出现 0 次。
  已改：①改为跳过（要挂必须在摇物装配**之前**插锚点骨，之后再改父子会让摇物抓好的局部变换失效）；
  ②碰撞体改挂 `LeftArm`/`RightArm`。闸门加「一根骨不得同时挂 DynamicBone/StaticBone 与 QuartzDriver」，
  **在崩溃包上验过会报 18 根骨**。
- **右手撕开**：轴向对齐上一版只做了 8 根肢体骨，手和手指没做——两只手同坐标系，
  一侧的手指肌肉被镜像作用。新工具 `tools/replay_runtime_pose.py` 把探针记录的实机姿势
  灌回出包网格离线重放，510 个面积爆裂 4× 的三角里 **280 个在右手、左手 0 个**；
  把 `_H` 骨钉回静止再跑一遍是 513 个（**不是矫正 rig 干的**）。
  已把对齐范围从 8 根扩到 **40 根**（+手+手指×2，原版 60 套实测离散 ±0.000），闸门同步扩。
- 残留：腰部 `+PelvisTwist CF A01`/`Bone_SpineTwist01_M` 与 Spine 之间还有 ~44 个爆裂三角
  （源自带的扭转骨在这边没人驱动），比右手小一个量级，未处理。
- **未验**：驱动器是运行时组件，离线跑不了，肩到底回来多少、裙子摆得对不对只能进游戏看。

---

（以下为 08-14 上午的记录）

## 交接：新会话从这里开始

### 结论先行：画面已经基本正常，但路线要换

`chs-sucu-00` 装在 `hmsz-cstm-0059` 上，换装 / 学园 / 撮影 / live 四个场景都不崩、颜色正常、
裙子不穿模，只剩前裙片偏硬（源模型那三片只有 1 根活动骨，是骨数不够，不是参数没调对）。

**但这是手调几个小时换来的，且换一件衣服要重来一遍。**
根因是我们在按「530 套的中位数」重建一套 rig，而源模型自己就带着作者调好的 rig
（42 根动态骨含 20 个字段、12 个碰撞体、胸部驱动、10 个 IK、22 个姿势驱动），
两边还是同一套 VL 中间件、7 个类名完全一样。

→ **已改为「组件搬运器」：不再按中位数猜，直接搬源模型自己的 rig。**
分析、字段对照表和实施结果见 [`docs/component-transfer-route.md`](docs/component-transfer-route.md)。

**搬运版已实机验证通过（2026-08-14 06:24 的包）**：物理表现正常，裙摆/翅膀/飘带/胸部全部正常，
无崩溃。这是第一个「还原源模型手感」而非「按中位数重建」的包。

过程中修掉的两处，都是**目标侧的通用规则**，不是给这个源打的补丁：

| 症状 | 规则 |
|---|---|
| 进换装硬崩（`UnityPlayer+0x143EF86`，与之前那次同一偏移） | **一条骨脉至多一个 QuartzDriver**。源用两级表达（外层 1:1 跟随、内层反向限位），合并成一个：系数相加、限位取最内层、宿主取最外层 |
| 胸部一直乱抖 | **取值域夹取**：源 damping 0.15 / stiffness 0.03 低于目标全库 529 个胸驱的下限（0.20 / 0.06），叠上目标独有的 pendulum 力项 → 欠阻尼。夹回目标域即好。42 根摇物骨 0 个越界，规则只咬到出问题的那一个组件 |

回退用 `.backup/2026-08-14-working-medians/`（旧的中位数版：包、prefab、全部 Editor 脚本、探针 DLL）。

### 本轮修掉的六个 bug（全部已实机验证）

| 症状 | 真因 |
|---|---|
| 进换装/撮影硬崩 | 每片裙摆挂了两个 `QuartzDriverSkirtBone`（`_A` 与 `_Repulsion_A` 父子各一个） |
| 身上亮线高光 | 源 def 图光泽 0.72 越过 `_SpecularThreshold`=0.6；IP 用材质 `_Smoothness=0.5` 压半，学马无此标量 → 改为按表面预设**封顶** |
| 撮影皮肤全黑 | 克隆材质冻结了按场景重建的 `_RampMap`/`_RampAddMap` → 每次 `BuildModel` 重克隆 |
| 裙子穿模 | `_S_End` 被排除出链，三片前裙摆一根活动骨都没有 |
| 裙子/翅膀炸开 | `around` 按全库多数取了 0，应按被替换那套取 1 |
| 裙子不贴大腿 + 僵硬 | 摇物骨 `collisionMask=-1` 撞上半径 0.23 m 的 `Hips` 胶囊；原版裙摆骨用通道 1 |

方法教训（三条，都栽过）：**先核日志再看画面**；**按被替换的那套取值，不要按全库多数**；
**"参数怎么调都没反应"时先确认被推的东西是活的**（碰撞体 ×5 推得动原版头发、推不动我们的裙子，
是因为那几片根本没有活动骨）。

### 实机环境当前状态

- 探针：`GakumasAvatarProbe.dll` **0.19.0-rematerial** 已部署到 `D:/Games/gakumas/BepInEx/plugins/`。
  它把每个材质的 34 个属性（标量+颜色）写进 `avatars.json`，用于同帧对照原版部件。
- `BuildModel` 收到的 part 清单一直就在 `hooks.log` 里（`Il2.Describe` 逐项打名字，别再重复实现）：
  `<body> / <face> / <hair>`，第 4 个是道具，实测 jsna 为 `mdl_prp_smartphone-jsna-00_smartphone`。
- `D:/Games/gakumas/BepInEx/config/gakumas-avatar-probe/swap-experiment.txt` 已恢复干净：
  只有 source / bundle / asset / `swing=off` 四行，**诊断用的 `color=` 已删除**。
- `SwingColliderCage.RadiusScale` 已 revert 回 `1f`（诊断值 5f 会打黄色警告）。

### 悬案（1、2 已关闭，3 仍未验）

1. ✅ **撮影 / live 皮肤全黑 —— 已修复并实机确认（2026-08-14，3Dmigoto 抓帧定位）**。
   同一 mesh（`vb0=a73a8119`）、同一 PS，两帧对照：撮影里我们的 body **t3/t5 没绑**
   （t3=1024×4 共用 toon ramp `_RampMap`，t5=128×16 随服装 `_bdy_rma` `_RampAddMap`），
   而**同帧的原版部件两个都绑着**。未绑定的 SRV 采样返回 0，皮肤靠 ramp 上色 → 全黑。
   根因：`RebuildMaterials` 克隆游戏材质只跑了一次，克隆冻结了快照，而这两个槽是游戏
   **按场景重建 + 重新赋值**的（`CampusActorModelParts.InitializeCampusMaterials`），
   上个场景的对象已销毁。修法：`CopyLayer` + `RebuildMaterials` 每次 `BuildModel` 都重跑
   （探针 **0.19.0-rematerial**）。实机确认不黑了；`hooks.log` 里每进一个场景应各有一组
   `materials: slot 0/1/2`。代价：每次重建泄漏 3 个 Material，未处理。

   顺带清掉的两条（都不是这次发黑的原因，但都是真偏差，已一并改）：
   - 旧结论"cloth 取了 `_RampAddMap` 的纯黑行"**已推翻**：被替换的 `hmsz-cstm-0059`
     主布料值是 `(51,79,15,144)`，LUT 行就是 15，和我们写的一致（原版只用 0/3/6/9/12/15
     六行，见 `docs/body-component-inventory.md` 顶点 COLOR 一节）。
   - 但 **rim（A 高位）原版 9、我们写 0** 确实错了（原版 65.9% 顶点是 9），已改
     `SurfacePresets` 的 Cloth 为 `(0,15,15,144)`。
   - 已排除：材质标量（与同帧原版逐项相同，只差 `_ActorIndex`）、t4 比值（皮肤 1.000、
     布料 0.426，都正常）、UV 通道（原版 UV1 全零是填充）、shader（两帧同一个 PS hash）。
2. ✅ **裙子穿大腿 —— 已修复**。真因不是缺驱动器，是 `_S_End` 被排除出摇物链，
   三片前裙摆一根活动骨都没有（层 0 是锚定层）。顺带修掉「不贴大腿 + 僵硬」：
   摇物骨 `collisionMask` 从 -1 改成原版裙摆用的通道 1，不再撞上半径 0.23 m 的 `Hips` 胶囊；
   同时删掉我们自己加的大腿胶囊（0059 原版没有，当初是按错误诊断加的）。
   **剩余**：前三片各只有 1 根活动骨，摆幅天生小于原版（原版每片 4 根），属源模型骨数限制。
3. **翅膀是否摆动**。尾巴和裙子已实测在动（Δ 0.06 / 0.156），翅膀从未进过位移前 5。

### 还没做的（按原版携带率排序，全部有据可查）

- `_bdy_rma` + `_RampAddColor`：随服装，必须作者/SDK 产出。
- 服装相关 driver：Waist 230/530、Frill 78、Poncho 39、LateRotationSimple 33、Sleeve 26+9、Furisode 25。
  sucu 没有这些部件，不阻塞当前验证。
- 骨名重映射：现在这条管线只吃「骨名已和学马一致」的源（IP 恰好满足）。这是离目标最远的一块。
- face / hair / 饰品 / 表情、ON-OFF 热开关、泄漏检查、descriptor/manifest、把换装逻辑搬出探针。

### 本次会话的方法结论

**症状驱动已放弃，改为闭合清查。** 全 530 套 body 已按两个轴穷举完，结论无未知项，
产物在 [`docs/body-component-inventory.md`](docs/body-component-inventory.md)：
组件轴 23 个类的对账表 + 材质/颜色轴的槽位与「随服装 vs 常量」划分 + 值表 + 复现命令。
扫描器在 `tools/inventory_body_components.py`、`tools/inventory_body_materials.py`、
`tools/driver_tables.py`；原始数据在 `reference/body-component-inventory.json`、
`reference/body-material-inventory.json`。**换游戏版本后重跑这三个脚本。**

另一条通用教训：「参数怎么调都没反应」时，先用**荒谬值**证明整条路径通不通
（碰撞体 ×5 一步就排除了整个碰撞方向），不要在合理值域里反复试。

---

（以下为 08-13 的记录）

## P0 已过门，机制换了

`CampusActorController.BuildModel` 换 part prefab 这条路线已实机贯通：IDOLY PRIDE 的
`chs-sucu-00` 服装装在学马 hmsz 身上，骨架 / 蒙皮 / 材质 / 贴图 / 顶点色 / 摇物 / 静态碰撞
全部正常。**README §2.1 的 AvatarHost + PoseBridge 已降级为备选方案。**

当天逐个撞开的六道关卡（细节全在 `[[unity-sdk-build-requirements]]` 和代码注释里）：

| 症状 | 根因 |
|---|---|
| `PropertySceneHandle is invalid` 崩进程 | 手上缺 `ActorAnimationIKCorrectionGoal`，rig 照建 job、5 个句柄全是 default |
| 身体完全不显示 | ① AssetStudio 的 bindpose 字段名是转置的 ② prefab 在 layer 0，游戏相机不画 |
| 贴图不生效 | 占位材质用 `Standard`，`SetTexture` 静默丢弃 → 9 张图根本没进包 |
| 翅膀霓虹绿 / 描边偏橙 | 顶点 COLOR 是四个 nibble 字段，IP 的字节在学马语义下解成亮绿描边；须按 skin/cloth 分类重写 |
| 裸露皮肤发灰、后来发黑 | t4.A 应是皮肤二值 mask（IP 那张是 13/255）；t1.B metallic 应为 0（IP 皮肤区 0.486，室内混环境光成黑） |
| 摇物一动不动 | `resetType` 写成 1(`Skin`)。它不在扫描器字段表里，所以"照抄原版参数"反而掩盖了它 |

## 仍然没做（离产品目标的距离）

- face / hair / 饰品 / 表情：一件没做。
- ON/OFF 热开关、20 轮重建、泄漏检查：没做。
- descriptor / manifest：schema 和校验器都在，实机管线一个不产出。
- 作者体验：输入路径写死在 `SdkPipeline` 里，吃 AssetStudio JSON 而非作者 prefab；摇物按骨名
  自动猜类别，作者无法介入（README §3.1 承诺的正好相反）。
- 换装逻辑住在勘探探针里（1700+ 行），发行插件是 99 行空壳。
- 已知表现缺陷：撮影场景全身变黑（定位中）；翅膀是否摆动未确认；`m_bdytrs` 匹配不到原版同名
  材质会退回 `m_bdyco`；皮肤 mask 靠颜色启发式（实测 precision 0.94 / recall 0.95）；
  `_RampAddMap` 沿用被替换角色的那张。

## 已落地

- 以 `gakumas.avatar.v1` 为协议前缀的 manifest/descriptor JSON Schema。
- 从 `mod-workspace/libraries` 生成的 asset-level reference inventory：
  - 19 个角色；
  - 530 个有效 body resource；
  - 210 个有效 hair resource；
  - Unity 版本证据为 `6000.0.67f1`；
  - 每个 renderer 记录 bone names、weighted bone names、root bone 和 skeleton 路径。
- `runtime-core` 已可在无 Unity/无游戏环境编译，提供 descriptor 校验和 runtime apply plan。
- Python 离线 validator 与 .NET validator 都拒绝绝对路径、父目录跳转、重复 renderer、未知表情目标和无效动态参数。
- Unity 6000.0.67f1 模板工程已实际编译通过 SDK 编辑器脚本；P1 源码镜像位于模板工程的
  `Assets/GakumasAvatarSdk/`，编译日志为 `mod-workspace/pipelines/ip/unity-template-builder/Logs/avatar-sdk-compile.log`。
- SDK 导出器支持 Humanoid 校验、自动/手动 renderer role、手动 BlendShape 表情映射、手动摇物链和碰撞体、descriptor/manifest 写出和 Windows AssetBundle 构建；同时提供 Unity batchmode 入口。
- 当前游戏运行版本确认为 Unity `6000.0.77f1`；解包 inventory 中的 `6000.0.67f1` 是资产证据来源版本，二者不再混写。
- BepInEx bootstrap 已改为“精确版本空白 IL2CPP 玩家离线生成标准代理”：不再要求目标 `GameAssembly.dll` 通过 Cpp2IL，也不再依赖运行时内存捕获。
- 最小发行缓存已在合成 Animator/SkinnedMeshRenderer/BlendShape 场景端到端通过：关闭自动生成和 xref 后，探针 `0.2.0-p0` 能加载并正确读回 `SyntheticSmile = 42`。
- 目标目录已预置 79 个 `UnityEngine*`/`Il2Cpp*` 代理，明确排除空白玩家的 `Assembly-CSharp.dll`、`__Generated.dll` 和地址/xref 数据库；目标 cache hash 已按真实游戏文件离线计算。

## 仍必须用 BepInEx 活体验证

解包 JSON 不能回答以下运行时事实，因此 inventory 明确把它们标成 `not_observed`：

1. ~~角色 `Animator.avatar` 是 Humanoid 还是 Generic~~ → **Humanoid**（`isHuman=true`，
   `BuildAvatar` 运行时构建，54/55 骨映射）；
2. ~~真实 `SkinnedMeshRenderer` 路径~~ → `<actor>/Root_Body/Geo_Body`，face 走
   `Root_Face/VLSkinningRenderer`（MeshRenderer + VL 自研蒙皮）；**face blendshape 名单仍未取**
   （表情走骨不走 BlendShape）；
3. ~~换装时机~~ → `BuildModel` 在建骨架**之前**，是唯一需要的挂点；rest pose 与 update 时序未单独测；
4. ~~替换后动画能否驱动外部模型~~ → **能**，而且不需要 AvatarHost：游戏用作者骨架自己重建 Avatar；
5. **暗光/场景材质变体仍未解决** —— 撮影场景全身变黑，探针 0.17.0 已加材质属性 dump 待取证；
   blendshape 权重写入和销毁/重载稳定性仍未测。

## P0 live probe checklist

优先使用 `runtime-bepinex/AvatarProbePlugin.cs` 做无侵入扫描；探针会在场景稳定后和角色签名变化时自动输出，必要时按 `F6` 强制输出。必要时再用 BepInEx + UnityExplorer
（仅作为勘探工具，不作为最终发行依赖）挂入一名目标角色，记录以下结果：

| 检查 | 通过条件 | 产物 |
|---|---|---|
| Animator 类型 | `Animator.avatar.isHuman` 与路线假设一致 | `animator-reference.json` |
| Avatar 骨骼 | Hips、Spine、Chest、Neck、Head、四肢和手指可解析 | `humanoid-bones.json` |
| Renderer 路径 | body/hair/face 的路径在 prefab 生命周期内稳定 | `renderer-reference.json` |
| BlendShape | 读取 face mesh 的完整名称和数量 | `blendshape-reference.json` |
| 替换实验 | 单个外部 Humanoid prefab 可驱动待测动作 | ✅ 已通过（IP `chs-sucu-00` 装在 hmsz 上） |
| 回滚实验 | 应用失败可恢复原 renderer 和材质 | ❌ 未做。当前"回滚"= 删掉 `swap-experiment.txt` 重启游戏 |

“替换实验”已通过，“回滚实验”仍未做 —— 所以现在**还没有**可发行形态，换装逻辑仍住在勘探探针里。
在此之前不改现有 C++ runtime，也不把 live-only 结论写入静态 reference。
