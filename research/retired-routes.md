# 已排除的三条路线

> 合并自 `3dmigoto-vs-ab-route.md`、`inverse-skin-matrix-recovery.md`、
> `pc-il2cpp-gmim-runtime-replacement.md`、`theherta4-gpu-vs-gakumas-cpu-vs-il2cpp.md`
> （2026-08-02）。四份文档的实现细节交给 git 历史，这里只保留**为什么排除**的论证和
> 仍然成立的硬结论。

本项目最终走 **AB bundle 路线**：把作者网格作为真正的 Unity 资产交给游戏，引擎原生蒙皮。
在此之前认真做过三条别的路线，都跑到过可用程度才放弃。记录它们是为了**别人别重走**。

## 0. 共同前提：学马是 CPU 蒙皮

这条事实决定了后面所有取舍：**角色 body 在 CPU 蒙皮完成之后才进 D3D draw。**

3DMigoto 抓到的 `VB0` 是当前帧已蒙皮的最终顶点（stride 40，Position/Normal/Tangent），
里面**没有 `BLENDINDICES` / `BLENDWEIGHT`**，Draw 的 CB/SRV 里也没有骨骼矩阵。

所以米哈游系那套（GIMI / WWMI / TheHerta4 / SSMT4）**照搬不过来**：它们能改权重，是因为
目标游戏在 draw/shader 层真的存在可替换的 blend buffer 与 skeleton buffer
（`ResourceBlendBuffer` / `ResourceMergedSkeleton` / `CommandListMergeSkeleton` 那一套），
外部模型的顶点组导成 `BLENDINDICES/BLENDWEIGHT` 后由 GPU 继续用。学马这一层是空的。

**这条不会过期**，是当初否掉「照抄 GIMI」的原始依据。

## 1. 3DMigoto 逆蒙皮（做到了实机贯通，0.9.0 整体移除）

### 做法

既然 `VB0` 是标准线性蒙皮的结果，就反解回去：

```text
posed_i = Σ_b ( w_ib · [p_i.x p_i.y p_i.z 1] · M_b )
Y = A·M   →   M = P·Y   →   P = (AᵀA + λI)⁻¹Aᵀ
```

`A`、`P` 只依赖 bind 位置和四权重，离线算一次；每帧 GPU 只做 `P·Y`，恢复出 152 个 4×3
有效蒙皮矩阵，再用它们驱动作者网格重蒙皮。全程只要 Blender 导出数据 + 3DMigoto 能读的
动态 VB + 两个 compute shader，**不需要 AssetBundle、Unity 编辑器或进程内 runtime**。

### 验证到什么程度（`hski-cstm-0000`，17,615 顶点 / 152 加权骨）

- 离线 20% 留出拟合：Position RMS `1.47e-5`；
- 按真实 HLSL 256-lane 顺序模拟：Position RMS `1.39e-6`，Normal/Tangent P95 `0.0198°`；
- **游戏内闭环**（2026-06-22 抓帧）：GPU 重建位置 vs 游戏原动态 VB，RMS `1.14e-6`，
  Max `1.73e-5`，**Compute 输出与最终 IA VB 逐字节一致**，开关实验画面视觉一致；
- 任意拓扑也成立：TTMR 测试 FBX 展开 37,761 GPU 顶点后由恢复矩阵正确驱动。

数值上这条路线是**成功**的。

### 为什么还是放弃

代价不在数学，在工程面：

| 维度 | 代价 |
|---|---|
| 必须传权 | 作者模型得先在 Blender 里把权重转到目标配置档骨架，不能用自己的 |
| 吃 shader 变体 | 贴图按寄存器 `t0/t1/t4` 硬绑，shader 变体一换槽位重排就整体错乱（暗光场景全身变色），得靠运行时全局布局探测才根治 |
| 能力封顶 | 换的是「已蒙好皮的最终几何」，碰不到骨 → **新增物理骨不可能**，摆动只能蹭原网格烘死的动作 |
| 描边要 hack | 新网格缺顶点 COLOR 会被默认白色冲掉 → 没描边，得手动传颜色 |
| 透明要 hack | 透明区 RGB 纯黑被双线性渗色，得 alpha-bleed + 带 alpha 的 DDS |

AB 路线把这些**从根上换成了一次性的打包门槛**：引擎自己蒙皮，描边/透明/贴图/物理全部
原生正确，还解锁新物理骨。换来的代价是锁 Unity 版本、bindpose 正确性由 bundle 保证。

