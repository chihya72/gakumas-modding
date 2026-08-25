# AB 路线技术笔记

> 合并自 `ab-route-handoff/docs/` 的 5 份文档（2026-08-02），原目录已删除。
> 丢掉的是已经全部完成的 4-Phase 落地计划，以及绑死在早期原型单案例和本机绝对路径上的
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

其余 schema 权威出处：模板打包契约见 `tools/build_phase3_templates.py`（它调用的 Unity
工程只用于一次性批量产模板，模板本体走网盘分发）；manifest 见 `gakumas_mi/core.py` 的
`write_bundle_source`；运行时消费见同级仓库 `gakumas-mod-runtime/src/runtime/ModRuntime.cpp`。

## 2. 运行时换网格机制

chinosk6 `gkms-localify-dmm` 插件如何把 mod 网格塞进游戏。理解这个才能懂为什么 bindpose
要转置、为什么共享骨自动 retarget、为什么无损方案要扩这里。权威源码在
`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`。

### 加载链

1. `version.dll`/`xinput1_3.dll` 代理注入 → IL2CPP runtime。
2. 扫 `gakumas-mod/mods/<id>/mod.json`,注册替换规则(bundle 懒加载)。
3. Hook AssetBundle 加载,命中原始资源名(如 `mdl_chr_hmsz-cstm-0000_body`)→ 加载 mod prefab。
4. 配对 renderer(targetRenderer↔modRenderer,按名),对每对做换网格。

### 换网格核心（`PatchModMeshSkinningToOriginalOrder`）

**关键:插件把补好的 mod 网格 `set_sharedMesh` 塞回原(学马活体)renderer**
（`SkinnedMeshRenderer_set_sharedMesh(pair.originalRenderer, clonedModMesh)`）。
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

> 面向接手 AB 路线物理骨的开发者。本节的机制结论(tip 骨、`UpdateChainInfo` 语义、参数字段)
> 是读源码 + 逐项实测得出的。**2026-08-11 起「新骨会摆」有了画面级证据**
> （`hmsz-fuyuko-icu` / `hmsz-cstm-0059`），完整流水线见 §10，调参的负结果见 §12。

### TL;DR

- **新骨独立 ActorSwing 已画面级跑通**（2026-08-11，`hmsz-fuyuko-icu`）。踩过的六个坑
  逐条见 §10；剩下的只有手感（幅度偏小），且已证实不由摆动参数决定，见 §12。
- **长期误诊的「1 层墙」根本不是 bug**,是**导出器漏数据**。`UpdateChainInfo` 一直是对的。
- 数据补齐后 `UpdateChainInfo` 自己就建出正确层数。**不要手搭 layer,也不要再逆向它**。
- **多数服装复用 base 骨 → 物理免费**,仍是作者首选;新骨物理是 opt-in 高级特性。

### 1. 「1 层墙」的真因(重要:别重走弯路)

历史上两轮结论都是误诊,已推翻,**勿再重复**:

| 被推翻的旧结论 | 实况 |
|---|---|
| 层结构在角色实例化时原生绑定,运行时够不着 → 需要 option A | ❌ 运行时完全够得着 |
| `UpdateChainInfo` 沿 `GetChild(0)` 建层,我们的骨没 `AddComponent`/不是第一子节点 | ❌ 组件和拓扑一直是对的;`SetAsFirstSibling` 修复从未触发过(`reordered=0`) |

**真因**:链缺了链尾(tip),所以少一层。**完整链深 N → N 层**,链尾**也在层里**。

> ⚠️ **2026-08-11 修正**:本节曾写「`UpdateChainInfo` 会排除每条链的最后一根骨,所以链深 N →
> N-1 层」。**排除那半句是错的。** 实测两边都把链尾算进层:
>
> ```
> 游戏自己的裙摆链  layer[4] bones=8 first=LeftBackSkirt5_S_End    ← 链尾在层里
> 我们建的长链      layer[4] bones=1 first=SStreamer_L_Aend_End    ← 同样在
> ```
>
> 结论方向不变(**必须给链尾**),但理由要改:不是"补了 tip 让真正该摆的那根不被排除",而是
> **链深每多一节就多一层,且末节朝向由链尾定义**。缺链尾 = 少一层 + 末节朝向未定义。

