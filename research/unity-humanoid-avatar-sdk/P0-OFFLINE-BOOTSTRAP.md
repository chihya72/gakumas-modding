# P0 Offline Bootstrap — Unity 6000.0.77f1

更新时间：2026-08-13

## 2026-08-13 实机结论：interop 代理路线作废，改走裸 il2cpp

下面"离线生成架构"整节的前提被实机推翻了，保留只作为失败记录。**不要再去修 Cpp2IL、
空白 player 或 interop 缓存。**

### 根因

Il2CppInterop 生成的代理**按 token 解析方法**（`GetIl2CppMethodByToken`），类和字段才按名字。
token 是按 build 编号的：空白 player 用 `link.xml` 全保留，发行版被 UnityLinker 裁过，
只要裁掉一个成员，之后所有 token 全部错位 → 代理拿到错的或空的 `MethodInfo` →
`il2cpp_runtime_invoke` 直接 AccessViolation。

所以**版本对齐（6000.0.77f1）修不了这个问题**：它只消除了 Unity 版本之间的漂移，
消不掉裁剪造成的漂移。除非 interop 由游戏自己的 build 生成（Cpp2IL 走不通），这条路没有出口。

### 三次崩溃与证据链

1. `SetupUnityLogging` AV —— BepInEx 自己把 `Application+LogCallback` 转委托。
   `UnityLogListening = false` 绕过，**这个配置必须保持 false**。
2. `new GameObject(name)` AV，然后 `Application.get_unityVersion()` AV ——
   两个方法在目标 `global-metadata.dat` 里**都存在**（已逐条核对），所以不是裁剪掉了方法，
   是指针解析错了。
3. 决定性对撞（probe 0.2.2）：同一个 `Application.get_unityVersion`，
   裸 `il2cpp_*` 按名字调用返回 `6000.0.77f1`，interop 代理调用当场 AV；
   两条路拿到的 **class 指针完全一致**（`Application=…4D240`、`GameObject=…535D0`）。
   → class 解析正常，method 解析坏掉。

`Application.OnAdvertisingIdentifierCallback` 那条 "field not found" 是真的裁剪，
按名字查所以能正确报错——这正是名字路线与 token 路线的差别。

### 现行路线（probe 0.3.0-raw，已实机通过）

- 数据访问全部走导出的 `il2cpp_*`，按名字：`Image → Class → Method → Invoke`；
- `Invoke` 前必须判空，拿不到 `MethodInfo` 就抛异常，**绝不把 0 指针喂给 runtime_invoke**；
- interop 只保留一个用途：`ClassInjector` 需要托管 MonoBehaviour 子类来换主线程 tick，
  注入走名字/指针，不吃 token，已验证可用；
- 79 个 interop 代理对采集没有价值，只是 BepInEx 预加载的死重量。

### 第一次活体证据（09:06 那次启动）

```
s1..s5 全通 → Load() complete
scan#1 frame=360   animators=1  (Motion Camera)
scan#2 frame=2040  animators=5
```

四个角色 animator：`hmsz|CampusActorController[0]`、`atbm[1]`、`fktn[2]`、`jsna[3]`，
**`isHuman = true`，`avatarName = "Humanoid Avatar"`** —— inventory 回答不了的
"是不是 Humanoid" 就此坐实：是 Humanoid，不是 Generic。

注意 `isInitialized = false`：`Resources.FindObjectsOfTypeAll` 会带回未激活对象和资源，
下一版探针要按 `gameObject.scene` 有效性把场景实例和 prefab 分开。

## 替换入口已打通：BuildModel（2026-08-13，probe 0.10.0）

**结论：在 `BuildModel(GameObject[])` 上把 part prefab 换掉，游戏会用我们给的 prefab 重建
骨架、`_boneInfos`、Humanoid Avatar 和摇物驱动器。骨架随包进入，不再受"必须沿用原版骨架"约束。**

