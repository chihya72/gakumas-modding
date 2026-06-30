# GakumasMI Blender 插件更新日志

版本号见 [`gakumas_mi/__init__.py`](gakumas_mi/__init__.py) 的 `bl_info["version"]`。
发布包用 `python tools/package_blender_addon.py` 生成（代码版不含 Body JSON 资源库；
加 `--with-body-lib` 可一并打包）。本地包不提交到公开仓库。

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
- COLOR 的安全族结论见 [`research/color-scan-20260627-091033.md`](research/color-scan-20260627-091033.md)：
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
