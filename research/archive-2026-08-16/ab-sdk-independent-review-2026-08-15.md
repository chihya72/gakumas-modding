# AB 与 Unity SDK 路线独立评审

日期：2026-08-15  
性质：独立技术评审，不是原方案的续写，也不是实现状态报告

## 1. 评审目的

本评审回答四个问题：

1. AB（native/AssetBundle 补丁）与 Unity SDK（自建 prefab）路线的结构性优劣是什么。
2. AB 应该从 SDK 的研究和实现中吸收什么。
3. `ab-route-v2-full-record.md` 与 `ab-v2-plan.md` 的核心论证和具体数据是否真实。
4. AB 能否进一步吸收 SDK 的自定义 Renderer，以及“Humanoid 不要求模型与游戏骨架完全一致”的能力。

评审重点是路线与论据。代码接线或局部 bug 只作为成熟度背景，不影响本轮路线判断。

## 2. 检查范围与方法

完整阅读：

- `research/ab-route-v2-full-record.md`
- `research/ab-v2-plan.md`

独立对照：

- AB 运行时：`../../gakumas-mod-runtime/src/runtime/ModRuntime.cpp`
- SDK 编辑器与运行时：`research/unity-humanoid-avatar-sdk/`
- SDK 组件/材质统计：`research/unity-humanoid-avatar-sdk/docs/body-component-inventory.md`
- 工作区迁移清单：`../../mod-workspace/backups/blend-originals/original-migration-manifest.json`
- 530 套原版 body bundle 的 driver、swing 和材质扫描结果
- 当前 IDA 数据库中的 `UnityFramework`

当前 IDA 样本：

- 文件：`D:\GIT\gkms-localify-ios\workspace\3.2.3\input\UnityFramework`
- SHA-256：`896585dff04ef0dabc6efe68172cc906c56133471b61145ffcfea50dc0846edd`

本轮没有重新逐个进游戏复演所有历史成品。因此“某个历史成品画面级成功/失败”只能归类为带产物支撑的项目记录，不能提升为本轮独立实机结论或受控成功率对比。

## 3. 总结论

在以下明确范围内，文档把 AB 定为主线是正确的：

> 将外部身体、服装、头发或脸替换进现有角色槽，同时尽量继续使用游戏原生的动画、骨架、材质初始化、物理组件和跨部件连接。

原因是结构性的：AB 修改原 prefab 上的活体 Renderer；SDK 把自建 prefab 交给游戏。前者天然保留更多游戏对象侧状态，后者必须重新提供游戏初始化所需的骨、组件、引用和渲染结构。

但两份文档把这种相对优势写得过于绝对。准确结论应是：

> AB 大量继承游戏对象侧契约，但仍有显著的模型、mesh、bindpose、骨序、材质、sidecar 和运行时契约；SDK 不需要手工重建游戏的每张内部列表，却必须提供足够的对象、组件和引用，让游戏能够重新填充这些列表。

SDK 应继续保留为：

- 完全不同的 Renderer/组件图或 prefab 层级的逃生舱；
- 自定义 Humanoid 比例或独立骨架的实验路线；
- Unity 内可视化检查、逆向结论验证和离线台架；
- AB 新能力的数据来源和原型环境。

即使关节间插骨实验 P4-E 成功，也只能说明 SDK 在“常规宿主替换”范围内可能不再必需，不能证明 SDK 在所有结构性场景中的必要性归零。

## 4. AB 与 SDK 的真实对比

