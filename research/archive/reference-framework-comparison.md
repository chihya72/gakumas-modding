# 同类 Model Importer 实现对照与 Gakumas 路线修正

日期：2026-06-22

> **状态更新（2026-06-22 晚）**：本文前半部分记录的是矩阵恢复成功前的调查
> 阶段，其中“尚未在 GPU 侧定位骨骼矩阵”和“下一次只回答矩阵是否存在”等描述
> 已被后续实验取代。GakumasMI 已能从最终 CPU-skinned VB 反解 152 个矩阵，并
> 用 Compute Shader 正确重建原 HSKI Body 和驱动任意拓扑。最新结论与路线见
> [current-status-and-roadmap.md](../current-status-and-roadmap.md) 和
> [inverse-skin-matrix-recovery.md](../inverse-skin-matrix-recovery.md)。保留本文原文是为了
> 记录当时证据与路线转折。

## 结论

GIMI、WWMI、SRMI、EFMI 并不是在最终 DrawCall 上用同一种办法替换任意动画模型。它们能完整换模的共同条件是：在 GPU 管线中能够取得未蒙皮顶点、骨骼权重和骨骼矩阵，并在游戏蒙皮之前替换输入，或拦截游戏的 Compute Skinning 后重新计算输出。

当前 Gakumas Body DrawCall 的 `VB0` 是 Unity 每帧上传的、已经完成蒙皮的动态缓冲。它只有最终 position/normal/tangent，不含 bone index/weight；所以直接照搬 GIMI 的 `vb0/vb1` 替换，或在最终 VS 中替换静态 T Pose，都不会自动获得动画。

这并不表示 Gakumas 不能实现 Blender-only Mod 流程。产品约束已经固定：不使用 AssetBundle，不要求 Unity，也不依赖 IL2CPP Runtime 换模。Gakumas 的可行 GPU 路线是把游戏每帧生成的最终动画 Body VB 当作驱动表面，在 3Dmigoto Compute Shader 中将 Blender 网格映射到该动画表面，生成与原版一致的 40-byte VB，再交回游戏原版 VS/PS 绘制。

## 参考项目的真实切入点

### EFMI（Arknights: Endfield）

- 导出器按组件区分 GPU posed 与 CPU posed。
- GPU posed 组件替换 IB、VB0、VB1、VB2，并重新发起 `drawindexedinstanced`。
- 官方模板对 CPU posed 组件明确写着：`Component is posed on CPU, vertex buffers modding not supported`；这种组件只能 `draw = from_caller`。
- 因此“EFMI 支持完整换模”不能直接推出它已经解决 Gakumas 当前这种 CPU-skinned DrawCall。

证据：

- `EFMI-Tools/efmi-tools/templates/per_component.ini.j2` 第 164–227 行。
- `migoto_object_builder.py` 第 356–358 行把非 `gpu_posed` 角色组件标为 `cpu_posed`。

上游仓库：<https://github.com/SpectrumQT/EFMI-Tools>、<https://github.com/SpectrumQT/EFMI-Package>

### GIMI（Genshin Impact）

- Blender 导出器生成分离的 Position、Blend、Texcoord 与 IB 缓冲。
- 典型绑定是 Position→`vb0`、Blend→`vb1`，并由游戏原有 GPU skinning VS 使用这些权重和游戏骨骼数据。
- 导出器自身不从“最终已蒙皮 VB”反推每帧骨骼；它利用的是游戏本来就暴露在 DrawCall 输入端的未蒙皮流。

证据：

- `Tools/blender_3dmigoto_gimi.py` 第 1819–1835 行生成 Position/Blend/Texcoord 资源及绑定。

上游仓库：<https://github.com/SilentNightSound/GI-Model-Importer>

### WWMI（Wuthering Waves）

- 替换 Position、Vector、Texcoord、Color、Blend 和 Index Buffer。
- 从 `vs-cb3/vs-cb4` 捕获骨骼常量缓冲，通过 `SkeletonMerger.hlsl` 合并多组件骨骼。
- 当顶点组编号变化时，通过 `BlendRemapper.hlsl` 与 `SkeletonRemapper.hlsl` 同步重映射权重和骨骼矩阵。
- 最终把自定义 Blend Buffer 和合并后的骨骼 CB 重新绑定到原 VS，让原渲染材质继续工作。

证据：

- `WWMI-Tools/wwmi-tools/templates/merged.ini.j2` 第 122–225、289–332、354–405 行。
- `WWMI-Package/WWMI/Core/WWMI/Shaders/` 中的 `SkeletonMerger.hlsl`、`SkeletonRemapper.hlsl`、`BlendRemapper.hlsl`。

上游仓库：<https://github.com/SpectrumQT/WWMI-Tools>、<https://github.com/SpectrumQT/WWMI-Package>

### SRMI（Honkai: Star Rail）

