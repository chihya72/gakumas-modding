# Unity Humanoid Avatar SDK + BepInEx Runtime 总体设计

> 状态：**P0 已过门。可行性已实机证明，但用的不是本文档原本设计的机制 —— 见 §2.1。
> 作者体验、包协议和发行运行时都还没做。**
>
> 建档：2026-08-13 · 与实现对齐：2026-08-13 晚
>
> 当前已发布、已实机的路线仍以 [`../current-status-and-roadmap.md`](../current-status-and-roadmap.md)
> 和 [`../ab-route-notes.md`](../ab-route-notes.md) 为准。

**读本文档前必须知道的三件事**（否则会照着已被推翻的设计动手）：

1. **主线机制换了。** 不再是"在 Actor 下建 AvatarHost + PoseBridge 每帧桥接姿势"，而是
   **在 `CampusActorController.BuildModel` 里替换 part prefab**，让游戏用作者的骨架自己重建
   Avatar、骨映射和摇物。§2.1 已改写；`AvatarHost`/`PoseBridge`/`ExpressionBridge`
   （§2.2 后半、§6.5、§6.7）降级为备选方案，只在 BuildModel 路线对某类资产失效时才做。
2. **已实机跑通的只有 body 一个部件的外观。** 骨架/蒙皮/材质/贴图/顶点色语义/摇物/静态碰撞
   都在游戏里验证过（IDOLY PRIDE 的服装装在学马身上）。face、hair、饰品、表情、ON/OFF
   热开关、泄漏检查**一件都没做**。
3. **代码有两套，已经分叉。** [`sdk-unity/`](sdk-unity/) 是本文档描述的导出器（会写
   descriptor + manifest），**没有实机验证过**；实机跑通的那套在模板工程
   `GakumasAvatarSdk/Assets/GakumasAvatarSdk/` 里，**不发任何协议文件，且输入路径写死**
   （吃 AssetStudio 导出的 `Geo_Body.json`，不是作者的 Unity prefab）。两者尚未收敛。

当前已落地的开发切片：[`P0-STATUS.md`](P0-STATUS.md)、[`contracts/`](contracts/)、
[`reference/asset-inventory.json`](reference/asset-inventory.json)、[`tools/`](tools/) 和
可脱离 Unity 编译的 [`runtime-core/`](runtime-core/)。
inventory 只代表解包数据中观察到的
skeleton/mesh 证据；Animator、face、rest pose 和生命周期行为必须由 BepInEx 活体探针确认。

## 0. 一句话定义

作者只需把任意来源模型整理成一个有效的 Unity Humanoid 角色，手动处理裙子、头发、飘带等
摇物和有限的表情映射，Unity SDK 即可导出一个 Avatar AssetBundle；Mod 配置只声明这个包要
替换哪些游戏角色。BepInEx Runtime 保留游戏原 Actor、动画、剧情逻辑和隐藏的原始表现层，
把游戏动作、表情与生命周期桥接给作者的完整外观。

本路线的产品边界是：

> **模型来源无关，不等于模型无需准备。** SDK 不关心模型来自 MMD、VRM、Mixamo、Blender、
> 3ds Max 或其他来源；它只关心最终导入 Unity 后是否满足统一的 Humanoid Avatar 契约。

---

## 1. 为什么建立一条新路线

当前已发布路线以“把 Mod Mesh 塞回游戏原 `SkinnedMeshRenderer`”为核心，已实机证明 body、
hair、多个材质段、新增摇物骨和热开关可以工作。它的优点是最大限度复用游戏原材质、原骨架和
原运行逻辑，缺点是作者资产必须向游戏当前资源契约靠拢：骨名、骨序、renderer、材质槽、
sidecar 和目标服装资源都进入了制作流程。

下一代方案换一个抽象层：

- 当前路线的交付物是“可塞进某个游戏 renderer 的网格”；
- 新路线的交付物是“可独立播放的完整 Unity Humanoid Avatar”；
- 当前路线按具体 body/hair 资源替换；
- 新路线按游戏角色身份替换完整外观；
- 当前路线让作者资产适应游戏骨架；
- 新路线让 Runtime 把游戏姿势适配到作者 Avatar。

这样才能真正做到：模型来源、骨名、层级、身高、比例和 renderer 数量都不进入玩家配置。

### 1.1 预期收益

1. 作者工作流收敛到 Unity 官方 Humanoid 标准，不再学习游戏内部骨架格式。
2. 一个包可以同时携带身体、头发、脸、饰品和多个 renderer。
3. 作者保留自己的骨架比例，不会被游戏角色体型强行拉伸。
4. 表情通过统一语义槽映射，不再依赖游戏和作者 Mesh 的 blendshape 索引碰巧一致。
5. 裙子、头发物理属于作者 Avatar，不要求翻译成游戏现有摇物骨名。
6. Runtime 用 C#、Unity API 和 Il2CppInterop 实现，版本相关代码集中在游戏适配层。
7. AvatarHost 可以整体创建和销毁，热切换比逐项恢复 Mesh、材质和骨数组更容易形成清晰所有权。

### 1.2 不承诺的事情

- 不把无骨架模型自动变成人形角色；作者仍需完成建骨、蒙皮和 Humanoid 配置。
- 不接受 `Avatar.isHuman == false` 或 `Avatar.isValid == false` 的模型进入正式包。
- 不支持非人形、四足、蛇形、多臂等超出 Unity Humanoid 表达范围的角色。
- 不自动修复坏权重、穿模、裙摆权重、法线、UV 或美术质量。
- 不保证任意来源 Shader 原样进入游戏都正确；材质必须经过 SDK 支持策略。
- 不自动把任意细分表情推断成游戏表情；作者至少要确认基础表情映射。
- 不把 Android 纳入设计、实现和发布约束。
- 不允许 Mod 作者把任意托管代码随 AssetBundle 注入游戏。

---

## 2. 核心架构决策

### 2.1 主线：在建骨架之前替换 part prefab（2026-08-13 实机确认）

`CampusActorController.BuildModel(GameObject[])` 拿到的是 body / face / hair 三个 part prefab，
而它**发生在游戏建骨架之前**。在这里把 body 换成作者的 prefab，游戏接着会用**作者的骨架**
重建部件、骨名映射、Humanoid Avatar 和摇物驱动器。