| 维度 | AB 路线 | Unity SDK 路线 |
|---|---|---|
| 游戏对象 | 保留原 prefab 和原活体对象 | 注入/替换为自建 prefab |
| Renderer | 默认把 mod mesh 写入原 Renderer | 自带 Renderer，可自由组织数量与层级 |
| 骨架 | 原活体骨 + 可新增辅助 Transform | 模型自己的完整骨架 |
| Humanoid | 继续使用游戏驱动的原活体 Humanoid 骨 | 为自建骨架建立/满足 Humanoid 映射 |
| 组件 | 原骨上的原组件天然保留；新骨才需要补 | 必须在自建对象上提供需要的组件和引用 |
| 材质 | 最安全地使用当前场景的原活体材质，可逐槽覆盖 | 当前实现也克隆当前场景的游戏材质，再转移 mod 贴图 |
| 模型制作成本 | A→T、合身、权重、破面、材质仍然是主要工作 | 同样存在，另加 Unity/Avatar/prefab 调试 |
| 结构自由度 | 受宿主 Renderer、骨架连接和生命周期约束 | 更适合完全不同的层级、比例、Renderer 和组件图 |
| 调试可观察性 | 运行时问题较多，常需进游戏检查 | Unity 内可以直接检查层级、组件、引用和 Avatar |
| 更新风险 | 少重建内容契约，但 native/IL2CPP hook 仍需维护 | 同时依赖运行时 hook、游戏组件类型和 Unity 序列化契约 |

### 4.1 AB 的决定性优势

`ModRuntime.cpp` 当前流程会：

1. 取得原 Renderer 与 mod Renderer；
2. 克隆 mod mesh；
3. 把顶点、法线、切线变换到原 Renderer 空间；
4. 把 skinning 修补到原活体骨或 hybrid bones；
5. 将 mesh 写回原 `SkinnedMeshRenderer`；
6. 默认继续使用原材质，并选择性覆盖贴图、颜色或 float。

关键位置：

- Renderer 配对和原状态快照：`ModRuntime.cpp:4500-4517`
- mesh 和 skinning 写回原 Renderer：`ModRuntime.cpp:4524-4536`
- 材质保留/覆盖：`ModRuntime.cpp:4559-4592`
- 缺失骨的运行时 graft：`ModRuntime.cpp:3135-3184`

因此 AB 继承的是原 `CampusActorModelParts`、原初始化时序、原骨名关系、原场景材质和原骨组件，而不仅是一个静态 mesh 模板。

### 4.2 SDK 的真实优势

SDK 的优势并不只是“能任意建骨”，因为 AB 也已经能新增 Transform。SDK 更有价值的部分是：

- 可直接设计整个 prefab、Renderer 数量和对象层级；
- 可在 Unity 内观察 Avatar、Renderer、组件和序列化引用；
- 更容易表达自定义比例和完整独立骨架；
- 更容易挂载复杂或新型组件；
- 可作为原版组件、材质和 Humanoid 行为的台架。

代价是，自建对象不能天然获得原 prefab 上已经存在的组件和关系。当前 SDK 运行时甚至要显式确保 `CampusActorModelParts` 存在，见：

- `research/unity-humanoid-avatar-sdk/runtime-bepinex/AvatarProbePlugin.cs:829-849`

这说明 SDK 的风险确实比 AB 大，但不等于它要手工填充 `CampusActorModelParts` 的全部内部列表。

## 5. 文档真实性分级

### 5.1 已独立确认

#### 19 根 Humanoid 必备骨

IDA 确认：

- `0xA845FF4` 分配长度为 19 的 bool 数组；
- `0xA846130` 按 HumanBodyBones 下标置位；
- `0xA846228` 对全部元素做 AND 检查。

因此 `HumanBodyBones` 0–18 必须存在的结论成立。

#### `RegisterBone`、重名与组件收集

IDA 中 `0xA8840E0` 的行为与文档核心伪代码一致：

- `_boneMap.ContainsKey(name)` 后直接早退；
- `layer >= 0` 时写 GameObject layer；
- 带 Renderer 的对象登记为 Renderer；
- 不带 Renderer 的对象登记为骨；
- 最后调用虚方法 `OnRegisterBone(name, bone)`。

所以重名不仅是覆盖风险，而是整根骨及其组件可能完全不被收集。这个结论成立。

#### `TransformCapacity = 256` 是软容量

`RegisterBone` 没有 256 边界检查，内部列表会正常扩容。因此 256 可以作为复杂度/风险 warning，不能写成硬错误或严格不变量。

