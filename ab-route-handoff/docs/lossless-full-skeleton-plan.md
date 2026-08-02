# ★ 无损全骨架嫁接方案(已实现几何基线)

> 实现状态(2026-07-15)：当前案例(rui-nurs→hmsz-0000)已完成几何无损基线；仍用 reparent 把 IP 专属骨
> 塌缩到匹配祖先,是**有损**的——吊带/翅膀/挂包位置错、形状被扯、不自摆。本方案把整套 IP
> 骨骼作为真实 Transform 补进学马活体骨架,做到网格+骨架结构 100% 无损。

## 为什么 reparent 一定有损

无 sidecar 的旧分支把 mod 网格骨权重按骨名 remap 到学马 renderer 的固定 146 骨,**没有同名的骨被丢弃/
fallback**。学马 renderer 的 `bones[]` 没有槽位容纳 IP 专属骨(吊带/翅膀/听诊器/挂包)。
无论 reparent 到哪根,那根独立骨的存在信息在学马骨架里没有承载体 → 必然有损。

实测(rui-nurs):11 根不匹配骨全是护士服专属摇曳/道具骨:
`Left/RightBackWing1-2_S`、`Left/RightFrontStethoscope1-2_S`、`Left/RightBackRibbon3-4_S`
(Ribbon 链几何上是左右后髋的**挂包/背带**,高约 0.47m)。当前 reparent:
Wing→Shoulder、Stethoscope→Spine2、Ribbon 链整体→Hips(强制刚性)。位置勉强对但都不自摆,
且 Wing 这类"父链走脊背、几何在别处"的骨 reparent 后会明显错位。

## 无损架构:混合 bones[] + 骨骼嫁接

**网格的顶点/权重/bindpose/COLOR 一个字节都不动。** 只改"每根骨从哪来":

mesh 的 `bones[]` 保持 **IP 原始 101 骨顺序**,逐骨:

| IP 骨类型 | 接法 | 驱动者 |
|---|---|---|
| 学马有同名(Hips/Spine/四肢/手指/大部分裙摆_S) | `bones[i]` 指向**学马活体 Transform** | 学马动画(自动 retarget 到学马体型) |
| IP 专属(学马没有的) | **新建 GameObject+Transform**,按 IP 原始 localTRS 摆好,`SetParent` 到「IP 父骨对应的学马活体骨」下 | 刚性跟随父骨,或挂物理(见下) |

关键收益:因为 `bones[]` 保持 IP 原顺序、bindpose 用 IP 原始的,**权重索引完全不用改、不用
归一化、无 drop、无 fallback**——比现在的 remap 实现还简单。吊带嫁接到 UpLeg 下就长在大腿上,
挂包嫁接到 Pelvis/Hips 下长在骨盆上,各回各家,几何无损。

嫁接锚点保证存在:IP 专属骨的父链最终都落到 Hips/Spine/UpLeg 等学马也有的骨(实测无例外);
若直接父骨也是 IP 专属,往上走到第一个学马存在的祖先。

### 蒙皮数学(为什么无损且能 retarget)

Unity 蒙皮:`skinnedV = Σ wᵢ · liveBoneMatrixᵢ · bindposeᵢ · v`

- 共享骨 i:`bindposeᵢ`=IP 原始,`liveBoneMatrixᵢ`=学马活体骨 → `学马骨×IP_bindpose` 自动把
  IP 顶点 retarget 到学马比例(当前案例已验证此机制,身体正常)。
- 专属骨 i:`liveBoneMatrixᵢ`=`学马父骨世界矩阵 × 嫁接localTRS`,`bindposeᵢ`=IP 原始 → 该件
  跟随学马父骨,形状=IP 原始。无损。

## 要动三样

### 1. 导出 IP 完整骨架(层级 + localTRS)【已实现】
IP bundle 的每个 Transform 带 `m_LocalPosition/Rotation/Scale` + `m_Father`。一次性导成
`build/rui_bones.json`(和学马 `Geo_Body.skeleton.json` 同格式:每 node 有 name/parent/
localPosition/localRotation/localScale)。UnityPy 可读(见 workspace 里生成 rui_bones.json 的做法,
把 parentChain 换成完整 TRS 即可)。**注意 root 名两边都是 Hips。**

### 2. 扩插件 `PatchModMeshSkinning`(核心改动)【已实现】
`gakumas-mod-runtime/src/runtime/ModRuntime.cpp` 现在保留无 sidecar mod 的旧 remap 分支；声明 `skeleton` 的 replacement
改成 `没同名 → 嫁接`:

