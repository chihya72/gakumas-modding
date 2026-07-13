# GakumasMI Blender 插件更新日志

版本号见 [`gakumas_mi/__init__.py`](gakumas_mi/__init__.py) 的 `bl_info["version"]`。
发布包用 `python tools/package_blender_addon.py` 生成（代码版不含 Body JSON 资源库；
加 `--with-body-lib` 可一并打包）。本地包不提交到公开仓库。

## 0.7.5 — UI 收敛为身体 / 发型，附属组件改为可选项

- 制作目标只保留「身体」「发型」：`m_bdyco` 是身体下的可选透明/镂空配饰，
  `Geo_HairProp` 是发型下的可选发饰，不再暴露为第三个顶层目标。
- profile 的逆蒙皮配置下沉到 component；一个发型 profile 可同时保存 hair 与 hairprop
  各自的 VB/IB、drawcall、骨架、贴图和逆算子，并兼容旧单组件 profile。
- 默认 HMSZ 发型 profile 合并为 hair + hairprop 双组件；勾选「制作发饰（可选）」即可在
  同一四步流程中切换附属组件。

## 0.7.4 — hair/hairprop 语义转正：发型替换全链内建（圆香波波头实机校准）

以 scsp 圆香波波头 + 三件发饰 → hmsz-hair-0023 的全程实机迭代为校准样本
（踩坑总表见 [`research/hair-replacement.md`](research/hair-replacement.md) §7）：

- **「头发」材质预设按实测修正**：t1 = (0.263, 0.125, 0, **A=0**)——hair 的 t1.A 不是
  body 的 AO，写 255 会打开暗面项、漏出未替换的原版 t4（蓝紫阴影）；光滑度写高会以
  黄绿色漏进阴影。t4 改为逐通道冷阴影 `linearMul`：`t4_lin = base_lin × (0.378, 0.367,
  0.474)`，替代 body 的单一 darken。中性 t1 在 hair 组件下也自动走 A=0 常量。
- **PNG→DDS 按语义选格式**：t0/t4 = sRGB(DXGI 29)、t1 = 线性(DXGI 28)。此前 t1 一律
  sRGB 会被 GPU 二次解码（阈值 0.45→0.056），整体暗沉——该隐患对 body mod 同样存在。
- **hair 顶点色转正**：描边色 nibble `(R高,R低,G高)/15` 为全网格常量档（深色/粉红/
  金浅/纯黑），不再用 body 的逐顶点基础色曲线（暗部量化塌成绿描边）；G低（ramp 行）/
  B（0~15 细宽度）/A（144/0 高光掩码）从带权重参考网格最近邻拷贝。
- **hairprop 顶点色转正**：按材质槽「材质类型」写常量——metal = 灰 `(3,3,3)` + A=144，
  其余 = 黑 `(0,0,0)` + A=0，B=8；不再走 body 曲线（黑蝴蝶结绿边）。VB1 手动补丁流程
  全部作废。
- **文档**：发型道具 = Geo_Hair + Geo_HairProp 双组件（游戏内无单独发饰选择，完整替换
  = 同一次抓帧出 hair + hairprop 两个包）；证伪旧「发饰包 / 跨包共用 Geo_Hair」表述；
  制作目标 tooltip 与 README 同步。
- **profiles 精简为默认两件套**：`atbm-cstm-0140`（带原生 co 第二材质段的 body 默认档，
  由已导出包离线重建，附 `rebuild_profile.py`）+ `hmsz-hair-0023-hair`（发型默认档）。插件默认配置档路径
  与测试（blender_smoke / inverse_skin_numeric / profile_contract_smoke）同步切换；
  旧 hski-cstm-0000 PoC 冻结契约随档移除，契约冒烟改锁新默认档的几何/骨架/算子/co 段。

## 0.7.3 — manifest 面向包管理器：目标显示游戏资源名 + 强制预览图

- **Blender 作者界面收敛为四步**：全局选择“身体（body）/发饰（hairprop）”，按
  `① 准备配置档 → ② 绑定模型 → ③ 准备材质 → ④ 导出模组` 操作；实验、runtime-only、
  直接 GPU 导出等入口默认折叠。发饰页把 `Head_Hair` 刚体与物理骨权重路线明确为二选一，
  hairprop 材质页不再显示 body 专用原生 co。