这与生产 runtime v1.0.0 的能力不同：那条路挂在 `AssetBundle.LoadAsset(Async)`，在资源出来
*之后*替换 Mesh/材质/贴图并按骨名重排 skinning，骨架只能是原版的
（`physics-new-bone-wall`、`ab-newbone-unitypy-crash-rootcause` 两堵墙的根源）。
BuildModel 发生在建骨架*之前*。

### 链路

```
BuildAsync(settings, descriptor, ct)
  → ActorLoadAsync(...)  → AssetKeeper.LoadAssetAsync<T>(name, ct)
  → BuildModel(GameObject[])      ← 替换点，数组元素可原地改写（Boehm GC，无写屏障）
  → BuildAvatar() / PostBuild()
```

`resources` 是 `GameObject[]`，长度不固定，按槽独立：
`mdl_chr_<角色>-<cstm|base|casl>-<编号>_<body|face|hair>`，道具是 `mdl_prp_*`
（jsna 实测 4 个槽，多一个 smartphone）。

### 两次实机验证

1. **场内换供体**：hmsz 的 body prefab 给 atbm → atbm 的 Geo_Body 变 19440 顶点/156 骨、
   hierarchy 365→386，Avatar 仍 valid 54/55；
2. **外部文件加载**：`mod-workspace/libraries/all_body/mdl_chr_atbm-trng-0000_body`
   经 `AssetBundle.LoadFromFileAsync(path).assetBundle.LoadAsset(name, typeof(GameObject))`
   装进 hmsz → 19440/156/384 变 **17062/124/341**，Avatar valid 54/55，无报错。

`all_body/` 那 530 个包可被游戏直接加载：标准 `UnityFS`，不需要 UnityCN 密钥或重新打包。

### 两个必须记住的细节

- **`AssetBundle.LoadFromFile`（同步版）被裁掉了**，只剩 `LoadFromFileAsync`；
  读 `AssetBundleCreateRequest.assetBundle` 会强制同步完成，等价替代；
- 同一个 AB 包**不能重复加载**，选供体包时要避开当前场上已加载的。

### 直接可得的副产品

跨角色穿衣不需要任何资源改动——把 body 槽指向另一个包即可，530 个包任意排列。
真正的 mod（自制 mesh/骨架）只需把包换成 UnityPy 改过的版本，加载路径完全一样。

## 外来资源实机贯通：IDOLY PRIDE 服装装进学马（2026-08-13，probe 0.16.x）

**《偶像荣耀》的 `mdl_chr_chs-sucu-00_body` 在学马 PC 客户端里正常建成并渲染**：IP 自带骨架
（142 节点，翅膀/尾巴/裙饰的 `_S` 骨一根不少）、IP 网格（11870 顶点）、IP 贴图，
`isHuman=True`、`avatarValid=True`、54/55 骨映射。头发和脸仍是学马原版部件。

### 包必须改的（离线，UnityPy）

转换脚本见 `scratchpad/ip_bundle_to_pc.py`（待产品化）。只改三处：

| 改动 | 原因 |
|---|---|
| 9 张贴图 ASTC → RGBA32 | ASTC 是 Android 专用，Windows 端不能采样，**改 header 没用必须重编码** |
| `target_platform` 13 → **19** | AB 包平台绑定，Unity 直接拒绝（"not built with the right version or build target"） |
| `Mesh.m_IsReadable` → 1 | 否则运行时改顶点色被 Unity 拒绝，**且只打日志不抛异常**（假成功） |

其余原样：142 Transform/GameObject、Mesh、SkinnedMeshRenderer、87 个 MonoBehaviour 全部保留。

### 运行时补的（插件）

- **材质**：克隆游戏自己的材质（拿到 `Campus/Actor/Default`、`_RampMap`/`_RampAddMap` 和全部参数），
  再把 mod 材质上的贴图按同名槽位搬过来。两边属性名完全一致：`_BaseMap`/`_DefMap`/`_ShadeMap`，
  不需要按文件名猜。槽位数不等时按材质名配对，多出来的回退到最后一个。
- **顶点色**：`Mesh.set_colors` 压平（值可从配置读，免重编译）。
- **摇物**：给每根 `_S` 骨挂 `ActorAnimation.ActorSwingDynamicBone`，参数抄原版服装实测值
  （damping .4 / stiffness .02 / spring .5 / mass .6 / pendulum .003 / rootWeight .3）。
  **已挂上 30 根，是否真的摆动未验证。**