```
Wing1 → Wing2            (缺 tip)  → 2 层
Wing1 → Wing2 → Wing3_End(完整)   → 3 层 ✓
```

> ⚠️ **不要手搭 layer。** 曾写过 40 行克隆 `ChainLayerInfo` 的补丁来硬凑层数;补齐 tip 后它
> 会和游戏自己产出的层**重复**,同一根骨被模拟两次 → 翅膀变形、听诊器摊平。已删除。
> **注意区分**:让 `UpdateChainInfo` 建层、再往它建好的层上写授权字段(见 §3),不是手搭层。

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
spring/mass` 即是)。同引擎源的抽取实现见 `tools/export_ip_swing_bones.py`。

只导源**真正授权**的 5 个字段:`damping / stiffness / spring / mass / useWindGlobalForce`。

> ⚠️ **2026-08-11 推翻**:曾断言「`pendulum/pendulumRange/wind/axisAdd*` 都不是序列化字段,
> 由运行时计算」。**全错。** 学马自己的 body bundle **内嵌 typetree**,530 套全扫下来
> `ActorSwingDynamicBone` 的每一个字段都是逐骨授权的序列化值(见
> `tools/scan_vanilla_swing_bones.py`)。据此产出原版基准表 `gakumas_mi/swing_presets.json`。
> 早期那张「按 248 字节定长偏移统计」的分布表作废——根本不用猜偏移。
>
> 后果很实际:`pendulumRange` 原版 **84.6% 取 1.0**(它是 pendulum 的作用范围,留 0 等于把
> 重力项乘没了)、`wind` 84.6% 取 1.0、`useLimit` 88.3% 是 1 且带真实角度限位。都是压倒性
> 多数、中位数即取这几个值,但**不是「一律」**——早期这里写成「一律」是过度概括。我们此前只写六项、
> 其余交给 `SetDefaultValues`,于是新骨在数据上"参数齐全",实际既不下垂也不受风。

### 3. 层语义(1539 条原版链实测 + 实机验证)

```
layer[0]  active=0  radius=0.050              ← 锚定层,1539/1539 无一例外
layer[1+] active=1  radius 0.010→0.015→0.025→0.030→0.033  ← 逐层递增
链尾      在最后一层里(不是被排除,见 §1 修正)
```

- `active=0` 的 layer[0] 是**正常的**,不要试图把它打开。
- **`active` / `radius` / `around` / `smoothing` 都是序列化授权字段,`UpdateChainInfo` 不设它们。**
  它只负责建层的**成员**(哪根骨在第几层)。游戏自己的链从 bundle 反序列化就带着这些值;
  运行时新建的层拿到的是 `ChainLayerInfo()` 默认值(`active=0` / `radius=0.05`)——
  **`active=0` 基本等于这条链不参与模拟**。所以新建链必须自己补写,见 §10。
- `around` 原版是**逐链手调**的(60% 关 / 40% 开),同一件衣服左右袖都能不一致,没有
  "某类部件就该开"的规律。默认留 0。

> ⚠️ **2026-08-11 推翻**:本节曾写「`UpdateChainInfo` 刚返回时读 `active` 必然是 0,它是每帧
> 更新的 LOD/剔除标志,跑起来才置 1」。**错的。** 同一帧同一份 dump 里,游戏自己的链
> `active=1` 而我们新建的链全 0 —— 差别不在时机,在**有没有被授权**。这条错误结论曾让
> 「日志里 active=0」被当成正常现象放过,直接掩盖了真病因。

### 4. 源物理参数的结构规律

`ActorSwingChain` 在源里**仅一条**,挂 `Pelvis`,`rootBones` = 各 `*1_S` 链根;
`ActorSwingDynamicBone` 覆盖全部 `*_S`。

> ⚠️ **这是偶像荣耀的结构,学马不是。** 学马一件衣服常有多条链,宿主随部位走:
> `Pelvis`(裙)、`Spine2`/`Spine`(外套)、`LeftShoulder`(披风)、`LeftArm_H`/`RightArm_H`(袖)、
> `Head_Hair`(头发)。而且学马的 `Hips` 和 `Pelvis` **是两根不同的骨**,别把
> 「学马叫 Hips」当成等价替换。

- tier 越深越硬:`damping` 0.44 → 0.75。
- 链根(`Wing1_S`/`Stethoscope1_S`)= `damping 0.5 / stiffness 0.05 / spring 0 / mass 0`
  → **刚性锚,自身不摆,由子骨摆**。这与第 3 节的 layer[0] 语义一致。

### 4.5 飘带蝴蝶结**不建链**(2026-08-11,530 套原版实证)

按类别统计原版摇物骨挂不挂 `ActorSwingChain`:

| 类别 | 骨数 | 挂链比例 | 常见宿主 |
|---|---:|---:|---|
| skirt(裙/裤/外套) | 24183 | **94%** | Pelvis / Spine2 / Spine / *UpLeg_H |
| cloth(披风/褶边/领腰) | 5020 | **54%** | *Shoulder / Pelvis / Spine |
| sleeve(袖) | 5639 | 25% | *Arm_H |
| ribbon(飘带/绳结/挂饰) | 6685 | **2.6%** | — |
| skin(腿/臀软组织) | 6745 | **0%** | — |

**蝴蝶结和飘带在原版里就是裸 `ActorSwingDynamicBone`**,靠 `swingDynamicBones` 逐骨模拟——
链只是裙摆专用的那层 `around/radius` 环形碰撞解算。此前一直照着裙摆给飘带建链,抄错了对象。

第 4 节那句「`ActorSwingChain` 在源里**仅一条**、挂 `Pelvis`」是偶像荣耀的结构,**学马不是**:
一件衣服常有多条链、宿主随部位走(披风挂 `LeftShoulder`、袖挂 `RightArm_H`)。

### 5. 已关闭缺口与当前边界

- ✅ **自建摇物骨已画面级确认**(2026-08-11,`hmsz-fuyuko-icu` / `hmsz-cstm-0059`):飘带正常
  摆动、长链末端花边不抽、右飘带不穿腿。**这是第一个画面级成功案例**,此前所有"跑通"说法
  都只有日志。日志侧同时全绿:骨 15/15 进 `swingDynamicBones`、并行表同长、参数活体读回
  一致、链尾齐全、两条链各 4/5 层且 `active`/`radius` 与原版同构。
  剩下的只有手感(幅度偏小),属调参且已证实不由这几个参数决定,见 §12。
  ~~注意别把 `layer[N].active=0` 当病因——它是每帧 LOD 标志~~ **这句是错的，已由 §3 推翻**：
  `active` 是序列化授权字段，新建层拿到的 0 **就是**病因，不是正常现象。
- ⚠️ **直接热 ON 不补建新增摇物骨/链**：它们只在 prefab graft 与角色初始化阶段进入
  Animation Rig。热开关可刷新已有活体的 Mesh、材质、骨绑定与碰撞体；只要 sidecar 的 swing
  结构发生变化，就必须重新进入场景再判断摆动效果。
- ✅ **`newBones: []` 不是静默丢数据**(2026-08-11 复核):7 个成品的
  `physicsInheritance.strategies` 里 `new_source_chain` 是 **0** 个,全部走了刚性/跟裙摆。
  也就是说 `integrate` 这条路径**一次都没被成品走过**,不是丢了、是没人用过。
- ✅ **`RegisterBones` 抛 `ArgumentOutOfRangeException` 的真因已定位**(2026-08-11):
  `CampusActorAnimationInitializeData` 里 `initialTransforms`(0xB0) 与
  `swingDynamicBones`(0xD8) 是**按下标并行**的两张表,由
  `ActorAnimationInitializeData(IEnumerable<IActorAnimationBone>)` 一次同步构建;运行时只往
  后者追加 → 长度失衡 → 取 `initialTransforms[i]` 越界 → **整个注册中途夭折**。而我们的
  "链注册成功"日志全部打印在调用 orig **之前**,所以日志全绿、装饰件不动。
  这个追加本来就不需要:`ActorSwingDynamicBone`/`ActorSwingChain` 都实现
  `IActorAnimationBone`,graft 跑在 prefab 上,晚一步的 `CampusActorAnimation.Initialize()`
  自己会收走它们。**已改为 graft 时在 prefab 上建链、删掉列表追加和 SEH 兜底。**
- ✅ **`limitInfo` 与碰撞体已导出**(2026-08-11)。字段↔偏移不用逆向了:学马 bundle 内嵌
  typetree,`tools/scan_vanilla_swing_bones.py` 直接按名字读。`LimitInfo` 运行时布局
  (`useLimit@0x10 / axisX@0x14 / axisY@0x1C / axisZ@0x24`)取自 il2cpp,与 `dynamicCollider`
  一样**在 graft 时自己 new 出来**再写 —— `SetDefaultValues` 不建这两个引用字段,直接写会被
  null 检查静默跳过。`UnityResolve::Class::address` 就是 `Il2CppClass*`,所以能直接
  `il2cpp_object_new`,不需要现成实例当模板。2026-08-11 实机确认:活体读回
  `colliderRadius=0.0200 collisionMask=-1`,与 sidecar 逐项一致。
- ✅ **`radius`/`smoothing` 是 per-layer 授权的**——前半句对,但「现由 `UpdateChainInfo` 自行
  计算,我们不干预」是错的:它根本不算,新建层拿到的是默认值。已由 §10 补写。

### 6. 泛化性:不限偶像荣耀

swing 系统是**学马自己的**(`ActorSwingChain`/`ActorSwingDynamicBone`),任何新骨要物理都得符合
学马 swing 规范,与源游戏无关。偶像荣耀只是**恰好共用 ActorAnimation 中间件** → 组件布局一致
→ 白送真实参数,**非必要条件**。自制骨手调参数一样成立。

**给开发者的路径(优先级从高到低)**:

1. **能复用 base 骨就复用**(新几何权重绑到现有裙摆/头发骨)→ 物理免费继承,**首选、零成本**,
   也是最低成本、样本最多的装饰物理做法（插件里叫「跟裙摆」）；自建摇物已另有 `hmsz`
   画面级成功样本，不再是“只有这一条有效”。
2. **必须新骨时**(翅膀/听诊器/尾巴,运动独立于 base):
   - 链式命名 `<部位>1_S / 2_S / ... / N_S_End`,父挂稳定骨(Shoulder/Spine/Hips)。
   - **必须给链尾 tip**,哪怕它没有蒙皮权重 —— `UpdateChainInfo` 会把 tip 也放进层；漏掉它会
     少最后一层和末端方向/长度信息，不要再解释成“最后一根会被排除”（见第 1 节）。
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

### 8. 导出侧的四个写入约定(2026-08-04 实证,别再写反)

新增骨的 TRS/bindPose 由插件自己写,**不经过 Mesh JSON**——游戏原始骨怎么写都不受影响,所以
这四条错了只有新增骨中招,且必须有 mod 真给这些骨刷权重才看得出来(权重为 0 时错误数据挂在
没人引用的骨上,静默潜伏)。dress-2219 一次性暴露全部四条:

| # | 约定 | 写错的表现 |
|---|---|---|
| 1 | bindPose 按 AssetStudio 的 `M<列><行>` 写,平移落 `M30..M32` | 写成转置 → 顶点被拉开约 1 米,装饰件炸成贯穿角色的黑刺 |
| 2 | `localRotation` 是 Unity 的 `(x,y,z,w)`;mathutils 迭代出来是 `(w,x,y,z)` | 直接 `list()` → w 跑到首位,朝向整个错掉 |
| 3 | 链**根**的 local 必须按**游戏骨架**父骨的静止姿势重算(`inverse(游戏父骨世界) × 作者骨世界`);链内部不动 | 沿用作者骨架的相对变换 → 骨被放到别处而 bindPose 记的是作者世界位置,装饰件坍缩成一片(两套骨架实测差 Hips 38mm / Spine 83mm / Spine2 67mm) |
| 4 | swing 必须带 `rootWeight`(0.3)和 `pendulum`(0.001) | 缺了 → `SetDefaultValues` 给 1.0/0 = 完全刚性 + 无重力,锁死在静止姿态翘着不下垂 |

> 第 4 条与本节第 2.2 小节「`m_Weight` 不是 `rootWeight`,别导别写」不矛盾:**不要从源模型导**
> 这两个值(源里没有),但**要写我方默认值**,否则运行时按刚性处理。

离线验证方法(比进游戏快得多):用真实 blend 模拟导出,量新骨的运行时位置与 bindPose 的偏差。
dress-2219 上修复前平均 208.2mm / 最大 572.4mm、修复后 0.0mm,且模拟出的修复前数值与实际
问题包逐位吻合。做法约 30 行:在 Blender 里对作者网格调 `_source_bone_sidecar_records()` +
`core.build_source_extra_bones()`,再用 `_target_rest_world(游戏骨架)` 沿 `parentName` 合成
每根新骨的运行时世界矩阵,与它 bindPose 的逆逐根比距离。改导出侧写入逻辑前先跑它。

### 10. 自建摇物骨/链的完整流水线(2026-08-11 定稿)

顺序和时机都是踩出来的,每一步都有对应的失败模式。

| # | 谁做 | 做什么 | 做错了会怎样 |
|---|---|---|---|
| 1 | 导出器 | 按 **部件类别 × 链上角色** 从 `swing_presets.json` 取参数,**字段写全** | 少写 `pendulumRange`/`wind` → 参数看着齐,实际不下垂不受风 |
| 2 | 导出器 | 每条链补合成链尾 `*_End` | 少一层 + 末节朝向未定义 |
| 3 | 导出器 | `useLimit=0`(除非源显式授权) | 见 §11 骨轴 |
| 4 | 导出器 | 按类别决定建不建链,宿主 + 按链长分组写进 `swingChains` | 飘带建链=抄错对象;长短混一条链会被截到最短 |
| 5 | 运行时 | **graft 时(prefab 上)** 建骨、建链、挂 rootBones | 放到 `RegisterBones` 里追加 → 并行表越界(见 §5) |
| 6 | 运行时 | `RegisterBones` hook 里,**调 orig 之前**对新链调 `UpdateChainInfo` | 不调 → 链是空壳、一层都没有 |
| 7 | 运行时 | 给新建的层补 `active`(layer>0 置 1)和 `radius`(逐层递增) | 不补 → `active=0`,链不参与模拟 |
| 8 | 运行时 | graft 时**自己 new** `dynamicCollider` / `limitInfo` 再写 | 这两个是引用字段,`SetDefaultValues` 不建它们,直接写会被 null 检查静默跳过 |

**5 之所以必须在 graft 时**:`ActorSwingDynamicBone` 和 `ActorSwingChain` 都实现
`IActorAnimationBone`,graft 跑在 `AssetBundle.LoadAsset` 拿到的 prefab 上,晚一步的
`CampusActorAnimation.Initialize()` 会自己把它们 `GetComponentsInChildren` 收进
`CampusActorAnimationInitializeData`,两张并行表由它保证同长。

**6/7 之所以要在 hook 里**:prefab 上 `AddComponent` 不触发 `OnEnable`,而
`OnEnable` 本来也不建层(游戏自己的链在 bundle 里就带着序列化好的 layers,不需要建)。

**8 之所以要在 graft 时**:曾经放在活体克隆上按**骨名**补写,那要一张全局 `name → params`
表 —— 两个 mod 用了同名骨就互相覆盖参数,碰巧和原版骨同名还会去改原版的碰撞体。自己
`new` 出对象当场写完,那张全局表和整趟活体补写一起删掉,跨 mod 污染从根上没了。

### 10.1 三条建链的硬约束

- **不建分叉链**。`UpdateChainInfo` 只沿**第一个**子节点建层,一根骨带两个子分支时另一支
  永远进不了链层,而我们却会按"最深那支"报一个链长 —— 等于静默建了条只覆盖一半的链。
  导出器检测到分叉直接不建:那些骨照样进 `swingDynamicBones` 逐骨模拟(原版飘带就是这么
  摆的),只是少了链那层环形碰撞,属于安全降级。
- **一根都没挂上的链要销毁**。空链照样会被 `CampusActorAnimation.Initialize()` 收进
  rigData,然后什么都不驱动。
- **分类词表两边必须一致**。`gakumas_mi/core.py` 的 `_SWING_CATEGORY_RULES` 和
  `tools/scan_vanilla_swing_bones.py` 的 `CATEGORY_RULES` 决定"查哪一档基准",分叉了就是
  查错档(实测 `Gown`/`Shirt`/`Inner` 曾在扫描器算 cloth、在插件落 ribbon,于是用错参数
  还不建链)。已有契约测试直接读扫描器源码比对。

### 11. 角度限位不能照搬(骨轴对不上)

`limitX/Y/Z` 是**按骨轴授权**的,而作者 rig 的骨轴和学马的不一样:

| | 子骨方向(=骨轴) | 扭转轴 | 摆动轴 |
|---|---|---|---|
| 原版 | local **−X**(22/22) | X | Y、Z |
| MMD 源 | local **−Z**(7/7) | Z | X、Y |

原版 `limitX=[0,0]` 是**锁扭转轴**(全库 34006 根这么写),照搬到 MMD 骨上就变成**锁死一条真·
摆动轴**,另一条还被夹到 ±30° → 参数全对却纹丝不动。

**不做主轴置换**:作者 rig 的骨轴可能是任意斜向,枚举不完,而猜错的代价正是"完全不动"这种
最难查的故障。限位只是防穿模的精修,原版自己 18% 的飘带骨也不开。默认 `useLimit=0`,源模型
显式给了的照它的来(IP 源同用 ActorAnimation 中间件,轴向一致)。

### 12. 摆动幅度：调参这条路走不通（2026-08-11 负结果，别再走）

`hmsz-fuyuko-icu` 画面跑通后唯一剩下的抱怨是幅度偏小。做过弱/标准/强三档（取原版分位数），
**实测证明这五个参数不是决定幅度的主因**，档位已撤销，只保留标准档（中位数）。

实测方法：临时挂了个每帧钩子量每根骨的**逐帧转角均值**（`°/帧`）——注意只量"相对静止姿态的
峰值"会被角色实例化那一下的初始化瞬移污染（能到 147°），必须跳过前 120 帧再取基准，而且
逐帧转角才是"它在动多少"的正确度量。

结果（同场景同动作，强档 vs 弱档）：

| 骨 | 强 | 弱 | 强/弱 |
|---|---|---|---|
| `Streamer_L_A1` | 0.109 | 0.161 | 0.68 |
| `Streamer_L_A2` | 0.124 | 0.193 | 0.64 |
| `Streamer_R_A1` | 0.099 | 0.124 | 0.80 |
| `Spine_Bow_R_B1` | 0.158 | 0.160 | 0.99 |

**把 `damping`/`stiffness`/`spring`/`mass`/`pendulum` 从原版分布一端拉到另一端，摆幅只动
±35%，方向还与预期相反。** 探针和每帧钩子已随之删除（一个为已放弃调查而常驻的每帧钩子，
迟早变成来路不明的性能/崩溃问题）。

三条附带事实，都可复用：

- **链尾恒 0°**：解算根本不写链尾的 local rotation，它只定义末节朝向。这是正常的。
- **极短段在松参数下会失稳**：`SStreamer_L_Aend`（3.5cm，是前一节的 1/6）在强档下
  `move` 是弱档的 6 倍、peak 40°，明显在数值振荡。印证了「段长悬殊」那条。
- **原版这套服装的参数和我们标准档几乎一致**（damping 0.4~0.5 / stiffness 0.015~0.02 /
  spring 0.4~0.6 / mass 0.4~0.8，`rootWeight` 这套服装 111 根全是 0.3、全库 89.5%），所以差别本来就不该在参数上。

**下次要接着查，先做这个对照**：把游戏自己的摇物骨一起量（同场景同动作，天然对照组）。
如果原版平均 `°/帧` 和我们相近，那"幅度小"就是场景本来动得少，无事可修；差得多才说明是
结构问题（我们的链每层 1 根骨 vs 原版 8 根、链宿主 `Hips` vs `Pelvis`、`ActorSwingGroup`
有没有注册）。**这个对照一直没做，是本轮最该先做而没做的一步。**

### 9. 工程坑

- **`UnityResolve::Class::SetValue` 是坏的**:声明 `-> void` 却 `return expr;`,**只在实例化时**
  才编译报错。写字段用 field offset 直写。
- UnityResolve 自带的 `List::Add` / `List::New` 同样不可用 → 用 `ListAddManaged`
  (inflated `Add` + `il2cpp_runtime_invoke`)、`CreateObjectLike`(`il2cpp_object_new` + ctor,
  照实例克隆类型,对泛型 List 和 `ChainLayerInfo` 都适用)。
- 多角色场景下 prefab/clone 指针会错位 → **按骨名匹配**,别存指针。

## 4. 「无损」的精确边界

- **几何 / 权重 / bindpose / COLOR / 骨骼结构**：100% 无损；
- **动画**：身体用学马编舞（retarget 是特性，不是损失）；
- **源专属骨变换、权重和建链数据**：已恢复；动态物理 2026-08-11 画面级跑通，见第 3 节 §10。

为什么 reparent 一定有损：学马 renderer 的 `bones[]` 固定 146 根，**没有源专属骨的槽位**。
插件早期「没同名就 fallback 到 Hips」会丢掉专属骨信息。现在的做法是没同名就
`il2cpp GameObject.new` 建 Transform、`SetParent` 到学马父骨、写源 localTRS、塞进 `bones[]`，
并保持源 bindpose 与权重不改。

---

## 5. 透明材质：原生 `m_bdyco` 的边界

> 2026-08-03 从 `transparent-material-status.md` 并入。镂空/cutout（原生 `m_bdyco`）
> 已验证完成；玻璃/薄纱级连续半透明不在支持范围。

> 镂空/cutout（原生 `m_bdyco`/`NATIVE_CO`）已验证完成；玻璃/薄纱级连续半透明
> 不在当前支持范围。

### 5.0 唯一当前路线

透明/镂空材质当前只保留一条正式路线：

**借用游戏原生 `m_bdyco` 第二材质段。**

插件层面的材质模式只应保留：

| 模式 | 含义 |
|---|---|
| `OPAQUE` | 使用主 body 材质段 `m_bdy` |
| `NATIVE_CO` | 使用游戏原生第二材质段 `m_bdyco` |

自建 `ALPHA_CLIP`、自建 `ALPHA_BLEND`、运行时模拟 cutout 材质、几何侧 alpha 裁切都不作为当前方案。

### 5.1 关键事实

`fktn-cstm-001` 证明游戏的 body 透明/镂空不是“主材质读 baseColor alpha”，而是：

- 同一个 `Geo_Body`；
- 同一套 body IB/VB；
- 两个材质段；
- `m_bdy` 绘制不透明主体；
- `m_bdyco` 绘制第二 submesh/index range；
- `m_bdyco` 使用自己的 base/def/shade 贴图，其中 base 是 `*_bdyco_col_alp`。

资产侧：

| Material | `_BaseMap` | 关键状态 |
|---|---|---|
| `m_bdy` | `t_chr_fktn-cstm-0001_bdy_col` | `_ShaderType=0`, `_Cull=2` |
| `m_bdyco` | `t_chr_fktn-cstm-0001_bdyco_col_alp` | `_ShaderType=1`, `_Cull=0` |

抓帧侧：

- 主 body 与 body-co 使用同一 IB/VB。
- body-co 是独立 `firstIndex / indexCount` 的 material section。
- body-co 绑定独立贴图槽，使用游戏原生 co shader/state。
- 导出时 `m_bdy` 的基础色 t0 与 `m_bdyco` 的透明材质 t0 必须分开绑定；两者各走各自 UV，
  不能用主 `m_bdy` baseColor 回退填充 `m_bdyco`。

结论：

**透明效果来自游戏原生 `m_bdyco` 材质段，而不是 `m_bdy` 上的 alpha。**

### 5.2 正式 3DMigoto 实现（已验证成功）

3DMigoto 正式路线已经采用并验证了这套 `m_bdyco` 实现，效果正常：

1. Profile 提取阶段记录同一 body IB/VB 下的全部 material sections。
2. 对含 `m_bdyco` 的服装，记录 co section 的 `firstIndex`、`indexCount`、draw、VS/PS、贴图槽。
3. Blender 材质标为 `NATIVE_CO` 时，把该材质段导出到原生 co section。
4. `mod.ini` 在 co section 上使用 `match_first_index`，并绑定该段自己的 `ps-t0/t1/t4`。
5. co draw 必须同样能获得当前帧蒙皮结果；不能只依赖主 body draw 的时序。

这个路线的核心价值是：**保留游戏当前版本的原生 shader/state/draw 上下文**。这样透明行为、描边、
投影和遮挡更接近原版，也避免自写 shader 随游戏更新老化。

### 5.3 `m_bdyco` alpha 行为实测：cutout 而非连续半透明

后续用 `dress_2271` 的 atlas 做了中间 alpha 实机验证：

- 原始透明 padding 区域叠加从上到下的渐变 A 通道后，部分像素已不再是 `A=0`，例如约
  `A=65/255`、`A=80/255`、`A=84/255`。
- 这些低 alpha 区域在游戏里仍然完全透明，说明 `m_bdyco` 不是按 `A>0` 即绘制。
- 把低 alpha 测试性抬到 `A=128/255` 后，原本透明 padding 整块通过并显示为黑块。

结论：

**当前已验证的 body `m_bdyco` 路线更接近 alpha test/cutout：低于阈值的像素 discard，
高于阈值的像素按其 RGB 绘制；不能把中间 alpha 当作真正的连续半透明混合。**

这也解释了为什么把透明 padding 的 alpha 抬高后会出现黑块：该区域的 RGB 本来就是黑色；
`A=128` 只让像素通过裁切，并不会让它按 50% 透明与背景混合。

因此当前结论需要更精确地表述为：`NATIVE_CO / m_bdyco` 是正式的 body 透明/镂空路线，
但已实测更适合 **镂空/cutout**，不能保证薄纱、玻璃等真半透明效果。游戏管线中可能存在其它
前向/合成透明 draw，但尚未找到可安全复用为角色 body 材质的专属路线。

### 5.4 已排除的做法

四条都试过并放弃，结论已并入 [`lessons-learned.md`](lessons-learned.md)：主 body `m_bdy`
直接用带 alpha 的 baseColor（透明区显示黑底，`m_bdy` 不按 alpha 透明）、把 `m_bdyco` 当连续
半透明 blend 用（低 alpha 被裁、抬高后 padding 成黑块）、自写 `ALPHA_CLIP` pass、自写
`ALPHA_BLEND` pass（后两条与游戏原生状态不一致、维护成本高，已移除）。

已移除的 PC IL2CPP 支线也独立得到同一结论：**透明必须走原生 `m_bdyco`**。

---

### 5.5 当前约束

- 没有原生 `m_bdyco` section 的 profile，不能导出 `NATIVE_CO` 材质。
- 若作者需要透明/镂空，应使用包含 body-co section 的服装生成配置档。
- 若目标服装没有 `m_bdyco`，该材质必须改回 `OPAQUE`，或更换/重建 profile。
- 只要有材质槽设为 `NATIVE_CO`，就必须提供单独的 `m_bdyco` t0；缺失时应停止导出，
  不能回退到 `m_bdy` 的基础色 t0。
- **「目标资源有几段」不等于「要提供几套贴图」。** 原版 body 的段数是 1、2 或 3
  （530 套 dump：186 / 326 / 18；3 段的是 `cstm-0119` 全系列与 `hski-0070/0071/0074`、
  `kcna-0131/0132`、`fktn-0071`，多出来的段是腰环、胸前小件这类零碎）。贴图只按**作者网格
  真正用到的段**出，空段保留原版材质——它在 mod mesh 里是 0 面片，不可见。0.9.3 之前按目标
  段数逐段要图，没做 co 的工程会被空着的段 1 拽去要 co 的 t0，报「材质槽 1 缺少 t0」。
- `m_bdyco` 当前按 cutout 使用最可靠；不要把中间 alpha 视作可连续混合的半透明。

最终原则：

**不要自造透明；body 镂空/cutout 复用游戏已经存在的 `m_bdyco`。**