#### AB 可以新增辅助骨

运行时已有 live skeleton graft、创建缺失骨、设置父子关系、替换 Renderer bones 和写入 mod bindposes 的路径。文档纠正“AB 固定 146 根骨”是正确的。

限定条件也正确：能创建任意辅助 Transform，不代表这些骨自动成为 Humanoid muscle 驱动骨。Humanoid 驱动仍取决于 Avatar 映射和游戏认识的骨名。

#### 12 种 QuartzDriver 及其分布

530 套 body bundle 全部扫描成功，12 种驱动器类型及主要计数与文档吻合。当前 SDK 的 `QuartzDriverRigger` 实际实现五类：

- HumanoidArm
- HumanoidHand
- HumanoidUpLeg
- Rotation
- Skirt

原版引用数据也支持以下可移植性判断：

- Skirt 引用 Left/RightUpLeg，可跨服装使用；
- Frill 引用 Left/RightArm；
- HumanoidSleeve 引用 Left/RightHand；
- Waist、Furisode、Poncho 依赖服装自己的 `*_O` 偏移骨，不能只复制 setting 后安装到任意目标。

#### AB 不会免除模型侧工作

A→T、合身、关节位置、权重、破面、透明和材质语义仍然需要作者处理。文档后来把“游戏侧继承”与“模型侧免费”明确区分，这是正确的修正。

### 5.2 方向正确，但措辞过强

#### “AB 契约面 ≈ 0；SDK ≈ 全部”

这个说法只有在把“契约面”严格限定为“原 prefab 已存在的游戏对象侧组件与初始化关系”时才近似成立。

AB 仍必须满足：

- mesh 坐标空间；
- 骨名、骨序和 parentIndex；
- bindpose 与 renderer 空间；
- boneWeights 与索引范围；
- submesh 和材质槽对应；
- COLOR、UV、法线和切线语义；
- sidecar/manifest 与运行时协议；
- 新骨上的 driver/swing/collider 互斥和引用完整性。

建议统一改为“AB 的游戏对象侧契约大部分继承，SDK 必须重新提供相应输入”。

#### “SDK 全部重建 22 个 List”

字面上不成立。SDK 运行时只需保证 `CampusActorModelParts` 以及骨上组件存在，游戏自己的 `Initialize/ProcessBones/UpdateSkinnedMeshRenderers` 会填充内部列表。

SDK 的真实负担是重建这些列表赖以形成的对象、组件和引用，而不是手工 new 并逐项填 22 张 List。

#### “AB 100% 无损”

当前 lossless graft 路径确实不会主动丢弃合法的四权重数据，并保留 mod bindposes；但运行时仍会做坐标变换、骨数组替换和 bindpose 空间修正。“不做破坏性权重重分配”比“100% 无损”更准确。

#### “模型侧成本同一量级”

这个判断合理，但现有证据主要证明 AB 的模型侧成本很高，并不是 AB/SDK 在相同模型、相同质量目标下的受控工时对比。因此应标为工程判断，不应当成统计结论。

#### “AB 5 个成品，SDK 2 个/MMD 0 个”

这可以证明当前 AB 工具链已经有更丰富的项目经验，也可以证明某些路线可行；不能直接推出两条路线的理论成功率。模型难度、时间投入、实现成熟度和验收目标都没有控制。

### 5.3 明确错误或内部矛盾

#### 材质“3/32”对比失真

`BodyImporter.cs:273-302` 确实只在 SDK placeholder material 上绑定：

- `_BaseMap`
- `_ShadeMap`
- `_DefMap`

但 SDK 运行时的真实做法不是直接使用 placeholder shader，而是：

1. 从当前场景的原 Renderer 取得游戏材质；
2. 按 `m_bdy`/`m_bdyco` 等名字选模板；
3. 复制构造游戏材质；
4. 把 mod 的三张贴图转移到克隆材质；
5. 将克隆材质设置到 mod Renderer。

见 `runtime-bepinex/AvatarProbePlugin.cs:949-1026`。

