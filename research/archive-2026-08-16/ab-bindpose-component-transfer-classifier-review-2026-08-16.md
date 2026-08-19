# AB bindpose、组件搬运与分类器补充评审

日期：2026-08-16  
性质：独立复核；作为 `ab-sdk-independent-review-2026-08-15.md` 的补充和局部纠正，不覆盖前文

## 1. 目的

本评审复核以下新分析：

1. AB 是否已经通过 mod bindpose 放宽骨位置、骨长和比例对齐要求。
2. `bindposeMode=mod-remapped/original` 是否是当前 AB 的静默总开关。
3. SDK 的 `TPoseBaker`、`HumanoidBridge` 是否应直接移植到 AB。
4. SDK 的源组件三层搬运是否是 AB 减少摇物调参的关键缺口。
5. AB 与 SDK 的摇物分类器是否已经同源、是否有可相信的准确率。
6. 这些能力的实施优先级应如何调整。

本轮只做代码、文档、工作区产物和离线数据复核，没有修改业务代码，也没有重新执行游戏内画面对照。

## 2. 结论摘要

新分析并非全部正确：

- **组件搬运部分基本正确**：SDK 已有“目标合成兜底 → 源组件逐实例覆盖 → 目标规则修正”三层管线；AB 目前没有通用源组件搬运层。对使用同一中间件、源包自带 rig 的模型，这是高价值缺口。
- **分类器部分方向正确，但实际问题更严重**：AB 的缩水版几何函数目前没有生产调用者，实际出包仍走名字分类；SDK 的 64.1% 数据又只属于旧版特征集，不能代表当前带 Reach/BodyShare/PivotAnchored 的实现。
- **`bindposeMode` 静默开关只描述旧路径**：当前带 `skeleton` 的 v2 包走 lossless graft，root 或骨/bindpose 契约不满足会报错，不会静默回退。
- **“AB 仍硬性要求源模型先烘成 T-pose”不成立**：SDK 的 69° 实验针对源骨架自建 Humanoid Avatar，不能直接套到 AB 的“游戏活体骨 × 源 bindpose”蒙皮。
- **目标取值域验证可独立做，但收益被高估**：当前范围表覆盖字段少且范围宽，更适合检查源搬运和手工覆盖，不会解决大多数类别选错、collisionMask、around 或 limit 语义问题。

此外，前一份独立评审把

```text
original_live_bone_rest × mod_bindpose ≈ identity
```

写成 AB 的统一硬条件，表述错误。该条件只适用于“源 mesh 已经绑定在目标静止骨架上”或“要求替换后静止 mesh 不发生重定向”的情况。使用源 bindpose 做 source-rest → game-pose 重定向时，非单位结果正是预期变换。

## 3. 当前 AB 有两条 skinning 路径

关键文件：`../../gakumas-mod-runtime/src/runtime/ModRuntime.cpp`。

### 3.1 当前 v2：带 `skeleton` 的 lossless graft

`PatchModMeshSkinningToOriginalOrder()` 首先检查：

```cpp
if (!replacement.skeletonAssetName.empty()) {
    return PatchModMeshSkinningLosslessly(...);
}
```

位置：`ModRuntime.cpp:3188-3193`。

manifest 的 `skeleton`/`skeletonAsset` 会写入 `skeletonAssetName`：

```cpp
const auto skeletonAssetName =
    GetFirstJsonString(item, { "skeleton", "skeletonAsset" }).value_or("");
```

位置：`ModRuntime.cpp:1543-1545`。

lossless 路径要求：

- original root 非空；
- original root 名与 mod root 名一致；
- mod bones 数与 mod bindposes 数一致；
- sidecar 骨数量与 mod bones 数一致；
- sidecar parentIndex 合法；
- 所有源权重索引合法。

root 或数量不满足时直接返回失败并写 Error，位置：`ModRuntime.cpp:3114-3132`。它不会进入 `bindposeMode=original`。

成功时：

- 同名骨使用游戏原活体 Transform；
- 缺失骨按 sidecar local TRS 在运行时创建；
- 使用 mod bindposes，并乘 Renderer 空间校正；
- 不重分配合法的源权重；
- 将 hybrid bones 写入原 Renderer。