```text
Game Actor
├─ Game Animator / controller          保留
├─ 剧情 / 镜头 / 交互 / 身份组件        保留
└─ BuildModel(parts[])                 ← 在这里换掉 parts[body]
   └─ 游戏用作者骨架重建：
      ├─ VLActorModelParts / boneMap
      ├─ Humanoid Avatar（BuildAvatar，实测 valid，54/55 骨映射）
      ├─ CampusActorAnimationRig（摇物 / IK 修正）
      └─ 动画照原样播放，比例按作者骨架
```

这条路线的意义是：**姿势重定向由游戏自己完成**，所以下面这三块工程量在主线上不需要：
隐藏原 renderer、`PoseBridge` 每帧姿势转换、表情通道桥接。§2.2 想要的"作者保留自己的骨架和
比例"由 Humanoid 重定向天然满足（142 节点骨架、含翅膀尾巴的额外骨都实机通过）。

代价（未解决，不要遗忘）：

- 这是**按部件替换**，不是按角色身份替换整套外观。现在一个包绑死一套服装资源名
  （`mdl_chr_hmsz-cstm-0059_body`），玩家换衣服 mod 就失效 —— 与 §5.3 和 §12.1 第 6 条冲突。
- face 走 VL 自研蒙皮、表情走骨不走 BlendShape，能不能同样替换**未验证**。

#### 2.1a 备选方案：AvatarHost（原主线，降级）

只有当 BuildModel 路线在某类资产上失效（例如 face），才回到下面这套。它的代价是要自己实现
姿势和表情桥接，也就是 §6.5 / §6.7 那两节。

默认模式不是返回作者 prefab 替换整个游戏角色对象。游戏 Actor 继续持有：

- Animator、Animator Controller 和游戏动画状态；
- 剧情、镜头、点击、导航、交互和角色身份组件；
- 游戏用于定位的挂点、碰撞、LOD、阴影和场景生命周期；
- 原始 face/body/hair 组件及其游戏侧驱动状态。

Runtime 在 Actor 下建立一个独立 `AvatarHost`，加载作者 prefab，并隐藏原始可见 renderer：

```text
Game Actor
├─ Game Animator / controller                 保留并继续更新
├─ Game skeleton / gameplay components        保留
├─ Original visual renderers                  隐藏，必要时继续接收表情写入
└─ GakumasAvatarHost                          Runtime 创建
   ├─ Author Animator + valid Humanoid Avatar
   ├─ Author body / hair / face / accessories
   ├─ PoseBridge
   ├─ ExpressionBridge
   ├─ Spring simulation
   └─ Runtime ownership marker
```

这样游戏仍然认为自己控制原角色；玩家看到的则是作者完整 Avatar。

### 2.2 作者 Avatar 保留自己的骨架（目标不变，手段已变）

> 主线上这条是**免费**的：游戏用作者骨架重建 Humanoid Avatar，重定向由它自己做。下面这段
> "Runtime 每帧把游戏姿势转换为标准人形姿势"属于 §2.1a 备选方案。
>
> 主线上真正的作者侧成本是**骨名**：`VLActorController` 有
> `static readonly Dictionary<HumanBodyBones, string> avatarMapToString`，配合由
> `OnRegisterBone(boneName, bone)` 填的 `_boneNameToTransformMap` —— 游戏是**先把
> `HumanBodyBones` 映射成骨名字符串、再按名字查 transform**。所以任意来源的模型需要一步骨名
> 重映射（另一条产品线的 `gakumas_mi/bone_remap_presets.json` 已有预设库）。IDOLY PRIDE 的
> 资产没暴露这个成本 —— 它和学马是同一套 VL 中间件，骨名本来就一致。

作者 renderer 的 `bones[]` 不改指向游戏 Transform。作者 Animator、Avatar、骨长和 rest pose
完整保留。Runtime 每帧把游戏姿势转换为标准人形姿势，再写入作者 Avatar。

这与“把作者 renderer 直接绑定到游戏骨骼”有本质差别：后者会把高矮胖瘦差异重新拉回游戏
体型，也无法兑现“只要绑成 Unity 人形即可”的产品目标。

### 2.3 Humanoid 是作者侧唯一正式身体契约

正式包的身体动画入口只有 Unity Humanoid：

```csharp
animator != null
animator.avatar != null
animator.avatar.isValid
animator.avatar.isHuman
```

SDK 不要求作者骨名与游戏一致，也不要求层级路径一致。它只记录 Unity `HumanBodyBones` 映射、
Avatar 根节点、renderer 和附加数据。

### 2.4 游戏 Animator 类型被隔离在 Runtime 适配层

作者工作流永远不暴露“游戏是 Humanoid 还是 Generic”。Runtime 提供统一接口：

```text
IGamePoseSource
    CapturePose(actor, canonicalPose)

IAvatarPoseTarget
    ApplyPose(canonicalPose, authorAvatar)
```

- 游戏源若是有效 Humanoid：优先复用持久 `HumanPoseHandler` 做 HumanPose 传递。
- 游戏源若是 Generic：`GakumasGamePoseAdapter` 用一次性 reference 数据和 rest-pose 校准，
  把游戏骨 Transform 转成标准人形语义姿势。
- 作者目标始终是 Humanoid，因此 Generic 复杂性只由 Runtime 维护一次。

在实机确认游戏 Animator 类型之前，两条源适配器都属于设计候选，不能提前删掉其中之一。

### 2.5 AB 只装资产和数据，不装作者代码

Il2CppInterop 可以在启动时注册 Runtime 自己的注入类型，但 AssetBundle 不能作为任意作者 C#
代码分发机制。包内允许：

- prefab、Mesh、Avatar、Material、Texture、Shader；
- AnimationClip（仅作者自用扩展，不参与游戏主体 retarget）；
- TextAsset 格式的 Avatar descriptor；
- SDK 自带且 Runtime 认识的普通 Unity 组件。

包内不允许把未知 `MonoBehaviour` 当作运行逻辑。摇物、表达式和生命周期全部写成数据，加载后由
Runtime 创建自己的组件。

---

## 3. 用户与作者体验

### 3.1 作者的理想流程

```text
导入模型
  → Rig 设为 Humanoid / 创建 Avatar
  → 打开 Gakumas Avatar SDK
  → 选择 Avatar Root
  → 自动发现 renderer 与基础表情
  → 作者确认 body / hair / face / accessory
  → 作者映射基础表情槽
  → 作者标记裙子 / 头发 / 飘带链与碰撞体
  → 选择标准材质策略
  → Validate
  → Build Package
  → 得到 mod.json + <name>.bundle
```

作者不需要：

