# Blender 插件 UI 参考与 GakumasMI 缺口

记录时间：2026-06-23

本轮范围：只阅读下载下来的参考插件源码、整理 UI/功能对比，并调整 GakumasMI 插件
源码中的中文文案和面板布局；没有启动用户 Blender 环境，也没有执行插件安装测试。

本轮直接下载并解压了上游发布包，而不是只看已有研究笔记：

- GIMI v7.0：`build/reference-plugin-zips/blender_3dmigoto_gimi.py`
- WWMI Tools v1.7.3：`build/reference-plugin-zips/extracted/WWMI-Tools-v1.7.3/WWMI-Tools`
- EFMI Tools v0.4.3：`build/reference-plugin-zips/extracted/EFMI-Tools-v0.4.3/EFMI-Tools`
- ZZMI v1.0 development 包：`build/reference-plugin-zips/extracted/3dmigoto.ZZMI.for.development`

## 1. 上游插件 UI 风格

### GIMI

GIMI 的 Blender 插件是单文件脚本，主要挂在 Blender 顶部菜单：

- `File > Import`
  - `3DMigoto frame analysis dump (vb.txt + ib.txt)`
  - `3DMigoto raw buffers (.vb + .ib)`
  - `Apply 3DMigoto vertex group map to current object (.vgmap)`
  - `3DMigoto pose (.txt)`
- `File > Export`
  - `3DMigoto raw buffers (.vb + .ib)`
  - `Exports Genshin Mod Folder`

它的用词偏底层 3DMigoto：

- Frame Analysis Dump
- Raw Buffers
- Vertex Group Map / vgmap
- Pose / Bone CB
- Vertex group step
- Export mod folder

这套 UI 的特点是“导入/导出文件格式工具”，不是完整工作台。适合作为底层术语参考，但不适合照搬为 GakumasMI 主界面。

### WWMI

WWMI 是完整侧边栏工具，位于 `3D Viewport > Sidebar > WWMI Tools`。核心结构：

- 顶部 `Mode` 下拉：
  - `Extract Objects From Dump`
  - `Import Object`
  - `Export Mod`
  - `Toolbox`
- 每种模式只显示相关字段。
- 导出模式下有子面板：
  - `Advanced`
  - `Mod Info`
  - `Ini Template`
  - `Partial Export`
  - 底部独立 `Export Mod` 按钮。

WWMI 的作者体验重点：

- 从 Frame Dump 自动提取对象；
- 导入对象源目录；
- 按组件集合导出；
- 自动补齐 Vertex Groups 和缺失 Mesh Data；
- Copy Textures；
- Write Mod INI；
- 支持 Mod 名称、作者、描述、链接、Logo；
- 支持 Ini Template 和局部导出。

源码对应关系：

- UI 主入口：`addon/ui.py`
- 模式枚举和导出选项：`addon/settings.py`
- 抓帧提取：`extract_frame_data/`
- Blender 导入：`blender_import/`
- Blender 导出：`blender_export/`
- 底层 3DMigoto 数据模型：`migoto_io/`
- INI 模板：`templates/*.ini.j2`

实际机制不是“作者给一个 FBX，插件自动理解所有东西”。它先从 Frame Dump 生成对象
源数据，然后导入 Blender。作者在 Blender 中围绕这些对象、顶点组和材质继续编辑。
导出时再根据集合、顶点组、贴图和模板生成 Mod。

### EFMI

EFMI 的 UI 与 WWMI 同源，但多了终末地需要的 LOD 提取：

- 顶部 `Mode` 下拉：
  - `Extract Objects From Dump`
  - `Extract LoDs From Dump`
  - `Import Object`
  - `Export Mod`
  - `Toolbox`
- LOD 提取包含：
  - Open World Frame Dump
  - Geo matcher method
  - Error threshold
  - Candidate count
  - VG matcher candidates

EFMI 比 WWMI 更强调“从抓帧中恢复对象结构、LOD、候选匹配”，这部分最接近 GakumasMI 后续要补的 Profile 自动化。

源码对应关系：