成功日志是：

```text
Applied lossless IP skeleton graft
```

而不是 `bindposeMode=mod-remapped`。

本轮检查 `mod-workspace` 当前 18 份 `mod.json`，全部带 `"skeleton"`，因此都应进入这一条路径。

### 3.2 旧路径：无 `skeleton` 时按 root 名自动选 bindpose

只有 `skeletonAssetName` 为空时才会到达：

```cpp
const auto useModBindposes = !originalRootName.empty()
    && originalRootName == modRootName
    && modBindposes->max_length > 0;
const auto bindposeMode = useModBindposes ? "mod-remapped" : "original";
```

位置：`ModRuntime.cpp:3241-3245`。

行为：

| 条件 | bindposeMode | 结果 |
|---|---|---|
| root 同名且存在 mod bindposes | `mod-remapped` | 按骨名把 mod bindposes 重排到原 bones 顺序 |
| root 不同、为空或无 mod bindposes | `original` | 使用原 mesh 的 bindposes |

这个分支确实存在静默退化风险：选择依据只是 root 名和 bindpose 非空，错误只在汇总日志中体现。

但不能把 `original` 一律视为错误。已经离线绑定到游戏原骨架的旧包可能有意使用 original bindposes。

推荐改进不是全局硬报错，而是：

1. 为旧路径增加显式 `bindposePolicy=mod|original|auto`；
2. 新包禁止或强烈警告 `auto`；
3. verifier 检查 manifest、root、bone/bindpose 数量和预期策略；
4. `auto → original` 时至少给出显著 warning；
5. 当前带 skeleton 的 lossless 路径继续保持契约不满足即硬失败。

### 3.3 正确的日志检查

当前 v2 包优先检查：

```text
Applied lossless IP skeleton graft
```

并检查：

- `createdBones`
- `matchedBones`
- `droppedInfluences=0`
- `fallbackVertices=0`

只有旧/无 skeleton 包才检查：

```text
bindposeMode=mod-remapped
bindposeMode=original
```

仅 grep `bindposeMode` 并把没有输出视为失败，会误判正常的 v2 lossless 包。

## 4. AB mod bindpose 的数学含义

### 4.1 运行时公式

对源 mesh 顶点 `v_source`，AB 使用 mod bindpose 时的蒙皮近似为：

```text
v(t) = Σ weight_i × M_game_i(t) × B_source_i × v_source
```

若源 bindpose 是标准定义：

```text
B_source_i ≈ inverse(M_source_i(rest))
```

则游戏静止帧为：

```text
v_game_rest
= Σ weight_i
  × M_game_i(rest)
  × inverse(M_source_i(rest))
  × v_source
```

其中

```text
M_game_i(rest) × inverse(M_source_i(rest))
```

就是把源绑定姿势映射到游戏静止姿势的逐骨变换。

### 4.2 为什么不要求乘积为单位矩阵

如果源骨架已经与游戏静止骨架完全一致，乘积才近似 identity，mesh 在游戏静止帧保持原样。

如果源是 A-pose、目标是 T-pose，则这个乘积理应是非单位旋转；它会把源 A-pose 的受权重几何重定向到游戏 T-pose。非单位并不自动意味着最终仍残留同样的 A/T 角度差。

因此：

- 源骨位置不必在导出前逐项重合游戏骨位置；
- 源骨长和比例可以编码在 source bindpose 中；
- 游戏活体骨最终决定动画时的目标骨位置和比例；
- 不能说运行时仍“保留模型自己的动画骨长”，更准确的是“保留源绑定空间，并重定向到游戏活体骨架”。

### 4.3 仍然存在的真实风险

bindpose 可以完成几何重定向，不等于形变质量自动正确：

- 大角度 A→T 的线性混合蒙皮可能造成肩、胯等混合带塌陷；
- 源权重依赖的 helper/twist 骨若没有正确创建或驱动，关节仍会坏；
- 源骨名映射错误会把权重落到错误的游戏骨；
- source-only 新骨的 local axis、driver 和 swing 语义仍需正确；
- 服装与目标体型的合身、穿模不会由矩阵自动解决；
- 相同语义骨之间的比例差会改变网格最终轮廓。

