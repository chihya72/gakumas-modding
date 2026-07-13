# 发型与发饰替换

更新时间：2026-07-13 · 状态：**路线已实机验证**（hski 兔耳换色/换网格 + 圆香花饰移植 hmsz 均通过）

> 发饰是继 body 之后第一个打通的多组件替换目标。核心结论：**发饰替换与 body 替换同构**，
> 复用同一条逆解链（抓帧提取 → 库匹配 → 逆算子 → compute 重蒙皮 → draw 替换），
> 生成器（`write_inverse_skin_package`）零改动即可出包。
> 发型本体（`Geo_Hair`，组件 `hair`）走完全同一条链，2026-07-13 已实机验证
> （hmsz-hair-0023 圆香波波头）；hair 组件的贴图/顶点色语义与 body 不同，见 §6。

## 1. 资产组织（实测事实，2026-07-13 修订）

- **一个 `_hair` bundle = 一个游戏内「发型」道具 = 两个独立部件**：发型网格 `Geo_Hair`
  （组件 `hair`）+ 发饰网格 `Geo_HairProp`（组件 `hairprop`）。378/378 个 `_hair` 包
  都同时含两者。从 octo 解密缓存获取（`Gakuen-idolmaster-ab-decrypt` 的
  `output/asset_bundle/other/`）。
- **游戏内只有「发型」选择，没有单独的「发饰」选择**——装备一个发型道具即同时渲染
  它的 Geo_Hair 与 Geo_HairProp 两个 drawcall。
- 同一角色不同 `hair-NNNN` 包的 `Geo_Hair` 不保证相同：
  hski 系列确实同拓扑（16345v/67410idx 跨包一致）但顶点位置逐包微调（pos md5 不同）；
  hmsz 系列连拓扑都不同（hair-0021: 12413v / 0023: 11459v / 0029: 12471v）。
  「官方换发饰只换 Prop」只是 hski 这类系列的近似现象，不是通则。
- **与 body/bodyco 的结构区别**：`m_bdyco` 是同一 body 网格的第二材质段（共用 VB/IB）；
  hair 与 hairprop 是**两个独立网格、各自 IB/VB、权重与贴图**，因此内部保留两个 component
  和两套 draw override，但由同一个发型 profile 与 UI 流程管理
  （实例：`hski.hair21-default-hmsz`（发型）+ `hmsz.hair23.madoka-hairprop`（发饰），
  出自同一次抓帧 FrameAnalysis-2026-07-13-015228 的两个 draw）。
- `cstm-NNNN_hair` 包 = 服装专属发型（同样是 Geo_Hair + Geo_HairProp 结构）。
  部分服装（如 ttmr-cstm-0111）没有专属 `_hair` 包，进游戏实穿才能确定实际用哪个发型包。
- **`Geo_HairProp` 的范围经常比"头顶挂件"大**：hski 兔耳 Prop 除耳朵外还包含编进头发的
  挑染发丝（包围盒覆盖整个头部 y 1.13–1.63）。**替换 = 整个 Prop 网格被替换**，
  自定义发饰若不带这些发丝件，原发丝会一并消失——作者必须知情。

## 2. 注入与材质（兔耳抓帧 FrameAnalysis-2026-07-12-041807 验证）

| 项 | 事实 | 与 body 对比 |
|---|---|---|
| VB 布局 | VB0 stride 40 + VB1 stride 12 | **完全一致** |
| 主 VS | `fe50b7a82b0f37be` | **同一个** |
| 阴影 VS | `221c573337491c78` / `436f9c16af3b54cf` | 同族 |
| 镜子 pass | VS `5b7fff8ecccaf579`，精简 PS、不绑全局贴图 | 同 body 降级行为 |
| 材质槽（主 PS） | t0=底色 / t1=打包遮罩 / t4=暗面色（512² BC7） | **布局 A 逐槽同构** |
| 布局探测 | 全局地标 `0ff26bed` 落 ps-t2 | **0.7.2 运行时探测直接适用** |
| 额外槽 | t5=ramp（1024×4，沿用原版）、t6=hhl 占位（4×4 dummy） | 作者仍只出 3 张图 |
| 贴图族命名 | `t_chr_<id>_hir_col_alp / hir_def / hir_sdw / hir_hhl / rmp` + `hirco_*` | 对应 bdy 系 |

