# PC IL2CPP `.gmim` runtime mesh replacement research

更新：2026-06-30 · 场景：`yuika.gmim` 运行时替换 `ttmr-cstm-0003` 的 `Geo_Body`

## 0. 当前结论

PC IL2CPP 注入路线已经证明：**可以把外部模型的顶点、法线、UV、分材质三角和按骨名权重带进游戏内**，
前提是运行时把 `.gmim` 的骨名权重重映射到当前活体 `SkinnedMeshRenderer.bones[]` 的骨序。

已实机确认：

- `yuika.gmim` 可在主线程创建 Unity `Mesh` 并装回目标 `Geo_Body`。
- 外部模型跟随游戏动作，骨名覆盖 `124/124` 时没有权重 fallback。
- 目标服装 `ttmr-cstm-0003` 的 `Geo_Body` 是正确替换目标：`verts=20278`、`submeshes=1`、`bones=140`。
- `yuika.gmim` 的 `30672 verts / 11 submeshes / 124 bones` 装入后可见，`tris=33598`。
- 当前剩余问题主要是**材质/贴图注入**，不是坐标、权重、bindpose 或动画。

这条路线与 3DMigoto inverse-skin 主线不同：它不从 D3D 抓帧重蒙皮，而是在 Unity/IL2CPP 层直接替换
`SkinnedMeshRenderer.sharedMesh`。它适合继续研究“游戏内真实 Mesh 替换”能力，但还不是插件主线。

## 1. 运行时 `.gmim` 数据契约

`.gmim` 当前承担一个轻量外部模型容器：

- 顶点、法线、UV；
- 多 submesh 的 triangle index；
- 骨名列表；
- 每顶点最多 4 个骨权重，权重按 `.gmim` 骨名索引存储。

运行时加载后执行：

1. 读取活体 `SkinnedMeshRenderer.bones[]`，用 `Transform.name` 建 `boneName -> liveIndex`。
2. 读取 `.gmim` 骨名，把每个顶点权重从 `.gmim` 骨序重映射到当前服装骨序。
3. 当前服装缺失的骨，权重 fallback 到 `Hips`，防止顶点飞掉。
4. `bindposes` 直接复用原 `Geo_Body.sharedMesh.bindposes`，天然匹配活体骨序。
5. 主线程创建新 Unity `Mesh`：`set_vertices`、`set_normals`、`set_uv`、`set_boneWeights`、
   `set_bindposes`、`set_subMeshCount`、`SetTriangles(int[], submesh)`。
6. 装回目标 `SkinnedMeshRenderer.sharedMesh`。

当前实测正确目标无 fallback：

```text
[mesh] loaded D:\Games\gakumas\yuika.gmim: verts=30672 submeshes=11 bones=124
[pick] selected Geo_Body ... verts=20278 submeshes=1 bones=140 match=124/124
[mesh] fallback vertices: full=0 partial=0 fallbackWeight=0.0
[mesh] DONE assigned real mesh=... to renderer=...
[probe] renderer='Geo_Body' mesh='(?)' verts=30672 submeshes=11 tris=33598 bones=140 bindposes=140
```

## 2. 目标 `ttmr-cstm-0003` 识别

先从 3DMigoto 导出的 `mr` 目录确认 profile：

- `C:\Users\10725\Desktop\mr\manifest.json`
- `profile`: `frame-FrameAnalysis-2026-06-29-065048-body-5b34da41`
- `conflicts`: `ttmr.cstm-0003.body.mesh`
- `mod.ini`: `[TextureOverrideMrBody] hash = 5b34da41`

因此这次 PC IL2CPP 替换目标是 `mdl_chr_ttmr-cstm-0003_body`。

AssetStudio 直接解包命令：

```powershell
& "D:\GIT\AssetStudio-net10.0-win\AssetStudio.CLI.exe" `
  "D:\GIT\Gakuen-idolmaster-ab-decrypt\output\asset_bundle\other\mdl_chr_ttmr-cstm-0003_body" `
  "D:\GIT\gakumas-modding\build\assetstudio-ttmr-cstm-0003-json" `
  --game Normal `
  --unity_version 6000.0.67f1 `
  --export_type JSON `
  --types Mesh Material Texture2D SkinnedMeshRenderer GameObject Transform MonoBehaviour `
  --group_assets ByType