所以“无需逐骨位置对齐”成立，“无需处理权重和关节质量”不成立。

## 5. T-pose 与 roll：SDK 结论不能直接套给 AB

### 5.1 SDK 的 69° 实验验证了什么

SDK 路线使用源模型自己的骨架建立 Avatar。源骨架的 rest pose 会成为 Humanoid retargeting 的基准。

`TPoseBaker.cs` 和 `AvatarBench.cs` 的记录支持：

- 外部模型大臂静止姿势偏差 69.1°/67.4°；
- 未烘焙时，同 muscle 值下的偏差保持到小数点后一位；
- 烘焙后手臂静止偏差 0.0°；
- 同 muscle 值下与参照手臂差 0.0°；
- 膝仍有 3.7°，被记录为比例差异。

这是 SDK 自建 Avatar 路线中“源 rest 必须成为正确 Humanoid T-pose”的强证据。

### 5.2 为什么不能直接推出 AB 也残留 69°

AB 不使用源骨架建立角色 Animator 的 Humanoid Avatar。它让游戏原活体骨直接乘 source bindpose。

SDK 的模型是：

```text
muscle → source Avatar → source skeleton
```

AB mod-remapped/lossless 的模型是：

```text
game animation → game live skeleton × source bindpose → source mesh
```

二者的 rest-pose 角色不同，不能把 SDK AvatarBench 的 69° 结果直接当成 AB 必然行为。

### 5.3 roll 的边界

对 AB 中匹配到原版的 Humanoid 骨：

- 动画 Transform 来自原版活体骨；
- 原版骨轴和驱动约定本身正确；
- 源 rest frame/roll 已包含在 source bindpose 映射里。

因此不能把源骨 roll 误差统一写成 AB 的硬失败条件。

roll/local axis 仍然会影响：

- source-only 新建骨；
- 直接读写 local axis 的 QuartzDriver；
- ActorSwing 或碰撞器的局部轴语义；
- Head 下直接 parent、没有经过 skinning/Avatar 的部件；
- 需要按源局部轴解释的辅助骨链。

### 5.4 对当前 G10 的影响

当前 `tools/audit_ab_rig.py` 的 G10 会把 mod bindpose 反推出的肢体方向与游戏静止方向比较，并认为差角会 1:1 出现在游戏里。

这个推论对 SDK 自建 Avatar 成立，但对 AB mod-remapped/lossless 尚未被实验证明，且与上述 skinning 公式冲突。

在完成 AB A-pose 对照前，G10 更适合改名为“rest retarget magnitude/risk”：

- 报告 source rest → game rest 的重定向角度；
- 大角度提示 LBS 塌陷和权重风险；
- 不直接断言最终动画必然残留同角度偏差；
- 不应仅凭 ≥15° 阻止 lossless mod-bindpose 包。

## 6. `TPoseBaker` 的真实价值与限制

文件：`research/unity-humanoid-avatar-sdk/GakumasAvatarSdk/Assets/GakumasAvatarSdk/Editor/TPoseBaker.cs`，443 行。

### 6.1 已确认能力

- 父先子后把四肢方向摆到规范 T；
- 包含腿、手臂、前臂和各手指；
- 使用手掌 thumb→pinky 方向对齐手臂 roll；
- 先保存旧 bindposes；
- 骨移动后同时重算顶点、法线、切线和新 bindposes；
- 使用 dual quaternion 混合 rest delta，避免直接平均旋转矩阵的明显体积损失；
- 已是 T-pose 时不改数据；
- 有 SDK AvatarBench 的样本级定量验证。

### 6.2 限制

- 目标方向表是固定的；
- `PalmAcross` 是现有参照标定值；
- 不完整处理 Spine、Shoulder、Neck、Head、Foot 的整体姿势；
- BlendShape delta 没有随网格变换，代码只发 warning；
- 只在现有 SDK 样本上证明，不代表所有 FBX/MMD/VRM；
- 它不会修正错误权重，也不会补齐缺失的 helper/twist 驱动；
- 从 C#/Unity Mesh API 移植到 Blender 不只是语法翻译，还要统一坐标系、矩阵顺序、分裂顶点、法线/切线、shape key 和多 Renderer 语义。

