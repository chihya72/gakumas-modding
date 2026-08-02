# PC IL2CPP `.gmim` runtime mesh replacement research

> **状态（2026-08-02）：路线已彻底放弃，探针代码已删除。**
>
> 原实现在 `experiments/pc-il2cpp-proxy/`（`dllmain.cpp` + `export_gmim.py` + CMake），
> 2026-08-02 整体删除，需要时从 git 历史取。删除理由有两条：
>
> 1. **结论已经被 AB 路线吸收。**本文证明的核心命题——「外部模型可以在运行时以真实
>    Unity `Mesh` 装进 `SkinnedMeshRenderer`，由引擎自己蒙皮」——正是 AB bundle 路线
>    在做的事，而 AB 走的是正规资产管线，不需要进程内注入。透明必须严格复用原生
>    `m_bdyco` 这条结论同样已经在 AB 路线上实机复验。
> 2. **文件名与生产 runtime 撞车。**探针产物同样叫 `xinput1_3.dll`，与同级仓库
>    `gakumas-mod-runtime` 的正式产物同名同目录，谁后放谁生效，是个静默事故源。
>
> 下文保留原始记录（研究时点：2026-06-30），**其中「3DMigoto 是正式路线」的定位已经过时**：
> 0.9.0 起插件只做 AB bundle，3DMigoto 只剩抓帧工具。第 4、5 节按当时语境读。
>
> 原文引用的 [`theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md`](theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md)
> 同批取回，其结论部分亦已废弃。

更新：2026-06-30 · 场景：`yuika.gmim` 运行时替换 `fktn-cstm-0001` 的 `Geo_Body`

## 0. 当前结论

PC IL2CPP 注入路线已经证明：**外部模型可以在游戏运行时以真实 Unity `Mesh` 形式装入
`SkinnedMeshRenderer.sharedMesh`**。已验证的数据包括：

- 顶点、法线、UV、顶点 COLOR；
- 多 submesh triangle index；
- 按骨名存储的 top-4 权重；
- 运行时按活体 `SkinnedMeshRenderer.bones[]` 重映射权重；
- 复用原 `Geo_Body` bindposes 后跟随游戏动作。

透明/镂空的决定性结论是：

**必须严格使用游戏原生 `Geo_Body.sharedMaterials[1] = m_bdyco`。**

单独把 `m_bdy` 改成类似透明材质的状态不可行；透明贴图本身有 alpha，但 `m_bdy` 的 shader 路径不把
`_BaseMap.a` 当透明处理，会把透明区域的 RGB 画出来，表现为黑底。导出阶段按 alpha 删除几何也不是
正确方案，它只能删掉少量全透明三角，不能复刻游戏原生材质的透明/镂空行为，也会破坏作者几何。

实机成功日志：

```text
[mesh] loaded D:\Games\gakumas\yuika.gmim: verts=30621 submeshes=11 bones=154 cutoutSubmeshes=6 (ver=3)
[mesh] using Geo_Body material slot[0]=... name='m_bdy (Instance)' (opaque m_bdy)
[tex] SetTextureID OK via _BaseMap id=73
[mesh] using Geo_Body material slot[1]=... name='m_bdyco (Instance)' (real m_bdyco)
[tex] SetTextureID OK via _BaseMap id=73
[mesh] build sharedMaterials: 2 -> 11 (opaque=... cutout=... cutoutSubs=6 atlasBase=1 atlasCutout=1)
[mesh] DONE assigned real mesh=... to renderer=...
[probe] renderer='Geo_Body' mesh='(?)' verts=30621 submeshes=11 tris=33530 bones=166 bindposes=166
```

因此 IL2CPP 路线中透明的最小正确条件是：

1. 目标服装的 `Geo_Body` 必须有原生第二材质槽 `m_bdyco`。
2. `.gmim` 必须记录每个 submesh 的 `opaque / native-co` 标记。
3. 运行时必须把不透明 submesh 分到 `sharedMaterials[0] = m_bdy`。
4. 运行时必须把 native-co submesh 分到 `sharedMaterials[1] = m_bdyco`。
5. 两个材质都要替换 `_BaseMap` 为外部 atlas；不能依赖 `mainTexture`。

## 1. `.gmim` 数据契约