- 提取目标服装的 Mesh JSON；
- 重命名成游戏骨名；
- 拍平到游戏层级；
- 知道 `Geo_Body`、`Geo_Hair` 或游戏材质槽；
- 为每件游戏服装分别导出；
- 手写 bindpose sidecar；
- 知道 BepInEx 和游戏 IL2CPP 方法名。

### 3.2 玩家安装体验

每个 Mod 是一个独立目录：

```text
gakumas-avatar-mods/
└─ miku-avatar/
   ├─ mod.json
   ├─ miku-avatar.bundle
   ├─ cover.png                  可选
   └─ LICENSE.txt                可选
```

玩家只安装包并在管理 UI 开关，不编辑骨骼、renderer 或 morph 配置。

### 3.3 最小配置

外部 `mod.json` 只声明分发信息、AB 入口和角色目标。示例见同目录
[`example-mod.json`](example-mod.json)。核心形态：

```json
{
  "schemaVersion": 1,
  "id": "miku-avatar",
  "name": "Miku Avatar",
  "version": "0.1.0",
  "author": "author",
  "enabled": true,
  "bundle": "miku-avatar.bundle",
  "asset": "Assets/GakumasAvatarSDK/Build/miku-avatar.prefab",
  "descriptor": "Assets/GakumasAvatarSDK/Build/miku-avatar.avatar.json",
  "targets": [
    { "characterId": "fktn" }
  ]
}
```

`characterId` 使用游戏 Master 数据中的稳定逻辑 ID，不使用某件服装的 body 资源名。默认语义是：

- 替换该角色的所有服装；
- 替换当前支持的所有角色展示场景；
- 同一角色同一时间只能启用一个完整 Avatar Mod；
- 多个目标角色可以复用同一个 AB。

场景过滤、服装过滤和局部替换不是 v1 必需能力。有真实需求后再以可选字段增加，不能让它们
污染最小配置。

---

## 4. Unity SDK 设计

### 4.1 交付形式

建议独立为 Unity Package：

```text
com.gakumas.avatar-sdk/
├─ package.json
├─ Editor/
│  ├─ AvatarBuilderWindow.cs
│  ├─ AvatarValidator.cs
│  ├─ AvatarPackageBuilder.cs
│  ├─ RendererSetupEditor.cs
│  ├─ ExpressionMappingEditor.cs
│  ├─ SpringBoneEditor.cs
│  └─ MaterialConverter.cs
├─ Runtime/
│  ├─ AuthoringMarkers.cs
│  └─ DescriptorModels.cs
├─ Shaders/
├─ Presets/
├─ Samples~/
└─ Documentation~/
```

SDK 使用与游戏匹配的 Unity `6000.0.67f1` 作为第一版固定构建环境。后续若证明相邻 patch
版本产生的 AB 可安全加载，再把“严格同版”放宽为经过验证的版本矩阵，不能凭理论放宽。

### 4.2 主窗口

主窗口分为六块，始终显示验证状态：

1. **Avatar**：选择根对象和 Animator，显示 Avatar 是否 valid/human。
2. **Renderers**：自动列出全部 `SkinnedMeshRenderer` / `MeshRenderer`，作者标注用途。
3. **Expressions**：把作者 blendshape 映射到标准表达式槽。
4. **Dynamics**：编辑裙子、头发、飘带链、参数和碰撞体。
5. **Materials**：检查/转换 shader 与渲染模式。
6. **Build**：填写包信息、运行校验、输出 bundle 与 manifest。

### 4.3 Renderer 分类

分类用于诊断、表达式查找、隐藏策略和性能报告，不限制 renderer 数量：

- `body`
- `face`
- `hair`
- `accessory`
- `effect`

同一分类可以有多个 renderer。未分类 renderer 在 UI 中告警，作者可明确设为 `ignore`。

每个 renderer 记录相对 Avatar Root 的稳定路径、类型、材质数量、blendshape 摘要和 bounds 模式。
SDK 导出前必须检查路径唯一性；不能只靠 GameObject 名字匹配。

### 4.4 Humanoid 验证

硬失败：

- 没有 Animator 或 Avatar；
- Avatar 不是 valid Humanoid；
- renderer 的蒙皮骨不属于选定 Avatar 层级；
- 缺少 Unity Humanoid 本身要求的必要骨；
- Avatar Root 缩放非有限值、任一轴接近 0，或层级存在非法变换；
- prefab 含 Missing Script；
- prefab 引用编辑器专用对象；
- 资产路径不在允许的构建根目录。

警告但可导出：

- 没有眼骨、下颌骨或手指；
- 没有任何表情；
- 身高或 renderer bounds 极端；
- 某些 Mesh 不可读，导致 SDK 无法做完整离线检查；
- renderer 数量、材质数量或顶点数超过性能建议值。

SDK 不重新发明 Humanoid 自动识别器。模型能否绑定由 Unity Avatar 配置器决定；SDK 只读取最终
结果并补充本项目特有校验。

### 4.5 姿势预览

SDK 提供目标参考姿势和测试动画预览，但预览用于发现问题，不把作者骨架拍平成游戏路径：

- 标准站姿；
- 极限抬臂和交叉手臂；
- 深蹲、迈步和落脚；
- 头颈极限；
- 一段代表性舞蹈循环；
- 高矮体型的脚底与 root offset 可视化。

预览要显示身体穿插、renderer bounds、摇物碰撞体和表达式权重，帮助作者在导出前修复美术问题。

### 4.6 表情映射

游戏表情先由 Runtime 转成与角色无关的标准语义槽，SDK 作者只对这些槽映射：

基础必选建议：

- `blinkLeft`、`blinkRight`
- `visemeA`、`visemeI`、`visemeU`、`visemeE`、`visemeO`
- `smile`

可选扩展：

- `angry`、`sad`、`surprised`
- `browUp`、`browDown`
- `eyeWide`、`eyeNarrow`
- `lookUp`、`lookDown`、`lookLeft`、`lookRight`

一个语义槽可以驱动多个目标 blendshape，并带比例、曲线、反相和 clamp：

```text
smile 0..1
  → Face / 笑い       scale=1.0
  → Face / 目細       scale=0.25
```

一个目标 blendshape 默认只能由一个映射写入；若作者显式选择组合模式，则 Runtime 按
`max`、`addClamp` 或 `multiply` 合成。默认 `max`，避免多条表情叠加超过作者预期。

没有完整映射只会导致表情退化，不阻断身体 Avatar 导出；引用不存在的 renderer、路径或
blendshape 则硬失败。

### 4.7 摇物和碰撞体

SDK 第一版不依赖 VRM SpringBone、Dynamic Bone 或游戏 `ActorSwingDynamicBone`。统一导出自己的
纯数据描述，Runtime 用同一套 `AvatarSpringSystem` 执行。