### 6.3 AB 是否需要移植

在数学和实机结论冲突尚未解决前，不应把“移植 TPoseBaker”直接排成 AB 第一产物改动。

先做一个受控实验：

| 版本 | 输入 | 路径 |
|---|---|---|
| A | 源 A-pose mesh + 源 bindposes，不烘焙 | 当前 skeleton/lossless graft |
| B | 同一模型经 TPoseBaker 烘成 T | 当前 skeleton/lossless graft |

固定：

- 同一骨名映射；
- 同一权重；
- 同一游戏宿主；
- 同一动画帧；
- 同一材质和比例设置。

比较：

- 静止姿势角度；
- 同一动画下的骨/网格方向；
- 肩、肘、腕、胯、膝边缘拉伸；
- 横截面体积；
- 左右对称；
- helper 骨承重；
- 冷加载与 hot apply。

若 A 没有 69° 残差、仅有关节塌陷，则 TPoseBaker 对 AB 的价值是离线预烘焙/体积质量，而不是动画正确性的硬前置。

## 7. `HumanoidBridge`：减少命名配置，不是绝对零配置

文件：`research/unity-humanoid-avatar-sdk/GakumasAvatarSdk/Assets/GakumasAvatarSdk/Editor/HumanoidBridge.cs`。

它确实利用：

```csharp
animator.GetBoneTransform(HumanBodyBones.*)
```

把 Unity 已识别的 Humanoid 骨改成游戏需要的固定名称，并处理：

- 55 根游戏身体骨名；
- 同名让位和全层级去重；
- 缺少 `Spine2` 时插入节点；
- 缺少 `Pelvis` 时插入节点并重挂双腿。

但代码明确要求：

- FBX Import Rig 已设为 Humanoid；
- `Animator` 存在；
- `Animator.avatar` 存在且 `isHuman`；
- 作者在 Configure 中确认映射。

因此准确表述是：

> Unity 的 Humanoid auto-mapper 可显著减少 Biped/Mixamo/MMD 等常见命名的手写桥接，但仍需要合法 Avatar 和必要时的人工确认。

AB 当前 `bone_remap_presets.json` 有 8 个预设：

- auto-rig-pro
- biped
- mixamo
- mmd-standard
- rigify
- scsp
- unity-humanoid
- vrm

SDK 的桥接方式仍值得 AB 学习为“离线辅助映射/导出映射”，但不能写成所有来源零配置。

## 8. 源组件三层搬运：新分析中最扎实的部分

主要文档：`research/unity-humanoid-avatar-sdk/docs/component-transfer-route.md`。

### 8.1 SDK 已实现的三层

1. **目标合成兜底**：按目标游戏 530 套统计装上目标需要的组件。
2. **同名/语义搬运**：源包有对应组件时，逐实例覆盖作者实际调过的字段。
3. **目标规则修正**：处理目标取值域、collisionMask、驱动器互斥和目标专属约定。

相关实现：

- `tools/export_source_components.py`
- `GakumasAvatarSdk/Assets/GakumasAvatarSdk/Editor/ComponentTransfer.cs`
- `tools/verify_transfer.py`
- `tools/inventory_target_ranges.py`
- `reference/target-value-ranges.json`

### 8.2 已确认数据

文档和实现记录支持：

- 离线验证 559 个字段，0 不符；
- sucu 源 `ActorSwingDynamicBone` 42 个，全部命中；
- 静态碰撞体从合成 30 个替换为源 12 个；
- 姿势驱动器 14 个；
- 胸部驱动 1 个；
- 42 个源摇物骨没有触发目标值域夹取；
- 胸驱有 2 个越界：damping 0.15→0.20、stiffness 0.03→0.06；
- 文档把该胸驱记录为唯一持续乱抖的实机异常组件。

### 8.3 为什么 AB 确实缺这一层

AB 当前有：

- `swing_presets.json` 的目标统计兜底；
- sidecar 中的每骨 swing/driver 表达；
- runtime 创建 DynamicBone、QuartzDriver 和 Chain 的能力；
- 作者手工覆盖入口。