### 又两条硬约束

- **骨名跨部件全局唯一**：body/face/hair 三个部件共用一张 `BoneNameToTransformDictionary`，
  重名直接 `ArgumentException` 打断建模。**自制 body 包不能带 `Head_Hair`/`Head_Face`**，
  那是脸和头发部件自带的（我加了一次，卡加载）。
- **`_RampAddMap`(rma) 是每套服装专属的**（`t_chr_<角色>-<服装>_bdy_rma`，128×16，16 行查找表）。
  克隆原版材质等于让 mod 几何去查原版服装的加色表，颜色必然不对。IP 那套要么自己生成 rma，
  要么把加色关掉只用贴图本色。`_RampMap`(rmp, 1024×4) 才是全角色共享的。

### 摇物：运行时挂组件不够（2026-08-13 实测证否）

给每根 `_S` 骨挂 `ActorSwingDynamicBone` 后**不会摆动**（肉眼确认 + `localRotation` 采样确认，
变化量来自动画本身）。真正的驱动方是 `ActorAnimation.ActorSwingChain`：

```
ActorSwingChain 挂在锚点骨上（不是摇物骨自己）
   rootBones = List<ActorSwingDynamicBone>   只放每条链的第一节（…1_S）
   chains.layers = List<ChainLayerInfo>      元素个数 = 链深度
```

atbm 实测 4 个 chain：`Pelvis` 裙 8 根 4 层、`Pelvis` 上层裙 8 根 3 层、
`Spine` 外套 6 根 2 层、`Head_Hair` 头发 7 根 6 层。**按深度分组，每组一个 chain。**

原版 `ActorSwingDynamicBone` 还填了这些我们没设的：`dynamicType=1`、`resetType=1`、
`<hierarchyDepth>=7`、`<initialTransform>`、`modelingTransform`、`limitInfo.useLimit=1`
+ 三轴限位、`dynamicCollider`(type/mask/半径 .05)。**参数不能跨服装抄**——同角色不同衣服的
stiffness 差 0.02↔0.5、pendulum 差 0.003↔0.3。

真值获取：探针写 `swing-reference/<角色>.txt`，**按角色分别落文件**，且必须先确认对象上真有
摇物组件再 dump（否则会抓到 `DefaultCamera` 得到空文件，白跑一轮）。

**推论：mod 包必须自带摇物装配**，或运行时完整复现 chain 构建。前者更现实——包能用 UnityPy
读写，字段布局已知，可以从原版包复制组件再重映射骨引用。

### 颜色现状（暂缓）

顶点色 COLOR 在这个 shader 里是数据不是颜色。压平成 `(0.318,0,0.059,.565)` 时翅膀渲染成棕色，
压平成 0 时的表现待测。选行规则尚未定论——rma 行 0/1 偏蓝、8-10 橙棕、14/15 纯黑，
但设 G=0 得到的是橙棕而非蓝，**说明"COLOR.G 低 nibble 选行"这条对本例不成立或不完整**。
皮肤偏灰是 `_DefMap`/`_ShadeMap` 通道语义的问题，要按预设库重做 t1/t4，不是搬源游戏的图。

## 角色运行时结构（2026-08-13 活体采集，probe 0.7.1）

采集手段：`GetComponents` + `il2cpp_object_get_class` 拿真实类型，沿字段/参数类型递归 dump 类
（121 个），再用 `il2cpp_field_get_value` 读实例字段值。输出在
`BepInEx/config/gakumas-avatar-probe/` 的 `class-dump/`、`instance-dump/`、`components.txt`、
`timeline.log`。**这些不需要任何离线 dump，受保护的 GameAssembly 自己会回答。**

### 组件构成