作者编辑：

- 链根与可选链尾；
- 是否自动收集单子链；
- stiffness、damping、gravity、drag、inertia；
- 角度限制与局部主轴；
- 每节点半径曲线；
- 碰撞层；
- 胸、腰、腿等语义骨上的 sphere/capsule collider；
- 多条裙摆链分组与相邻链约束；
- 左右镜像复制。

硬失败：链循环、节点不在 Avatar 层级、链跨越无关分叉、没有可解析节点、参数非有限值。

第一版只承诺稳定的 CPU LateUpdate 解算；不承诺布料级自碰撞、相邻裙片无穿透或 GPU cloth。
复杂裙子仍是作者手工工作量最大的部分。

### 4.8 材质策略

“来源不限”必须通过统一的 Unity 输出材质收口。第一版提供三档：

1. `GakumasToon`：SDK 标准默认，目标是融入游戏主光照和描边。
2. `AvatarToon`：为 MMD/VRM 类贴图提供较宽松的转换入口。
3. `Custom`：高级模式，保留作者 Shader，但标记为非兼容性保证范围。

标准模式至少覆盖：

- Opaque
- Cutout
- Transparent
- Emission
- 双面开关
- 阴影和描边基础参数

SDK 要明确区分“模型支持”和“来源材质支持”。导入插件产生的临时 Shader、编辑器预览 Shader、
丢失 Shader 和不属于白名单的 Shader 默认硬失败或要求作者显式转成 `Custom`。

### 4.9 构建输出

一次 Build 完成：

1. 运行全部校验；
2. 复制/生成干净的构建 prefab，不修改作者场景对象；
3. 删除 editor-only marker，将 authoring 数据烘成 TextAsset descriptor；
4. 规范化资源路径和 bundle name；
5. 构建 `StandaloneWindows64` AssetBundle；
6. 生成外部 `mod.json`；
7. 生成 `build-report.json`，保存 SDK、Unity、协议、资产统计和警告；
8. 可选生成 zip，但 zip 只包含分发文件，不包含 Unity 工程源资产。

每次构建生成不可变 `buildId`。Runtime 日志同时打印 mod id、buildId 和 descriptor hash，避免
作者拿旧 AB 配新 manifest 后无法诊断。

---

## 5. 包与协议设计

### 5.1 外部 manifest 和内部 descriptor 分工

`mod.json` 是玩家与管理器协议：

- 包是谁；
- 是否启用；
- AB 在哪里；
- 入口 prefab 和 descriptor 在哪里；
- 替换哪个角色；
- 冲突和显示信息。

AB 内 descriptor 是 SDK 与 Runtime 协议：

- Avatar 根和 Animator；
- renderer 列表；
- 表情映射；
- 摇物链和 collider；
- 材质模式；
- root/scale 策略；
- 协议与构建信息。

玩家配置不重复内部资产细节，防止一份数据存在两个可互相矛盾的来源。

### 5.2 Manifest v1 建议字段

必需字段：

| 字段 | 说明 |
|---|---|
| `schemaVersion` | 外部 manifest 协议，第一版为 `1` |
| `id` | 稳定、全局唯一的 Mod ID |
| `name` | 玩家可见名称 |
| `version` | Mod 自身语义版本 |
| `author` | 作者 |
| `enabled` | 当前启用状态 |
| `bundle` | 相对 Mod 目录的 AB 路径 |
| `asset` | AB 内 Avatar prefab 路径 |
| `descriptor` | AB 内 descriptor TextAsset 路径 |
| `targets` | 至少一个目标角色 |

可选字段：`description`、`homepage`、`cover`、`priority`、`tags`。

路径必须是相对路径，禁止绝对路径和 `..` 逃逸。AB 内资产路径由 SDK 生成并由 Runtime 精确加载。

### 5.3 目标和冲突语义

第一版 target 只有：

```json
{ "characterId": "fktn" }
```

Runtime 以 `characterId` 建冲突组。同一角色只能启用一个完整 Avatar Mod。一个 Mod 可以声明多个
角色，此时它占用所有目标；任何目标与已启用 Mod 相交都拒绝开启，不能出现一半目标生效的状态。

游戏更新导致 characterId 不存在时，Mod 保留安装但显示“不支持当前客户端”，不回退到模糊资源名
匹配。

### 5.4 Descriptor v1 逻辑结构

```json
{
  "protocol": 1,
  "sdkVersion": "0.1.0",
  "unityVersion": "6000.0.67f1",
  "buildId": "...",
  "avatarRoot": ".",
  "animator": ".",
  "renderers": [],
  "expressions": [],
  "springChains": [],
  "colliders": [],
  "rootMotion": {
    "mode": "actorAnchored",
    "groundOffset": 0.0,
    "scaleMode": "author"
  },
  "materials": {
    "mode": "standard"
  }
}
```

具体 JSON Schema 等垂直切片跑通后冻结；当前只冻结职责和关键字段，不提前锁死尚未实测的数据形状。

### 5.5 协议兼容

- Runtime 只加载自己明确支持的 descriptor protocol。
- 新增可选字段保持向后兼容；改变已有语义必须升 protocol。
- SDK 不能用版本字符串猜兼容，构建时写明确 protocol。
- Runtime 遇到未知 protocol 必须拒绝整个 Avatar，并恢复原角色可见状态。
- manifest 成功不代表 AB 可用；启用前要完成入口、descriptor、Avatar 和 renderer 预检。

---

## 6. BepInEx Runtime 设计

> **与实现的差距（2026-08-13）**：本节整套还没实现。今天能换装的代码住在
> `runtime-bepinex/AvatarProbePlugin.cs`（1700+ 行的**勘探探针**，本文档 §7 明确说过它不作
> 发行依赖），发行侧 `AvatarRuntimePlugin.cs` 只有 99 行空壳。已实机验证的运行时职责只有四项：
> hook `BuildModel` 换 part prefab、从被替换部件抄 `m_Layer`、把作者材质的贴图搬到原版材质的
> 克隆上、按需重写顶点 COLOR。
>
> 主线不需要 §6.5 `PoseBridge` 和 §6.7 `ExpressionBridge`（见 §2.1），这两节按备选方案保留。

### 6.1 模块边界

