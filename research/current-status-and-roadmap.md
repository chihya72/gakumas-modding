# GakumasMI 当前进度、同类工具对比与后续计划

更新时间：2026-06-25  
当前状态：**单 t0 身体的 Blender → 3DMigoto Mod → 游戏(换模 + 动画 + 贴图 + 多 mod 共存)
完整闭环已达成并发布 v0.5.0**,已在跨服装实机验证。

> **2026-06-25(v0.5.0）现状速览（以本块为准，下方旧章节为历史过程记录）**
>
> 已打通并发布:
> - **一键完整配置档**：抓帧目录 + Body JSON 资源库（+ 角色代号）→ 注入信息 / 结构数据 / 逆算子；
>   全部 body 可用（无 Unity 骨架时从 `m_BoneNameHashes` + `m_BindPose` 合成骨架）。
> - **逆解蒙皮导出**：任意拓扑跟随游戏动画，跨服装（TTMR→hmsz）实机跑通。
> - **贴图**：基础色 PNG 自动转 DDS；「中性 t1/t4」去除原版遮罩/阴影对新贴图的干扰。
> - **分材质烘焙 t1/t4（0.5.0）**：按 Blender 材质槽逐材质烘焙遮罩/阴影，预设（皮肤珊瑚阴影、
>   哑光皮革、织物、金属…）由实机抓帧逐材质实测；每材质可用「明暗 / 阴影色」微调。专为
>   自定义 atlas / MMD 等**无游戏 t1/t4 来源**的模型还原游戏观感。
> - **注入**：mod.ini 改为 **IB-only 触发**，多个 body mod 共存零冲突警告。
> - **运行时**：`3Dmigoto-MI`（dev 配置 + 按键文档；二进制不入库）。
>
> 完成度(工具视角):内核 ~92% · 贴图材质 ~80% · 健壮性/回归 ~55% · 产品化 ~45%。
>
> 已确认边界:**学马所有 body 都是单 t0**,工具的单 t0 模型与游戏结构一致——多材质身体导出
> **不需要**(MMD 移植版出现多贴图属作者侧问题,应在 Blender 里合成单图)。
>
> 后续工具缺口(单 t0 前提):①**回归测试 + 冻结**(本链已踩过多个导出/格式 bug,需上自动回归
> 防回退);② 多组件(脸/头发/饰品,各自也是单 t0);③ 分材质预设细化(目前皮肤/布料/皮鞋/金属
> 等已由抓帧实测,后续多抓几套服装继续校准,见 [`material_presets.json`](../blender_addon/gakumas_mi/material_presets.json));
> ④ Mod Manager / 玩家发布配置。

> **2026-06-24 架构锁定与清理**：项目已锁定为「**AssetStudio 静态结构 + 逆解每帧
> 矩阵（C）+ 3DMigoto 注入**」这一条主线（即路线 B+C）。本次清理从代码树移除了
> 以下已排除路线（均可从 git 历史恢复）：
>
> - **表面驱动 / SurfaceMap 路线**：删除 `core.write_surface_package`、
>   `_pack_surface_buffers`、`GMI_OT_export_surface_mod`、`shaders/SurfaceMappedBody.hlsl`、
>   `shaders/SurfaceDriveCS.hlsl`、`tools/build-tpose-vb0.ps1`。
> - **进程内 IL2CPP Runtime 路线**：删除 `runtime/native/`、`tools/inject-runtime.ps1`。
>   注意这是「进程内替换 Mesh」的运行时，**与玩家侧 3DMigoto Mod Runtime（路线第
>   5 阶段）不是一回事**，后者继续保留。
>
> - **手/颈拆件保留路线（原 P2）**：删除 `GMI_OT_create_native_body_sets` 与
>   `select_native_hand/neck` 操作器、`_create_native_sets_for_obj`、相关 UI 按钮、
>   `tools/build_mesh_region_map.py`。配置档里的 `skinning.regionMap` 字段与
>   `body-regions.json` 成为无用残留，可在下次整理时移除。
>
> 保留的核心：`RecoverMatricesCS`（恢复每帧矩阵）、`SkinCustomCS`（重蒙皮）、
> 逆算子构建与配置档 / 结构数据管线。`Geo_Body.json` 是骨骼 / 权重 / bind pose 的
> 唯一来源；抓帧只用于「取实时 `VB0`」和「取注入 hash」。

## 1. 产品目标与固定边界

作者侧目标流程：

```text
导入目标 Profile 的参考模型/骨架
→ 在 Blender 中制作或放置衣服
→ 将衣服蒙皮到目标 Profile 骨架
→ 一键验证、导出并打包 Mod
```

固定边界：

- 不要求 Mod 作者安装 Unity；
- 不使用 AssetBundle 实现模型替换；
- 不使用进程内 Runtime DLL 替换 Unity Mesh；
- 不修改或替代汉化插件 `version.dll`；
- 玩家侧只需要 GakumasMI/3DMigoto Runtime 与作者导出的 Mod；
- 额外骨骼、布料和物理不是首期目标。

## 2. 已完成且已验证的核心能力

### 2.1 运行环境和 Profile

- 游戏可用 `-force-d3d11` 运行并由 3DMigoto 注入；
- 已定位 HSKI Body 主绘制、阴影、描边和材质贴图槽；
- Profile：`profiles/hski-cstm-0000`；
- Body：17,615 vertices、74,664 indices、152 个加权骨骼；
- Body IB hash：`4d5dfe7b`；
- 动态 VB0 stride：40 bytes。

### 2.2 从最终 CPU 蒙皮 VB 恢复动画矩阵

游戏没有在 Body Draw 前暴露常见的未蒙皮 Position/Blend 输入，也没有发现可直接
复用的 GPU skinning matrix SRV。当前方案使用 AssetStudio 导出的 bind mesh 和
四权重构造逆算子，每帧从游戏最终动态 VB0 恢复 152 个有效 4x3 蒙皮矩阵。

游戏内已验证结果：

- GPU 恢复矩阵相对同帧 CPU/HLSL 模拟 RMS：`1.55e-6`；
- GPU 重建原 HSKI 位置相对游戏动态 VB RMS：`1.14e-6`；
- 最大位置误差：`1.73e-5`；
- Compute 输出与最终 IA VB 逐字节一致；
- 开启同源重建 PoC 时画面与原版一致。

稳定检查点：`checkpoints/2026-06-22_inverse-skin-game-validated`。

### 2.3 任意拓扑 GPU 替换

Blender FBX `mdl_chr_ttmr-cstm-0119_body` 已作为自定义拓扑测试：

- 10,383 个 Blender 顶点；
- 12,587 triangles；
- 按 loop/UV seam 展开为 37,761 个 GPU 顶点；
- 37,761 个有效索引，补齐至原 Body 的 74,664 draw capacity；
- 自定义 VB/IB 能替换 HSKI Body 并跟随当前游戏动画；
- 保留游戏原 VS/PS，不依赖 Unity 或 AssetBundle。

### 2.4 HSKI Body 数据契约审计（2026-06-23）

已新增 `tools/audit_profile.py`，把散落在 Profile、AssetStudio JSON 和 Frame
Analysis 中的结论改为可重复执行的检查。当前审计结果为 **60/60 通过**：

- 17,615 vertices / 74,664 indices / R16 IB；
- VB0 stride 40、VB1 stride 12 的数组长度和格式一致；
- 152 个 Bind Pose 中源网格实际使用 147 根骨骼；
- 5 根 Source Inactive 骨与数值不可辨识的 `RightFrontRibbon1_S` 已分开记录；
- 42,839,680-byte R32 inverse operator 与 Profile 尺寸及 SHA-256 一致；
- Shadow/Main/Outline 三个 Pass 的 VS、PS、DrawIndexed 参数和输入流一致；
- 8 次跨时段抓帧均保持 Body IB 和三个 Pass 的签名不变；
- t0/t1/t4 的捕获文件尺寸、DXGI 格式和槽位均与 Profile 一致。

机器可读结果：

- `profiles/hski-cstm-0000/audit-report.json`
- `profiles/hski-cstm-0000/data-contract.md`

另外已把原 Body 拆为 387 个确定性连通区域，并生成 vertex/triangle region map。
当前自动标出的手/颈区域只是 Blender 中供作者复核的候选，不会自动删除模型：

- `profiles/hski-cstm-0000/body-regions.json`
- `Buffers/BodyVertexRegions.R16_UINT.buf`
- `Buffers/BodyTriangleRegions.R16_UINT.buf`

这已经证明项目最关键的技术命题成立：**Gakumas 的 CPU-skinned Body 仍可通过
3DMigoto Compute 路线驱动 Blender 任意拓扑模型。**

## 3. 当前 HSKI + TTMR 衣服实验状态

TTMR FBX 本身是从外部模型制作后蒙皮到 TTMR 骨架的作者资产。要用于 HSKI，正确
作者流程不是在运行时强行把 TTMR 骨架重定向到 HSKI，而是在 Blender 中把衣服
重新蒙皮到 HSKI Profile 骨架。

当前离线流程：

1. 从 `Geo_Body.json` 导入 HSKI bind mesh、152 骨骼和四权重；
2. 导入并标准化 TTMR FBX 的单位和对象变换；
3. 使用 Blender Data Transfer `POLYINTERP_NEAREST` 从 HSKI Body 向 TTMR 网格传权重；
4. 限制到四影响并归一化；
5. 导出自定义 bind/skin buffer、VB1、IB、Compute Shader 和 INI；
6. 在 Body IB Override 中直接绑定目标材质的 `ps-t0/t1/t4`。

已确认：

- 10,383 个目标顶点全部获得有效 HSKI 权重；
- GPU 展开后每顶点权重和为 1；
- 全身最近表面传权重版本整体稳定，不再发生全屏爆炸；
- 衣服主体、腿部和大部分手臂能跟随 HSKI 动画；
- TTMR UV/贴图可被正确采样。

当前未解决：

- 相邻手指距离太近，最近表面传权重会串指，表现为手指过长或变形；
- TTMR Body 几乎不包含可用颈部（只有 10 个以 `Neck` 为主权重的顶点），缺脖子
  主要是几何缺失，不是单纯权重错误；
- HSKI `t1 PackedMask`、`t4 ShadeColor` 已完成单通道极值实测：`t1` 为
  R=卡通阴影阈值、G=光滑度、B=金属度、A=环境遮蔽/间接光；`t4` 为 RGB=阴影色、
  A=阴影色混合强度。简单复用 BaseColor 或常量 Mask 会造成色偏；
- 目标模型的材质分区、顶点色、法线和 tangent 还没有完整转换；
- 旧的常量 ShadeColor 试验已经由原纹理保留式单通道探针取代，不再作为材质方案。

当前游戏测试状态：

- 启用：`D:\Games\gakumas\Mods\test.ttmr-outfit-on-hski`；
- 使用稳定的全量 HSKI 最近表面权重；
- 失败的运行时骨架重定向、混合权重和语义手指实验均已移入 `DISABLED_*`；
- 当前状态适合作为继续研究的测试基线，不应发布。

## 4. 已排除或失败的路线

这些实验必须保留记录，避免后续重复：

| 实验 | 结果 | 结论 |
|---|---|---|
| 静态 T Pose VB 直接替换 | 不跟随动画 | 游戏 Draw 输入已是 CPU 蒙皮结果 |
| 自定义 VS 重建 SurfaceMap | 几何可见但材质退化 | 应保留游戏原 VS/PS，用 Compute 生成原格式 VB |
| TTMR 骨名直接映射到 HSKI | 大面积错位/拉伸 | 同名不代表 bind pose、层级和辅助骨兼容 |
| 每骨 target→source bind correction | 收敛但仍严重畸变 | 不应作为普通作者的运行时自动 retarget 基础 |
| 保留 TTMR 与 HSKI 同名骨权重 | 再次全屏爆炸 | TTMR 权重属于 TTMR bind rig，不能直接作为 HSKI 权重 |
| 按同名手指分区取最近 HSKI 顶点 | 手指更严重拉长 | 两套手部 bind 几何位置不一致，不能继续自动猜 |
| 只替换 BaseColor | HSKI 图案仍参与着色 | 必须处理 t1/t4 和材质语义 |
| BaseColor 直接复制为 ShadeColor | 整体粉色色偏 | t4 Alpha/通道有专用含义，不能直接复用 |
| 表面驱动 / SurfaceMap 自定义 VS | 几何可见但材质退化 | 应保留游戏原 VS/PS，用逆解矩阵重蒙皮；相关代码已于 2026-06-24 删除 |
| 进程内 IL2CPP Runtime 替换 Mesh | 启动崩溃 / 进程保护 / 违反产品边界 | 改用逆解矩阵；`runtime/native` 已于 2026-06-24 删除 |
| 抓帧反解 T-pose 几何 / 重建骨骼权重 | 数学病态、无中生有 | 结构数据全部来自 `Geo_Body.json` |

## 5. 与主流 Model Importer 工具的差距

### 5.1 主流工具实际承担的职责

- **GIMI**：导入/导出 Position、Blend、Texcoord、IB；作者通常在 Blender 中保留
  原权重或使用 Data Transfer/Weight Paint 完成外部模型蒙皮。导出器主要负责格式化
  数字顶点组和缓冲，而不是任意骨架自动重定向。
- **WWMI**：除完整导入导出外，提供对象合并、顶点组补齐/合并、权重影响中心匹配、
  Blend Remap、Skeleton Merger、Shape Key 和模板化 Mod 导出。Skeleton Merger 处理
  游戏本身提供的组件骨骼矩阵，不负责给外部骨架自动刷出正确权重。
- **EFMI**：提供 Frame Dump 自动提取、LOD 搜索、顶点组匹配、分离 Buffer 导入导出和
  模板化打包；其 README 仍把 Bones Merging 列为计划功能。

上游：

- <https://github.com/SilentNightSound/GI-Model-Importer>
- <https://github.com/SpectrumQT/WWMI-Tools>
- <https://github.com/SpectrumQT/WWMI-Package>
- <https://github.com/SpectrumQT/EFMI-Tools>
- <https://github.com/SpectrumQT/EFMI-Package>

发布包实物中的 Blender 插件 UI、按钮文案、源码模块和作者流程对照见
`research/blender-plugin-ui-reference.md`。

### 5.2 能力对比

| 能力 | GIMI | WWMI | EFMI | GakumasMI 当前 |
|---|---|---|---|---|
| 游戏对象自动提取 | 基础/脚本化 | 完整 | 完整 Frame Dump | HSKI Profile 自洽；Frame Dump 自动建 Profile 待实现；UI 已调整为“提取对象” |
| 原模型与权重导入 | 是 | 是 | 是 | HSKI Body 带权重参考已接入 Blender UI；UI 已调整为“导入对象” |
| 任意拓扑导出 | 是 | 是 | 是 | 已验证 PoC，并接入带权重 GPU 导出入口 |
| 游戏动画驱动 | 原 GPU skinning | CB Skeleton merge/remap | 按组件管线 | 逆算最终 CPU-skinned VB，已验证 |
| 外部模型自动换骨架 | 否，作者处理 | 否，工具辅助 VG | 否，工具辅助 VG | 曾错误尝试，现已排除 |
| 权重传递 UI | 主要用 Blender | 合并/匹配工具较完整 | LOD/VG 匹配 | 已有“蒙皮转权”入口、风险标记和手/颈语义修正，仍需可视化复核工具 |
| 手/颈等原生身体保留 | 作者拆件/合并 | 组件化导出 | 组件化导出 | 已生成 387 区域映射和候选，已有选择集按钮，待合并/保留 UI |
| 材质多贴图语义 | 生态成熟 | 自动收集/模板化 | 自动收集/模板化 | HSKI t0/t1/t4 与通道已验证，已有“材质模板”入口和 DDS 绑定，待节点/PNG→DDS 模板 |
| Shape Key | 社区方案 | 完整支持 | 计划/有限 | 未实现 |
| LOD/多组件 | 作者配置 | 完整 | 自动 LOD | 仅 HSKI Body |
| 一键作者导出 | 成熟 | 成熟 | 成熟 | 核心函数和中文化 UI 可用，仍缺单按钮校验→导出→复制闭环 |
| Validator/兼容提示 | 基础 | 完整 | 完整 | HSKI Profile 60/60 数据契约审计；作者网格验证仍需完善 |

GakumasMI 当前的优势不是作者工具完整度，而是已经解决了主流项目通常不面对的
输入条件：**从最终 CPU-skinned VB 反解矩阵并重新蒙皮自定义拓扑。** 当前最大差距
已经从 GPU 动画算法转移到 Blender 作者体验、身体部件处理和材质转换。

## 6. 后续实施计划

### P0：冻结当前 GPU 核心

- 把矩阵恢复、同源重建和任意拓扑导出加入自动离线测试；
- 固定 HSKI Profile、逆算子 SHA-256、Shader 编译产物和 Buffer layout；
- 将所有实验性骨架 remap 从默认导出路径移除；
- 默认只接受已经蒙皮到当前 Profile 骨架的模型。

验收：同源 HSKI 重建误差保持当前量级，自定义网格不出现 NaN、越界或 draw 冲突。

进度（2026-06-23）：Profile、逆算子、三 Pass、8 次抓帧签名和材质资源描述已纳入
自动审计；`tests/profile_contract_smoke.py` 已通过。HSKI Body 的 t0/t1/t4 槽位、
PackedMask 四通道以及 ShadeColor Alpha 已通过原纹理保留式单通道极值测试。尚需把
GPU 数值误差 fixture 和 Shader 编译产物接入同一测试入口。

### P1：完成标准 Blender 蒙皮工作流

- 插件入口：`导入对象`；
- 插件按钮：`导入带权重参考模型`；
- 插件入口：`蒙皮转权`；
- 插件按钮：`从配置档传递权重`；
- 支持最近面插值、限制四权重、归一化和未加权检查；
- 显示传递距离、截断权重、未映射组和高风险区域热图；
- 明确要求作者在 Blender Weight Paint 中检查宽袖、裙摆、手指等区域；
- 不承诺任意异骨架一键 retarget。

进度（2026-06-23，插件 0.3.4）：上述入口已接入 Blender UI，并已改为中文工作台式
布局；本次只做源码、UI 文案和文档整理，未重新使用用户 Blender 环境做安装测试。
传递后自动限制四权重、
归一化、检查未加权顶点，并生成 `GMI_WEIGHT_RISK` 颜色属性与
`GMI_REVIEW_HIGH_RISK` 顶点组；旧骨组仅用于手指/颈部语义消歧。Blender 4.2.7
headless 测试作为历史记录保留；下一步是用真实 TTMR FBX 进行交互式精修验收。

0.3.2 新增：

- `导入配置档对象`：一键导入抓帧参考、带权重原模型、参考骨架，并建立
  `GMI_ProfileReference` / `GMI_AuthorMesh` / `GMI_Export` 集合；
- `选择高风险顶点`：直接选中 `GMI_REVIEW_HIGH_RISK` 供作者复核；
- `选择原生手部` / `选择原生颈部`：把 HSKI 原生身体候选区域暴露为可见选择；
- `创建身体材质模板`：在 Blender 材质上记录 t0/t1/t4 语义；
- `校验并导出模组`：把校验和导出串成一个主按钮。

0.3.3 新增：

- `更新 Profile 抓帧源`：扫描用户选择的 `FrameAnalysis-*` 目录，递归校验当前
  Profile 所需的 IB/VB0/VB1 与 Body `t0/t1/t4` 贴图资源；
- 支持 3DMigoto 在文件名中省略 VB0 hash 的情况：当 `drawcall_map.json` 能确认
  该 draw/binding 属于目标组件时，使用 draw 编号回退匹配；
- 写出 `profile-capture-update-report.json`，明确列出缺失资源和匹配模式
  `hash` / `drawNumberFallback` / `none`；
- 离线检查 `FrameAnalysis-2026-06-22-105210`：Body IB/VB0/VB1 可识别，VB0 依赖
  draw 编号回退；Body 三张贴图未在该帧 dump 中出现，需要单独贴图抓帧或保留
  既有纹理 Profile。

0.3.4 新增：

- 面板按钮、分组、主要字段、悬浮提示和插件说明同步中文化；
- `Profile / Mod / Body` 等面向作者的词统一改为 `配置档 / 模组 / 身体`；
- 保留 `JSON / DDS / GPU / VB / IB / hash / t0/t1/t4` 等技术缩写，便于与
  3DMigoto 日志和导出文件对照；
- README 与插件源码版本同步到 0.3.4；包含配置档资产的 ZIP 发布包保留在本地
  `dist/gakumas_mi-0.3.4-zh-20260623-204112.zip`，不直接提交到公开仓库。
- 作者界面收敛为主线出口：保留 `校验网格`、`校验并导出模组`、
  `导出带权重 GPU 模组`，移除非主线入口。

0.3.5 新增：

- `从抓帧生成配置档`：从任意 `FrameAnalysis-*` 目录自动扫描 drawcall、IB、VB0/VB1、
  stride、顶点数、索引数和可见 `ps-t*` 贴图槽位；
- 生成 runtime-only 配置档文件：`profile.json`、`drawcall_map.json`、
  `texture_map.json`、`material_map.json`、`extraction-report.json`；
- 自动候选评分：优先选择 IB/VB0/VB1 齐全、符合 Body 常见 `40 + 12` 双 VB 布局、
  索引/顶点规模较大、并且在多个 pass 中重复出现的 draw 组；
- 当同一 Body 资源组存在三个 pass 时，默认选中中间 draw 作为主 pass。真实 HSKI
  抓帧 `FrameAnalysis-2026-06-22-105210` 已自动选中 `Draw 000335`，
  得到 `17615` 顶点 / `74664` 索引，和人工分析一致；
- 新增命令行工具 `tools/extract_frame_profile.py`，支持 `--draw` 强制指定主 Draw；
- 支持 VB0 文件名缺少 hash 的情况：新配置档写入 `resourceFiles`，后续导入抓帧参考时
  可以按文件名兜底读取。

边界：帧数据只能确认运行时 GPU 资源和绑定关系，不能单独还原完整 Unity 骨架名、
权重和 BindPose。因此 0.3.5 生成的配置档标记为 `runtime-only-frame-extracted`；
后续蒙皮转权仍需要 AssetStudio 原模型 JSON 与骨架 JSON 作为权重源。

### P2：身体/衣服拆件与原生皮肤保留

这是当前 HSKI 实验的下一优先级：

1. 根据材质、顶点组和几何区域把目标 FBX 分为衣服与皮肤；
2. 删除目标模型不可靠的手、手指和颈部皮肤；
3. 保留 HSKI 原生手、手指、颈部及其原始权重；
4. 合并 HSKI 皮肤与目标衣服，同时保持总索引不超过 74,664；
5. 为保留皮肤建立独立材质区或正确的目标 UV 映射；
6. 检查接缝、法线、描边和阴影。

验收：张手、握拳、抬手、扭头时手指和颈部无明显拉伸或缺面。

进度（2026-06-23）：已完成原 Body 连通区域映射。下一步不是继续用坐标硬编码删除，
而是在 Blender 中把候选区域建立为可见选择集，让作者确认保留的 HSKI 手/颈，再将
TTMR 对应皮肤区域显式排除。

插件 0.3.2 已可从区域映射生成 `GMI_NATIVE_HAND`（2271 顶点）和
`GMI_NATIVE_NECK`（801 顶点）选择组；实际删除目标皮肤、复制原生几何和接缝合并仍待实现。

### P3：材质 Profile 与贴图打包

- 将已验证的 HSKI `t0/t1/t4` 通道语义固化为 Blender 导出模板；
- 不再用常量猜测 PackedMask；
- 支持作者分别提供 BaseColor/Mask/Shade，或由插件按 Profile 规则生成；
- 在目标 Body IB Override 中直接绑定贴图，避免全局 Shader hash 冲突；
- 支持 FBX 多材质分区和顶点色/材质 selector；
- 正确导出 loop normal、tangent、UV0/UV1。

验收：正背面颜色一致、无原 HSKI 图案串入、描边和受光与原游戏材质一致。

插件 0.3.2 已将可选 BaseColor/PackedMask/ShadeColor 直接绑定进同一个 Body IB
Override，并在导出时强制检查 2048×2048 BC7/色彩空间格式；loop normal 与 tangent
也改为按三角循环实际导出。PNG→DDS 自动转换与多材质 selector 尚待实现。

### P4：把实验脚本产品化为插件

- 将 `tools/reweight_hski_fbx_mod.py` 的可靠部分移入 Blender UI；
- PNG→DDS 转换与 Profile 格式选择自动化；
- 一次导出生成单一 Mod 包，不再生成相互冲突的测试包；
- 自动生成 manifest、INI、Buffers、Textures、报告和预览；
- 导出前阻止未三角化、未归一化、超过容量、未知骨骼等错误；
- 增加干净 Blender 环境的端到端测试和 ZIP 发布流程。

### P5：扩展生态能力

- Profile 制作工具与版本指纹；
- Face、Hair、Accessory 和多 Body 材质组件；
- LOD 与多 Drawcall；
- Shape Key/表情；
- Mod 合并、切换、冲突检测和版本迁移；
- 只有在游戏数据确实提供额外矩阵时，再研究辅助骨/Skeleton merge。

## 7. 下一次恢复工作时的起点

不要继续尝试 TTMR→HSKI 运行时骨架映射，也不要继续猜手指权重。当前恢复点为：

```text
运行 tools/audit_profile.py（当前应为 60/60）
→ 在 Blender 导入 body-regions.json 并复核 HSKI 手/颈候选
→ 识别并移除 TTMR 手/颈皮肤
→ 合入 HSKI 原生手和颈部
→ 再完成 t0/t1/t4 材质语义
```

在此之前，当前游戏包只用于验证技术链，不作为插件质量或最终 Mod 效果展示。