因此“SDK 只写 3 个属性，剩余 29 个必须重建”不成立。SDK 会继承模板材质上的 shader、共享 ramp 和其他参数。

反过来，“AB 继承原材质，所以 32 个属性全对”也不是普遍事实。530 套材质扫描显示，下列项目随服装变化：

- `_RampAddMap`：服装专属的 `*_bdy_rma`；
- `_RampAddColor`；
- `_DefValue`；
- `_Glossiness`/`_Smoothness`；
- `_SrcBlend`/`_DstBlend`。

当前如果只覆盖 Base/Def/Shade，不论 AB 还是 SDK，都会继承被替换宿主的这些值，而不是自动得到新服装正确的值。

AB 在材质生命周期上仍更安全，因为它使用当前活体 Renderer 的材质；但“32 项天然全对”必须删除或改成“游戏公共参数与当前场景初始化状态天然继承，服装专属参数仍需显式处理”。

#### “54 个候选 → 7 个成品”不成立

`B054` 是编号，不是数量。

`../../mod-workspace/backups/blend-originals/original-migration-manifest.json` 当前只有 9 条记录：

- B005
- B007
- B010
- B015
- B019
- B027
- B036
- B053
- B054

现有证据只支持“9 个已归档原始/候选 blend → 7 个最终 authoring blend”。如果确实曾有 54 个候选，需要补出目录清单、迁移记录或其他可复现来源。

#### 256 同时被写成“不变量”和“软 warning”

两份文档后段已经正确写出 256 不是硬上限，但不变量表仍保留“节点总数 ≤ 256”。这在逻辑上冲突。应改为预算 warning，例如：

> 节点数超过原版已知常见范围或 256 时报告复杂度风险，但不阻止出包。

### 5.4 尚未证实

#### P4-E：Humanoid 关节之间插骨

AB 已经能新增叶子或辅助骨，但尚未证明可以在 `Spine1` 与肩/颈之间插入 `Spine2` 后，仍让游戏正确建立 Avatar、播放动画并维持跨部件关系。

在 P4-E 实机完成之前：

- 不能写“AB 确认做不到”；
- 也不能写“SDK 必要性将归零”；
- 正确状态是“结构性边界未决”。

#### 历史画面级成功记录

盘上存在成品、release、blend 和实验记录，但本轮没有逐个重新进入换装、live、撮影等场景复验。因此这些记录可作为工程历史，不能当作本轮独立画面确认。

## 6. 其他数据核对

### 6.1 Swing 全量重扫

重新扫描 530 个原版 body bundle：

- 失败：0
- 骨记录：48,292
- chain：1,539
- layer：5,223
- 排除 layer 0 后，`around=1`：1,334 / 3,684 = 36.21%
- 各层 smoothing 的中位数均为 0

所以“around 大约四成、smoothing 中位数为 0”的定性结论成立。但文档中的 174-chain 样本范围没有说明，应补充样本来源，避免被误读为全 530 套统计。

### 6.2 `UpdateChainInfo`

IDA 的 `0x1316A88` 确认旧 chain/layer 存在时会继承部分字段，新层才写默认值。文档的行为结论成立。

当前 IDA 中该函数实际大小约为 `0xA34`，文档记录的 `0xA20` 是轻微陈旧的函数范围信息，不影响行为结论。

### 6.3 工作区规模

当前 `mod-workspace` 总量约为 26.0 GiB；文档写 26.6 GB，可能是十进制/二进制单位或盘点时间差，不构成实质错误。具体重项目的文件数和体积基本吻合。

## 7. AB 应该从 SDK 学什么

原则：吸收 SDK 的数据、测量、验证和作者反馈，不把“自建整个 prefab”重新变成默认路线。

### 7.1 材质语义与逐场景生命周期

这是当前文档遗漏最大、最值得优先吸收的一项。

AB 应明确区分：

- 游戏/角色公共材质状态：继续从当前活体材质继承；
- 服装专属状态：允许由 manifest 或作者工具提供；
- 场景动态绑定状态：不得提前冻结，必须从当前场景模板取得。

