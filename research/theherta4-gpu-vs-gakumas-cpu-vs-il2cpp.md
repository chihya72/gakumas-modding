# TheHerta4 / Gakumas 3DMigoto / Gakumas IL2CPP 能力边界对比

更新：2026-06-30

参考远端：

- TheHerta4: https://github.com/StarBobis/TheHerta4
  - 检查 commit: `0fad2974e9303a34aa5820c4edc18be030fa4ece`
  - 日期：2026-06-24 23:20:43 +0800
  - 提交：`添加ZZMI的DX12格式Mod生成支持`
- SSMT4-Alpha: https://github.com/StarBobis/SSMT4-Alpha
  - 检查 commit: `14d468e564820b5e74ee28f6cf924e4a68a847ee`
  - 日期：2026-06-13 06:26:24 +0800

## 0. 结论先行

TheHerta4/SSMT4 的能力强在 **GPU 图形管线可见的模型资源替换**：导入/导出
`POSITION / NORMAL / TANGENT / TEXCOORD / COLOR / BLENDINDICES / BLENDWEIGHT`
等 D3D vertex buffer 语义，生成 3DMigoto/SSMT 可用的 `.buf`、`.ib`、贴图资源和 `.ini`
override。

这套能力在米哈游系 GPU skinning 或 GPU-pre-skinning 游戏里非常强，因为 3DMigoto 能接触到：

- 原始或接近原始的 mesh vertex input；
- `BLENDINDICES / BLENDWEIGHT`；
- skeleton / bone matrix 常量缓冲或资源；
- vertex limit raise；
- submesh / component draw；
- material texture slots。

学马当前 3DMigoto 路线遇到的根本差异是：**学马角色 body 是 CPU skinning 结果进入 D3D draw**。3DMigoto
抓到的是已经被游戏 CPU 蒙皮后的动态 VB0，而不是带骨权重的原始 mesh 输入。因此 3DMigoto 层不能像
TheHerta4/WWMI 那样直接把外部模型自己的 `BLENDINDICES / BLENDWEIGHT` 塞进游戏 shader 让它继续蒙皮。

IL2CPP 路线的真正价值不是透明材质，而是它进入了 Unity 逻辑层：可以替换
`SkinnedMeshRenderer.sharedMesh`，直接提交 Unity `BoneWeight[]`、`bindposes`、`subMeshCount` 和
`sharedMaterials`。因此它是目前唯一能在学马里接近“直接使用外部模型自身权重”的路线。

但 IL2CPP 不会自动让 mod 更简单。它把 3DMigoto 的抓帧/逆解/导出复杂度，换成了进程内注入、IL2CPP
API、Unity 对象生命周期、骨名/骨序/bindpose 兼容、材质槽复用等复杂度。

## 1. 三条路线所在层级

| 路线 | 入口层级 | 看到的数据 | 写回的数据 | 典型能力 |
|---|---|---|---|---|
| 米哈游系 TheHerta4/SSMT4/WWMI/ZZMI | D3D/3DMigoto 图形资源层 | 原始或可替换的 VB/IB、Blend buffer、Skeleton buffer、Texture slots | `.buf/.ib/.ini` 资源 override | GPU 层换模型、换权重、换贴图、骨架资源重映射、shape key |
| 学马 3DMigoto 正式路线 | D3D/3DMigoto 图形资源层，但输入已 CPU-skinned | 当前帧已蒙皮后的动态 VB0、IB、材质 draw/state | 自定义最终 VB/IB、贴图、native-co draw | 逆解矩阵后 GPU 重蒙皮；正式打包分发；透明已通过原生 `m_bdyco` 验证 |
| 学马 IL2CPP `.gmim` 研究路线 | Unity/IL2CPP 对象层 | `SkinnedMeshRenderer`、`bones[]`、`bindposes`、`sharedMaterials`、Unity Mesh API | 新 Unity `Mesh`、`BoneWeight[]`、submesh、材质槽、贴图 | 运行时真实 Mesh 替换；可按骨名带入外部权重；研究底层行为 |

这三者不是“谁更高级”的单线关系，而是入口层级不同。TheHerta4 的强项要求图形管线暴露足够多的
pre-skin 或 skinning 相关资源；学马 3DMigoto 的问题正是这些资源在 draw 时已经被 CPU 消化掉了。