`.gmim` 当前是实验用轻量容器：

- magic `"GMIM"`；
- `ver=3`；
- 顶点、法线、UV、COLOR；
- 骨名列表；
- 每顶点最多 4 个权重，权重索引指向 `.gmim` 骨名表；
- submesh triangle index；
- 每个 submesh 的 `mode`：`0=opaque`，`1=native-co`。

导出端只写“实际有正权重的非 `GMI_` 顶点组”。这解释了为什么
`%USERPROFILE%\Desktop\yuika.blend` 里有更多 vertex groups / armature bones，但
`yuika.gmim` 记录为 `bones=154`：实际被顶点权重引用的骨名就是 154 个。

运行时流程：

1. 读取活体 `SkinnedMeshRenderer.bones[]`，用 `Transform.name` 建 `boneName -> liveIndex`。
2. 把 `.gmim` 权重从导出骨序重映射到当前服装骨序。
3. 缺失骨 fallback 到稳定骨，目前主要落到 `Hips`。
4. `bindposes` 直接复用原 `Geo_Body.sharedMesh.bindposes`。
5. 主线程创建新 Unity `Mesh` 并设置 vertices/normals/uv/colors/boneWeights/bindposes。
6. 设置 `subMeshCount`，逐 submesh 调 `SetTriangles(int[], submesh)`。
7. 按 `.gmim` 的 submesh mode 构造 `sharedMaterials`：`m_bdy` / `m_bdyco`。
8. 装回 `SkinnedMeshRenderer.sharedMesh`。

当前实测目标：

```text
游戏目标 Geo_Body: verts=18041 submeshes=2 bones=166 bindposes=166
yuika.gmim: verts=30621 submeshes=11 bones=154 cutoutSubmeshes=6
骨名命中: 144/154，缺失 10 个 bone_... 辅助骨，1142 个顶点存在部分 fallback
```

## 2. 材质事实

### 2.1 `m_bdy`

`m_bdy` 是普通 body 不透明材质。`mainTexture` 为空是正常现象，贴图通过命名属性绑定：

| Unity material property | 语义 |
|---|---|
| `_BaseMap` | base color |
| `_DefMap` | packed / def |
| `_RampAddMap` | ramp add |
| `_RampMap` | ramp |
| `_ShadeMap` | shade |

运行时必须通过 `Shader.PropertyToID("_BaseMap")` + `Material.SetTexture(int, Texture)` 替换贴图。

### 2.2 `m_bdyco`

`%USERPROFILE%\Desktop\fktn-cstm-001` 是真实 body cutout 对照。它包含：

| Material | `_BaseMap` | 关键状态 |
|---|---|---|
| `m_bdy` | `t_chr_fktn-cstm-0001_bdy_col` | `_ShaderType=0`, `_Cull=2` |
| `m_bdyco` | `t_chr_fktn-cstm-0001_bdyco_col_alp` | `_ShaderType=1`, `_Cull=0` |

`m_bdyco` 不是 Unity 常规 alpha-blend 材质：`_Surface=0`、`_ZWrite=1`、`_SrcBlend=1`、
`_DstBlend=0`。透明/镂空来自游戏自己的 `m_bdyco` shader/state/draw 上下文。

在 IL2CPP 路线里，严格使用 `sharedMaterials[1]` 后透明生效，证明 `m_bdyco` 是必要条件。

## 3. 已排除路线

| 路线 | 实测结果 | 结论 |
|---|---|---|
| 只给 `m_bdy` 换一张带 alpha 的 `_BaseMap` | 透明区显示为黑底 | `m_bdy` 不吃 `_BaseMap.a` |
| 手动把 `m_bdy` 改成类似 `m_bdyco` 的 float/keyword 状态 | 仍不透明或黑底 | 不能复刻原生 `m_bdyco` 的完整 shader/state |
| 自建替代 cutout 材质 | 透明行为不等价 | 不是严格原生 `m_bdyco`，不作为方案 |
| 导出阶段按 alpha 删除透明几何 | 只能删少量全透明三角，无法处理真实材质透明 | 破坏几何，不作为透明方案 |
| 使用 `Geo_Dresscurtain` 作为 body cutout 参考 | 材质属于独立 renderer | 与 `Geo_Body.m_bdyco` 无关 |