```
buildBoneNameMap(学马活体 bones) -> nameToLiveTransform
newBones[101]  // IP 原顺序
for i in 0..100:
    name = ipBoneName[i]
    if name in nameToLiveTransform:
        newBones[i] = nameToLiveTransform[name]           // 共享:用学马活体骨
    else:
        go  = il2cpp GameObject.new(name)                 // 专属:新建
        t   = go.transform
        parentName = ipParentResolvedToLive(name)         // 走 IP 父链到第一个学马存在的骨
        t.SetParent(nameToLiveTransform[parentName], false)
        t.localPosition/Rotation/Scale = ipLocalTRS[name] // 从 rui_bones.json sidecar
        newBones[i] = t
renderer.bones      = newBones                            // 混合数组,IP 原顺序
mesh.bindposes      = ipBindposes(原始,不改)
mesh.boneWeights    = 不改(索引已对)
// 保留现有 TransformModMeshVerticesToOriginalRendererSpace 的空间校正
```

探针实验已验证 IL2CPP 在学马 `il2cpp_object_new` 建 GameObject/Transform、`SetParent`、写
localTRS 可行(结论见
[`research/pc-il2cpp-gmim-runtime-replacement.md`](../../research/pc-il2cpp-gmim-runtime-replacement.md);
探针代码 `experiments/pc-il2cpp-proxy/` 已于 2026-08-02 删除,需要时从 git 历史取)。
注意跨线程:建对象/改层级必须在主线程(hook `Time.get_deltaTime` 泵),不能在轮询线程。

### 3. prefab/bundle 侧【已实现】
JSON→Mesh 导入器额外把 `rui_bones.json` 打进 bundle(TextAsset),供插件读专属骨的 localTRS。
或插件直接从 mod 目录读随包的 `rui_bones.json`。mesh 本身仍是 101 命名骨(导入器已有),
bindpose 仍是 IP 原始(已转置修正)。

## "无损"的精确边界

- **几何/权重/bindpose/COLOR/骨骼结构**:100% 无损。
- **动画**:身体用学马编舞(retarget 是特性,不是损失)。
- **IP 专属骨物理**:已恢复(2026-07-17)。见下节。

## 物理层(已跑通)

学马与 IP 是**同一套 QualiArts ActorSwing 框架**,类名逐字相同(已在学马 global-metadata 核实:
`ActorSwingChain/DynamicBone/BreastBone/Collider` + `ActorSwingJob*`)。做法:给嫁接骨挂**学马
原生 ActorSwing 组件**。本案例的 IP `ActorSwingDynamicBone` 只有 marker，但组件还需要正确的
默认参数、初始姿态、建模引用和 Job 更新组注册，不能仅靠 `GameObject.AddComponent(Type)` 完成。
- 已确认：Rui 的 11 根缺失骨全部是 `ActorSwingDynamicBone`；hmsz 使用同名类，且目标
  `ActorSwingChain` 位于 `Pelvis`。
- **runtime 路线成立,`GameObject.AddComponent(Type)` + 灌源参数就够**,不需要 option A。
- 前提是 sidecar 必须补两样:每骨的摆动参数,以及**每条链的链尾 tip 骨**(无蒙皮权重、不在
  `m_Bones`,要单列 `extraSwingBones`)。缺任一样都不摆。
- 「`UpdateChainInfo` 对新骨只建 1 层」的旧结论是**误诊**:它会排除每条链的最后一根,缺 tip 时
  真正该摆的那根被当成 tip 排除了。补齐后它自己就建对层数,插件不干预 layers。
- **当前结论**:已支持。详见 `physics-bones-findings.md`。

## 建议执行顺序

1. **无损几何基线(已完成并实机验证)**:导 IP 全骨架 TRS → 插件嫁接;保留 mesh/权重/
   bindpose/COLOR 和专属骨结构。
2. **物理(暂停)**:能复用 base 裙摆/头发骨就复用;必须使用新增骨时保持静态跟骨。
   不再扩大运行时 hook,除非先拿到 initializeData 构建前入口的独立证据。

关联:memory `pc-il2cpp-gimi-path`、`rui-nurs-hmsz0000-ab-mod`;3Dmigoto 路线交接包见
`../05-ai-handoff`(那条路线因骨调色板被目标服装焊死,**原理上无法加骨**,所以无损全骨架只有
AB/引擎路线能做)。