## 2. TheHerta4 具体做了什么

远端代码中，TheHerta4 是 Blender addon，核心工作是围绕 SSMT4 workspace 做导入、编辑、导出。

### 2.1 导入

`SubmeshJson` 描述一个 submesh 的 D3D 数据：

- `GamePreset`
- `WorkGameType`
- `GPU-PreSkinning`
- `VertexLimitVB`
- `CSOutputVertexLimitVB`
- `CategoryHash`
- `CategoryDrawCategoryMap`
- `BoneMatrixFileName`
- `VGMap`
- `CategoryBufferList`
- `IndexBufferList`
- `TextureMarkUpInfoList`

导入时读取 `.buf/.ib`，按 `D3D11ElementList` 解析语义。遇到 `BLENDINDICES` 和
`BLENDWEIGHT/BLENDWEIGHTS` 时，创建 Blender vertex groups。WWMI merged 模式还会用 `VGMap` 把 local
blend index 映射为 global bone ID。

这说明 TheHerta4 的“骨骼权重”本质上是 D3D buffer 语义和 Blender 顶点组之间的互转，不是 Unity
`SkinnedMeshRenderer.bones[]` 语义。

### 2.2 导出

导出时从 Blender mesh 读取顶点、loop、UV、COLOR、顶点组，重新打包成目标游戏的 D3D layout：

- `POSITION`
- `NORMAL`
- `TANGENT`
- `COLOR`
- `TEXCOORD`
- `BLENDINDICES`
- `BLENDWEIGHT`

`ObjBufferHelper` 会根据 `D3D11GameType` 把顶点组转换成目标格式，例如：

- `R8G8B8A8_UINT`
- `R16_UINT`
- `R32G32B32A32_UINT`
- `R8_UNORM`
- `R16G16B16A16_UNORM`
- `R32G32B32A32_FLOAT`

导出结果不是 Unity mesh，而是 3DMigoto/SSMT 资源：

- category `.buf`
- index `.buf/.ib`
- texture resources
- `TextureOverrideVB`
- `TextureOverrideIB`
- `TextureOverrideVertexLimitRaise`
- `ResourceBuffer`
- `ResourceSkeletonOverride`
- `CommandList...`
- shape key / blend remap / skeleton remap 相关 resource

### 2.3 米哈游系权重为何能“直接带进去”

在 WWMI 路线里，代码会显式处理：

- `ResourceBlendBuffer`
- `ResourceMergedSkeleton`
- `ResourceExtraMergedSkeleton`
- `CommandListMergeSkeleton`
- `CommandListRemapMergedSkeleton`
- `SkeletonMerger`
- `SkeletonRemapper`
- `BlendRemapper`
- `vs-cb3 / vs-cb4`
- `vb4`

也就是说，它能改权重，是因为目标游戏的 draw/shader 层真的存在可替换的 blend buffer 与 skeleton
buffer。外部模型的 vertex groups 被导成 `BLENDINDICES / BLENDWEIGHT` 后，游戏或 WWMI 的 GPU 路径会继续
使用这些数据。

这和学马 3DMigoto 抓到 CPU-skinned VB0 的情况不同。学马 draw 层没有可供 3DMigoto 正常接管的
`BoneWeight[]` 或 Unity `bones[]`。

## 3. 学马 3DMigoto 正式路线的边界

### 3.1 已经成立的能力

- 正式 Blender 插件导出。
- 3DMigoto 普通 mod 包部署。
- 任意拓扑 mesh 的最终 GPU 绘制。
- 通过原始 body profile 逆解当前帧骨骼矩阵。
- 在 GPU 侧对外部 mesh 做重蒙皮，写成学马当前 draw 能吃的最终 VB。
- 透明/镂空已通过原生 `m_bdyco` material section 实机验证，效果正确。
- 贴图可以走原生 material section 的 texture slots。

### 3.2 本质限制

学马 3DMigoto 路线看不到 Unity 层：

- 看不到 `SkinnedMeshRenderer.bones[]`；
- 看不到 Unity `BoneWeight[]`；
- 不能替换 `sharedMesh`；
- 不能让游戏 CPU skinning 重新处理外部模型；
- 不能把外部模型原始权重原样交给游戏内部动画系统。