这些路线保留为避坑记录。当前唯一正确路径是：**目标 `Geo_Body` 原生双材质槽 +
submesh 分配到真实 `m_bdyco`**。

## 4. IL2CPP 注入路线 vs 3DMigoto 路线

| 维度 | IL2CPP 注入 `.gmim` | 3DMigoto 正式路线 |
|---|---|---|
| 注入层级 | Unity/IL2CPP 层，替换 `SkinnedMeshRenderer.sharedMesh` | D3D draw 层，按 IB/VB/hash 覆盖 |
| 网格形态 | 游戏内真实 Unity `Mesh` | GPU buffer 中的自定义 VB/IB |
| 动画来源 | 直接使用 Unity `bones[]` + bindposes + BoneWeight | 从游戏当前帧 CPU-skinned VB0 逆解矩阵，再 GPU 重蒙皮 |
| 外部权重 | 可直接带入，但必须按骨名映射到活体骨序；缺骨需要 fallback | 作者模型在 Blender 内转权到目标配置档骨架，再导出 |
| 材质透明 | 必须复用原 renderer 的 `m_bdy / m_bdyco` 槽 | 已采用原生 co material section，并用游戏 `m_bdyco` draw/state 实机验证成功 |
| 贴图 | 可通过 Unity `Material.SetTexture(_BaseMap)` 替换 | 通过 3DMigoto 资源绑定替换 `ps-t0/t1/t4` |
| 调试可见性 | 可枚举 live renderer/bones/materials，日志直观 | 抓帧可精确看到 draw、资源槽、VS/PS、firstIndex |
| 稳定性 | 进程内注入，受 IL2CPP API/Unity 版本/线程约束影响，崩溃风险高 | 不进 Unity 进程逻辑层，符合现有 mod 注入模型 |
| 打包分发 | 需要 DLL 注入与本地运行时代码 | 普通 3DMigoto mod 包，用户部署成本低 |
| 适合用途 | 研究、验证 Unity 层真实 Mesh 替换能力 | 正式插件主线与用户发布 |

### IL2CPP 路线优势

- 证明了外部模型权重可以在运行时按骨名带进游戏，只要 bindpose/骨序处理正确。
- 能直接观察 `SkinnedMeshRenderer`、`bones[]`、`sharedMaterials`，适合研究游戏内部结构。
- 对 mesh/submesh/material 的实验迭代很快，不必每次走完整 3DMigoto 打包。

### IL2CPP 路线劣势

- 需要进程内 DLL 注入，风险和维护成本高。
- Unity/IL2CPP 方法重载、线程限制、对象生命周期都可能导致崩溃。
- 透明仍不能绕过游戏材质结构，最终也必须严格依赖原生 `m_bdyco`。
- 不适合作为面向普通作者/玩家的正式发布路径。

### 3DMigoto 路线优势

- 已是项目正式闭环：Blender → 3DMigoto → 游戏。
- 不进入 Unity 逻辑层，分发就是普通 mod。
- 抓帧能稳定定位 body 与 native-co 的 draw / firstIndex / texture slots。
- 透明已经通过原生 `m_bdyco` section 实机验证成功，与游戏自己的 shader/state 保持一致。

### 3DMigoto 路线劣势

- 需要逆解每帧矩阵并重蒙皮，算法和配置档生成复杂。
- 依赖抓帧 profile 与 hash/firstIndex，游戏资源结构变动时需要重新生成配置档。
- 对作者而言，权重仍应在 Blender 内转到目标骨架，不能把任意外部 rig 原样当成游戏权重。

## 5. 当前定位

IL2CPP `.gmim` 是**研究路线**：用于理解 Unity 层 Mesh、骨骼、材质槽和原生 `m_bdyco` 行为。

3DMigoto 是**正式路线**：用于插件导出、用户安装、多人分发和长期维护。

IL2CPP 支线的透明结论向 3DMigoto 已验证成功的正式路线收敛：

**不要自造透明；IL2CPP 也必须复用游戏原生 `m_bdyco` 材质段。**

更完整的 TheHerta4/SSMT4、学马 3DMigoto、学马 IL2CPP 层级对比见
[`theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md`](theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md)（同样已废弃结论部分）。
