# AB 路线技术笔记

> 合并自 `ab-route-handoff/docs/` 的 5 份文档（2026-08-02），原目录已删除。
> 丢掉的是已经全部完成的 4-Phase 落地计划，以及绑死在 `rui-nurs` 单案例和本机绝对路径上的
> 复现步骤；留下的是**读源码得出的机制结论**和**踩过坑才知道的数据规范**。
>
> 数据侧脚本移到了 `tools/`：`export_ip_swing_bones.py`（骨架 sidecar，含摆动参数与链尾 tip）、
> `process_ip_geo_body.py`（源 Mesh JSON → 目标网格）、`process_ip_textures.py`（贴图）。
> 作者操作步骤看 [`../docs/wiki/Home.md`](../docs/wiki/Home.md)。

## 1. 三段契约：看懂这段就懂全局

```text
[数据]  geojson + bones sidecar + PNG + mod.json          ← 全部可无 Unity 产出
   │
[打包]  → .bundle (Mesh + prefab骨架 + Texture2D + TextAsset)  ← 唯一碰 Unity 的一步
   │      现在由 tools/patch_unity_bundle.py 给 R32 模板打补丁，作者侧不开 Unity
   │
[运行时] xinput 插件 hook AssetBundle.LoadAsset               ← 已跑通
         · 按【骨名】匹配 mod 骨 → 原 renderer 活体骨
         · mesh 落到【原 renderer】，保留原材质，只按属性换贴图
         · 缺失骨按 sidecar 新建 GameObject + ActorSwingDynamicBone
```

**三个决定难度的关键事实（读插件源码得出）**：

1. 插件按**骨名字符串**认骨（`BuildBoneNameIndexMap`），**不看 `m_BoneNameHashes`**。
   → bundle 里 prefab 的骨 Transform 只要**名字对、顺序对**，TRS 无所谓。
2. mesh 被 clone 后设到**原 body 的 renderer** 上，`replaceMaterials:false` 保留原材质，
   贴图按 `mod.json` 的 `property` 逐槽替换。→ bundle 里的材质是占位。
3. 顶点空间由插件 `TransformModMeshVerticesToOriginalRendererSpace` + bindpose 空间修正处理。
   → mesh 可以在 mod prefab 自己空间里，不用预对齐。

**Unity 版本 6000.0.67f1**（bundle 头写死，必须匹配游戏运行时）。

其余 schema 权威出处：模板打包契约见 `mod-workspace/pipelines/ip/unity-template-builder/`；
manifest 见 `gakumas_mi/core.py` 的 `write_bundle_source`；运行时消费见同级仓库
`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`。

## 2. 运行时换网格机制

chinosk6 `gkms-localify-dmm` 插件如何把 mod 网格塞进游戏。理解这个才能懂为什么 bindpose
要转置、为什么共享骨自动 retarget、为什么无损方案要扩这里。权威源码在
`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`。

### 加载链

1. `version.dll`/`xinput1_3.dll` 代理注入 → IL2CPP runtime。
2. 扫 `gakumas-mod/mods/<id>/mod.json`,注册替换规则(bundle 懒加载)。
3. Hook AssetBundle 加载,命中原始资源名(如 `mdl_chr_hmsz-cstm-0000_body`)→ 加载 mod prefab。
4. 配对 renderer(targetRenderer↔modRenderer,按名),对每对做换网格。

### 换网格核心(`PatchModMeshSkinningToOriginalOrder`,~L1142)

**关键:插件把补好的 mod 网格 `set_sharedMesh` 塞回原(学马活体)renderer**
(`SkinnedMeshRenderer_set_sharedMesh(pair.originalRenderer, clonedModMesh)`,~L1798)。
原 renderer 保留**学马活体 bones[]**(被学马动画驱动)。

流程:
1. `CloneUnityObject`:clone mod 网格(顶点/**colors32**/UV 全保留,不动)。
2. `TransformModMeshVerticesToOriginalRendererSpace`:把 mod 顶点变换到原 renderer 空间
   (处理 renderer transform 偏移)。
3. `PatchModMeshSkinningToOriginalOrder`:
   - `BuildBoneNameIndexMap(originalBones)`:学马活体骨 名→索引。
   - 遍历 mod bones,按名找学马骨:`modToOriginalBoneIndex[i] = 学马索引 或 -1`。
   - **没找到的 → fallback 到 Hips**(`fallbackBoneIndex`)。← **这就是有损的根源**。
   - 重排权重索引到学马骨序;归一化;`droppedInfluences`/`fallbackVertices` 统计。
   - **bindpose**:当 `originalRoot名==modRoot名`(都是 Hips)→ `useModBindposes`:
     `remappedBindposes[origIdx] = modBindpose[i] × bindposeSpaceAdjustment`。
     即**用 mod(IP)自己的 bindpose**,乘一个 renderer 空间校正矩阵。
   - `SetMeshBindposes` + `SetMeshBoneWeights`(不动顶点/颜色)。