- UI 主入口：`addon/ui.py`
- 模式枚举和 LOD/Matcher 参数：`addon/settings.py`
- Frame Dump / LOD 提取：`extract_frame_data/`
- 对象匹配与 Geometry Matcher：`migoto_io/object_extractor/`、`migoto_io/migoto_model/`
- 导入导出和模板：`blender_import/`、`blender_export/`、`templates/`

EFMI 的“自动”主要是自动从抓帧恢复对象、LOD 和组件候选；外部模型的造型、拆件、
Weight Paint、材质贴图准备仍然发生在 Blender 作者工作流里。

### ZZMI

ZZMI v1.0 development 发布包主要是 3DMigoto 运行包，没有找到与 WWMI/EFMI 同级别的 Blender add-on UI。当前阶段不把 ZZMI 作为 Blender UI 主要参考。

## 2. 上游插件怎么导入原模型和权重

### GIMI

GIMI 直接读取 3DMigoto dump 的 `vb/ib/fmt`：

- POSITION / NORMAL / TANGENT / TEXCOORD 等语义转成 Blender mesh 属性；
- BLENDINDICES / BLENDWEIGHT 转成顶点组权重；
- `.vgmap` 用于把游戏里的数字骨骼/顶点组编号映射到 Blender 顶点组；
- 导出时再把 Blender 顶点组写回 BlendIndices/BlendWeights。

所以 GIMI 的“权重导入”来自游戏 GPU Drawcall 暴露的 buffer，不是从外部 FBX 自动
推导，也不是运行时自动换骨架。

### WWMI / EFMI

WWMI/EFMI 把这件事产品化：

1. `Extract Objects From Dump` 从 Frame Dump 找到对象组件；
2. 提取 VB/IB、组件 metadata、纹理和模板所需信息；
3. `Import Object` 把对象源目录导入 Blender；
4. 插件根据对象 metadata 建集合、网格、顶点组、Shape Key/LOD/材质信息；
5. 作者在 Blender 里改模型、合并/拆分对象、修权重、补数据；
6. `Export Mod` 收集集合、贴图、Mod 信息和模板，生成可安装 Mod。

也就是说，成熟插件的核心不是“自动替作者完成所有蒙皮”，而是把对象提取、数据导入、
导出打包、模板和常见修补工具做完整，让作者不必手写 3DMigoto 配置。

## 3. 任意拓扑导出能不能做

可以做，但前提是运行时能把作者网格送进游戏当前动画管线。

主流插件通常依赖游戏原本的 GPU skinning / 骨骼 CB / BlendWeights 管线：

- 作者模型需要带有目标游戏兼容的顶点组和权重；
- 插件负责把这些权重写成游戏期待的 buffer；
- 不保证“外部骨架一键自动转成目标角色骨架”。

GakumasMI 的特殊点是 HSKI Body 输入已经是 CPU-skinned final VB，所以我们不能照搬
普通 GPU skinning 路线。现在已验证的 GakumasMI 路线是：

```text
游戏最终动态 Body VB
→ Compute 反解当前帧骨骼矩阵
→ 作者网格使用 HSKI Profile 权重
→ Compute 重新蒙皮作者任意拓扑网格
→ 输出给原 Body Drawcall
```

因此任意拓扑导出可以做，而且 PoC 已经成立；后续重点是把“作者网格如何获得可靠
HSKI 权重、如何保留手/颈原生身体、如何打包材质”做成插件流程。

## 4. 材质多贴图语义能不能模板化

可以模板化。WWMI/EFMI 已经有类似结构：

- `texture_collector.py` 收集贴图；
- `ini_maker.py` 和 `templates/*.ini.j2` 生成 INI；
- UI 里有 Copy Textures、Ini Template、Mod Info 等导出选项。

GakumasMI 应该采用同类做法，但模板内容必须按 Gakumas/HSKI Profile 来定义：

- t0：BaseColor；
- t1：PackedMask，当前已验证为 R 阴影阈值 / G 光滑 / B 金属 / A AO；
- t4：ShadeColor，RGB 阴影色 / A 混合强度；
- 后续需要把 PNG/TGA 输入、DDS 格式、sRGB/UNORM、BC7/BC4/BC5 等规则写进 Profile
  和 Blender UI。