至少应支持审计和显式覆盖：

- `_RampAddMap`
- `_RampAddColor`
- `_DefValue`
- `_Glossiness`/`_Smoothness`
- `_SrcBlend`/`_DstBlend`
- alpha test/cutout 对应参数

SDK 遇到过克隆材质跨场景后 `_RampMap`/`_RampAddMap` 引用失效的问题。AB 默认使用活体材质可以避开这类问题，但一旦增加自定义 Renderer 或私有材质克隆，同一生命周期规则也会重新出现。

### 7.2 几何分类、预览与人工覆盖

应吸收 SDK 的 ChainClassifier 思路：

- 按几何位置、方向、链长、分叉和父骨判断候选类别；
- 输出置信度和分类理由；
- 在 Blender/preview 中可视化；
- 允许作者逐链覆盖；
- report 明确“不确定”，而不是静默采用猜测。

目标应是降低调参成本，不是宣称语义分类可以完全自动化。

### 7.3 姿势、roll 与关节塌陷测量

SDK 的价值在测量方法，而不是把当前 `TPoseBaker` 原样搬入 AB。

可复用：

- rest-pose 方向偏差；
- 左右 roll 对称性；
- 手掌和手指方向；
- 肩、肘、腕、膝的弯曲/扭转塌陷探针；
- helper bone 承重与跨关节混合带统计。

不应直接复用：

- 只覆盖有限骨的固定瞄准表；
- 单一样本标定出来的 palm/roll 常量；
- 看不到 Shoulder、Spine、Neck、Head、Foot 的“自动 T-pose”结论。

### 7.4 Helper 权重和 Driver 数据

AB 应吸收 SDK/原版扫描得到的统计和语义：

- 哪类 helper 骨在原版承担多少权重；
- 哪些 driver 读取 Humanoid DOF；
- 哪些 driver 引用通用身体骨；
- 哪些依赖服装自己的 `*_O` 偏移骨；
- driver、ActorSwing 和 collider 的写入互斥关系。

但不要机械实现并自动安装全部 12 种 driver。原骨已经有的组件应继续复用；只在新增骨确实需要且引用完整时创建新组件。

### 7.5 台架、闸门和可复现报告

SDK 在 Unity 中的可观察性应移植为 AB 的：

- dry-run；
- preview；
- 变更前后量化；
- per-job 开关；
- 坏样本会报、原版不报的双向闸门；
- 日志与实际产物交叉验证。

## 8. 自定义 Renderer：AB 可以吸收

### 8.1 推荐的能力分层

| 等级 | 结构 | 建议 |
|---|---|---|
| R0 | 使用原 Renderer，只替换 mesh | 默认主线，最稳定 |
| R1 | 在原 prefab 下新增 Renderer，继续共享原活体骨 | 值得实现的 AB 增强模式 |
| R2 | 新增 Renderer，并使用独立 Humanoid 骨架/Avatar | 复杂度接近 SDK，保留为逃生舱 |

R1 可以解决：

- 独立透明件或不同 render queue；
- 需要单独显隐的部件；
- 一个宿主 Renderer 无法合理表达的额外 mesh；
- 独立 bounds 或更新策略；
- 不适合挤进原 submesh/material slot 的附件。

### 8.2 为什么技术上可行

IDA 已确认 `RegisterBone` 会把带 Renderer 的对象登记进 Renderer 相关列表，而不是当作普通骨。`CampusActorModelParts` 的内部列表由游戏初始化流程填充，不要求作者手工构造。

AB 运行时也已经具有 R1 所需的大部分基本操作：

- 创建 GameObject/Transform；
- 设置 parent；
- 设置 `SkinnedMeshRenderer.sharedMesh`；
- 设置 bones 和 rootBone；
- 读取/设置 sharedMaterials；
- 复制 layer；
- 刷新 bounds 和 Renderer 状态。

### 8.3 必须补齐的契约

自定义 Renderer 不能只做到“画出来”。至少需要处理：