- **修复发饰 profile 的顶点数提示仍扫描 `Geo_Body.json`**：Blender 的完整/分步配置档入口
  现在都按组件传入 `Geo_HairProp`；新增 Blender 4.2 UI 冒烟检查覆盖目标枚举、折叠 API、
  图标与两条 profile 入口。
- **导出 manifest `targets` 改为被替换的游戏内模型资源名**（如 `mdl_chr_hski-cstm-0000_body`），
  取自 profile `target.bodyResource/hairResource/faceResource`（按组件），而非旧的
  `body.weightedMesh`。让用户在包管理器里直接看到本 mod 替换了游戏里的哪个 body/hair/face；
  profile 缺资源名时回退旧语义。`schemaVersion` 升到 2，新增 `cover` 字段。
- **导出强制附预览图**：导出面板新增「预览图」字段（`gmi_cover_image`，png/jpg/webp），
  不填直接报错取消。`core._prepare_cover` 校验存在/格式/magic 字节/≤2MB 并复制为包内
  `cover.png`；operator 侧对过大图用 Blender 自动缩到 ≤1024px 再入包（合理限制体积）。
- 测试：`tests/mod_ini_contract.py` 新增 `test_manifest_target_is_body_resource_and_cover`，
  断言 `targets` 为游戏资源名、`cover` 落盘、缺预览图报错（7→8 项，全绿）。

## 0.7.2 — 运行时全局布局自动探测（彻底弃用 PS 枚举）

- **不再枚举 pixel shader hash。** 游戏按光照把 `baseColor/packedMask/shadeColor`
  重排到不同 `ps-tN` 槽（0.7.1 靠 `slotVariants` 逐 PS 登记，新场景一冒新 PS 就漏），
  现改为**运行时靠全局 body 地标贴图 `0ff26bed` 的槽位自动判布局**：
  - 地标在 `ps-t2` → 布局 **A**：`t0/t1/t4`（含自定义 shade）
  - 地标在 `ps-t3` → 布局 **B**：`t1/t2/t5`（唯一挪动 base/mask、会导致「棋盘格全身错乱」的变体）
  - 都不中 → **C/未知**：只绑 `t0/t1`，不绑自定义 shade（安全兜底，base/mask 永远对，
    绝不错乱/消失）。
  新场景、新服装、新角色全部自动覆盖，作者只需 base/mask/shade 三张贴图，**永不碰 PS hash**。
- **导出 ini 结构变化**：`[Constants]` 加 `$gmi_<Mod>_layout` / `_probe` 全局；新增
  `[CommandList<Mod>DetectLayout]`（`checktextureoverride = ps-t2 / ps-t3` 探地标）与自包含的
  `[TextureOverride<Mod>BodyLayoutLandmark]`（`hash = 0ff26bed` + 由 IB hash 派生的
  `match_priority`，多 mod 同装不冲突）。主体段与 native co 段都改成按 `$..._layout` 的三分支绑定。
- **移除 0.7.1 的逐 PS `slotVariant` 机制**：`core.py` 删除 `_section_slot_variant_ini`、
  `_section_material_binding_block` 等 5 个函数，新增 `_landmark_layout_sections` /
  `_landmark_binding_block`。TextureOverride 的重复 hash 用 `match_priority` 消歧
  （`allow_duplicate_hash` 只对 ShaderOverride 合法，放 TextureOverride 上会告警）。
- 已在 `D:/Games/gakumas/Mods/` 的 6 个活跃 mod 上手工验证：干净重启后 3DMigoto 日志
  无 `Unrecognised entry` / `Duplicate TextureOverride` 告警，暗光/正常/镜面场景均正常。
- 测试：`tests/mod_ini_contract.py` 的 `test_pixel_shader_slot_variants_are_conditional`
  改写为 `test_body_layout_is_runtime_autodetected`，断言地标探测三分支结构（7/7 通过）。
- 详细复盘结论已收敛进当前实现与回归测试。

## 0.7.1 — body / bdyco 材质贴图彻底分离

- **修复低亮度 PS 变体贴图槽错位**：`50b619789b23bd7a` 这类低亮度 shader 中，
  `baseColor/packedMask/shadeColor` 分别改读 `ps-t1/ps-t2/ps-t5`，其中 `ps-t4` 是深度比较槽。
  profile 现在支持 `slotVariants`，导出 ini 会按当前 PS 自动切换槽位，避免暗光下把
  `shadeColor` 误塞进深度槽后出现大块彩色阴影。
