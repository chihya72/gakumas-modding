# AB 路线：降低作者成本的实施依据

日期：2026-08-16
性质：**工作依据**，不是评审。前面两份评审的结论收敛到这里，加上本轮自验查出的新问题。
目标（作者提出）：① 不用把源模型和游戏模型完全对齐来替换权重 ② 摇物链等表现要好 ③ 不要花大量时间调参

上游：
- [`ab-sdk-independent-review-2026-08-15.md`](ab-sdk-independent-review-2026-08-15.md)
- [`ab-bindpose-component-transfer-classifier-review-2026-08-16.md`](ab-bindpose-component-transfer-classifier-review-2026-08-16.md)
- [`ab-route-v2-full-record.md` §10](ab-route-v2-full-record.md)（上一轮的修正与根因）

**本文推翻的旧表述索引在 §6。看到那几处请以本文为准。**

---

## 1. AB 有两条 skinning 路径，不是一条

这是理解后面所有结论的前提。分派点在 `PatchModMeshSkinningToOriginalOrder()` 的**第一行**：

```cpp
// ModRuntime.cpp:3190
if (!replacement.skeletonAssetName.empty()) {
    return PatchModMeshSkinningLosslessly(...);
}
```

| | **路径 A：lossless graft**（当前） | **路径 B：legacy**（旧包） |
|---|---|---|
| 触发 | manifest 带 `skeleton` / `skeletonAsset` | 不带 |
| bindpose | **恒用 mod bindpose**（乘 renderer 空间修正，`:3171-3178`） | 按 root 骨名**自动选**：同名用 mod，不同名用原版（`:3241-3245`） |
| 骨架 | 同名骨复用**游戏活体 Transform**，缺失骨按 sidecar 运行时新建（`BuildHybridBoneArray`，`:3165`） | 只 remap 骨序 |
| 契约不满足 | **硬失败**：root 不匹配 / 骨数≠bindpose 数 / sidecar 数不符 / 权重索引越界 → `Log::Error` + `return false`（`:3116-3132`、`:3140-3160`） | **静默**退回 `bindposeMode=original` |
| 成功日志 | `Applied lossless IP skeleton graft` | `bindposeMode=mod-remapped` / `=original` |

**实测：`mod-workspace` 现有 18 份 `mod.json` 全部带 `skeleton`，即全部走路径 A。**

```bash
grep -c '"skeleton' mod-workspace/mods/*/*/mod.json
```

> ⚠️ 因此 `grep bindposeMode` **不适用于当前包**，没有输出是正常的。查当前包要 grep
> `Applied lossless IP skeleton graft`，并核 `createdBones` / `matchedBones` /
> `droppedInfluences=0` / `fallbackVertices=0`。

路径 B 的静默退化风险真实存在，但它只影响旧包，且 `original` 不一定是错的（离线预绑定到游戏骨架的旧包可能有意如此）。**处置方式是显式化，不是全局硬报错**：manifest 加 `bindposePolicy=mod|original|auto`，新包禁 `auto`，`auto→original` 给显著 warning。优先级低（当前无包受影响）。

---

## 2. 数学：AB 到底要求什么

路径 A 的蒙皮是：

```text
v(t) = Σ wᵢ · M_game_i(t) · B_source_i · v_source
```

游戏静止帧：

```text
M_game_i(rest) · inverse(M_source_i(rest))
```

**这个乘积是"源绑定姿势 → 游戏静止姿势"的逐骨重定向，它非单位是预期行为，不是误差。**

因此：

| | 结论 |
|---|---|
| 源骨**位置**要不要逐项重合游戏骨 | ❌ 不要。重定向会做 |
| 源**骨长 / 比例** | ❌ 不要。编码在 source bindpose 里，游戏活体骨决定最终比例 |
| 源**骨轴 / roll**（匹配到原版的 humanoid 骨） | ❌ 不是硬失败条件。已包含在 bindpose 映射里 |
| 源 **rest 必须先烘成 T-pose** | ⚠️ **未证实**（见 §3） |
| 权重质量、helper/twist 骨、合身穿模 | ✅ **仍然全是手工**。矩阵不解决这些 |

**真实风险不在角度残差，在混合带**：大角度 A→T 的线性混合蒙皮会让肩、胯的过渡区塌陷（一个 50/50 权重的顶点拿到两个相差 69° 的刚体变换的平均）。这是形变质量问题，不是"动画整体差 69°"。