4. `set_sharedMesh(原 renderer, 补好的网格)` + 贴图/材质覆盖。

### 三条由此推出的关键事实

#### A. 为什么 bindpose 要转置、且必须正确
运行时 `useModBindposes` 直接用 mod 网格的 bindpose 参与蒙皮:
`skinnedV = Σ wᵢ · 学马活体骨ᵢ · IP_bindposeᵢ · v`。
IP_bindpose 若转置/非法 → 整个蒙皮爆炸(incident §3)。**bindpose 正确性由我方 bundle 保证**,
插件不修。

#### B. 为什么共享骨自动 retarget 到学马体型
`学马活体骨ᵢ × IP_bindposeᵢ`:IP 顶点在 IP bind 空间,被学马活体骨驱动。因为 root 名相同
(Hips)走 useModBindposes,IP 与学马同 QualiArts 骨架,该乘积把 IP 网格自动重定向到学马比例。
**这就是为什么不需要 Blender 预烘对齐**。

#### C. 为什么 reparent 有损、无损方案要扩这里
学马 renderer 的 `bones[]` 固定 146 根,**没有 IP 专属骨的槽位**。插件当前"没同名就 fallback
Hips"→ 专属骨信息丢失。无损方案(本文第 4 节)改这里:**没同名就
`il2cpp GameObject.new` 建 Transform、SetParent 到学马父骨、写 IP localTRS、塞进 bones[]**,
并保持 IP 原始 bindpose/权重不改。这是对本函数的增量分支,不是重写。

### 我方网格不碰的字段(所以要在 bundle 里就正确)

插件 clone 后**不动**:顶点、法线、切线、UV、**colors32(描边)**、submesh、材质槽结构。
→ 这些必须在 JSON→Mesh 导入器阶段就正确(COLOR 描边、bindpose 转置、UV)。
插件**会改**:bindpose(乘空间校正)、boneWeights(remap 骨序)、贴图(按 mod.json 覆盖)。

### 贴图覆盖

`ApplyMaterialTextureReplacements`:按 mod.json 的 rendererName+materialSlot+property 从 bundle
加载 Texture2D 覆盖。`replaceMaterials=false` 时复用学马原材质只换贴图(_BaseMap/_DefMap/_ShadeMap)。
材质槽数不足时(学马单材质 vs mod 双 submesh)slot1 覆盖可能不生效——native-co 小件的已知限制。

### 诊断日志(mod-plugin.log)

`[ModAsset] Patched mod mesh skinning ... matchedBones=90 droppedInfluences=0 fallbackVertices=0
bindposeMode=mod-remapped originalRoot="Hips" modRoot="Hips"` +
`Weighted bone diagnostics ... modTop=[...] originalTop=[...]`(两者一致=权重落对骨)。
几何炸但这些行正常 → bindpose/坐标问题,不是骨映射。

## 3. 新增物理骨（swing）：结论与规范

> 面向接手 AB 路线物理骨的开发者。2026-07-17 实机跑通(rui-nurs→hmsz-0000:翅膀、裙摆、
> 缎带、两个听诊器均正常摆动)。

### TL;DR

- **新骨独立 ActorSwing 物理:已支持。** 运行时路线(插件建链 + `AddComponent`)成立,
  不需要 option A(bundle 授权原生组件),不需要角色初始化前的附挂入口。
- **长期误诊的「1 层墙」根本不是 bug**,是**导出器漏数据**。`UpdateChainInfo` 一直是对的。
- 数据补齐后 `UpdateChainInfo` 自己就建出正确层数。**不要手搭 layer,也不要再逆向它**。
- **多数服装复用 base 骨 → 物理免费**,仍是作者首选;新骨物理是 opt-in 高级特性。

### 1. 「1 层墙」的真因(重要:别重走弯路)

历史上两轮结论都是误诊,已推翻,**勿再重复**:

| 被推翻的旧结论 | 实况 |
|---|---|
| 层结构在角色实例化时原生绑定,运行时够不着 → 需要 option A | ❌ 运行时完全够得着 |
| `UpdateChainInfo` 沿 `GetChild(0)` 建层,我们的骨没 `AddComponent`/不是第一子节点 | ❌ 组件和拓扑一直是对的;`SetAsFirstSibling` 修复从未触发过(`reordered=0`) |