> 逆算子还有一个可观测性限制值得记：设计矩阵 588 个活跃列的数值秩是 585，
> `RightFrontRibbon1_S` 只影响 3 个顶点、总权重 0.048，数值上不可辨识。
> 这个「低权重骨不可观测」的判据保留到了今天——现在叫 `unobservableBones`，
> 由 `summarize_bind_mesh` 从每骨权重和算出。

**3DMigoto 本身没有被放弃**，它现在的唯一角色是抓帧工具（做配置档必须用它抓一帧）。

> **两个 compute shader 去哪了。**`RecoverMatricesCS.hlsl`（反解矩阵）与
> `SkinSourceCS.hlsl`（重蒙皮）原在 `experiments/inverse-skin/`，2026-08-02 随目录删除。
> 需要时从 git 历史取：`git show b991250:experiments/inverse-skin/RecoverMatricesCS.hlsl`。
> 注意它们的头两行把 `SOURCE_VERTEX_COUNT`/`COEFFICIENT_COUNT` 写死在已删除的
> `hski-cstm-0000` 上，不是可直接复用件。

## 2. PC IL2CPP 进程内注入（证明了引擎自蒙皮可行，被 AB 路线取代）

### 做法与结论

`xinput1_3.dll` 代理注入，用 `GameAssembly.dll` 导出的 il2cpp C API 解析类型，
把外部模型作为真实 Unity `Mesh` 装进 `SkinnedMeshRenderer.sharedMesh`。自定义容器
`.gmim` 记录顶点/法线/UV/COLOR、按骨名存的 top-4 权重和每 submesh 的 opaque/native-co 标记；
运行时读活体 `bones[]` 建 `boneName → liveIndex` 映射重排权重，复用原 `Geo_Body` 的 bindposes。

**实机成功**：`yuika.gmim` 30,621 顶点 / 11 submesh / 154 骨，装进 `fktn-cstm-0001` 正常显示、
跟随动画。

### 透明的决定性结论（仍然成立）

**必须严格使用游戏原生 `Geo_Body.sharedMaterials[1] = m_bdyco`。** 已排除的做法：

| 试过的路线 | 实测结果 |
|---|---|
| 只给 `m_bdy` 换一张带 alpha 的 `_BaseMap` | 透明区显示为黑底 —— `m_bdy` 不吃 `_BaseMap.a` |
| 手动把 `m_bdy` 改成类似 `m_bdyco` 的 float/keyword 状态 | 仍不透明或黑底，复刻不出完整 shader/state |
| 自建替代 cutout 材质 | 透明行为不等价 |
| 导出阶段按 alpha 删几何 | 只能删少量全透明三角，且破坏几何 |

`m_bdyco` 不是常规 alpha-blend：`_Surface=0`、`_ZWrite=1`、`_SrcBlend=1`、`_DstBlend=0`、
`_ShaderType=1`、`_Cull=0`，透明来自游戏自己的 shader/state/draw 上下文。

### 为什么放弃

1. **结论已被 AB 路线吸收。**它证明的核心命题——「外部模型可以在运行时以真实 Unity Mesh
   装进 renderer，由引擎自己蒙皮」——正是 AB 路线在做的事，而 AB 走正规资产管线，
   **不需要进程内注入**；
2. **文件名与生产 runtime 撞车。**探针产物同样叫 `xinput1_3.dll`，与 `gakumas-mod-runtime`
   同名同目录，谁后放谁生效；
3. 进程内注入本身风险高：IL2CPP 重载解析、GC、对象生命周期、主线程约束都可能崩游戏，
   分发门槛也远高于普通 mod 包。

> 附一条仍然有用的工程结论：**il2cpp 方法重载必须按参数类型名签名解析**
> （`il2cpp_class_get_methods` + `il2cpp_method_get_param` + `il2cpp_type_get_name`）。
> `il2cpp_class_get_method_from_name(name, argc)` 会取错重载导致静默失败——
> `LoadImage(Texture2D,byte[],bool)` vs `(Texture2D,NativeArray<byte>,bool)` 都是 argc=3。
> 这条对现在的 runtime 仍然适用。

## 3. 结论

| 路线 | 拦截层 | 谁做蒙皮 | 结局 |
|---|---|---|---|
| 米哈游系 GIMI/WWMI | D3D 图形资源层 | 游戏 GPU | **不适用**：学马 draw 层没有 blend/skeleton buffer |
| 3DMigoto 逆蒙皮 | D3D draw（引擎之后） | 没人，几何是烘死的 | 实机贯通后于 0.9.0 移除；保留抓帧用途 |
| PC IL2CPP 注入 | Unity 对象层 | Unity 引擎 | 证明可行后被 AB 取代，代码 2026-08-02 删除 |
| **AB bundle** | **Unity 资产（引擎之前）** | **Unity 引擎** | **当前唯一正式路线** |