所以材质模板不是“全局套一个 shader”，而是每个 Profile/组件声明自己有哪些贴图槽、
每个通道含义是什么、导出时如何绑定到对应 TextureOverride。

## 5. GakumasMI 当前 UI 调整

GakumasMI 0.3.x 已改为更接近 WWMI/EFMI 的侧边栏模式：

- 顶部 `模式` 下拉：
  - `提取对象`
  - `导入对象`
  - `蒙皮转权`
  - `导出模组`
  - `材质模板`
- 按钮中文化：
  - `从抓帧生成配置档`
  - `更新配置档抓帧源`
  - `导入配置档对象`
  - `导入抓帧参考模型`
  - `导入带权重参考模型`
  - `生成原生手部 / 颈部选择集`
  - `选择原生手部`
  - `选择原生颈部`
  - `从配置档传递权重`
  - `选择高风险顶点`
  - `校验网格`
  - `校验并导出模组`
  - `导出带权重 GPU 模组`
  - `创建身体材质模板`
  - `导出贴图模组`
- 字段中文化：
  - `配置档目录`
  - `抓帧目录`
  - `新配置档输出`
  - `主 Draw`
  - `原模型 JSON`
  - `骨架 JSON`
  - `风险距离`
  - `修正手指/颈部`
  - `基础色 t0`
  - `混合遮罩 t1`
  - `阴影色 t4`

0.3.2 还补了几个作者流程入口：

- `导入配置档对象`：只选配置档目录和组件，就会同时导入抓帧参考、带权重原模型、
  参考骨架，并建立 `GMI_ProfileReference` / `GMI_AuthorMesh` / `GMI_Export` 集合；
- `选择高风险顶点`：直接选中 `GMI_REVIEW_HIGH_RISK`，让作者进入 Weight Paint 复核；
- `选择原生手部` / `选择原生颈部`：把区域映射候选暴露成可见选择操作；
- `创建身体材质模板`：在 Blender 材质上记录 t0/t1/t4 语义，作为作者预览和导出提示；
- `校验并导出模组`：把校验与当前主线带权重 GPU 导出串成一个主按钮。

0.3.4 收口：

- 作者界面收敛为主线出口，只保留校验、主导出和当前 GPU 权重导出路线；
- 研究入口不再作为作者工作流展示。

0.3.5 补齐提取入口：

- `从抓帧生成配置档`：面向未知 Body，从 `FrameAnalysis-*` 自动生成 runtime-only
  配置档；
- `主 Draw` 默认为 0 自动选择，也可以填入 3DMigoto 顶部显示的 Draw 编号强制指定；
- 新配置档会记录 `resourceFiles`，解决 VB0 文件名缺少 hash 时无法回读的问题；
- UI 文案强调这是运行时资源配置档，不等同于完整骨架/权重来源。

这些入口仍然复用已有导入、传权、校验和导出算法，没有改变底层 GPU Runtime 路线。

## 6. 与上游成熟插件相比还缺什么

### P0：自动提取游戏对象

WWMI/EFMI 已经可以让作者选择 Frame Dump，然后自动提取对象源目录。GakumasMI 目前 Profile 数据已经自洽，但 HSKI Profile 仍主要依赖研究阶段手工整理。

当前 0.3.2 已补最小入口：

- `导入配置档对象` 可以隐藏 `原模型 JSON / 骨架 JSON` 的普通作者入口；
- JSON 字段仍可用于开发阶段定位问题。

0.3.3 已补最小版：

- `更新 Profile 抓帧源`；
- 自动校验 Body IB/VB0/VB1 与 t0/t1/t4 是否存在；
- 对 VB0 hash 被 3DMigoto 文件名省略的抓帧，按 `drawcall_map.json` 的 draw 编号回退匹配；
- 生成 `profile-capture-update-report.json`，报告 `hash` / `drawNumberFallback` / `none` 匹配模式。

仍需要补：