**真因**:`UpdateChainInfo` **会排除每条链的最后一根骨**——链尾(tip)只用来定义末节的朝向和
长度,本就不该参与模拟。所以**完整链深 N → N-1 层**。

我们的链缺 tip,于是:

```
Wing1 → Wing2            (缺 tip)  → 游戏把 Wing2 当成 tip 排除 → 只剩 1 层,不摆
Wing1 → Wing2 → Wing3_End(完整)   → Wing3_End 是 tip → 2 层,Wing2 正常摆 ✓
```

**「只有 1 层」是游戏对残缺输入的正确反应,不是缺陷。** 补上 tip,同一条链自动变 2 层。

> ⚠️ **不要手搭 layer。** 曾写过 40 行克隆 `ChainLayerInfo` 的补丁来硬凑层数;补齐 tip 后它
> 会和游戏自己产出的层**重复**,同一根骨被模拟两次 → 翅膀变形、听诊器摊平。已删除。

### 2. 两个数据缺口(真因所在,都在导出侧)

#### 2.1 链尾 tip 骨没导出

53 根摆动骨里有 **14 根没有蒙皮权重** → 不在 `SkinnedMeshRenderer.m_Bones` → 只走 `m_Bones`
的导出器完全看不到它们。

- **坑:按 `_End` 后缀筛会漏掉 `RightFrontStethoscope3_S`**(它没有 `_End` 后缀却同样无权重)。
  **要按「在不在 `m_Bones` 里」判**,不是按名字。
- 它们**不能进 sidecar 的 `bones` 数组**——那里必须与 mod mesh 的骨数组同长同序,插件有硬校验
  `sidecarBones.size() != modBones->max_length` → 直接拒绝。
- 所以单列顶层 `extraSwingBones` 段,按 `parentName` 挂。全部 14 根的父骨都在 `bones` 里。

典型受害者:`LeftFrontStethoscope1_S` 的唯一子骨就是 tip,漏掉后整条链只剩一个锚点,
**物理上不可能摆**。

#### 2.2 摆动参数没导出

导出器只导 TRS;插件建骨后只调 `SetDefaultValues`,拿到一套**惰性默认值**(`mass=0`、
`spring=0`、`stiffness=0.05`)→ 骨摆不起来。

源数据同时解释了为什么「翅膀不动」看起来像 bug 其实是巧合:

```
LeftBackWing1_S  spring=0.0  mass=0.0   ← 链根锚点,源里本来就是惰性(与默认值巧合相同)
LeftBackWing2_S  spring=0.3  mass=0.5   ← 我们却灌了 0/0 → 摆不起来
```

**提取法(比旧的 AssetStudio 定长偏移法简单得多)**:源 bundle **typetree 内嵌**,UnityPy 直接
读得动 MonoBehaviour,53/53 全出,无需 dummy DLL、无需固定偏移、无需镜像回填。`m_Script` 指向
缺失的 CAB 依赖 → 拿不到类名 → **按 typetree key 签名认 swing 骨**(含 `damping/stiffness/
spring/mass` 即是)。实现见 `../scripts/export_rui_bones.py`。

只导源**真正授权**的 5 个字段:`damping / stiffness / spring / mass / useWindGlobalForce`。

> ⚠️ **`m_Weight` 不是 `rootWeight`。** 源里所有骨 `m_Weight=1.0`,而 base 骨运行时读到
> `rootWeight=0.3` → 它是运行时算出来的,**别导别写**。同理 `pendulum/pendulumRange/wind/
> axisAdd*` 都不是序列化字段,由运行时计算。

### 3. 层语义(实机验证)

```
layer[0] active=0  bones=各链根            ← 锚定层,设计上永不摆
layer[1] active=1  bones=各链 depth-1 骨   ← 真正在摆
tip                不在任何 layer 里        ← 只定义末节朝向
```

- `active=0` 的 layer[0] 是**正常的**,不要试图把它打开。
- 在 `UpdateChainInfo` 刚返回时读 `layer[1].active` 会是 0;它是**每帧更新的 LOD/剔除标志**,
  跑起来才置 1。别据此判断建层失败。
- base 服装 = 5 层 40 骨,同一套语义。

### 4. 源物理参数的结构规律

`ActorSwingChain` 在源里**仅一条**,挂 `Pelvis`(学马叫 `Hips`),`rootBones` = 各 `*1_S` 链根;
`ActorSwingDynamicBone` 覆盖全部 `*_S`。