因此，学马 3DMigoto 的“权重”必须在插件/导出链内转成它自己 GPU 重蒙皮可以使用的数据。也就是：

1. Blender 里把作者模型权重转到目标配置档骨架；
2. 导出外部 mesh 顶点、权重、贴图、submesh；
3. 游戏内由 3DMigoto 使用逆解出的每帧矩阵重蒙皮；
4. 输出最终 D3D draw 能吃的 VB。

这条路线很聪明，也适合正式发布，但它不会变成 TheHerta4/WWMI 那种“直接交给游戏 GPU skinning”的模型。

## 4. 学马 IL2CPP `.gmim` 路线的边界

### 4.1 已经实验证明的能力

IL2CPP 支线已经实机证明：

- 可以按 F8 找到正确 `Geo_Body`；
- 可以在主线程创建 Unity `Mesh`；
- 可以设置 vertices / normals / uv / colors；
- 可以设置 `BoneWeight[]`；
- 可以复用目标 `Geo_Body.sharedMesh.bindposes`；
- 可以设置多个 submesh 的 triangles；
- 可以把新 mesh 装回 `SkinnedMeshRenderer.sharedMesh`；
- 可以按 `.gmim` 骨名映射到 live `bones[]`；
- 可以同时使用 `m_bdy` 与真实 `m_bdyco` 两个原生材质槽；
- 可以给两个材质槽替换 `_BaseMap` atlas；
- 透明在严格使用真实 `m_bdyco` 后已经生效。

### 4.2 它为什么能接近“外部模型自身权重”

因为 `.gmim` 记录的是按骨名保存的权重，运行时能读取 live renderer 的 `bones[]`：

1. `.gmim` 骨名表：外部模型权重引用的骨名。
2. live `bones[]`：当前服装实际用于 skinning 的 Unity Transform 数组。
3. `boneName -> liveIndex`：运行时映射。
4. `BoneWeight.boneIndex0..3`：重写成当前服装骨序。
5. `bindposes`：先复用原 `Geo_Body`，保证索引语义对齐。

如果外部模型本身就是按学马同名骨架绑定，并且 rest pose / bindpose 与目标 renderer 兼容，那么 IL2CPP
路线确实可以比 3DMigoto 更直接：不需要把权重烘到 3DMigoto 自己的重蒙皮管线里，而是让 Unity 的
`SkinnedMeshRenderer` 继续处理。

### 4.3 它不能自动解决的问题

IL2CPP 能带入外部权重，不等于任意外部权重都可用。

仍然必须满足：

- 骨名能映射；
- 骨语义相同；
- rest pose / bindpose 坐标空间相容；
- 缺失骨要有明确 fallback；
- 权重引用的骨不能大量落到 `Hips`；
- mesh 坐标转换正确；
- normals/tangents/COLOR/UV 与 shader 预期一致；
- submesh 的 opaque / `m_bdyco` 分配正确；
- 目标服装必须本来就有可复用的原生材质槽。

当前实测里，`yuika.gmim` 有 `154` 个实际权重骨，目标 `Geo_Body` 有 `166` 根 live bones，但命中
`144/154`，缺失 `10` 个 `bone_...` 辅助骨。这说明“骨数量看起来接近”不等于“权重完全兼容”。如果缺失骨权重
影响明显，仍然会有局部塌陷、飞点或动作异常。

### 4.4 IL2CPP 的主要风险

- 进程内注入，崩溃直接影响游戏。
- Unity/IL2CPP method pointer、重载、GC、对象生命周期都需要逐项处理。
- 主线程约束严格。
- 游戏更新后 API layout、shader property、renderer 结构可能变化。
- 打包分发比 3DMigoto mod 困难。
- 普通作者/玩家安装成本高。
- 多 mod 共存、卸载、热重载、异常恢复都需要额外工程。

## 5. 透明材质的定位

透明问题已经不应再作为“路线优劣”的核心争论。

事实是：

- 3DMigoto 正式路线已经采用原生 `m_bdyco` material section，并实机验证效果正确。
- IL2CPP 支线也证明必须严格复用 `Geo_Body.sharedMaterials[1] = m_bdyco`。
- `m_bdy` 即使使用带 alpha 的 `_BaseMap`，也不会正确透明。
- 手动改 `m_bdy` 状态、普通替代材质、导出阶段按 alpha 删除几何，都不是可行路线。

