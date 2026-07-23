# 3Dmigoto 流程 → chinosk6 bundle mod 路线图

> 本文件是完整分步路线图。GakumasMI/Piece 1 代码在本仓 `gakumas_mi/`，改 P1 从那边进。
>
> 文中「详见 work-summary 8.x」指向 `work-summary-2026-07-15.md`——那是过程记录，按
> `research/README.md` 的约定不入库，只在本地未版本化工作区 `D:\GIT\IP\06-ab-route-handoff\docs\`。
> 结论已收敛进本包各文档，正常接手不需要它。

> **进度（2026-07-15）**：Phase 1、2A、2B 均已实现并验证通过。
> - P1（Blender 4.2.7 跑 `export_bundle_source` 算子）+ 2A（Unity 6000.0.67f1 batchmode 产 bundle）：端到端通过；修复了 `rootBone` 硬编码泛化 bug。
> - 2B（`gakumas-modding/tools/patch_unity_bundle.py` UnityPy 模板补丁）：解码 diff 证实与 2A 产物 Mesh/贴图/TextAsset **全等价**（`hmsz_0000_ruinurs_2b.bundle`）。
> - 详见 `work-summary-2026-07-15.md` 第八节 / 8.1。
> - **Phase 3 完成**：908 个模板全建齐并全 R32，统一存放在 `GakumasModeBundle_0119_Build/AssetBundles/Windows`（build 脚本模板路径已改恒 UInt32；`dist/templates` 副本已废弃）。2B 直接 `--template` 指向该目录的 `template_*.bundle`。
> - **2B 覆盖面扩展**：真实 mod（madoka 泳装 body，65796 顶点 / 原 9 材质）走通免 Unity 2B。补了三块——R32 模板（破 65535 顶点上限）、P1 材质归并 `core.merge_material_groups`（9→1 submesh，按目标 bdy/bdyco 归并+校验）、2B `_tex_key` 属性名归一化。详见 work-summary 8.2。
> - **✅ 游戏内验证通过**：madoka body（泳装 v9，65796 顶点 / 原 9 材质）经免 Unity 2B 链在游戏里渲染正确。修了骨序对齐 bug（2B `_reorder_smr_bones`：模板 prefab `m_Bones` 按 sidecar 拓扑序重排，否则插件无损嫁接失配→跳过换网格）。**免 Unity 2B 链（Blender→R32 模板→UnityPy→游戏）首次端到端贯通。** 详见 work-summary 8.3。
> - **✅ 游戏内验证通过：hair/hairprop**：使用 madoka `发型doing.blend` 测试 `mdl_chr_ttmr-hair-0002_hair`，`Geo_Hair` 与 `Geo_HairProp` 均完成 2B 替换；日志为 `matchedBones=81`、`meshApplied=2`、`textureApplied=2`、`skippedMeshes=0`。另修复 hair 颜色贴图误绑定：`t0=Hair21_D`、`t1=Hair21_MSK`、`t4=Hair21_SDW`。详见 work-summary 8.4。
> - **✅ Phase 4（物理骨）已跑通（2026-07-17）**：runtime 路线成立，**不需要 option A**。
>   「只建 1 层」是误诊：`UpdateChainInfo` 会排除每条链的最后一根，而我们的 sidecar 缺链尾
>   tip（无蒙皮权重→不在 `m_Bones`），于是真正该摆的那根被当 tip 排除了。补齐 tip +
>   每骨摆动参数后，层数由游戏自己建对，插件不干预 layers。
>   详见 [`physics-bones-findings.md`](physics-bones-findings.md)。

**目标**:让现有 3Dmigoto/GakumasMI 换装作者，以最小成本产出 `hmsz_0000_ruinurs.bundle` 那样的结果——原生蒙皮、正确描边/透明、专属骨骼与物理——**且开发者侧不装 Unity**。

**给接手的新人**:先读本文件第 0 节（契约）再动手。每个 Phase 都有「做什么 / 具体步骤 / 复用哪段现成代码 / 完成判据（怎么验证）」。按 Phase 顺序推进，每个 Phase 的验证 oracle 就是它已经跑通的上游产物。

---

## 0. 契约：三段，看懂这段就懂全局

```
[数据]  geojson + bones sidecar + PNG + mod.json      ← 全部可无 Unity 产出
   │