AB 当前没有：

- 从源 AssetBundle 逐实例导出完整组件；
- 通用 `components.json`/sidecar schema；
- 按宿主骨和类型逐实例覆盖源字段；
- 源组件与合成组件的替换/去重规则；
- 与源清单逐字段回读对照；
- target-value-ranges 的通用接入。

因此“AB 现在主要只有第一层”基本成立。

### 8.4 适用范围

收益大的来源：

- 源包与目标使用相同或高度相近的 VL/ActorSwing 中间件；
- 源包保留 MonoBehaviour typetree；
- 源 rig 已由原作者调好；
- 宿主骨和引用可以可靠映射。

收益小或为零的来源：

- 普通 MMD/VRM；
- 只剩 mesh/skeleton 的 Genshin rip；
- typetree 被清掉的 bundle；
- 使用完全不同物理解算器的源。

### 8.5 “零调参”应降级为“显著减少”

仍然需要目标侧处理：

- 源没有的 `ActorSwingChain`；
- collision channel；
- 目标 IKCorrection；
- 骨名和 referenceBone 重映射；
- 多级/重复 driver 合并；
- 源/目标字段单位语义差异；
- 不同目标角色的碰撞笼和身高；
- 材质、COLOR、贴图和透明语义。

“559 字段 0 不符”证明序列化结果符合搬运规则，不等于目标游戏中的动态行为与源游戏逐帧等价。

## 9. 目标取值域验证：可独立做，但不是主要调参解法

当前 `target-value-ranges.json` 覆盖：

| 类 | 字段 |
|---|---|
| ActorSwingDynamicBone | damping、stiffness、spring、mass |
| ActorSwingBreastBone | average、damping、stiffness、spring |

DynamicBone 的全局范围较宽：

- damping：0.0–1.0
- stiffness：0.0–0.9
- spring：-0.3–1.15
- mass：0.0–15.0

这种全库 min/max 可以抓：

- 源组件超出目标游戏从未出现过的明显异常；
- 作者手写覆盖的数量级错误；
- 不同 solver 同名字段但量纲不一致的信号。

它抓不到：

- 数值在全局合法范围内，但属于错误类别；
- collisionMask 错通道；
- around 错误；
- limit 轴或局部坐标系错误；
- 错误的 rootWeight/pendulum/chain 结构；
- 裙摆使用 ribbon 的合法数值。

AB 合成预设本身来自目标库，通常已在范围内，因此对纯合成路径的新增收益有限。

建议：

- 先作为 audit warning/error，不静默 clamp；
- 对源组件搬运和作者覆盖启用；
- 报告原值、目标范围、处理动作；
- collisionMask 等目标类别规则独立实现；
- 如需自动 clamp，必须 per-job 可见且能关闭。

## 10. 分类器复核

### 10.1 AB 的几何函数没有接入生产

`gakumas_mi/core.py:2975` 定义：

```python
swing_category_by_geometry(anchor, direction=None, siblings=None, fallback_name=None)
```

它使用：

- anchor
- direction
- siblings
- fallback name

但全仓实际调用者只有测试以及函数内部 fallback，没有生产出包调用。

生产路径仍调用名字分类：

- `gakumas_mi/operators.py:733`
- `gakumas_mi/core.py:3165`

所以准确状态不是“AB 已搬分类器、漏三个特征”，而是：

> AB 已写缩水版几何函数和单元测试，但实际出包仍走名字规则。

### 10.2 与 SDK 当前分类器的特征差异

AB 缺少：

- chain length；
- Reach：链实际影响顶点的最大辐射范围；
- ReachDirection：由受影响几何而不是骨 offset 决定方向；
- BodyShare：受该链影响顶点中 Humanoid/body 权重占比；
- PivotAnchored：链根是否具有可作为真实摆动枢轴的结构；
- 每链 Evidence；
- 不确定性和分类置信度。

骨和肉分家时，只看骨向量会误判；BodyShare/Reach 是 SDK 当前实现中针对这一点新增的特征。

### 10.3 120 套准确率已复算

重新运行：