- 创建时机：最好在 `ProcessBones/RegisterBone` 前；hot apply 时需要显式重新登记或刷新；
- GameObject layer；
- bones/rootBone 与 bindposes；
- sharedMaterials 和逐场景材质模板；
- submesh/material 数量一致性；
- localBounds、`updateWhenOffscreen`；
- shadow、probe、sorting、enabled 等 Renderer 状态；
- opaque combine 路径是否会收它；
- body/face/hair 全局骨名唯一；
- 冷加载、热应用和回滚都能恢复原状态。

R1 会扩大 AB 的游戏侧契约，但仍保留原 prefab、原 `CampusActorModelParts`、原 Animator 和原主要骨架，远小于完整 SDK 路线。

### 8.4 建议验收矩阵

新增 Renderer 实验至少覆盖：

1. 换装冷加载；
2. 已生成角色后的 hot apply；
3. live 场景；
4. 撮影场景；
5. opaque 与 cutout/transparent 各一个；
6. Animator 播放、身高修正和镜头裁剪；
7. OFF/回滚恢复；
8. Renderer 实际进入游戏内部列表，而不只是肉眼可见。

## 9. Humanoid 不必完全对齐：AB 只能吸收一部分

### 9.1 SDK 已经证明的内容

Unity Humanoid 不要求：

- 模型骨长与游戏原骨完全一致；
- 本地骨轴完全一致；
- Transform 数量完全相同；
- 辅助骨完全相同。

它要求的是：

- HumanBodyBones 映射有效；
- 必备骨存在；
- 层级可构成合法 Avatar；
- 静止姿势接近正确的 T-pose；
- 关节位于模型合理的解剖位置；
- roll、左右对称、手掌和手指方向不能严重错误。

SDK 的实验表明，Humanoid 可以吸收很多本地轴差异，但错误的 A-pose 和 roll 不会自动消失。A-pose 偏差会进入动画，绕肢体轴的错误会表现为手臂、袖子或手掌翻转。

### 9.2 对 AB 的正确启示：从“逐骨重合”改成“语义对齐”

AB 作者侧不应该要求源骨架每根骨的位置、长度和局部轴都逐项复制学马骨架。更合理的转换流程是：

```text
源模型骨架
  → 按 Humanoid 语义映射
  → 烘焙到规范 T-pose
  → 检查关节位置、roll 和左右对称
  → 将权重映射/转移到学马活体骨
  → 计算与活体静止骨架一致的 bindposes
  → 输出 AB 包
```

也就是说，SDK 可以教 AB 使用 HumanBodyBones 语义做转换和验证，而不是要求源 Transform 与游戏 Transform 一开始就完全相同。

### 9.3 AB 运行时仍有硬条件

> ⚠️ **2026-08-16 已推翻本节。** 下面的 `≈ identity` 只适用于"源 mesh 已绑定在目标静止骨架上"。
> 当前 lossless 路径用 source bindpose 做 `source-rest → game-pose` 重定向，**乘积非单位正是预期行为**。
> 本节连同 §9.1 的 T-pose 硬要求、对 roll 的统一表述，一并以
> [`ab-author-cost-reduction-2026-08-16.md` §2/§3/§6](ab-author-cost-reduction-2026-08-16.md) 为准。

AB 最终由游戏原活体骨驱动，因此对每个实际承重骨，静止帧应近似满足：

```text
original_live_bone_rest × mod_bindpose ≈ identity
```

如果不满足，模型即使在自己的 SDK Avatar 中是合法 Humanoid，塞进 AB 后也会在静止帧立即旋转、拉伸或错位。

因此 AB 可以放宽的是“源骨架初始形态必须逐项等于游戏骨架”，不能放宽的是“最终 mesh、权重和 bindpose 必须与实际驱动它的活体骨自洽”。

### 9.4 独立 Humanoid 骨架为什么接近 SDK

若要让 AB 完整保留模型自己的骨长和比例，需要在原 prefab 下放第二套骨架，并把游戏活体骨的动画重定向到它。至少要处理：