- **修复原生 co 材质共用 body t1/t4 的问题**：`NATIVE_CO` 段现在绑定
  `body.section1` 自己的 `t0/t1/t4` 资源；没有填写 co 的 `t1/t4` 时生成 co 专属中性图，
  不再复用 `m_bdy` 的 PackedMask / ShadeMap，避免透明材质与身体材质叠出灰斑。
- **调整材质模板 UI**：贴图绑定拆成「不透明 body / m_bdy」与「原生 co / m_bdyco」
  两块，co 现在有独立的基础色、混合遮罩和暗面材质字段。
- **分材质烘焙按渲染材质分流**：材质槽设为 `原生co` 时，烘焙会额外输出
  `gmi_baked_co_packedMask.dds` 与 `gmi_baked_co_shadeColor.dds`，并写回 co 字段。co 会按
  `m_bdyco` 自己的 atlas 尺寸烘焙，不要求与 body atlas 同尺寸。
- **修复 UV 重叠时 co 挖空 body t1/t4**：body 与 co 现在先按材质槽过滤三角形，再分别栅格化；
  co UV 覆盖在 body 皮肤 UV 上时，不会再把 body 的 material id 覆盖成中性洞。
- **抓帧主 draw 选择支持短角色代号提示**：`gmi_body_resource` 填 `shro` 这类短代号时，
  会用 Body JSON 资源库里所有匹配 body 的顶点数集合过滤候选，避免抓帧里同屏多角色时选错
  body；完整 body 名仍走精确匹配。`tools/extract_frame_profile.py` 新增
  `--body-json-library` / `--body-resource` 参数；提示会写进 `profile.target.bodyResource`。
- **打包附带 profiles**：`tools/package_blender_addon.py` 会把仓库 `profiles/` 目录
  （含 `texture_map.json` 槽位/`slotVariants` 标注）一并打进插件 ZIP 的
  `gakumas_mi/profiles/`。
- 测试：`tests/mod_ini_contract.py` 覆盖 co 专属 t1/t4 绑定与 `slotVariants` 条件绑定契约；
  `tests/frame_profile_extract_smoke.py` 覆盖短代号顶点数提示；
  `tests/material_bake_blender_smoke.py` 更新为检查 body/co 双输出。

## 0.7.0 — t1/t4 材质语义收敛与旧 Profile 防错

- **修正 t4/sdw 语义**：`t4.rgb` 明确为 `t0/baseColor` 的暗面材质颜色版，用来在卡通暗面保留
  衣服自身花纹、布料纹理和颜色；它不是投影阴影本身带图案。`t4.a` 继续按原生 `sdw`
  近似二值材质遮罩处理，不当作透明度或连续阴影强度。
- **修复旧 Profile 槽位坑**：旧抓帧 profile 可能把 `ps-t2` 环境 cubemap 误标为
  `body.shadeColor`，真正的 `_ShadeMap/sdw` 则在 `body.t4 / ps-t4`。0.7.0 导出时会自动把
  `shadeColor` 迁移到同前缀的 `t4/ps-t4`，避免暗面继续读取原服装 `sdw`，导致新衣服暗部出现
  不属于当前服装的彩色图案。
- **新增 t1 单通道输入**：分材质烘焙时可单独填写 `t1.R/G/B/A` 图。四个通道都填时按整图合成
  完整 PackedMask；只填部分通道时，先按材质预设烘焙，再仅覆盖有有效内容的材质区域，避免
  空白 atlas 黑区污染皮肤或无贴图材质。
- **UI 文案收敛**：`t4` 在界面中改称「暗面材质 t4/sdw」。逐材质行只保留 `材质类型`、
  `渲染材质`、`明暗`；不再暴露 `t4.A` 手调项，`t4.A` 由材质类型预设自动写入二值结果。
- **原生 co 贴图绑定对齐游戏逻辑**：基础色 `t0` 对应 `m_bdy`，透明材质 `t0` 对应 `m_bdyco`，
  两者各走各自 UV，互不回退。只要有材质槽设为 `原生co/NATIVE_CO`，导出时就必须提供
  「透明材质 t0 / m_bdyco」，否则直接报错，避免把 `m_bdy` 贴图错误套到 co 材质上。