```text
GakumasAvatarRuntime
├─ Bootstrap
│  ├─ BepInEx plugin entry
│  ├─ version/capability checks
│  └─ main-thread dispatcher
├─ Catalog
│  ├─ manifest scan
│  ├─ validation
│  ├─ conflicts
│  └─ enable state persistence
├─ GameAdapter
│  ├─ actor discovery and identity
│  ├─ lifecycle patches
│  ├─ pose source
│  ├─ expression source
│  └─ scene capability detection
├─ Assets
│  ├─ AssetBundle cache
│  ├─ descriptor loader
│  └─ prefab ownership
├─ AvatarHost
│  ├─ spawn / bind / destroy
│  ├─ original visual snapshot
│  └─ per-actor state
├─ Pose
│  ├─ HumanPose path
│  ├─ Generic source adapter
│  └─ root/scale calibration
├─ Expression
│  ├─ canonical channels
│  └─ author blendshape outputs
├─ Dynamics
│  ├─ spring chains
│  └─ colliders
├─ UI
│  └─ mod list / toggle / diagnostics
└─ Diagnostics
   ├─ live actor inspector
   ├─ reference dumper
   └─ structured logs
```

`GameAdapter` 是唯一允许直接引用游戏生成类型、字段和方法的位置。Catalog、包协议、Pose 算法、
Expression、Dynamics 和 SDK 数据模型都应可在不启动游戏的情况下测试。

### 6.2 BepInEx 版本策略

Unity IL2CPP 的 BepInEx 6 仍应视为需要固定构建的外部底座，而不是自动跟随最新版本：

- 锁定一份已在当前客户端启动成功的 `Unity.IL2CPP-win-x64` 构建；
- 连同 Il2CppInterop、Cpp2IL 和 HarmonyX 版本写入 release metadata；
- 不在玩家机器上自动升级；
- 游戏更新后先运行 bootstrap smoke，再发布 Runtime 兼容声明；
- 首次 interop 生成失败时给出可操作错误，不能继续半初始化 Mod；
- 保存已生成 interop assemblies 的版本指纹，避免混用旧客户端产物。

BepInEx 只降低日常 Unity/IL2CPP 开发成本，不消除游戏更新和 metadata 更新风险。

### 6.3 Actor 发现与身份

不能用“场景里第一个 Animator”或 GameObject 名字猜角色。`GameAdapter` 必须找到游戏真正的角色
创建/组装生命周期，并取得稳定 `characterId`。每个活体 Actor 建立：

```text
ActorKey = native Unity instance identity + generation
CharacterId = stable master key
Context = home/live/story/... capability flags
```

Runtime 只在 Actor 已完成原始模型组装后挂 AvatarHost。角色复用、对象池和换装重建必须提升
generation，防止把上一代对象状态恢复到新角色。

### 6.4 原始外观隐藏与恢复

对每个原 renderer 保存精确快照：

- `forceRenderingOff` 或最终选定隐藏属性；
- `enabled`；
- GameObject active 状态；
- ShadowCastingMode 和其他被 Runtime 改动的显示字段。

优先使用不阻断游戏继续写表情和更新状态的隐藏方式。不能简单销毁原 face，也不能假定
`renderer.enabled = false` 后游戏仍会更新其 blendshape。

关闭 Mod 或加载失败时：

1. 停止 Pose/Expression/Dynamics；
2. 销毁作者 AvatarHost 及 Runtime 创建的 Unity 对象；
3. 恢复仍属于同一 Actor generation 的原 renderer 快照；
4. 清理 AB 引用和缓存；
5. 验证原角色重新可见。

任何阶段失败都必须以“原角色可见”收口，不能留下透明角色或半套 Avatar。

### 6.5 PoseBridge

#### Humanoid 源路径

源和目标都为 Humanoid 时，持久化：

- source `HumanPoseHandler`；
- target `HumanPoseHandler`；
- 复用的 `HumanPose` 与 muscle 数组；
- root/ground 校准数据。

每帧在游戏最终身体动画完成后读取 source pose，再写 target。禁止每帧创建 handler、数组、字典
或 LINQ 临时对象。

#### Generic 源路径

若游戏 Animator 是 Generic，需通过一次 reference dump 建立：

- 游戏语义骨 → Transform 路径；
- 游戏 rest local/world rotation；
- 标准人形语义；
- root、hips、足底和身高参考；
- 不参与 Humanoid 的游戏辅助骨排除表。

实现候选有两种，P0 实测后择一：

1. 用隐藏的标准 Humanoid driver 骨架接收 Generic 骨姿势，再由 HumanPoseHandler 读出；
2. 直接按 rest-space rotation delta 写作者 `HumanBodyBones`，并单独处理 hips/root。

选择标准不是代码最短，而是脚底稳定、肩颈和手指质量、更新顺序以及不同体型的一致性。

#### Root 与比例

默认 `actorAnchored`：

- Avatar Root 跟随游戏 Actor 世界位置和朝向；
- 作者自身比例保持不变；
- hips/body pose 使用人形姿势；
- SDK 保存的 `groundOffset` 修正脚底基准；
- 不把游戏角色身高缩放强加给作者模型。

后续可增加 `matchGameHeight`，但不能作为默认。极高/极矮模型与场景道具、镜头构图不匹配属于
可预期结果，SDK 应在预览中告警而不是暗中改比例。

### 6.6 更新顺序

目标顺序：

```text
游戏 Animator 和游戏程序动画
  → 游戏最终身体骨修正
  → PoseBridge 写作者身体
  → ExpressionBridge 写作者表情
  → AvatarSpringSystem 解算裙子/头发
  → 渲染
```

单纯 `LateUpdate` 只是第一候选。若游戏在更晚阶段修改骨或表情，则需 Harmony postfix 到最终更新
点或使用 PlayerLoop 注入。P0 必须用逐帧探针证明顺序，不能只凭画面“似乎能动”。

### 6.7 ExpressionBridge

Runtime 的游戏适配层输出 canonical channel，不把游戏内部 blendshape 名暴露给作者包：

```text
Game face state
  → GakumasExpressionAdapter
  → canonical channels 0..1
  → descriptor mappings
  → target renderer.SetBlendShapeWeight(index, weight)
```

优先让隐藏原 face 继续被游戏驱动，再在最终更新后读取它的实时权重或上游控制状态。运行时加载
作者 Mesh 后按名字解析并缓存目标 blendshape index；每帧只写发生有效变化的权重。

必须实测：

- 游戏按名字还是按 index 驱动原 face；
- face 是否分多个 renderer；
- 眨眼、口型和剧情表情是否来自同一路径；
- renderer 隐藏后权重是否继续更新；
- 同帧表情写入的最终时序。

### 6.8 Dynamics