roll / local axis 仍然要紧的地方（**只有这些**）：source-only 新建骨、直接读写 local axis 的 QuartzDriver、ActorSwing / 碰撞体的局部轴、直接 parent 到 Head 不过蒙皮的部件。

---

## 3. SDK 的 69° 不能直接套给 AB

| | 驱动模型 | 源 rest 的角色 |
|---|---|---|
| SDK | `muscle → 源 Avatar → 源骨架` | **源 rest 就是 Avatar 的零点** → 偏 69° 则动画偏 69°（AvatarBench 实测，小数点后一位都一样） |
| AB 路径 A | `游戏动画 → 游戏活体骨 × source bindpose → 源 mesh` | 源 rest **只通过 bindpose 参与重定向**；Avatar 是游戏自己的 |

两者 rest 的角色不同。`TPoseBaker` 对 SDK 有强证据，**对 AB 没有**。

因此 `tools/audit_ab_rig.py` 的 **G10 现有语义站不住**：它假设"bindpose 反推的肢体方向与游戏静止方向的差角会 1:1 出现在游戏里"。这对 SDK 成立，对路径 A 未经证明，且与上面的公式冲突。

**G10 应改名改语义**：`rest retarget magnitude`（重定向幅度）——
- 报告 source rest → game rest 的逐骨角度；
- 大角度提示 **LBS 塌陷和权重风险**，不断言动画残差；
- **不应仅凭 ≥15° 阻止路径 A 的包出货**。

---

## 4. 新发现：唯一那把离线尺子量的是旧路径

`tools/simulate_ab_skinning.py:89-90`：

```python
rest_inverse = (world @ bone.matrix_local).inverted()      # ← 游戏骨架的 rest
result[bone.name] = (world @ pose_bone.matrix) @ rest_inverse
```

它算的是 `M_game(t) × M_game(rest)⁻¹ · v` —— 用**游戏 bindpose**，即**路径 B**的数学。当前所有包走路径 A（`M_game(t) × B_source · v`）。

**后果**：这个模拟器**只在"网格已经完全对齐到游戏静止姿势"时成立** —— 正是作者要摆脱的那个前提。源留在 A-pose 靠 bindpose 重定向时，它的读数没有意义。它的 docstring 自己也写着「it is relative to rest, so breaking the rest itself makes it look *better*」。

**修法**：把 `rest_inverse` 换成从**导出的 mod bindpose**（或源骨架 rest）取，与运行时同源。改动小，但不改就没法做 §5 的 A/T 对照。

---

## 5. 优先级：按**源类型**分，作者的项目构成已经给出答案

两份评审都同意要按源类型分。查了实际项目：

| 项目 | 源 |
|---|---|
| chisaki-swimsuit / daikokushu-rabbit / miku / dress-2219 / madoka-swimsuit | MMD / scsp |
| mltd-stage | 外部 rip |
| fuyuko-icu、两个 hair | 原版件改造 |
| ~~rui-nurs（IP，唯一同中间件源）~~ | **已废弃**，只跑通数据侧 |

> **现有 9 个项目里，没有一个是自带 VL rig 的同中间件源。**
> 所以 SDK 的**源组件搬运（第 2 层）对当前作者的实际工作买不到任何东西** ——
> 它只对 IP/sucu 那类保留 typetree 且原作者已调好 rig 的 bundle 有效。有 IP 项目时再做。

### 排序