```text
python tools/measure_chain_classifier.py 120
```

得到：

- 总体：64.1%，2317/3615；
- skin recall：83.0%；
- skirt recall：81.8%；
- ribbon recall：54.2%；
- sleeve recall：59.1%；
- cloth recall：0.5%。

与 SDK 文档记录一致。

### 10.4 全 530 套复算

重新运行无 limit：

- 总体：65.1%，10811/16604；
- skin recall：84.4%；
- skirt recall：83.3%；
- ribbon recall：53.3%；
- sleeve recall：55.9%；
- cloth recall：2.4%。

结果说明：

- 64%/65% 不能支持“无需人工确认”；
- skin 安全性明显改善；
- cloth 分类仍非常差；
- 作者覆盖和证据日志仍是必要组成。

### 10.5 评分器本身已经与 SDK 当前实现漂移

`tools/measure_chain_classifier.py` 的预测只使用：

- anchor
- local direction
- chain length
- siblings

它没有实现当前 `ChainClassifier.cs` 的：

- Reach
- ReachDirection
- BodyShare
- PivotAnchored

所以 64.1%/65.1% 只属于旧版/简化算法，不能当作当前 SDK 完整分类器的准确率。

### 10.6 “381 套量过”注释不可靠

`core.py:2953` 写“SDK 侧 ChainClassifier 在 381 套原版上量过”，但：

- 可复现的分类器文档数据是 120 套/3615 链；
- 当前脚本默认可跑 530 套；
- 381 更像裙摆服装/锚点范围统计，而不是分类准确率实验；
- AB 侧没有自己的评分产物。

这条注释应改成明确数据来源，不能继续作为 AB 分类器已验证的证据。

### 10.7 正确的接入顺序

1. 让 AB 生产路径真正调用几何分类器；
2. 生产分类器和评分器共用同一实现或同一特征 JSON；
3. 先复现旧特征集准确率；
4. 再加入 Reach/BodyShare/PivotAnchored；
5. 重新计算 confusion matrix 和各类 recall；
6. 保留作者逐链覆盖；
7. 输出每链 Evidence 和低置信度提示；
8. skin 类优先 fail-safe：宁可钉住，也不要给身体辅助骨挂摇物。

简单把 `measure_chain_classifier.py` 复制到 AB tools/，却继续让评分逻辑和生产逻辑各维护一份，会再次产生漂移。

## 11. 修订后的实施优先级

### 11.1 所有来源共同的第一步

**做当前 lossless 路径的 A-pose/T-pose 双包对照。**

目的：回答 AB 是否真的需要离线 T-pose 烘焙，以及运行时 source-rest → game-rest 映射的主要问题究竟是角度残差还是蒙皮塌陷。

这是决定是否移植 TPoseBaker 的前置实验，成本低于直接移植。

### 11.2 bindpose 策略显式化

- 当前 skeleton/lossless 路径继续硬验证；
- 旧路径 `auto` 降级给强 warning；
- 新 manifest 要求显式 policy；
- verifier 报告实际将走的路径；
- 日志区分 `lossless-graft`、`legacy-mod-remapped`、`legacy-original`。

收益是消除静默和错误诊断，但由于当前 18 份包都走 lossless，它不是“立刻消掉所有手工对齐”的万能修复。

### 11.3 同中间件源：优先源组件搬运

若主要痛点来自 IP/sucu 一类自带 VL rig 的 bundle：

1. AB 版 `export_source_components.py`；
2. sidecar components schema；
3. runtime/打包阶段逐实例覆盖；
4. 源/合成组件去重；
5. target rules；
6. 回读逐字段验证。

这是该来源类型下降低几小时手调最直接的能力。

### 11.4 MMD/VRM/普通 rip：优先真正接通分类器

这些来源没有可搬 rig。应优先：

1. 接通生产几何分类；
2. 同步评分器；
3. 加 Evidence/作者覆盖；
4. 根据真实 confusion matrix 决定是否实现 BodyShare/Reach。

### 11.5 目标值域验证

可低成本独立加入，但应定位为安全网：

- 对源搬运/作者覆盖 warning；
- collisionMask 等类别规则单独处理；
- 不把全局 min/max 当作类别调参器；
- 默认不静默修改。