角色根对象 = `<角色缩写> | CampusActorController[N]`，挂 19 个组件，核心是
`Campus.Common.CampusActorController`，另有 `VL.Animation.MotionDefinePlayer`、
`VL.VLActorExpression`、`VL.VLActorFacialSystem`、`Campus.Common.CampusActorAnimation`、
`ActorAnimation.CampusActorAnimationRig`、`VL.VLActorCollider`、`VL.VLActorAO`、
`Campus.Common.CampusActorHipCorrector`、多个 `Octo.AssetKeeper`。

### 部件系统

`_descriptor`（`CampusActorDescriptor`）：`_uniqueId = "hmsz-cstm-0059"`、`_name = "hmsz"`、
`_humanoid = True`、`_assets` = 三个资源名、`_gameObjects` = 对应三个 prefab。

角色 = 三个 `CampusActorModelParts`（`_children`）：

| partsId | assetName | 骨(_boneInfos) | renderer | skinningModel | 材质 |
|---|---|---|---|---|---|
| body | `mdl_chr_hmsz-cstm-0059_body` | 232 | SkinnedMeshRenderer | null | 2 (`m_bdy`,`m_bdyco`) |
| face | `mdl_chr_hmsz-base-0000_face` | 28 | **MeshRenderer** `VLSkinningRenderer` | `VLActorFaceModel` | 9 (`m_fce`,`m_fcp`,`m_eye`,`m_ehl`,`m_ebs`) |
| hair | `mdl_chr_hmsz-base-0000_hair` | — | SkinnedMeshRenderer ×2 (`Geo_Hair`,`Geo_HairProp`) | null | `m_hir`,`m_hirco` |

**只有服装（body）带 cstm 编号，face/hair 是 base-0000。**
**脸不是 SkinnedMeshRenderer**：VL 自研 Job 蒙皮算顶点，普通 MeshRenderer 出图
（`_vlSkinningMaterialInfos` + `ScheduleRenderingJobs`）。renderer 数量不固定，
某些服装还有第四个部件（ttmr 的 `Root_Dresscurtain/Geo_Dresscurtain`）。

### 动画与表情

- **没有 AnimatorController**，走 PlayableGraph：`VL.Animation.AnimationPlayerBase`
  持有 `PlayableGraph _graph`，主播放器是 `MotionDefinePlayer`；
- **表情是骨/muscle 驱动**，不是 BlendShape：`VLActorExpression` 用 `AnimationScriptPlayable`
  + Burst job 写 `_expressionBones` / `MuscleExpressionData`。全部快照 blendShapeCount 均为 0；
- `VLActorFacialSystem` 里确实有 BlendShape 路径（`SetBlinkBlendShapeWeight`），但那条要有
  `VLActorFaceModel` 的 blendshape 数据才走，当前角色不走。

### Avatar 是运行时构建的

`CampusActorController.BuildAvatar()` + `GetHumanDescription(HumanBone[], SkeletonBone[])`
+ `GetSkeleton(Transform, bool)`，配合 `_humanBodyBoneMap`、`_boneNameToTransformMap`。
即游戏自己用 `AvatarBuilder` 从加载好的骨架造 Humanoid Avatar，`_avatar` 字段就是产物，
`IsBuildSuccess = True`。**替换路线不需要离线做 Avatar 资源，介入这里即可。**
54/55 HumanBodyBones 有映射（只缺 `Jaw`），`Chest→Spine1`、`UpperChest→Spine2`。

### 摇物系统

`CampusActorModelParts` 上按部位分类，不是通用链（hmsz-cstm-0059 body 实测）：

```
dynamicBones(111)  chains(2): Pelvis, LeftShoulder
quartzDriverRotationBones(4): LeftLeg_H RightLeg_H LeftForeArm_H RightForeArm_H
quartzDriverSkirtBones(8)  quartzDriverFrillBones(2)  quartzDriverHairBones(0)
另有 Waist / Furisode / Poncho / HumanoidHand / HumanoidSleeve / HumanoidUpLeg / HumanoidArm
initialTransforms + initialLeft/RightBreast(End)Transforms = rest pose 缓存
```

### 生命周期