| # | 做什么 | 打中目标 | 成本 | 验收 |
|---|---|---|---|---|
| **1** | **把几何分类器接进生产**。`core.py:2975` 的 `swing_category_by_geometry()` 目前**只有测试调它**，生产（`core.py:3165`、`operators.py:733`）仍走 `swing_category(name)` 名字规则 | ②③ | 低 | MMD 的 `スカート`、rip 的 `Bone_HemA01_L` 能拿到正确类别；生产与评分器**共用一份实现**（否则必然再漂移） |
| **2** | **模拟器改吃 source bindpose**（§4），然后做 A/T 双包离线对照 | ① | 低 | 同模型两版（A-pose 不烘 / TPoseBaker 烘成 T），同骨名映射、同权重、同宿主、同帧；量静止角度、肩肘腕胯膝边缘拉伸、横截面体积、左右对称 |
| **3** | **G10 改语义**为重定向幅度报告，不再阻止出货（§3） | ① | 低 | 现有 6 个成品跑一遍，读数从"违规"变成"幅度 N°" |
| **4** | 逐链 **Evidence + 低置信度提示**，保留作者一行覆盖 | ③ | 低 | 每条链打出锚点 / 朝向 / 骨数 / 链长 / 判定理由 |
| **5** | 按 #2 结果决定 **TPoseBaker 移植** | ① | **高** | 若 A 版只有关节塌陷、无全局角度残差 → 它是形变质量工具，不是硬前置，可以延后 |
| **6** | 分类器补 `Reach` / `BodyShare` / `PivotAnchored` / chain length | ③ | 中 | 先有 #1 的 confusion matrix，再决定加哪个 |
| — | ~~取值域夹取~~ | — | — | **降级为安全网**：`target-value-ranges.json` 只覆盖 2 个类，且 `ActorSwingDynamicBone.damping` 范围是 **0.0–1.0**（全值域，永远抓不到）。抓到的 2 个越界全在 BreastBone（范围窄）。只对**源搬运和作者手工覆盖**开，默认 warning 不静默 clamp |
| — | ~~源组件搬运~~ | — | — | 当前无同中间件源。有 IP 项目时按 `component-transfer-route.md` 三层做 |

### 分类器准确率的真实状态

- `measure_chain_classifier.py` 的 `predict(anchor, direction, length_cm, siblings)` **不含** Reach/BodyShare/PivotAnchored。
- 因此 **64.1%（120 套 / 3615 链）、65.1%（530 套 / 16604 链）只属于简化特征集**，不代表当前 `ChainClassifier.cs`。（数字引自 08-16 评审的复算，本轮未自行重跑。）
- `skin` recall 83–84% 是最要紧的一项（判错 = 给**身体本身**挂摇物）；`cloth` 只有 0.5–2.4%。
- **65% 支持不了"无需人工确认"** —— 作者覆盖和证据日志是必需品，不是锦上添花。
- `core.py:2953` 注释里的「SDK 侧在 **381 套**原版上量过」**无对应实验**，应改为明确来源或删除。

---

## 6. 本文推翻的旧表述（看到请以本文为准）

| 出处 | 旧表述 | 现状 |
|---|---|---|
| `ab-sdk-independent-review-2026-08-15.md` §9.3 | `original_live_bone_rest × mod_bindpose ≈ identity` 是 AB 硬条件 | **错**。只适用于"源 mesh 已绑定在目标静止骨架上"。用 source bindpose 做重定向时，非单位正是预期（§2） |
| 同上 §9.1 | 把 SDK 自建 Avatar 的 T-pose 要求写得像 AB 的统一要求 | **未证实**（§3） |
| 同上 §9 | roll 误差是 AB 的硬失败条件 | **过强**。对匹配到原版的 humanoid 骨不成立；只对 source-only 新骨等场景成立（§2 末） |
| `ab-route-v2-full-record.md` §3.2「静止姿势对齐（A→T）」行 | 「闸门 G10 量的正是它」 | G10 的前提对路径 A 未证明，应改语义（§3） |
| 2026-08-16 对话中的分析 | `bindposeMode` 是当前所有 AB 包的静默总开关 | **错**。当前 18 份包全走路径 A，契约不满足是硬失败（§1） |
| 同上 | AB 已把 ChainClassifier 判据搬过来，只漏三个特征 | **错，而且更糟**：几何函数是死代码，生产仍走名字规则（§5 #1） |
| 同上 | 取值域夹取是性价比最高的一条 | **高估**（§5 表末） |

---

## 7. 方法论备忘

上一轮在 `ab-route-v2-full-record.md` §10.5 写下四条错误根因，**这一轮又犯了第 2、3 条**：

- 读了 `PatchModMeshSkinningToOriginalOrder` 的 legacy 分支，**没读它上面三行的 dispatch** —— 深度不对称；
- 把 SDK bench 的 69° 直接当成 AB 的行为 —— **形容词/数字没挂对应路径的 `file:line`**。

§4 那条新发现（模拟器算旧路径）就是拿这两条当探针查出来的 —— **两份评审都没查到**。探针有效，但要主动跑，不是写进文档就自动生效。

**下次改这类结论前的固定动作**：
1. 任何运行时行为结论，先确认它属于**哪条路径**，并把路径写进结论；
2. 任何跨路线搬来的数字（SDK → AB），先确认**驱动模型是否相同**；
3. 任何"已经有了"的判断，`grep` 一次**生产调用者**，不看定义看调用。