注意：贴图 hash 直换不触发（本游戏通病），必须由 ShaderOverride 的
`checktextureoverride = ib` 带起 IB hash 的 TextureOverride——生成器输出的 mod.ini 已内置。

## 3. 制作流程

与 body 完全同一条链，只是 `component` 与资源库不同：

1. **建发饰 JSON 资源库**（一次性）：
   ```
   python tools/export_all_body_json.py --input <hair包目录> --suffix _hair \
       --mesh-name Geo_HairProp --output .local/assetstudio-hairprop-json --skeleton
   ```
2. **抓帧**：游戏内穿戴目标发饰，3DMigoto Frame Analysis 抓全帧。
3. **提取 profile**：
   ```
   python tools/extract_frame_profile.py <抓帧目录> profiles/<名字> \
       --component hairprop --body-resource mdl_chr_<角色>-hair-NNNN_hair
   ```
   自动选 draw 会按 40+12 双 VB 打分，仍建议用资源库顶点数核对；不对就 `--draw` 指定。
4. **补全逆解**：Blender 步骤①选择“发型”并勾选“制作发饰（可选）”；插件把 hair 与
   hairprop 的配置合并到同一 profile。脚本底层仍分别调用
   `complete_inverse_skin_profile(profile_dir, 资源库, component_id="hairprop")`。发饰骨多为头发
   物理骨，少量不可观测骨正常。
5. **Blender authoring**：导入参考模型与骨架 → 建自定义发饰 → 在步骤②二选一：硬质发饰刚体绑定到
   `Head_Hair`，需要摆动的软发饰传递权重并复核 → 准备 t0/t1/t4 → 校验并导出。`skin` 数据格式为
   `[(骨索引, correction索引, 权重)]`，权重在源骨架上时 correction 恒 0 + 单个恒等矩阵。
6. **验证**：装入 Mods，确认原发饰（含发丝件）整体消失、新网格跟随头部动画、描边/投影正常。

## 4. 已验证 PoC（2026-07-12，hski 兔耳 = hski-hair-0023，IB `8dab3a7b`）

- **贴图换色**：IB TextureOverride 绑 ps-t0 纯青 → 耳朵+挑染丝全部变青（证明注入路径 + Prop 范围）。
- **网格替换**：纯 Python 合成 24 顶点立方体（100% 权重绑 Prop 主宿主骨、放骨主导顶点质心），
  `write_inverse_skin_package(component_id="hairprop")` 出包 → 游戏内原发饰整体消失、
  立方体正确戴在头顶随动画运动，描边/投影正常。**生成器零代码改动。**

## 5. 边界

- LIVE 暗光场景的 hair 系 PS 槽位重排尚未实抓验证（地标探测机制已确认适用，风险低）。
- Blender 插件的「组件」字段（`gmi_component_id`，默认 `body`）已贯穿各操作器，
  作者选 `hair` / `hairprop` 即走对应链；资源库目录换成对应库即可
  （同一批 `_hair` 包可分别建两个库：`--mesh-name Geo_Hair` 与 `--mesh-name Geo_HairProp`）。
- 发型本体已用 `hmsz-hair-0023` 实机验证；注入结构与发饰一致，但材质/顶点色语义不同，见 §6。

## 6. hair（发型本体）组件与 body 的语义差异（2026-07-13 实机踩坑）

结构（VB 布局/VS 族/地标探测/逆解链）与 body 完全同构，但**贴图与顶点色语义不同，
直接套 body 规则会出杂色**：

- **t1 packedMask**：原版实测常量约 `(R=67, G=32, B=0, A=0)`。`A` 不是 body 的 AO
  （写 255 会打开某个暗面项、漏出未替换的原版 t4 → 蓝紫阴影）；`G`（光滑度）写高会以
  黄绿色漏进阴影。t1 必须存成**线性 DDS（DXGI 28）**——插件 `_png_to_dds` 默认写
  sRGB(29)，会让阈值被二次解码、整体暗沉；0.7.4 起插件已按语义自动选择格式。