- **抓帧主 draw 选择更稳**：自动抽 profile 时优先匹配期望顶点数和可见贴图绑定数，减少选到
  shadow/depth/helper draw 后生成错误贴图槽位的风险。
- 测试：`tests/mod_ini_contract.py` 新增旧 profile `shadeColor=ps-t2` 自动迁移到 `ps-t4`
  的回归；`tests/material_bake_smoke.py` 覆盖 t1 通道覆盖和材质预设 t4.A；`tests/frame_profile_extract_smoke.py`
  覆盖可见 draw 选择与贴图槽位语义。

## 0.6.2 — 透明路线收敛到原生 co（移除自建镂空/半透明）

- **删除自建透明路径**：`渲染材质` 不再有 `镂空(ALPHA_CLIP)` / `半透明(ALPHA_BLEND)`，
  只剩 `不透明` 与 `原生co(NATIVE_CO)`。透明/镂空统一交给游戏原生第二材质段 `m_bdyco`
  的 draw 上下文绘制（借用原版 shader/state/贴图）。旧工程里残留的 `ALPHA_CLIP/ALPHA_BLEND`
  值导出时按 `不透明` 处理。
- 移除随包 shader `GMIFinal/GMIInheritMaskA/GMIAlphaBlend/GMIAlphaClip/GMIClipMRT/GMINativeClip`
  与 `镂空阈值(gmi_alpha_cutoff)` 属性；导出不再写 `GMINativeClip{n}.hlsl`。
- 抓帧复核（`FrameAnalysis-2026-06-30-045108` + `mdl_chr_fktn-cstm-0001_body`）确认 `m_bdyco`
  与主 body **共用 VB0/VB1/IB**、仅 submesh 范围不同，且第二段在 5 个 VS pass 中的 4 个出现；
  NativeCo override 对全部 5 个 VS 都 `checktextureoverride = ib`。详见
  [`research/transparent-material-status.md`](research/transparent-material-status.md)。
- 补充 `m_bdyco` alpha 行为实测：低 alpha 渐变区域仍被裁切，抬到 `A=128/255` 后透明 padding
  以黑块显示，确认当前 body-co 路线更接近 cutout/alpha test，不是连续半透明 blend。
- 测试：`tests/mod_ini_contract.py` 删去 cutout/alpha-blend 契约，新增「旧 alpha 值回退不透明」
  与「原生 co 缺 t0 报错」；`tests/inverse_skin_index_format_smoke.py` 移除 alpha-blend 用例。

## 0.6.0 — 透明材质保守路径 + 文档整理

- **透明材质路径固化**：材质属性新增 `渲染材质`（不透明 / 透明）。透明段从主 body
  draw 拆出，走 `InheritMask`（只测深度不写深度，反向 Z）+ `AlphaBlend`（MRT、RT1 预乘
  alpha）两段，优先保证 **A=0 镂空干净 + 投影/遮挡正常**；半透明在同模型已有 coverage
  的像素上可靠显示。随包附带 `GMIFinal.hlsl` / `GMIInheritMaskA.hlsl` / `GMIAlphaBlend.hlsl`
  / `GMIAlphaClip.hlsl`。详见 [`research/transparent-material-status.md`](research/transparent-material-status.md)。
- 文档全面整理：新增本 CHANGELOG，归档已排除路线与逐步实验记录到 `research/archive/`，
  透明材质合并为单一结论文档。

## 0.5.50 — 描边颜色与顶点 COLOR 预设收敛

- 新拓扑衣服顶点 COLOR 默认使用「衣物常量」安全色，避免原版区域/拓扑相关 COLOR
  串到错误几何上产生移动色块。
- 描边颜色来源可选：取自基础色 / 按材质预设 / 黑色常量。
- COLOR 的安全族结论已收敛进插件预设与回归测试：
  中性化 R/G/A，保留 B 高位 `0xf0`，仅用 B 低位作描边宽度。

## 0.5.30 — 首次导出稳定性与 UV/COLOR 防错

- 修复「第一次导出错乱、第二次正常」：UV layer 引用在 `calc_tangents()` 后按名称重取，
  不再使用失效引用。