```

AssetStudio 对 `SkinnedMeshRenderer` 有一次 EOF 读取错误，但 `Mesh`、`Material`、`Texture2D`
已成功导出，不影响当前材质/网格判断。

导出结果：

- `Mesh/Geo_Body.json`
- `Material/m_bdy.json`
- `Texture2D/t_chr_ttmr-cstm-0003_bdy_col.json`
- `Texture2D/t_chr_ttmr-cstm-0003_bdy_def.json`
- `Texture2D/t_chr_ttmr-cstm-0003_bdy_rma.json`
- `Texture2D/t_chr_ttmr-cstm-0003_bdy_sdw.json`
- `Texture2D/t_chr_ttmr-base-0000_rmp.json`

`Geo_Body.json` 关键字段：

```text
m_SubMeshes[0].indexCount = 76584
m_SubMeshes[0].vertexCount = 20278
m_VertexCount = 20278
m_Name = Geo_Body
```

这与运行时 probe 的目标完全一致：

```text
[probe] renderer='Geo_Body' mesh='Geo_Body' verts=20278 submeshes=1 bones=140 bindposes=140  <== BODY
```

## 3. 材质和贴图事实

`Material/m_bdy.json` 显示原材质名是 `m_bdy`。重要结论：**`mainTexture` 为空是正常现象**，
这套 shader 不靠 `Material.mainTexture`，而是靠命名 `TexEnv`。

`m_bdy` 的有效贴图属性：

| Unity material property | Texture2D |
|---|---|
| `_BaseMap` | `t_chr_ttmr-cstm-0003_bdy_col` |
| `_DefMap` | `t_chr_ttmr-cstm-0003_bdy_def` |
| `_RampAddMap` | `t_chr_ttmr-cstm-0003_bdy_rma` |
| `_RampMap` | `t_chr_ttmr-base-0000_rmp` |
| `_ShadeMap` | `t_chr_ttmr-cstm-0003_bdy_sdw` |

因此运行时不能只看 `get_mainTexture()`，应优先探测 `_BaseMap`。

3DMigoto `mr` 导出侧的贴图槽也吻合：

| 语义 | D3D slot | 文件 |
|---|---|---|
| BaseColor | `ps-t0` | `Textures/Body.BaseColor.dds` |
| PackedMask | `ps-t1` | `Textures/Body.PackedMask.dds` |
| ShadeColor | `ps-t4` | `Textures/Body.ShadeColor.dds` |

### 3.1 真正镂空参考：`fktn-cstm-0001`

先前把 `ttmr-cstm-0003_body` 当成镂空参考是误判。它只有 `m_bdy`，`bdy_col` 的 alpha
基本全是 254/255，没有真实透明信息。

`C:\Users\10725\Desktop\fktn-cstm-001` 才有真实 body cutout 对照：

| Material | `_BaseMap` | 关键状态 |
|---|---|---|
| `m_bdy` | `t_chr_fktn-cstm-0001_bdy_col` | `_ShaderType=0`, `_Cull=2` |
| `m_bdyco` | `t_chr_fktn-cstm-0001_bdyco_col_alp` | `_ShaderType=1`, `_Cull=0` |

`t_chr_fktn-cstm-0001_bdyco_col_alp.png` 的 alpha 分布约为：

- alpha 0：377266 像素；
- alpha 1-253：194291 像素；
- alpha 254：97569 像素；
- alpha 255：379450 像素；
- alpha < 254 合计约 54.5%。

OBJ 也能看到 `Geo_Body_0` / `Geo_Body_1` 两段，说明真实资产是通过 body + body-co
两个材质/子网格表达镂空，而不是单一 `m_bdy` 上打开标准 Unity `_AlphaClip`。

`EnableCutout()` 把材质切到更接近 `m_bdyco` 的状态：`_ShaderType=1`、`_Cull=0`、
`_AlphaClip=0`、`_Cutoff=<author>`。

### 已实现：per-submesh 材质拆分（2026-06-30）

之前的硬伤是 `EnsureSharedMaterials` 把 11 个 submesh 槽**全填同一个 base 材质**，并直接对
base 调 `EnableCutout` → 整个身体都变镂空态。现已改为复刻真实资产的 `m_bdy + m_bdyco` 拆分：

1. **`.gmim` 升到 ver=3**，每个 submesh 带 `mode`（0=不透明 / 1=镂空co）+ `cutoff`。
   `export_gmim.py` 按材质槽的 `gmi_alpha_mode`（NATIVE_CO/CO，与主插件同一标记）、
   `--cutout-materials` CLI、或材质名含 `bdyco` 判定 mode。
2. **DLL 按 mode 装配 `sharedMaterials`**：不透明 submesh → base `m_bdy`（不动，保持
   `_ShaderType=0`）；镂空 submesh → `CloneCutoutMaterial()` 克隆 base 后只在**克隆**上
   `EnableCutout(cutoff)`。atlas 先 in-place 贴到 base，克隆继承贴图。

这样两条路线（3DMigoto 原生co / IL2CPP cutout submesh）由**同一个 Blender 材质标记**
`gmi_alpha_mode = NATIVE_CO` 驱动。

下一轮 F8 后理想日志：

```text
[mesh] loaded ...: ... cutoutSubmeshes=N (ver=3)
[mesh] cloned cutout material base=... clone=... cutoff=0.330
[mesh] build sharedMaterials: 1 -> 11 (opaque=base cutout=0x... cutoutSubs=N atlasInPlace=1)
```

**仍是经验未知**：`_ShaderType=1` 这套状态在 Campus shader 上是否真产生 alpha discard，
要 F8 实测。若仍不透明，再 dump 一个真实 `m_bdyco` 实例的材质状态逐项对齐（`DumpMaterial`）。

## 4. 已踩坑

### 4.1 目标 renderer 选择

同一画面会有多个 `Geo_Body`，不能按第一个名字匹配。当前选择策略：

- 读取 `.gmim` 骨名；
- 枚举所有 `Geo_Body` 候选；
- 对每个候选计算 `.gmim` 骨名在该 renderer `bones[]` 中的覆盖率；
- 选择覆盖率最高者，当前正确目标是 `match=124/124`。

### 4.2 submesh 与材质槽

目标 `ttmr-cstm-0003` 原身体是 `submeshes=1`，但 `yuika.gmim` 是 `submeshes=11`。

已验证两种策略：

- 合并 11 个 submesh 到 1 个 submesh：几何完整出现，说明 mesh/skinning/bindpose/坐标链路正确。
- 扩展 `sharedMaterials` 到 11 个槽并重复原材质：几何也能显示，能保留 `.gmim` 的 submesh 拆分。

当前代码采用第二种，日志：

```text
[mesh] expand sharedMaterials: 1 -> 11 (duplicate existing materials, atlasInPlace=0)
[mesh] step: subMeshCount=11 + SetTriangles (target original submeshes=1, materialsReady=1)
```

### 4.3 贴图替换崩溃

直接创建新 `Texture2D` 并替换材质贴图指针曾经导致游戏崩溃。参考
`D:\chinosk6\gkms-local\app\src\main\cpp\GakumasLocalify` 后确认更稳的路线是：

- 用 `Texture2D(2, 2)` 创建纹理；
- 通过 `UnityEngine.ImageConversion.LoadImage(Texture2D, Byte[], bool markNonReadable)` 填充 PNG bytes；
- 优先对原材质已有 texture 做 in-place `LoadImage`，少换对象指针。

### 4.4 Unity material 方法重载

`Material.HasProperty/GetTexture/SetTexture` 同时有 `string` 与 `int propertyID` 重载。
只用 `il2cpp_class_get_method_from_name(name, argc)` 可能拿错重载。当前日志出现过：

```text
[tex] material has no usable mainTexture: ...; probing shader texture properties
[tex] HasProperty(_BaseMap)=0
[tex] HasProperty(_DefMap)=0
...
```

这与 AssetStudio 的 `m_bdy.json` 矛盾，推断为重载解析错误或运行时材质实例不是导出态 `m_bdy`。

当前修正方向：

- 解析 `Shader.PropertyToID(string)`；
- 优先用 `Material.HasProperty(int)`、`GetTexture(int)`、`SetTexture(int, Texture)`；
- 用 `il2cpp_class_get_methods` + 参数类型名精确选择 `String` / `Int32` 版本；
- string 版本仅作 fallback。

下一轮启动日志应关注：

```text
[resolve] HasProperty(System.Int32) -> ...
[resolve] GetTexture(System.Int32) -> ...
[resolve] SetTexture(System.Int32) -> ...
[resolve] PropertyToID(System.String) -> ...
[tex] String Has/Get/Set=...  ID Has/Get/Set=...
```

按 F8 后理想日志：

```text
[tex] PropertyToID(_BaseMap)=...
[tex] HasPropertyID(_BaseMap/...)=1
[tex] GetTextureID(_BaseMap/...) -> ...
[tex] LoadImage OK texture=...
[tex] atlas applied in-place via _BaseMap
```

## 5. 当前状态

| 模块 | 状态 |
|---|---|
| PC xinput 注入 | 可加载，日志输出正常 |
| IL2CPP 类型/方法解析 | 可用，正在加强重载解析 |
| 目标 body 选择 | 已按骨名覆盖率稳定选中 |
| `.gmim` 读取 | 可用 |
| 骨名权重重映射 | 可用，当前 `124/124` 覆盖 |
| bindpose 处理 | 复用原 `Geo_Body`，实机可动 |
| 多 submesh 写入 | 可用 |
| 材质槽扩展 | 可用 |
| atlas 贴图注入 | 已可通过 `_BaseMap` property ID 路径替换 |
| 透明/cutout | per-submesh 材质拆分已实现（.gmim ver=3 + 克隆 m_bdyco 材质）；`_ShaderType=1` 是否真 discard 待 F8 实测 |

## 6. 与“直接带外部权重进游戏”的关系

可以直接带进游戏的不是“任意外部 rig 的权重”，而是满足以下条件的权重：

- 权重绑定的骨名能映射到当前活体 `bones[]`；
- bindpose 与当前活体骨架兼容，或运行时复用当前目标 bindposes；
- 外部模型本身的坐标、尺度、姿态已对齐到当前角色空间；
- 缺失骨要有明确 fallback 策略。

`yuika.gmim` 这轮能动，是因为采用“骨名重映射 + 目标 bindpose 复用”。这不等价于异游戏 rip
原权重天然可用；异 rig/bindpose 仍然会爆炸。对 Blender 插件主线而言，智能传权仍是更可靠的作者流程。