- 每帧相对旋转重定向；
- root motion 和身高；
- IK；
- 手指、twist 和 helper；
- Animator/LateUpdate 执行顺序；
- QuartzDriver、ActorSwing 和 collider 写哪一套骨；
- face/hair/body 跨部件引用；
- Avatar 构建和生命周期。

这实际上是在 AB 中重新实现运行时 Humanoid retargeter，复杂度会重新接近 SDK。

推荐边界：

- 自定义 Renderer + 原活体骨：进入 AB；
- Humanoid 语义映射、T-pose/roll 验证：进入 AB 作者工具；
- 独立 Humanoid 骨架、自定义比例和第二套 Avatar：继续留在 SDK 逃生舱。

## 10. 不建议从 SDK 原样搬入的内容

- 完整自建 prefab 重新成为默认路线；
- 当前样本特化的 `TPoseBaker` 常量；
- 不检查引用就安装全部 driver；
- 把 per-submesh 固定颜色写成统一顶点 COLOR；
- 用提前冻结的材质克隆代替当前场景活体材质；
- 把 Unity 台架中的一次成功当成所有模型通用结论。

## 11. 对原两份文档的具体修订建议

建议但本轮未直接修改原文：

1. 把“AB 契约面 ≈0；SDK ≈全部”改成“AB 大量继承游戏对象侧契约；SDK 需重新提供对象、组件与引用”。
2. 把“SDK 重建 22 个 List”改成“SDK 必须提供能让游戏重新填充 22 个 List 的组件图”。
3. 删除“SDK 只写 3/32，AB 32 个全对”的对比，换成当前实际材质生命周期说明。
4. 新增服装专属 `_RampAddMap` 和可变 scalar/color/blend 的缺口。
5. 把 INV-3 从硬不变量降为节点预算 warning。
6. 把“54 个候选 → 7 个成品”改为有清单支持的数字，或补齐 54 个候选的证据。
7. 给每项结论标注“IDA 事实 / 全量扫描 / 项目记录 / 工程推论 / 待实验”。
8. 把“SDK 必要性可能归零”限定到常规宿主替换范围，并保留 SDK 的 Renderer、独立骨架和 Unity 台架价值。
9. 在路线对比中补上 AB 的 native hook、运行时生命周期、hot apply 和调试可观察性成本。
10. 增加 R1“自定义 Renderer、共享原活体骨”作为 AB 与完整 SDK 之间的中间路线。

## 12. 最终路线建议

### 默认路线

继续使用 AB：

- 替换现有身体、服装、头发、脸；
- 能复用原 Animator、骨架、材质和组件；
- 新需求可以由少量辅助骨、ActorSwing 或 driver 表达。

### AB 下一步最有价值的能力

按优先级：

1. 修正文档中的材质和契约表述；
2. 做 R1 自定义 Renderer + 原活体骨的最小实验；
3. 把 SDK 的服装专属材质统计纳入 AB manifest/audit；
4. 把 Humanoid 语义映射、T-pose、roll 和关节探针纳入作者工具；
5. 完成 P4-E 关节间插骨实验；
6. 根据真实结构性失败案例决定是否扩大 SDK 逃生舱。

### 保留 SDK 的条件

出现以下任一情况时继续使用或评估 SDK：

- 必须拥有完全不同的 prefab/Renderer/组件结构；
- 必须保留模型自己的 Humanoid 比例和独立骨架；
- AB 的共享原骨架无法表达目标动画或组件关系；
- 需要 Unity 内完整可视化调试或序列化组件；
- P4-E 或后续结构实验确认 native graft 无法完成目标。

最终判定：

> AB 主线的方向正确，但理由应从“AB 几乎没有契约、SDK 全部重建”修正为“AB 最大限度继承活体游戏对象状态，因此在常规替换范围内风险最小”。SDK 不应与 AB 平行承担普通换装，但应继续作为自定义 Renderer/骨架能力的研究来源和真正的结构性逃生舱。