`timeline.log` 实测：换角色是**销毁重建**，同一帧一进一出，而且 `CampusActorController[N]`
的索引会被新角色继承（fktn 走、kcna 拿到同一个 `[2]`）。**任何按索引或名字缓存 actor 的做法
都会指到错的对象。**

### 写探针踩的三个坑

1. `il2cpp_field_get_value` 按字段真实大小拷贝，缓冲区小于结构体就冲掉堆，进程稍后崩在
   不相关的地方且 ErrorLog 为空 → 先判 `il2cpp_class_is_valuetype`，只读已知固定大小的类型；
2. `il2cpp_type_get_name` 输出泛型是 `List<T>` 不是 ``List`1``，按 backtick 匹配会静默失效；
3. 泛型嵌套类型名拼文件名会超 MAX_PATH，要截断加哈希，且每次写盘单独 try/catch。

## 结论（以下为 2026-08-13 之前的记录，前提已被上面推翻）

当前困境不是“还差一个更好的 GameAssembly 内存 dump”，而是把目标游戏的受保护 IL2CPP
二进制误当成了必须通过的生成入口。对于只调用标准 Unity API 的 Avatar probe/runtime，
完整游戏代理程序集不是必要条件。

最终路线是：

1. 用与游戏完全一致的 Unity `6000.0.77f1` 构建一个未保护的空白 Windows IL2CPP player；
2. 在空白 player 上让固定版 BepInEx/Cpp2IL/Il2CppInterop 离线生成标准 Unity 代理；
3. 发行时只带 `UnityEngine*.dll`、`Il2Cpp*.dll` 和本项目插件；
4. 用真实游戏文件计算 BepInEx cache hash，并关闭自动 interop 生成与 xref 扫描；
5. 第一次启动游戏只做无侵入活体采集，不做替换。

这样绕过的是“目标二进制离线不可分析”这一点，不是绕过 Unity/IL2CPP 类型系统。插件仍使用
BepInEx 6 + Il2CppInterop 的正常类型代理和 class injection。

## 仓库与解包证据

- `reference/asset-inventory.json`：19 个角色、740 个有效资源，其中 530 body、210 hair；
- inventory 已记录 skeleton path、renderer bone names、weighted bones 和 root bone；
- inventory 不能回答 Animator 是否 Humanoid、活体 face renderer、BlendShape 当前权重、真实 rest
  pose 和生命周期时序，这些字段继续保持 `not_observed`；
- `gakumas-mod-runtime/manager/tools/metadata_index.py --selfcheck` 对当前
  `global-metadata.dat` 解出 50,652 个类型，三个既有锚点全部通过；
- 目标 metadata 已确认存在 probe/runtime 所需的 Animator、Avatar、SkinnedMeshRenderer、Mesh、
  Resources、Scene、Input 与 AssetBundle 方法；
- 游戏日志和 `UnityPlayer.dll` 确认当前运行时版本是 `6000.0.77f1`。inventory 中的
  `6000.0.67f1` 只代表被纳入资产证据的旧资源版本。

## 原路线为什么失败

### 目标文件直接跑 Cpp2IL

受保护的 `GameAssembly.dll` 在磁盘上没有可被当前 Cpp2IL 定位的 code registration，最初报错
是 `No codegen modules found for mscorlib`，导致 `BepInEx/interop` 为空；后续
`UnityEngine.CoreModule` 缺失只是连锁结果。

### 运行时捕获 GameAssembly

捕获运行时已物化的 PE 能找到 metadata registration 和大量方法，但 Cpp2IL 在建立 application
model 时仍发生 `Il2CppMetadata.GetTypeDefinitionFromIndex` 越界。根因是运行时
`Il2CppType.Datapoint` 已成为进程指针，而当前 LibCpp2IL 仍按 metadata index 解释。

扩大捕获范围、附加 heap section 或重写更多指针都不能恢复字段原本的索引语义。因此该方向停止，
捕获 DLL 保留作研究证据，但不再进入启动链。

### 用相近补丁版代理

`6000.0.67f1` 与 `6000.0.77f1` 的 Animation/Input token 恰好稳定，但 CoreModule 中约
13,515 个方法 token 已偏移。相近版本代理“能加载”不代表调用正确，因此不能发行。最终安装并使用
精确 `6000.0.77f1` 工具链，从源头消除 token、mscorlib 和泛型实例差异。

## 离线生成架构

空白工程位于工作区 `.local/interop-source-unity6000`，只用于生成/验收，不提交大型构建产物。
它具有以下特征：

- Windows x64 + IL2CPP；
- `link.xml` 保留 probe/runtime 需要的标准 Unity 模块；
- 合成场景创建 Animator、三节点骨链、SkinnedMeshRenderer、一个 Mesh 和
  `SyntheticSmile` BlendShape；
- BlendShape 权重固定为 42，作为端到端断言；
- player 留出 150 帧让 class injection、自动扫描、JSON 序列化和退出完整发生。

固定底座：

- BepInEx `6.0.0-be.785`；
- Il2CppInterop `1.5.3.0`；
- Cpp2IL Core `2022.1.0.0`；
- Unity `6000.0.77f1 (88f89d0d8b31)`。

## 发行缓存边界

包含：

- 73 个 `UnityEngine*.dll` 代理；
- 6 个 `Il2Cpp*.dll` 代理；
- `assembly-hash.txt`；
- `GakumasAvatarProbe.dll`。

明确排除：

- 空白 player 的 `Assembly-CSharp.dll`；
- `__Generated.dll`；
- `MethodAddressToToken.db`；
- `MethodXrefScanCache.db`。

排除项要么属于空白应用自身，要么包含空白 `GameAssembly` 的本地地址，放入游戏会制造错误契约。

目标配置固定为：

```ini
UpdateInteropAssemblies = false
UnityBaseLibrariesSource = 6000.0.77.zip
ScanMethodRefs = false
PreloadIL2CPPInteropAssemblies = true
```

Doorstop 入口必须恢复为：

```ini
target_assembly = BepInEx\core\BepInEx.Unity.IL2CPP.dll
```

## 已通过的离线门禁

1. 精确版空白 player 的 Cpp2IL 找到 code/metadata registration；
2. Il2CppInterop 生成完成，chainloader 零错误启动；
3. probe `0.2.0-p0` 成功 class injection；
4. 最小发行缓存、禁用自动生成后仍成功启动，日志中没有 Cpp2IL/xref；
5. JSON 中有 1 Animator、3 hierarchy nodes、1 renderer；
6. `SyntheticSmile` 名称与权重 42 均正确；
7. probe 的 47 个 Unity 方法引用都能在目标 `6000.0.77` base libraries 精确解析；
8. 目标 interop 目录与已验证缓存逐文件 SHA-256 一致；
9. 目标 cache hash 与真实 `GameAssembly.dll`、Unity base libraries 和生成器版本一致；
10. 游戏进程未启动，部署阶段没有运行目标 executable。

## 第一次游戏启动目标

第一次启动只验证 bootstrap 与采集，不做 Avatar 替换：

- BepInEx 日志应出现 `Loading [Gakumas Avatar Probe 0.2.0-p0]`；
- 不应出现 `Running Cpp2IL`、`Generating interop assemblies` 或
  `UnityEngine.CoreModule` 缺失；
- 进入能看到角色的界面后，探针会低频检测 Animator/mesh 签名变化并自动写新 JSON；
- 输出目录是 `BepInEx/config/gakumas-avatar-probe/`；
- `F6` 只作为强制快照备用，不是正常流程的必需步骤。

收到第一次活体 JSON 后，按顺序完成：

1. 归一化 Animator/HumanBodyBones/rest transform reference；
2. 确认 Humanoid/Generic、controller/update/culling/root-motion 行为；
3. 归一化 body/hair/face renderer、bones/root bone/material/shader reference；
4. 生成每角色 BlendShape reference，并与 SDK morph mapping 合并；
5. 做只读时序探针，确定换装/销毁/重载绑定点；
6. 再进入单角色 AvatarHost 替换、失败回滚和长期稳定性实验。

在上述活体证据回来前，不实现完整替换，不猜游戏 Actor 路径，也不把静态 inventory 当成 Animator
真值。