### 11.6 TPoseBaker

只在 AB A/T 对照确认存在明确收益后移植。移植时必须同时处理：

- 顶点；
- bindpose；
- 法线和切线；
- shape keys/BlendShapes；
- 多 mesh/多 Renderer；
- Blender/Unity 坐标和矩阵顺序；
- 破坏性改写开关和 before/after 量化。

## 12. 对两份既有评审文档的影响

### 12.1 需要修正的旧结论

`ab-sdk-independent-review-2026-08-15.md` 中以下内容应在后续修订：

- §9.1 把 SDK 自建 Avatar 的 T-pose要求写得像 AB 的统一要求；
- §9.3 把 `original_live_bone_rest × mod_bindpose ≈ identity` 写成 AB 硬条件；
- 对 roll 的表述没有区分原版匹配骨与 source-only 新骨；
- 没有区分 skeleton/lossless 与旧 `bindposeMode` 路径；
- 低估了 SDK source component transfer 对同中间件源的价值；
- 没有指出 AB 几何分类器目前未接入生产。

### 12.2 仍然成立的旧结论

- AB 继续适合作为普通宿主替换主线；
- SDK 继续适合作为独立骨架、完整 prefab 和 Unity 台架的逃生舱；
- AB 应吸收 SDK 的数据、测量和验证，而不是默认自建整个 prefab；
- 模型合身、权重、关节质量和材质语义不会因为 bindpose 自动消失；
- 组件搬运只对源包保留兼容 rig 的来源有效；
- 自动分类必须保留人工覆盖和证据日志。

## 13. 最终判定

对被复核分析的逐项评价：

| 项目 | 判定 |
|---|---|
| 旧路径 root 名控制 `mod-remapped/original` | 事实正确 |
| 它是当前所有 AB 包的总开关 | 错；当前 v2 包走 skeleton/lossless |
| `original` 静默退化应提高可见性 | 正确 |
| 所有 `original` 都应硬报错 | 过强；可能存在有意预绑定的旧包 |
| AB 不要求逐骨位置完全对齐 | 基本正确，mod bindpose 会做 source→game 重定向 |
| AB 仍硬性要求源先成为 T-pose | 未证实且数学上不能由 SDK 69°实验推出 |
| 源骨长、比例、骨轴全部免费 | 过强；重定向存在，但权重/helper/形变质量仍需处理 |
| SDK TPoseBaker 已证明有效 | 对 SDK 自建 Avatar 和现有样本成立 |
| 立即将 TPoseBaker 移植为 AB 第一优先级 | 证据不足，应先做 AB A/T 对照 |
| HumanoidBridge 比 8 张预设更泛化 | 方向正确 |
| Biped/Mixamo/MMD 作者绝对零配置 | 过强，仍需合法 Avatar 和映射确认 |
| SDK 三层组件搬运存在且 AB 缺第二层 | 基本正确 |
| 同中间件源可大幅减少摇物调参 | 正确，且证据较强 |
| MMD/VRM/rip 也能因此零调参 | 错；无源 rig 时只能合成 |
| 目标值域夹取可独立实现 | 正确 |
| 它是 AB 合成路径性价比最高的修复 | 高估；当前范围少且宽，类别规则更关键 |
| AB 已使用几何分类器 | 错；函数存在但生产未调用 |
| AB 缺 Reach/BodyShare/PivotAnchored/Evidence | 正确，另缺 chain length |
| 120 套 64.1%/skin 83% | 已复算确认 |
| 该数字代表 SDK 当前完整分类器 | 错；评分器未包含当前新增特征 |
| `381 套量过` 注释存在数据漂移 | 正确，当前没有对应准确率实验 |

最终建议：

> 先用当前 skeleton/lossless 路径实测 A-pose 是否真的留下角度偏差，再决定 TPoseBaker；同时把旧 bindpose 自动选择显式化。对同中间件源，优先吸收 SDK 的逐实例组件搬运；对无源 rig 的模型，优先把几何分类器真正接入生产并让评分器与生产实现共源。目标取值域作为安全网加入，而不是替代类别和语义验证。