因此透明结论对两条路线是一致的：

**不要自造透明，必须复用游戏原生 `m_bdyco` 绘制路径。**

## 6. 能力边界对照

| 能力 | 米哈游系 TheHerta4/SSMT4 | 学马 3DMigoto 正式路线 | 学马 IL2CPP `.gmim` |
|---|---|---|---|
| 替换 mesh 拓扑 | 强，导出 VB/IB | 强，正式路线已实现 | 强，Unity Mesh 已验证 |
| 使用外部模型原始权重 | 在 GPU skinning 资源可见时强 | 不能原样交给游戏，需要转到本项目重蒙皮数据 | 有潜力直接使用，前提是骨名/bindpose/坐标空间兼容 |
| 读取 Unity `bones[]` | 不能 | 不能 | 可以 |
| 替换 Unity `sharedMesh` | 不能 | 不能 | 可以 |
| 复用游戏 CPU skinning | 不适用或取决于游戏 | 不能，抓到的是 CPU skinning 之后 | 可以 |
| GPU skeleton/bone buffer remap | 强，WWMI 重点能力 | 学马 draw 层缺少同等入口 | 不走 D3D skeleton buffer |
| 每帧动作来源 | 游戏 GPU/compute skinning 资源 | 逆解 CPU-skinned VB0 得到矩阵 | Unity `SkinnedMeshRenderer` 原生 skinning |
| 透明材质 | 依赖目标游戏 draw/material section | 已用原生 `m_bdyco` 成功 | 必须复用真实 `m_bdyco` |
| 作者工作流 | 成熟，米系社区标准 | 当前正式目标 | 研究性，仍需工程化 |
| 玩家分发 | 普通 3DMigoto/XXMI 包 | 普通 3DMigoto 包 | DLL 注入，门槛高 |
| 稳定性 | 取决于游戏更新和 hash | 相对可控，贴近现有 mod 生态 | 风险最高，崩溃面最大 |

## 7. 战略判断

如果目标是“正式发布、普通玩家安装、社区作者可复用”，学马 3DMigoto 仍然应该是主线。它已经证明透明、
贴图、最终绘制和插件链路可闭环。

如果目标是“验证更底层能力、直接利用外部模型本身权重、绕过 CPU-skinned VB0 逆解的根本限制”，IL2CPP
路线值得继续。它是当前唯一能进入 Unity `SkinnedMeshRenderer` 层的路线，也是唯一能真正尝试
“外部权重按骨名进游戏”的路线。

但如果问“采用 IL2CPP 模式是不是一定能做出更简单、效果更好、渲染更还原的 mod”，结论要分开说：

- **更简单**：对普通玩家和正式发布不更简单。对研究者可能更直接，因为能看见 `bones[]` 和 Unity Mesh。
- **效果更好**：有潜力，特别是外部权重与目标骨架高度一致时，可以避免 3DMigoto 后处理层的逆解误差。
- **渲染更还原**：只有在严格复用原生 `m_bdy/m_bdyco`、正确 submesh 分配、正确 COLOR/UV/贴图通道时才更还原。
- **权重更还原**：IL2CPP 的潜力最大，因为它可以提交真实 Unity `BoneWeight[]`。但前提是骨名、bindpose、坐标空间都对。

最终建议：

1. 3DMigoto 继续作为正式路线。
2. IL2CPP 继续作为研究路线，重点验证“按骨名直接带权重”的稳定性，而不是再探索自建透明。
3. IL2CPP 进入下一阶段前，需要建立验收标准：
   - 多服装稳定定位目标 `Geo_Body`；
   - `m_bdy/m_bdyco` 材质槽自动识别；
   - 骨名缺失报告和权重影响统计；
   - bindpose 兼容性检查；
   - atlas/secondary map/COLOR/tangent 验证；
   - unload/restore 不崩溃；
   - 同一场景多角色不误替换。

一句话总结：

**TheHerta4 的成功来自米哈游系 GPU skinning 资源在 3DMigoto 层可见；学马 3DMigoto 的难点来自 CPU
skinning 后才进入 draw；IL2CPP 是学马里唯一能绕回 Unity skinning 前的数据层的路线，但它是研究和工程风险更高的路线，不是天然更易发布的路线。**