`AvatarSpringSystem` 只操作作者 Avatar 的装饰骨，不写游戏骨架。它在 PoseBridge 后更新，按
descriptor 创建链和 collider。第一版重点：

- 正确生命周期；
- 无 NaN、无爆炸；
- 帧率变化下行为可接受；
- 角色切换和热卸载无残留；
- 多 Avatar 实例互不共享运行状态。

所有运行时缓存属于 AvatarHost；同一个 prefab 实例化两次必须有两套独立的粒子/链状态。

### 6.9 AssetBundle 生命周期

- manifest 扫描不等于立刻加载全部 AB；按启用目标和 Actor 出现懒加载。
- 同一 Mod 多个 Actor 实例共享 AB 和只读 descriptor，但 prefab、Material 实例和模拟状态按 Actor
  独立。
- Runtime 创建的 GameObject、Material 或 Mesh 明确记录所有权并 `Object.Destroy`。
- AB 的 unload 只能在没有活体实例和无其他共享引用时执行。
- 热重载先创建并验证新 Host，成功后再切换显示；失败继续保留旧 Host 或恢复原角色。

### 6.10 管理与诊断 UI

玩家 UI 只显示：

- Mod 名称、作者、版本、封面；
- 替换角色的官方名称；
- 开关、冲突和兼容状态；
- 必要的“需要重新进入场景”提示。

开发模式额外显示：

- 当前 Actor、characterId、context、generation；
- 源 Animator 类型和 Avatar 状态；
- Pose/Expression 更新点与最近帧；
- 作者 Avatar、renderer、morph 和 dynamics 绑定结果；
- 每阶段 CPU 时间、分配和对象数；
- 一键 dump reference 和验证报告。

不能让作者通过猜日志完成常规制作。凡是 SDK 能在导出前确定的问题，都应在 SDK 硬失败。

---

## 7. 参考数据与维护流水线

Runtime 不应把角色差异散落成大量 `if (characterId)`。游戏版本 reference 至少包含：

- 客户端 build/version；
- 角色 Master ID 与显示名；
- Actor 定位和身份字段；
- 源 Animator 类型；
- Generic 路径需要的语义骨路径和 rest pose；
- 原 face renderer、blendshape 列表和 canonical expression 映射；
- 原 visual renderer 分类；
- 支持场景与已知生命周期差异。

建立自动化 `runtime dump → normalized reference → diff → reviewed update`：

1. 开发版 Runtime 在当前客户端 dump 活体 Actor。
2. 工具生成稳定排序、去实例地址的 reference。
3. 与上一客户端 reference 做结构 diff。
4. 对骨、face 和身份变化运行兼容测试。
5. 人工确认后随 Runtime adapter 发布。

SDK 不需要为每个角色携带完整骨架 reference；这些是游戏 Runtime 的版本数据。作者只在
`mod.json` 选择 `characterId`。

---

## 8. 开发路线与阶段门

原则：**先证明 Runtime 抽象成立，再投入完整 SDK UI。** 当前 C++ Runtime 和七个实机成品继续
作为画面、材质和生命周期对照；在新路线通过正式阶段门之前不迁移、不删除。

**2026-08-13 实际进度对照**（阶段划分按下面原文，完成度按实现）：

| 阶段 | 状态 | 说明 |
|---|---|---|
| P0 | ✅ 已过门 | 出口条件全部满足，另外顺带冻结了摇物、静态碰撞笼、t1/t4/COLOR 语义的真值 |
| P1 | ⚠️ 主线机制改了，只做了 body 外观 | 换装机制、骨架、蒙皮、材质、贴图、顶点色、摇物、静态碰撞都实机通过；**face / hair / 饰品 / 表情 / ON-OFF / 泄漏检查 = 0**。下面 P1 原文里的 AvatarHost / PoseBridge / ExpressionBridge 属于 §2.1a 备选方案，主线不做 |
| P2 | ❌ 未开始 | schema 与校验器都在（`contracts/`、`runtime-core/`、`tools/`），但实机那条管线**不产出 descriptor/manifest**，配置是探针目录下四行手写 txt |
| P3 | ❌ 未开始 | 实机那条管线的输入路径写死在源码里，吃 AssetStudio JSON 而不是作者 prefab；§3.1 承诺的作者流程一步都没有 |

**当前最偏离目标的一项**：§3.1 明确承诺作者"不需要提取 Mesh JSON"，而实机管线恰恰只吃 JSON。
下一步工作按此排序：把输入换成工程里的 Unity prefab → 把换装逻辑从探针搬进发行插件 → 接上
descriptor/manifest → 材质/摇物改成作者标注而不是按骨名和颜色猜。

### P0：平台与活体勘探

目标：回答所有能推翻架构的未知项。

工作：

- 固定一份 BepInEx IL2CPP 构建，用精确 Unity `6000.0.77f1` 空白 IL2CPP player 离线生成标准 interop，并在当前客户端禁用自动生成后加载；
- 加载最小插件，验证主线程 Unity API、Harmony patch、自定义注入 `MonoBehaviour`；
- 定位真实 Actor 生命周期和稳定 characterId；
- dump Animator 类型、Avatar、骨架、原 renderer、face blendshape 与材质；
- 证明隐藏原 renderer 后游戏逻辑、表情和动画仍继续更新；
- 确定最终 pose 与 expression 更新时序。

出口条件：

- 连续启动三次均稳定加载；
- 至少主页和一个非主页场景能稳定识别同一角色；
- 明确回答 Humanoid/Generic；
- 保存一份可重复生成的 reference；
- 不修改业务游戏代码或现有 Runtime。

失败收口：如果预生成标准 interop 仍无法在当前客户端稳定 bootstrap，整条 Runtime 路线暂停；不再回到目标 `GameAssembly.dll` 捕获/Cpp2IL 循环。

### P1：手工垂直切片

目标：不做正式 SDK，用手工 prefab 和最小 C# Runtime 证明完整 AvatarHost。

样本要求：

- 一个与游戏体型明显不同的有效 Humanoid 模型；
- body、hair、face 至少三个 renderer；
- 眨眼和五口型；
- 一条长发或裙摆链。

工作：

- 手工制作 AB + descriptor + manifest；
- Actor 出现后加载完整 prefab；
- 隐藏原外观并保留游戏 Actor；
- PoseBridge 跑通站立、移动、舞蹈和镜头切换；
- ExpressionBridge 跑通眨眼、口型和一个剧情表情；
- 一条作者摇物链工作；
- OFF 恢复原角色，ON 重建 Avatar；
- 场景退出无 Unity 对象和 AB 引用泄漏。