- **t4 shadeColor**：不是 body 的 `base×单一 darken`，而是冷阴影：
  `t4_lin = base_lin × (0.378, 0.367, 0.474)`（暗化 + 偏蓝），A=0。
- **顶点 COLOR**：描边色 nibble 编码与 body 同构（`(R高,R低,G高)/15` = 描边 RGB），
  但**全网格常量、增益极大、宁小勿大**（蓝紫发 hmsz=(0,0,1)、粉发 hski=(1,0,0)、
  金发 fktn=(4,2,1)；(2,1,0) 实机即偏土黄）。不能用 BASECOLOR 逐顶点合成
  （暗部量化后红分量塌 0 → 暗绿描边）。B 为 0~15 细描边宽度（body 的 255 会出杂色），
  A 为 144/0 二值掩码——B/A 应从参考网格最近邻拷贝。
- hair 主 PS 还绑 t3（R16 2048²）/t5·t7（ramp）/t6（近常量淡紫）等未替换槽，
  语义未逆向；实测三张图（t0/t1/t4）+ 正确顶点色即可达到与原版一致的观感。

## 7. 发型替换踩坑总表：插件已自动处理 vs 需作者手动（2026-07-13 全程复盘）

以 scsp 圆香波波头 + 三件发饰 → hmsz-hair-0023 全程实机迭代为准。

### 7.1 插件已自动处理（gakumas_mi 0.7.4 起，作者无感）

| 坑 | 症状（修复前） | 0.7.4 处理方式 |
|---|---|---|
| hair t1.A ≠ AO | A=255 打开暗面项，漏出未替换的原版 t4 → 蓝紫阴影 | 「头发」材质预设改为实测常量 (0.263, 0.125, 0, **A=0**)；中性 t1 在 hair 组件下也走 A=0 |
| hair t1 光滑度过高 | G≈153 以黄绿色漏进阴影 | 同上，预设 G=0.125 |
| t1 被存成 sRGB DDS | 阈值被 GPU 二次解码（0.45→0.056），整体暗沉 | PNG→DDS 按语义选格式：t0/t4=sRGB(29)、t1=线性(28) |
| hair t4 套 body 暗化公式 | 阴影色相不对 | 预设 `linearMul` 冷阴影：`t4_lin = base_lin × (0.378, 0.367, 0.474)` |
| hair 描边逐顶点合成 | 暗部量化塌成 (0,1,0) → 绿边 | 「发型描边色档」全网格常量（深色/粉红/金浅/纯黑 4 档）；G低/B/A 从参考网格最近邻拷贝 |
| hairprop 描边同病 | 黑蝴蝶结绿边 | 按材质槽类型写常量：metal=(3,3,3)+A144、其余=(0,0,0)+A0、B=8 |

### 7.2 需作者手动（流程/判断题，插件管不了）

| 事项 | 要点 |
|---|---|
| 选对源资产 | 同角色多款发型（scsp 圆香有 001/002/005/010），枚举后按骨链特征区分（如 `HAIR_Side_Tail`=马尾）并渲染预览确认，别只看编号 |
| 空间对齐 | 用**发根骨→`Head_Hair` 锚点映射 + 统一缩放**（scsp→Gakumas 实测 ×1.0557），别用原点缩放；**发型与发饰必须用同一套变换**，否则相对位置漂移 |
| 解剖差异微调 | 头骨形状差异锚点管不住（圆香耳位比莉波低 → 耳环单独 +15mm），按实机截图毫米级手动偏移部件 |
| 发饰材质类型标注 | 金属件材质槽标 `metal` → 灰描边+高光掩码；亮色布件（白花等）想要灰描边也标 metal；不标默认黑描边 |
| 暗环境金属发乌 | metal 预设 metallic=0.75 大量混入环境立方图，室内昏暗时小饰品会发乌——饰品建议用布料 t1 参数（或单独提亮该件暗面图） |
| 双 draw | hair 与 hairprop 需各自 draw override，但同属一个发型 profile 和制作流程 |
| 开发环境 | 无头脚本跑导出前，确认 Blender 已安装的 gakumas_mi 与仓库同步（枚举缺项报 `enum not found` 即版本落后） |