- 直接拦截游戏 Compute Skinning shader。
- 从游戏 CS 槽取得 skinning matrix（例如 `cs-t2/cs-t10`）。
- 自定义 `MultiSkinning*VG.hlsl` 读取自定义 T Pose position/normal/tangent、Blend weight/index 和游戏矩阵，输出每帧蒙皮后的 40-byte 顶点流。
- 这是与 Gakumas 最接近的参考算法，但前提仍是骨骼矩阵存在于可拦截的 GPU SRV。当前 Gakumas 抓帧尚未发现对应 Compute Skinning 调用。

证据：

- `SRMI/Core/SRMI/BatchedPose.ini` 的 ShaderOverride 与 `ResourceSkinningMatrix = ref cs-t*`。
- `SRMI/Core/SRMI/Shaders/MultiSkinning4VG.hlsl` 对 position/normal/tangent 的四权重矩阵蒙皮实现。

上游仓库：<https://github.com/SpectrumQT/SRMI-Package>

### ZZMI（Zenless Zone Zero）

公开仓库主要分发打包后的 3Dmigoto ZIP 与工具脚本，核心配置没有像 EFMI/WWMI/SRMI 一样以易审计源码形式展开。本阶段不根据项目名或用户体验臆测其蒙皮实现；后续从实际 Mod 包和帧捕获验证它使用的是分离 GPU 顶点流、Compute Skinning，还是定制 3Dmigoto 分支。

上游仓库：<https://github.com/leotorrez/ZZ-Model-Importer>

## 与 Gakumas 当前证据的对照

| 条件 | GIMI | WWMI | SRMI | EFMI CPU posed | Gakumas Body 当前状态 |
|---|---:|---:|---:|---:|---:|
| Draw 前可替换未蒙皮 Position | 是 | 是 | 是 | 否 | 尚未发现 |
| Draw 前可替换 Blend weight/index | 是 | 是 | 是 | 否 | 最终 VB0 中不存在 |
| GPU 可见骨骼矩阵 | 是 | 是，VS CB | 是，CS SRV | 不适用 | 尚未在 3Dmigoto 帧中定位 |
| 最终 Draw 输入已蒙皮 | 否 | 否 | CS 输出后是 | 是 | 是 |
| 单靠最终 DrawCall 可新增动画顶点 | 是 | 是 | 是 | 否 | 否 |

已确认的 Gakumas Body 数据：

- 原始 Unity Mesh：17,615 vertices、74,664 indices、152 个加权骨骼，含 bind pose 与每顶点四骨骼权重。
- Draw 输入：40-byte stride 的动态 VB0，内容为已变形 position/normal/tangent。
- 3Dmigoto 可读取并替换最终 VB0，也可替换 IB；但这发生在 Unity CPU skinning 之后。
- 因而 IB 缺面实验会保持动画，静态 T Pose VB 替换则不会被游戏重新蒙皮。
- 对 `FrameAnalysis-2026-06-22-012851` 的调用日志复核显示：Body 主 Draw 为调用 `000342`；该调用前没有游戏 Compute Skinning dispatch。日志中的 `Dispatch(276,1,1)` 来自我们自己的 `SurfaceDriveCompute`，不是游戏蒙皮。Body Draw 只绑定最终 VB 并执行 `DrawIndexedInstanced(74664,1,0,0,0)`。

## 修正后的实施顺序

1. 保持当前原版 VS/原版 VB/IB 控制组，不再继续 Surface Map 材质实验。
2. 用 3Dmigoto 帧日志搜索 Body Draw 之前是否存在可关联的 skinning CS、bone matrix SRV/CB 或 GraphicsBuffer 上传。
3. 若找到 GPU 骨骼矩阵：移植 SRMI 的 Compute Skinning 模式，输入由 Blender 导出的 T Pose + Blend，输出与游戏一致的 40-byte 动态 VB0。
4. 若 GPU 侧没有骨骼矩阵：使用已经验证可读取的最终动画 Body VB，执行 surface/cage deformation；不转向 AssetBundle 或 IL2CPP Runtime。
5. Compute Shader 输出自定义 40-byte VB0，随后绑定自定义 VB0/VB1/IB，但保留游戏原版 VS/PS，避免替换 VS 造成的扁平材质与语义丢失。
6. Blender 插件自动生成 surface map、VB/IB、贴图和 INI；Mod 作者只需要 Blender。
7. 最后处理映射质量、离体服装、额外骨骼、BlendShape 和布料等边界。

## 当前首要判定点

下一次抓帧分析只回答一个问题：**Gakumas 的当前角色姿态矩阵是否曾以 D3D11 CB/SRV 的形式出现在 Body Draw 之前？**

- 若是：优先采用 SRMI/WWMI 类 GPU 路线。
- 若否：采用最终动画 VB 驱动的 GPU surface/cage deformation。该路线仍由 3Dmigoto + Blender 插件完成，不引入 Unity、AssetBundle 或进程内 Runtime。