- tier 越深越硬:`damping` 0.44 → 0.75。
- 链根(`Wing1_S`/`Stethoscope1_S`)= `damping 0.5 / stiffness 0.05 / spring 0 / mass 0`
  → **刚性锚,自身不摆,由子骨摆**。这与第 3 节的 layer[0] 语义一致。

### 5. 已知缺口

- **`limitInfo`(每骨限位)当前不导出**。源里对末端 `*_End` 会把限位放开到 [-180,180]。目前实机
  表现正常,但如果将来出现摆动越界/穿模,这是第一个该补的地方。
- **`radius`/`smoothing` 是 per-layer 授权的**(base layer[0]=0.05 vs layer[1]=0.005),现由
  `UpdateChainInfo` 自行计算,我们不干预。若手感不对再查这里。

### 6. 泛化性:不限偶像荣耀

swing 系统是**学马自己的**(`ActorSwingChain`/`ActorSwingDynamicBone`),任何新骨要物理都得符合
学马 swing 规范,与源游戏无关。偶像荣耀只是**恰好共用 ActorAnimation 中间件** → 组件布局一致
→ 白送真实参数,**非必要条件**。自制骨手调参数一样成立。

**给开发者的路径(优先级从高到低)**:

1. **能复用 base 骨就复用**(新几何权重绑到现有裙摆/头发骨)→ 物理免费继承,**首选、零成本**。
   rui-nurs 的裙摆就是这么工作的(`matchedBones=90`)。
2. **必须新骨时**(翅膀/听诊器/尾巴,运动独立于 base):
   - 链式命名 `<部位>1_S / 2_S / ... / N_S_End`,父挂稳定骨(Shoulder/Spine/Hips)。
   - **必须给链尾 tip**,哪怕它没有蒙皮权重 —— 否则真正该摆的那根会被当 tip 排除(见第 1 节)。
   - 每骨给 `damping/stiffness/spring/mass`;链根用惰性值(spring 0 / mass 0)当锚。
     没有源参数就手调,或借相似 base 骨(尾巴借裙摆、飘带借 ribbon)。
   - 链根挂 `ActorSwingChain.rootBones`,其余交给 `UpdateChainInfo`。

### 7. option A(bundle 授权原生组件):已不需要

A = 把组件+参数授权进 mod bundle,让游戏 load 时原生建链。**runtime 路线成立后 A 无收益,
不要重启。**

仅保留两条有价值的历史事实:

- **加载关是通的**:il2cpp 按 **(程序集, 命名空间, 类名)** 解析 MonoScript;用
  `ActorAnimation.Runtime.asmdef + namespace ActorAnimation + 真类名/字段名` 后,bundle 授权的
  原生组件可被完整反序列化(`chains=1 dynamicBones=3 rootBones=3 damping=0.44`)。
  「A 加载即死」是错的。曾尝试的真实 script PathID 注入路线已废弃,asmdef 才是正解。
- **集成关未通**:`RegisterBones` 内 `List.get_Item` 越界 ——
  `CampusActorAnimationInitializeData` 在 hook 前已构建多组按索引对应的并行表,只追加
  `swingDynamicBones/swingChains` 会破坏长度关系。要走 A 必须找到该表构建前的实例化入口。
  **既然 runtime 路线已通,这条别碰。**

### 8. 工程坑

- **`UnityResolve::Class::SetValue` 是坏的**:声明 `-> void` 却 `return expr;`,**只在实例化时**
  才编译报错。写字段用 field offset 直写。
- UnityResolve 自带的 `List::Add` / `List::New` 同样不可用 → 用 `ListAddManaged`
  (inflated `Add` + `il2cpp_runtime_invoke`)、`CreateObjectLike`(`il2cpp_object_new` + ctor,
  照实例克隆类型,对泛型 List 和 `ChainLayerInfo` 都适用)。
- 多角色场景下 prefab/clone 指针会错位 → **按骨名匹配**,别存指针。

## 4. 「无损」的精确边界

- **几何 / 权重 / bindpose / COLOR / 骨骼结构**：100% 无损；
- **动画**：身体用学马编舞（retarget 是特性，不是损失）；
- **源专属骨物理**：已恢复（2026-07-17），做法见第 3 节。

为什么 reparent 一定有损：学马 renderer 的 `bones[]` 固定 146 根，**没有源专属骨的槽位**。
插件早期「没同名就 fallback 到 Hips」会丢掉专属骨信息。现在的做法是没同名就
`il2cpp GameObject.new` 建 Transform、`SetParent` 到学马父骨、写源 localTRS、塞进 `bones[]`，
并保持源 bindpose 与权重不改。