出口条件：

- 身体比例保持作者模型原样；
- 连续运行和切场景无明显一帧延迟、脚底漂移或骨骼爆炸；
- 连续 20 轮 ON/OFF/ON 后对象数和原生内存不持续增长；
- 任一加载错误都能自动恢复原角色可见。

失败分支：

- HumanPose 质量不足：比较 direct bone retarget 和隐藏 driver；
- Generic 源无法稳定标准化：将游戏 reference 骨适配作为核心，而不是把复杂性推回作者；
- 表情无法从隐藏原脸读取：向上游表情控制器 patch，但仍输出 canonical channel。

### P2：协议和无 UI 构建器

目标：冻结能支撑 SDK 的最小包契约。

工作：

- 定义 manifest v1、descriptor v1 和验证器；
- Unity 菜单命令从指定 prefab 生成标准包；
- Runtime 严格校验 protocol、buildId、Avatar 和资产路径；
- 支持多 renderer、标准材质和表达式表；
- 建立 SDK/Runtime 共用协议测试样本；
- 增加坏包、旧协议、缺资产和路径逃逸测试。

出口条件：同一个源工程可重复得到语义一致的包，错误包在进入场景前被拒绝。

### P3：Unity SDK MVP

目标：作者无需手写 JSON 和构建脚本。

工作：

- 六块式 EditorWindow；
- 自动 renderer 发现与分类；
- Humanoid、路径、Missing Script 和资产依赖校验；
- 基础 expression mapping UI；
- 简单 spring chain/collider authoring；
- 标准材质转换；
- 一键 Build Package 和 build report；
- 一个完整 sample Avatar 和作者文档。

出口条件：一位未参与 Runtime 开发的测试作者只按文档，把一个已有 Humanoid 模型打成可进游戏
的包；过程中不编辑 JSON、不接触游戏骨名和资源名。

### P4：场景覆盖和产品化

目标：从技术样片变成普通玩家可用的 Mod 系统。

工作：

- 覆盖已确认存在的主页、演出、剧情等角色场景；
- 对象池、换装、重登录、多人/多 Actor 场景；
- 管理 UI、冲突、错误恢复和封面；
- AB 缓存、加载时间、内存和 GC 优化；
- 日志轮转和诊断包导出；
- 固定 BepInEx 分发与安装器；
- 游戏更新 smoke/reference diff 流程。

出口条件：支持场景矩阵全部通过，普通玩家不需要 UnityExplorer 或手动清缓存才能使用。

### P5：高级表现

只有 P4 稳定后再开展：

- 更细游戏表情语义；
- 眼神和注视目标桥接；
- 相邻裙摆约束、更稳定的碰撞；
- Custom Shader 高级接口；
- Avatar LOD；
- 第一人称/摄影模式特殊规则；
- SDK 批量校验和命令行 CI 构建。

这些不是 MVP 条件，不能挤占 Pose、生命周期和失败恢复。

---

## 9. 验证矩阵

### 9.1 模型矩阵

至少保留以下真实样本，不能只用一个模型证明“任意 Humanoid”：

| 样本 | 证明目标 |
|---|---|
| Unity/标准 Humanoid | 基线 |
| Mixamo | 常见英文骨架来源 |
| VRM/VRoid | 多 renderer、日系表情与材质 |
| MMD 转 Humanoid | 日文 morph、复杂裙骨和中间层 |
| 明显矮于游戏角色 | 作者比例、脚底和镜头 |
| 明显高于游戏角色 | 作者比例、root 和场景交互 |
| 无完整表情模型 | 表情退化而非整体失败 |
| 多材质透明模型 | 标准材质边界 |

每个“来源支持”声明必须来自真实模型完整打包和实机，不从命名规范或理论推断。

### 9.2 动作矩阵

- 待机与呼吸；
- 行走/转身；
- 快速舞蹈；
- 双臂过肩与手交叉；
- 深蹲和单脚支撑；
- 头颈大角度；
- 镜头切换和暂停恢复；
- 低帧率与帧率波动。

检查肩、肘、腕、髋、膝、足、脊柱、头颈、脚底、root 朝向和一帧延迟。

### 9.3 表情矩阵

- 左右独立眨眼；
- 五口型连续切换；
- 说话同时眨眼；
- 笑、惊讶、悲伤等组合；
- 表情权重快速归零；
- 多 renderer face；
- 缺目标 morph；
- 同一 morph 多输入合成。

### 9.4 生命周期矩阵

- 启动即启用；
- Actor 已存在后热 ON；
- 热 OFF；
- 连续 ON/OFF/ON；
- 换场景；
- 同场景角色重建；
- 换装但 characterId 不变；
- 多 Actor；
- AB 损坏、descriptor 损坏、Avatar 无效；
- 游戏退出和异常返回主页。

### 9.5 性能观测

第一版不先虚构硬预算，但必须逐帧记录并设回归基线：

- PoseBridge CPU 时间；
- ExpressionBridge CPU 时间；
- Dynamics CPU 时间；
- 每帧 GC allocation，目标稳态为 0；
- 每 Avatar GameObject/Transform/renderer 数；
- Mesh、Material、Texture 和 AB 原生内存；
- 首次加载和二次实例化耗时；
- 20 轮热切换后的对象与内存趋势。

性能门在 P1 样本测量后冻结，不能用未经实测的毫秒数字当设计事实。

---

## 10. 主要风险与对策

| 风险 | 影响 | 当前对策 |
|---|---|---|
| BepInEx/Cpp2IL 不支持客户端 metadata | Runtime 无法启动 | P0 第一门；固定实测构建，不先开发 SDK |
| 游戏源 Animator 是复杂 Generic | 直接 HumanPose 不可用 | GamePoseAdapter + reference；作者仍只面对 Humanoid |
| 游戏晚于 Runtime 修改身体骨 | 抖动或一帧延迟 | 查最终更新点，Harmony postfix/PlayerLoop 注入 |
| 不同体型导致脚底、道具和镜头错位 | 表现不自然 | actorAnchored + groundOffset + SDK 极端体型预览 |
| 原 renderer 隐藏后停止表情更新 | 作者脸无表情 | 选择不阻断更新的隐藏方式，必要时 patch 上游表情控制器 |
| HumanPose muscle 丢失非人形辅助骨 | 发饰/裙子无动作 | 身体只走 Humanoid；装饰骨由作者 dynamics 自驱 |
| 自定义 Shader 与游戏管线不兼容 | 粉色、无阴影、画风割裂 | 标准 Shader 默认，Custom 明确降级支持 |
| AB 中未知组件或丢脚本 | 加载异常 | SDK 与 Runtime 双重白名单/缺脚本校验 |
| AvatarHost 热卸载泄漏 Unity 原生对象 | 长会话内存上涨 | 明确所有权、Destroy、20 轮生命周期门 |
| 游戏更新改变 Actor/face 字段 | Mod 失效或崩溃 | 游戏类型只在 Adapter，自动 dump/diff reference，fail closed |
| “任意模型”被误解成零准备 | 用户预期失控 | 文档始终写“任意有效 Unity Humanoid”，校验给明确修复入口 |
| 复杂裙子工作量仍高 | 作者门槛 | 链批量、镜像和预设；不虚假承诺全自动布料 |