- 从未知 Frame Dump 自动创建全新 Profile；
- 自动识别 Body 主 draw、IB、VS、PS、t0/t1/t4 并写入新的映射文件；
- 自动复制纹理、VB/IB、ShaderUsage、log；
- 自动输出 `profile.json`、`material_map.json`、`texture_map.json`、`Reference`、`Buffers`；
- 对当前 Gakumas 的 CPU-skinned Body 特殊说明：Frame Dump 不能直接恢复原始 skin weight，仍需要游戏资源或内置 Profile 的权重源。

### P1：对象导入体验

WWMI/EFMI 的入口是 `Import Object`，用户面对的是“对象源目录”，不是零散 JSON 文件。GakumasMI 当前还有 `原模型 JSON / 骨架 JSON` 字段，偏研究工具。

当前 0.3.2/0.3.3 已补：

- `更新 Profile 抓帧源`；
- `导入配置档对象`；
- `选择高风险顶点`；
- `选择原生手部` / `选择原生颈部`；
- `创建身体材质模板`；
- `校验并导出模组`。

仍需要补：

- 自动导入 Body 权重参考、材质、贴图预览；
- 自动创建 Collection：
  - `GMI_ProfileReference`
  - `GMI_AuthorMesh`
  - `GMI_Export`
- 显示 Profile 摘要：角色、组件、顶点数、骨骼数、贴图槽、已验证状态。

### P2：作者模型蒙皮工作流

WWMI/EFMI/GIMI 依赖原游戏的 BlendIndices/BlendWeights，作者通常保留或调整顶点组；GakumasMI 因为 Body 是 CPU-skinned final VB，必须使用 Profile 权重源和自动转权。

当前已经有：

- 导入 HSKI 带权重参考；
- 最近面插值传权；
- 四权重限制；
- 手指/颈部语义修正；
- 风险顶点标记。

需要补：

- 可视化“高风险顶点”按钮；
- 一键选择/隐藏/分离 `GMI_REVIEW_HIGH_RISK`；
- 手、颈、原生身体保留/合并 UI；
- 对袖口、裙摆、手套、鞋等常见部位提供权重预设或检查规则；
- 自动生成“需要作者手动 Weight Paint 的区域报告”。

### P3：材质与贴图模板

WWMI/EFMI 具备复制贴图和模板化 INI 的能力。GakumasMI 已验证 HSKI Body 的：

- `t0` BaseColor；
- `t1` PackedMask：R 阴影、G 光滑、B 金属、A AO；
- `t4` ShadeColor：RGB 阴影色、A 混合强度。

需要补：

- Blender 材质节点模板；
- PNG/TGA 自动打包 DDS；
- 自动生成 PackedMask；
- 自动检查 DDS 格式、尺寸、sRGB/UNORM；
- 多材质槽到 t0/t1/t4 的映射 UI；
- 贴图预览和通道解释。

### P4：导出与打包体验

WWMI/EFMI 的最终出口是 `Export Mod`，并包含 Mod 信息、Logo、INI 模板、复制贴图、局部导出等完整体验。

GakumasMI 当前核心导出可用，但还缺：

- 单个主按钮：`导出模组`；
- 导出前自动执行校验；
- 自动复制到游戏 Mods 目录；
- Mod 名称、作者、描述、链接、Logo；
- Debug/Release 两种输出；
- INI 模板编辑；
- 一键重新导出并提示用户游戏内按 F10。

### P5：Validator/错误提示

WWMI/EFMI 会把错误高亮到对应字段。GakumasMI 当前主要依赖 Blender report。

需要补：

- 错误字段高亮；
- 问题分级：错误 / 警告 / 建议；
- “为什么失败”和“下一步怎么修”的中文解释；
- 导出报告保存为 `validation-report.json/md`。

## 7. 推荐下一步开发顺序

1. 完成 `从 Frame Dump 创建 Profile` 的最小版本；
2. 完成手/颈/原生身体保留的“复制/合并/排除目标皮肤”操作；
3. 完成 DDS 自动生成和贴图格式转换；
4. 完成高风险顶点热图显示和报告导出；
5. 最后补 Ini Template、Mod Info、局部导出和自动复制。