[打包]  → .bundle (Mesh + prefab骨架 + Texture2D + TextAsset)   ← 唯一碰 Unity 的一步
   │
[运行时] chinosk6 xinput 插件 hook AssetBundle.LoadAsset          ← 已跑通
         · 按【骨名】匹配 mod 骨 → 原 renderer 活体骨
         · mesh 落到【原 renderer】，保留原材质，只按属性换贴图
         · 缺失骨按 sidecar 新建 GameObject + ActorSwingDynamicBone
```

**三个决定难度的关键事实（读插件源码得出，别忘）**：
1. 插件按 **骨名字符串** 认骨（`ModRuntime.cpp` `GetUnityObjectNameString` / `BuildBoneNameIndexMap`），**不看 `m_BoneNameHashes`**。→ bundle 里 prefab 的骨 Transform 只要**名字对、顺序对**，TRS 无所谓。
2. mesh 被 clone 后设到**原 body 的 renderer**上，`replaceMaterials:false` 保留原材质，贴图按 `mod.json` 的 `property` 逐槽替换。→ bundle 里的材质是占位。
3. 顶点空间由插件 `TransformModMeshVerticesToOriginalRendererSpace` + bindpose 空间修正处理。→ mesh 可以在 mod prefab 自己空间里，不用预对齐。

**权威参考文件**（新人必看）：
- 打包契约 / geojson schema：`GakumasModeBundle_0119_Build/Assets/Editor/BuildGakumasModBundleRuiNurs0000.cs`
- manifest schema：`GakumasModeBundle_0119_Build/Assets/Mods/hmsz_0000/mod.json`
- 运行时消费：`plugin/ModRuntime.cpp`（`LoadIpBoneSidecar` 1235、`BuildHybridBoneArray` 1301、`PatchModMeshSkinningLosslessly` 1518、`...ToOriginalOrder` 1593）
- 现有数据侧样板（per-mod 硬编码，要泛化的对象）：`D:\GIT\gakumas-modding\ai-model-workspace\rui-nurs-hmsz-0000\scripts\process_geo_body.py`
- Unity 版本：**6000.0.67f1**（bundle 头写死，必须匹配游戏运行时）

---

## Phase 1 — Piece 1：GakumasMI「导出 bundle 源」算子

**做什么**：在 GakumasMI 加一个导出算子，从它**已有的**内存数据吐出 `<mod>/bundle-src/` 目录：`*.geojson.txt` + `*_bones.json.txt` + `*.png` + `mod.json`。不新增算法，只是把现有数据换个 schema 序列化。

**fork 点（关键）**：`D:\GIT\gakumas-modding\gakumas_mi\operators.py:1021–1110` —— 这里已经把
```
vertices, normals, tangents, uv0, uv1, colors, skin, faces, materials
```
装配进 `data` dict（1110 行），**紧接着**才走 `_inverse_skin_export_data`(913) → `write_inverse_skin_package`。新算子在拿到这份 `data` 后**分叉**：不走逆蒙皮，直接序列化成 geojson。

### 步骤

1. **写 geojson 序列化器**，字段名**必须**和 build 脚本的 `Geo` 类一致（`JsonUtility` 按名反序列化）：
   | geojson 字段 | 来源（operators.py 的 data） |
   |---|---|
   | `m_VertexCount` | `len(data["vertices"])` |
   | `m_Vertices`（扁平 3/顶点） | `data["vertices"]` |
   | `m_Normals`（3/顶点） | `data["normals"]` |
   | `m_Tangents`（4/顶点） | `data["tangents"]` |
   | `m_UV0`（2/顶点） | `data["uv0"]` |
   | `m_Colors`（4/顶点，**打包描边字节**） | `data["colors"]`（见步骤 3） |
   | `m_Indices` | 由 `data["faces"]` 展平 |
   | `m_Skin[{weight[4],boneIndex[4]}]` | `data["skin"]`（每顶点 top-4） |
   | `m_BindPose[{M00..M33}]` | 骨架 bindpose（见步骤 2） |
   | `m_SubMeshes[{indexCount,firstVertex,vertexCount,firstByte,baseVertex}]` | 材质分段（`data["materials"]`） |

   ⚠️ **保留一个已验证的怪点别去"修"**：build 脚本 `mesh.indexFormat = UInt32` 但 `m_SubMeshes.firstByte/2`（R16 偏移）取三角形起点。rui-nurs 就这么跑通的，照抄。

2. **bones sidecar**：复用 `core.py` 的 `build_bone_name_hierarchy_template`(1210) + `_synthesize_skeleton_from_mesh`(1254)，已产出 `{name, parentIndex, localPosition, localRotation, localScale}`。bindpose 从 mesh 取（core.py:1197 已有）。
   **双消费者，输出 superset**：build 脚本只读 `{index, name}`，插件 `LoadIpBoneSidecar` 读 `{name, parentIndex, localPosition, localRotation, localScale}` → 每条同时含这些字段即可。

3. **COLOR**：复用 `_synthesize_export_native_colors`(operators.py:701)，**不要**把 `process_geo_body.py` 的硬编码 COLOR 逻辑搬过来。产出的打包字节写进 `m_Colors`。

4. **贴图**：GakumasMI 已产 t0/t1/t4（`core.write_rgba8_dds`）。这里改成或额外导 PNG（`Image.save`）。**t1（`_DefMap`）必须线性**——这个约束打包时才生效（见 Phase 2），Piece 1 只需正确导出像素。

5. **mod.json**：按基础 body 填模板（参考 `Assets/Mods/hmsz_0000/mod.json`）：`source`=目标 body 资源名、`renderers` 映射（`Geo_Body`→`Geo_Body`）、`textures` 属性表（slot0 `_BaseMap/_DefMap/_ShadeMap`、slot1 同 co）、`replaceMaterials:false`、`skeleton`=sidecar 路径。

### 完成判据（oracle）
用泛化后的算子跑 rui-nurs，产物 `bundle-src/` 逐字段 diff 现有手工产物 `Assets/Mods/hmsz_0000/*`（geojson、bones、6 张贴图、mod.json）。**能复现 = Piece 1 成立**。顺手把 `process_geo_body.py` 的权重 reparent + COLOR 逻辑合进 GakumasMI 通用代码，删掉 per-mod 硬编码。

---

## Phase 2 — Piece 2：把 bundle-src 打成 .bundle

分两步：**2A 先用 Unity 当 oracle 跑通**，**2B 再做开发者侧的无 Unity 补丁工具**。2A 的产物是 2B 的验证基准。

### 2A — headless Unity build（当参照系，不是最终交付）
**做什么**：把 `BuildGakumasModBundleRuiNurs0000.cs` 的写死路径参数化成 `BuildGakumasModBundle(modRoot)`，命令行跑：
```
Unity.exe -batchmode -quit -projectPath <工程> -executeMethod BuildGakumasModBundle.BuildFromArg -modRoot <path>
```
`ConfigureTextures()` 里 t1→线性/其余 sRGB/不压缩/可读的逻辑保留。
**完成判据**：吃 Phase 1 产物 → 出 bundle → 进游戏经插件加载 = 复现当前 rui-nurs 效果。

### 2B — UnityPy 模板补丁（开发者侧最终交付，无 Unity）
**做什么**：拿一个模板 bundle（Phase 3 产；开发 2B 期间先用现成 `hmsz_0000_ruinurs.bundle`），用 UnityPy **原地覆写数据**，不重建结构。

### 步骤
1. `UnityPy.load(template.bundle)`，遍历 objects。
2. **Mesh**：`read_typetree()` → 覆写 `m_VertexData`（顶点流按模板**现有** `m_Channels/m_Streams` 布局打包 pos/normal/tangent/uv0/**color32**）、`m_IndexBuffer`+`m_SubMeshes`、`m_BindPose`、`m_Skin`(boneWeights) → `save_typetree()`。
   ⚠️ **唯一硬活**：顶点流打包必须匹配模板通道布局。**读模板 mesh 的现有 channel layout，只换值不改结构**。UnityPy 写 mesh 别扭就换 **AssetsTools.NET(C#)**（造/改 asset 更成熟）。
3. **Texture2D**：`Texture2D.set_image(PIL)` 覆写；确认 t1 是线性（模板已是则继承）。
4. `env.file.save()` 写出 bundle。

### 完成判据（oracle）
**同一份 Phase 1 输入**，分别用 2A(Unity) 和 2B(UnityPy) 出两个 bundle，进游戏 A/B 对比应**渲染一致**。一致 = 2B 成立，**同骨架换装从此不再需要 Unity**，2A 退居 Phase 3/4 内部工具。

---

## Phase 3 — 全套 template.bundle

**做什么**：为开发者会用到的每个**基础 body** 各产一个模板 bundle，让开发者按 body-ID 取模板做补丁，永不碰 Unity。同骨架下**一个模板覆盖该 body 的所有服装**。

> **状态（2026-07-15）**：已完成扩展版 Phase 3。共生成 530 个 body + 378 个 hair 模板（hair 包含 `Geo_Hair`/`Geo_HairProp` 多 renderer），产物位于 `D:\GIT\gakumas-modding\dist\templates`，`manifest.json` 共 908 项。生成工具为 `D:\GIT\gakumas-modding\tools\build_phase3_templates.py`。

### 步骤
1. 列出要支持的基础 body（服装 ID 清单）。
2. 每个 body 用它**自己未改的** AssetStudio 导出产 geojson+skeleton——复用现成 `D:\GIT\gakumas-modding\tools\export_all_body_json.py`（`--mesh-name Geo_Body --skeleton`，输出 `Geo_Body.json` + `Geo_Body.skeleton.json`）。
3. 对每个 body 跑一次 2A → 得 `template_<bodyid>.bundle`，打到项目 `dist/`（见 gakumas-modding 记忆：打包一律进 dist/）。
4. 写一个 `templates/manifest.json`：`{ bodyId: templateBundlePath }`，2B 工具按 mod.json 的 `source` 选模板。

### 完成判据
「恒等补丁」测试：拿某 body 的模板，用**它自己的** mesh+贴图跑 2B 补丁 → 进游戏该 body 渲染**无变化**。说明模板结构正确、补丁无损。

---

## Phase 4 — 成型：新增物理骨骼

> **✅ 2026-07-17 翻案跑通（覆盖本节旧结论）**：1 层墙真因不是集成入口失败，而是导出侧两处
> 数据缺口——链尾 tip 骨（走 `extraSwingBones` 段）+ 每骨摆动参数（从源 bundle typetree 读出）。
> 补齐后 `UpdateChainInfo` 自己就建对层数，翅膀/裙摆/缎带/听诊器实机真摆。权威记录见
> [`physics-bones-findings.md`](physics-bones-findings.md) §9。**以下 4a/4b 为翻案前记录，仅存证。**

**做什么**：支持**加新骨 + 物理**的服装（护士服听诊器/裙摆）。拆两个独立子问题。

### 4a. 打包侧：bundle 授权组件（加载能力已证）
- 插件 `PatchModMeshSkinningLosslessly`(ModRuntime.cpp:1518) 要求 `sidecarBones.size() == modBones` 且逐序名字匹配 → mod prefab 的 `SMR.bones` **必须含全部骨（含新增的 11 根）**为命名 Transform，且 `m_BindPose` 数量对齐。
- **结构实现仍有两条**：
  - **过渡**：这类服装单独跑 2A（Unity），模板就带全套骨。
  - **终态**：2B/UnityPy **结构级插骨**——向 bundle 追加 GameObject+Transform 对象、扩 `SMR.m_Bones` 的 PPtr 数组、扩 Mesh bindpose、写富 sidecar TextAsset。有界但比纯覆写麻烦。
- asmdef 探针已证明 il2cpp 可完整反序列化 `ActorSwingChain/DynamicBone`、`rootBones` 和参数;
  这只是加载能力,不代表角色初始化可接受后挂子树。
- Piece 1 若未来重启,sidecar 仍需带新骨 `parentIndex/localTRS` + 物理参数（见 4b）。

### 4b. 运行时侧：当前 hook 面已否定
- §5 多角色崩溃已根治;运行时建链也已完成,但 `UpdateChainInfo` 对运行时新骨只建 1 层。
- option A live attach 能按 sharedMesh 精确命中 hmsz,并在 `RegisterBones` 前补入
  `3 dynamicBones + 1 chain`;原生函数随后因 initializeData 并行表长度错位抛
  `ArgumentOutOfRangeException`。
- **禁止重复**:修改共享 prefab、返回运行时 clone、在 `RegisterBones` 时追加 List。
- **未来唯一合理入口**:在 `CampusActorAnimationInitializeData` 构建之前让授权骨子树已存在,
  或由游戏直接实例化包含 mesh/骨/组件的完整合法服装 prefab。没有该入口证据前不投 2B 结构插骨。

### 完成判据
未来重启时:完整合法角色能正常加载,授权探针 `ChainInfo.layers>1`,听诊器/裙摆正常摆动,
且其他角色不受影响。当前完成判据**未达成**,产品行为为专属新骨静态跟骨。

---

## 附:仓库地图（新人导航）

| 用途 | 路径 |
|---|---|
| Piece 1 改这里（GakumasMI 算子/核心） | `D:\GIT\gakumas-modding\gakumas_mi\operators.py`、`core.py` |
| Piece 1 fork 点（数据装配） | `operators.py:1021–1110` |
| COLOR / 骨架合成（复用） | `operators.py:701`、`core.py:1210/1254` |
| 基础 body 导出（Phase 3） | `D:\GIT\gakumas-modding\tools\export_all_body_json.py` |
| 数据侧硬编码样板（泛化对象，然后删） | `...\ai-model-workspace\rui-nurs-hmsz-0000\scripts\process_geo_body.py` |
| 打包 oracle（2A / Phase 3） | `...\06-ab-route-handoff\GakumasModeBundle_0119_Build\Assets\Editor\BuildGakumasModBundleRuiNurs0000.cs` |
| geojson / mod.json schema 真相 | 同上 build 脚本 + `Assets\Mods\hmsz_0000\mod.json` |
| 运行时插件 | `...\06-ab-route-handoff\plugin\ModRuntime.cpp`（源 `D:\GIT\git.chinosk6.cn\gkms-localify-dmm\src\GakumasModPlugin\ModRuntime.cpp`） |
| 当前进度 / 未决项 | `...\06-ab-route-handoff\docs\work-summary-2026-07-15.md` |

## 分工与开发者成本（复述目标）
- **工具作者**：Phase 1/2B 工具 + Phase 3 模板（用 Unity，一次性/每 body 一次）。
- **mod 开发者**：Blender 前期流程**不变** → 新按钮「导出 bundle 源」→ 跑 UnityPy 补丁脚本（**无 Unity**）→ 装 chinosk6 插件替代 3Dmigoto（一次性）。
- **顺序**:Phase 1 + 2A 先打通闭环(今天可做,零序列化风险)→ 2B 消灭 Unity → Phase 3 铺模板 → Phase 4 啃物理。