- 移除静默 fallback UV（读不到 UV 直接停止导出，而非写 `(0,0)` 导致 VB1 大面积 `(0,1)`）。
- 增加最终 VB1 UV 校验（NaN/Inf/异常大坐标直接报错，不再钳到 fp16 `65504`）。
- 非法 UV layer 清理与报告（`export-report.json` 记录 `uvLayers.candidates` 与
  `invalidUvLayersRemoved`）。
- 系统性清理 NaN/Inf（COLOR 转 0–255、PNG/DDS 像素、原生 COLOR 合成矩阵）。
- 新增 `应用分材质 COLOR` 按钮；「校验并导出」直接调用导出 operator 的 `execute`，减少
  `bpy.ops` 套娃和状态不同步。

## 0.5.22 — 原生顶点 COLOR 与分材质控制

- 新增 `原生合成顶点 COLOR(实验)`（`gmi_enable_native_color_transfer`）：按原版 `m_Colors`、
  贴图、位置/法线/UV 等特征为 MOD 网格合成逐顶点 COLOR。
- 新增描边宽度模式（`gmi_outline_width_mode`）与顶点 COLOR 导出模式（`gmi_vertex_color_mode`）。
- 分材质烘焙 / COLOR 拆为可折叠材质模板区；`material_presets.json` 开始写入材质默认 COLOR。
- 移除 0.5.6 残留的 `gmi_semantic_correction`（手指/颈部语义修复）。

## 0.5.6 — 基础流程版本

- 完整主流程可用：导入配置档对象 / 抓帧参考 / 带权重参考；从配置档传递权重；校验并
  导出（原拓扑 / 带权重 GPU）；创建身体材质模板；按材质烘焙 t1/t4；导出贴图模组。
- 材质系统偏「t1/t4 烘焙」，COLOR/描边方案尚不完整；仍含后续废弃的手指/颈部修复选项。

## 0.5.1 — 运行时替换链修复（重要）

修复同一 body IB 被多 pass、多段绘制时的替换：

- **全 VS 触发**：profile 记录 body IB 关联的全部 VS，每个生成
  `ShaderOverride…checktextureoverride = ib`，避免只覆盖部分 VS 导致其它 pass 叠图。
- **主体段定位 + drawindexed**：用 `match_first_index = <主体偏移>` + `handling = skip`
  + `drawindexed = <索引数>, 0, 0`，跳过原 draw、从自定义 IB 的 0 画满。
- **尾部段跳过**：同 IB 尾部段（原版裙摆等配件）逐段 `handling = skip`，避免原版配件漏出。

> 旧 profile 需**重新提取**才会带上述字段。

## 0.5.0 — 分材质烘焙 t1/t4

- 单 t0 身体的 Blender → 3DMigoto → 游戏（换模 + 动画 + 贴图 + 多 mod 共存）完整闭环
  达成并发布，跨服装实机验证。
- 一键生成完整配置档（注入 + 结构 + 逆算子）；缺 Unity 骨架时从 `m_BoneNameHashes` +
  `m_BindPose` 合成骨架，资源库 500+ 套全部可用。
- 新增按 Blender 材质槽逐材质烘焙 t1/t4（皮肤珊瑚阴影、哑光皮革、织物、金属…，预设由
  实机抓帧实测），专为自定义 atlas / MMD 等无游戏 t1/t4 来源的模型还原观感。
- mod.ini 改为 IB-only 触发，多个 body mod 共存零冲突警告。

## 0.3.x — 中文化工作台与一键配置档（历史）

- 0.3.2：`导入配置档对象`、`选择高风险顶点`、`创建身体材质模板`、`校验并导出模组` 等主线入口成形。
- 0.3.3：`更新 Profile 抓帧源`，支持 3DMigoto 文件名省略 VB0 hash 时按 draw 编号回退。
- 0.3.4：面板/字段/提示全面中文化（Profile→配置档、Mod→模组、Body→身体），收敛主线出口。
- 0.3.5：`从抓帧生成配置档`（runtime-only），自动候选评分选主 Draw；新增 `tools/extract_frame_profile.py`。

## 0.1.0 – 0.2.x — 起步（历史）

- 0.1.0：Blender 4.2 LTS 上的参考 Mesh 导入、索引 Mesh 校验/导出、DDS 贴图包导出。
- 0.2.x：带权重参考导入（`Geo_Body`：152 根加权骨骼）。