---

## 11. 工程与仓库规划

设计验证后建议拆为三个发布单元，但协议模型共享：

```text
gakumas-avatar-sdk/          Unity Package、样本、作者文档
gakumas-avatar-runtime/      BepInEx IL2CPP plugin、游戏 Adapter、玩家 UI
gakumas-avatar-contracts/    JSON Schema、C# DTO、协议测试向量
```

如果维护成本要求先单仓，目录也应保持同样边界：

```text
src/
├─ Contracts/
├─ Runtime.Core/
├─ Runtime.GameAdapter/
├─ Runtime.Plugin/
├─ Sdk.Editor/
└─ Tests/
```

测试分层：

- Contracts：纯 .NET，schema、路径、冲突、兼容；
- Pose math：纯 .NET/Unity Test Framework，rest delta、root、scale；
- SDK：EditMode，校验器、构建器、坏 prefab；
- Runtime core：脱离游戏的 catalog、descriptor、状态机；
- Game adapter：metadata/reference 契约测试；
- PlayMode：作者 Avatar prefab、表情、dynamics；
- 实机：场景、生命周期、画面和内存。

当前 `gakumas-mod-runtime` 不直接原地改写成新 Runtime。P0/P1 使用独立实验插件，避免未验证的
BepInEx 路线破坏已发布系统。P2 冻结协议后再决定是否复用管理器数据模型和 manifest 逻辑。

---

## 12. 已冻结决策、待验证事实和暂缓决策

### 12.1 已冻结的产品决策

1. PC Windows only，不考虑 Android。
2. 作者输出必须是有效 Unity Humanoid Avatar。
3. 模型来源、骨名、层级和身体比例不进入**玩家**配置。（**修正**：骨名仍进入**作者**流程 ——
   游戏按名字解析 Humanoid 映射，见 §2.2，所以 SDK 需要一步骨名重映射。）
4. 默认保留游戏 Actor/Animator/逻辑，替换完整外观。
5. ~~作者 Avatar 保留自己的骨架，由 Runtime 做姿势桥接。~~ **已改**：作者骨架照样保留，但姿势
   重定向由**游戏自己**完成（§2.1），Runtime 不做姿势桥接。
6. `mod.json` 按稳定 `characterId` 选择目标，不按具体服装资源名。
   （**未兑现**：当前实现按服装资源名匹配，玩家换衣服即失效。）
7. 一个包可以携带所有 renderer、脸、表情和作者物理。
8. 作者代码不随 AB 执行；Runtime 功能由数据描述。
9. Unity SDK 是唯一正式作者入口，手写 JSON 仅用于开发和诊断。
10. 当前已发布 C++ AB Runtime 在新路线过门前保持不动。

### 12.2 P0 必须回答的事实

1. 当前游戏 Animator 是 Humanoid 还是 Generic，是否因场景不同。
2. 最终身体骨更新点在哪里。
3. characterId 从哪个活体组件稳定取得。
4. 原 face 的 renderer、blendshape 和驱动入口是什么。
5. 隐藏原 renderer 后 face 权重是否继续变化。
6. 当前 BepInEx/Il2CppInterop 固定构建与预生成缓存能否稳定启动 Unity `6000.0.77f1`。
7. 当前游戏渲染管线下，SDK 标准 Shader 的最低正确实现是什么。
8. Actor 在主页、演出和剧情场景的组装与销毁时序是否共用适配点。

### 12.3 暂缓到实证后决定

- Generic 源采用隐藏 driver 还是 direct bone delta；
- 原 renderer 用 `forceRenderingOff`、`enabled` 还是游戏专用显示开关；
- 标准 Shader 是复刻游戏材质、独立 Toon，还是混合策略；
- Runtime UI 复用当前游戏内设置页还是先用独立开发 UI；
- manifest 是否沿用现有 Mod Manager 的字段外壳；
- 是否支持按服装或场景过滤 target；
- 是否允许同一个角色按上下文启用多个 Avatar；
- dynamics 是否需要 Jobs/Burst 或 GPU 路线。

这些决策都依赖 P0/P1 证据，设计稿不假装已经知道答案。

---

## 13. 最小成功定义

这条路线的第一个真正成功，不是 SDK 窗口完成，也不是 AB 能加载，而是：

> 取一个来源与学马无关、比例明显不同、带脸和一条裙子/长发链的 Unity Humanoid 模型，作者不
> 改游戏骨名、不提取目标服装、不写 JSON；SDK 导出后只在 `mod.json` 选择一个 characterId，
> 游戏中该角色在至少两个场景保持作者比例播放原游戏动作、眨眼和口型，摇物工作，且连续热开关
> 和切场景不会泄漏或留下不可见原角色。

达到这一条，才说明“只做 Unity SDK，不关心用户模型从哪来、长什么样”的核心契约成立。

---

## 14. 外部技术依据

- BepInEx IL2CPP 安装仍使用其特定 IL2CPP 构建流程：
  <https://docs.bepinex.dev/master/articles/user_guide/installation/unity_il2cpp.html>
- BepInEx 提供 HarmonyX 与 RuntimeDetour：
  <https://docs.bepinex.dev/master/articles/dev_guide/runtime_patching.html>
- Il2CppInterop 自定义类型注入能力与限制：
  <https://github.com/BepInEx/Il2CppInterop/blob/master/Documentation/Class-Injection.md>
- Unity `HumanPoseHandler`：
  <https://docs.unity3d.com/6000.0/Documentation/ScriptReference/HumanPoseHandler.html>
- Unity blendshape 写入是 renderer + index 接口：
  <https://docs.unity3d.com/6000.0/Documentation/ScriptReference/SkinnedMeshRenderer.SetBlendShapeWeight.html>

这些资料证明 API 能力，不代替当前游戏的 P0 实机验证。
