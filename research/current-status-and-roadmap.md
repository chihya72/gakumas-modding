# GakumasMI 当前状态、完成度与后续计划

更新时间：2026-07-05 · 插件版本：**0.7.3**

> 本文是项目**当前状态与完成度的权威来源**。版本逐项变更见
> [`../CHANGELOG.md`](../CHANGELOG.md)；透明材质专题见
> [`transparent-material-status.md`](transparent-material-status.md)；
> 产品早期愿景/边界见 [`archive/roadmap-early-draft.md`](archive/roadmap-early-draft.md)（已归档，状态以本文为准）。
>
> **0.7.0→0.7.2 关键变化**：0.7.1 用 profile `slotVariants` 逐 PS 登记材质槽位（新场景冒新 PS 就漏），
> 0.7.2 彻底弃用 PS 枚举，改为**运行时靠全局 body 地标贴图 `0ff26bed` 的槽位自动判布局**
> （A=`t0/t1/t4`、B=`t1/t2/t5`、C/未知=只绑 `t0/t1` 安全兜底）；新场景/服装/角色自动覆盖，
> 作者永不碰 PS hash。见 [`session-20260704-gmi-global-layout-and-mirror.md`](archive/session-20260704-gmi-global-layout-and-mirror.md)。

## 0. 一句话现状

单 t0 身体的 **Blender → 3DMigoto → 游戏**（换模 + 动画 + 贴图 + 多 mod 共存）完整闭环
已达成并跨服装实机验证。一键即可对任意 body 生成完整配置档。当前重心在**作者体验、
材质还原与导出健壮性**，核心 GPU 算法已不是瓶颈。

## 1. 完成度评估（0.7.2）

| 模块 | 完成度 | 说明 |
|---|---:|---|
| GPU 核心（逆解每帧矩阵 + 重蒙皮 + 注入） | ~95% | 同源重建与游戏动态 VB0 逐字节一致，RMS ≈ 1e-6；任意拓扑跨服装实机跑通。已冻结、已审计，0.6.x–0.7.2 期间无变动。 |
| 配置档生成（一键：注入 + 结构 + 逆算子） | ~90% | 抓帧 + Body JSON 资源库一键产出；缺骨架时从 `m_BoneNameHashes` + `m_BindPose` 合成，500+ 套全可用。0.7.0 抓帧主 draw 选择更稳（优先匹配期望顶点数/可见贴图绑定数）；0.7.1 支持填短角色代号按资源库顶点数集合过滤候选，避免多角色同屏选错 body。 |
| 蒙皮转权（作者模型 → 配置档骨架） | ~75% | 全身最近表面传权重稳定、自动限四权重/归一化、风险标记。手指/宽袖/裙摆仍需人工复核，缺可视化精修工具；0.6.x–0.7.2 无进展。 |
| 贴图 / 材质（t0 自动 DDS、分材质 t1/t4 烘焙、中性、COLOR/描边） | ~85% | t0/t1/t4 通道语义已实机实测并在 0.7.0 收敛（t4.rgb=暗面材质颜色版、t4.a=近似二值遮罩，非阴影强度灰阶）；0.7.1 把 `m_bdy`/`m_bdyco` 材质彻底分离——`NATIVE_CO` 绑 co 自己的 t0/t1/t4、缺 co 通道时生成 co 专属中性图、按材质槽过滤三角再分别栅格化避免 co 挖空 body；材质模板 UI 拆成「不透明 body」「原生 co」两块，烘焙额外输出 `gmi_baked_co_*`。0.7.2 材质槽位改为运行时全局布局自动探测（见第 3 节）。缺多套服装持续校准、PNG→DDS 多材质 selector。 |
| 透明材质（镂空/cutout 已达成；真半透明暂缓） | ~85% | **cutout/镂空路线已实机验证完成**：0.6.2 起废弃自建 `ALPHA_CLIP`/`ALPHA_BLEND`（污染/维护成本高），改为唯一正式路线——借用游戏原生第二材质段 `m_bdyco`（`NATIVE_CO`），保留原生 shader/state/描边/投影/遮挡；0.7.0 补上 `m_bdy`/`m_bdyco` t0 分离与缺失报错。已实测确认该路线是 **cutout/alpha-test**。⚠️ 玻璃/薄纱级**真连续半透明暂时放弃研究、优先级降低**：接受"仅镂空、不做真半透明"为**当前边界**，完成度按此可行边界计（≥80%）；若日后偶然找到角色专属前向透明窄触发点再重启评估（见 P3）。 |
| 健壮性 / 回归测试 | ~75% | 数据契约审计（60/60）+ CI 跑的 6 个测试：buffer 打包契约、mod.ini 契约（含 0.7.0 旧 profile 迁移、0.7.1 co 专属 t1/t4 绑定、0.7.2 `test_body_layout_is_runtime_autodetected` 地标探测三分支回归）、抓帧抽取（含 0.7.0 draw 选择 + 0.7.1 短代号提示）、逆解数值（合成）、材质烘焙（0.7.1 body/co 双输出）；逆解数值与契约审计另有本地数据档（见 P0）。 |
| 产品化（多组件 / Mod Manager / 发布） | ~60% | 仅 HSKI Body 单组件主线；脸/头发/饰品、Shape Key、LOD 未做。**Mod Manager 已功能完备并随 `3dmigoto-gkms-v0.5.0` 发布**（Inno 安装包、应用图标）：扫描/启停/F10 重载/冲突检测/完整性校验、路径记忆、封面缩略图、拖拽安装（文件夹/zip）、打开目录；不做 d3dx 图形化设置页（改发 `键位说明.txt` + 默认 hunting=2 关绿字）。0.7.3 起 manifest `targets`=被替换的游戏资源名、强制预览图，正对上管理器展示。规划见 [`mod-manager/docs/plan.md`](../mod-manager/docs/plan.md)。 |

**已确认边界**：学马所有 body 都是**单 t0**，工具的单 t0 模型与游戏结构一致。多材质身体
导出**不需要**（MMD 移植版的多贴图属作者侧问题，应在 Blender 里合成单图）。

## 2. 插件当前能力（0.7.2 操作器一览）

提取 / 导入：
- `一键生成完整配置档`（注入 + 结构 + 逆算子）、`从抓帧生成配置档`、`匹配 Body JSON 资源库`、
  `更新配置档抓帧源`、`导入配置档对象`、`导入抓帧参考模型`、`导入带权重参考模型`。

蒙皮转权：
- `从配置档传递权重 + 颜色`（含对齐守卫、风险距离标记）、`选择高风险顶点`。

材质模板：
- `创建身体材质模板`、`按材质烘焙 t1/t4`（0.7.0 起支持 `t1.R/G/B/A` 单通道局部覆盖）、
  `应用分材质 COLOR`、`导出贴图模组`。
- 材质属性：材质类型预设、`渲染材质`（`不透明` / `原生co NATIVE_CO`，0.6.2 起不再有自建
  `镂空`/`半透明`）、明暗微调；`t4.A` 不暴露为作者选项，由材质类型预设固定。0.7.1 起贴图绑定
  拆成「不透明 body / m_bdy」与「原生 co / m_bdyco」两块，co 有独立基础色/混合遮罩/暗面字段。
- 材质槽位（0.7.2）：作者只出 base/mask/shade 三张贴图，导出 ini 靠全局地标运行时自动判布局，
  不再需要逐 PS 登记 `slotVariants`。

导出：
- `校验并导出模组`（主线）、`校验模组`、`导出带权重 GPU 模组`、`导出原拓扑模组`。

## 3. 已验证的核心事实（不要重新论证）

- **三层数据模型**：静态结构（骨骼/权重/bindpose）来自 AssetStudio `Geo_Body.json`；每帧
  动画来自实时 `VB0` 经 `RecoverMatricesCS` 反解的 152 个矩阵；注入靠 3DMigoto hash 覆盖
  + `SkinCustomCS` 重蒙皮回原格式 40 字节 VB0。
- **逆解链已实机验证**：GPU 恢复矩阵 vs CPU/HLSL 模拟 RMS `1.55e-6`；重建位置 vs 游戏动态
  VB RMS `1.14e-6`；最大误差 `1.73e-5`；Compute 输出与最终 IA VB 逐字节一致。详见
  [`inverse-skin-matrix-recovery.md`](inverse-skin-matrix-recovery.md)。
- **HSKI 数据契约审计 60/60 通过**：17,615 顶点 / 74,664 索引 / R16 IB；VB0 stride 40、
  VB1 stride 12；152 bind pose 中 147 根实际使用。机读结果见
  `../profiles/hski-cstm-0000/audit-report.json` 与 `data-contract.md`。
- **材质通道语义**：`t0`=基础色；`t1`=R 卡通阴影阈值 / G 光滑度 / B 金属度 / A 环境光遮蔽；
  `t4`=暗面材质图，RGB 是基础色暗色版 / A 是近似二值材质遮罩；它不是投影阴影本身带图案，也不应烘成连续阴影强度灰阶。
- **顶点 COLOR 是区域/拓扑相关的打包参数，不是普通颜色**：直接复用原版 COLOR 到自定义裙
  子会在错误几何上激活同一 shader 分支，产生移动暗块。安全族见
  [`color-scan-20260627-091033.md`](color-scan-20260627-091033.md)。
- **透明材质架构结论**：唯一正式路线是借用游戏原生第二材质段 `m_bdyco`（`NATIVE_CO`），
  已实机验证为 cutout/alpha-test 而非连续半透明；0.6.2 已移除自建 `ALPHA_CLIP`/`ALPHA_BLEND`
  两条路线。详见 [`transparent-material-status.md`](transparent-material-status.md)。
- **材质槽位靠运行时全局布局探测，不枚举 PS hash（0.7.2）**：游戏按光照把
  `baseColor/packedMask/shadeColor` 重排到不同 `ps-tN`；导出 ini 用全局地标贴图 `0ff26bed`
  的落槽（`ps-t2`→A、`ps-t3`→B）在运行时判布局，未命中则安全兜底只绑 `t0/t1`。
  0.7.1 的逐 PS `slotVariants` 已废弃（新 PS 一冒就漏）。详见
  [`session-20260704-gmi-global-layout-and-mirror.md`](archive/session-20260704-gmi-global-layout-and-mirror.md)。

## 4. 已排除 / 失败的路线（保留以免重蹈）

| 路线 | 结果 | 结论 |
|---|---|---|
| 静态 T-pose VB 直接替换 | 不跟随动画 | 游戏 Draw 输入已是 CPU 蒙皮结果 |
| 自定义 VS 重建 SurfaceMap | 几何可见但材质退化 | 应保留游戏原 VS/PS，用逆解矩阵重蒙皮（代码已删，见 git 历史） |
| 进程内 IL2CPP Runtime 替换 Mesh | 崩溃 / 进程保护 / 违反边界 | 改用逆解矩阵（`runtime/native` 已删）。背景见 `archive/runtime-skinning-bridge.md` |
| 抓帧反解 T-pose 几何 / 重建骨骼权重 | 数学病态、无中生有 | 结构数据全部来自 `Geo_Body.json` |
| TTMR 骨名直接映射到 HSKI / 运行时 retarget | 大面积错位/拉伸 | 同名不代表 bind pose/层级兼容；作者应在 Blender 重蒙皮到目标骨架。见 `archive/ttmr-cstm-0119-body-plan.md` |
| 保留 TTMR 与 HSKI 同名骨权重 | 全屏爆炸 | 外部权重属外部 bind rig，不能直接当 HSKI 权重 |
| 按同名手指分区取最近 HSKI 顶点 | 手指拉长 | 两套手部 bind 几何不一致，不能自动猜 |
| 只替换 BaseColor / 把 BaseColor 当 ShadeColor | 图案串入 / 整体粉色 | 必须处理 t1/t4 通道语义 |
| 全局前向 shader hash hook 做透明 | 污染整帧 UI/场景 | 需角色专属窄触发点（见透明专题） |
| 自建 `ALPHA_CLIP`/`ALPHA_BLEND` pass 做透明（0.6.0 方案，0.6.2 已移除） | 与游戏原生状态不一致、维护成本高；延迟合成 coverage 与背景半透明冲突 | 改为唯一路线：借用游戏原生第二材质段 `m_bdyco`（`NATIVE_CO`），详见透明专题 |
| 把 `m_bdyco` 当连续半透明 blend 使用 | 中间 alpha 低值仍被裁切，抬高后 padding 显示黑块 | `m_bdyco` 当前更接近 cutout，不能承诺真半透明 |

## 5. 后续计划（按优先级）

### P0 — 巩固核心与回归（健壮性 55% → ~75%，基本完成）
进度（CI 已接入，`.github/workflows/ci.yml` 每次 push/PR 跑 6 个测试）：
- ✅ 导出 buffer 打包契约回归 `tests/export_buffers_regression.py`：锁定 VB0/VB1 字节布局、
  权重归一化、材质→连续 draw_range 分组、R16/R32 选择与补齐，以及 0.5.30 类防错
  （UV NaN/Inf/越界停止导出、COLOR NaN→安全、fp16 钳制）。
- ✅ mod.ini 生成契约回归 `tests/mod_ini_contract.py`：用合成 profile 锁定 0.5.1 多 pass
  替换链（全 VS `checktextureoverride`、主体段 `match_first_index`+`drawindexed`、尾部段
  `handling=skip`）与当前 `NATIVE_CO`/`m_bdyco` 透明路径（旧 alpha 值回退不透明、原生 co
  缺 t0 报错、旧 profile `shadeColor=ps-t2` 自动迁移到 `ps-t4`）；0.6.0 的自建
  InheritMask/AlphaBlend 契约已随 0.6.2 一并从测试里删除。
- ✅ 逆解数值 fixture `tests/inverse_skin_numeric.py`：合成网格 + pinv 算子的恢复算法
  测试（CI 跑，recon≈6e-8）；真实 hski 算子的重建/骨矩阵 RMS 阈值（本地数据，缺失则
  SKIP）——实测 recon 1.8e-5（=README 最大位置误差 1.73e-5）、骨 P95 5.7e-5，并守住
  「不可观测骨数量」不回退。
- ✅ 0.7.0 新增材质/抓帧回归：`tests/material_bake_smoke.py` 覆盖 t1 通道局部覆盖与
  t4.A 材质预设；`tests/frame_profile_extract_smoke.py` 覆盖主 draw 选择与贴图槽位语义。
- 仅 `tests/profile_contract_smoke.py` 仍是纯本地（需游戏抓帧目录），不进 CI。

### P1 — 作者蒙皮体验（转权 75% → 目标 90%）
- 传递距离 / 截断权重 / 未映射组 / 高风险热图的可视化复核工具；
- 手指、宽袖、裙摆的引导式精修流程。

### P2 — 材质与贴图（材质 85% → 目标 90%）
- 多套服装持续校准 `material_presets.json`；
- PNG→DDS 自动化与多材质 selector；
- `m_bdy` 基础色 t0 与 `m_bdyco` 透明材质 t0 已按原生逻辑分离；`NATIVE_CO`
  缺少单独 t0 必须报错，不能回退主基础色；
- 描边/COLOR 安全族的 UI 收敛。

### P3 — 透明材质（~85%，**已暂缓 / 优先级降低**）
- 镂空/cutout 子目标已用原生 `m_bdyco`（`NATIVE_CO`）验证完成，是当前的正式边界；
- **玻璃/薄纱级真连续半透明：暂时放弃研究、优先级降低。** 已确认 `m_bdyco` 是 cutout 而非
  半透明（详见透明专题第 3、5 节），继续投入产出比低，暂接受"仅镂空"为最终边界；
- 仅在**偶然发现**角色专属前向透明窄触发点时才重启评估，不主动排期。

### P4 — 生态扩展（产品化 ~60%）
- ✅ Mod Manager 已功能完备并随 `3dmigoto-gkms-v0.5.0` 发布（扫描/启停/F10/冲突/完整性/
  路径记忆/封面/拖拽安装/Inno 安装包）；后续为增量打磨，非阻塞。
- 脸 / 头发 / 饰品多组件（各自也是单 t0）—— 产品化的主要剩余大块；
- Shape Key / 表情、LOD / 多 Drawcall。

## 6. 与主流 Model Importer 的定位差异

GakumasMI 的独特价值不是作者工具完整度，而是解决了 GIMI/WWMI/EFMI 通常不面对的输入
条件：**从最终 CPU-skinned VB 反解每帧矩阵并重蒙皮自定义拓扑**。当前最大差距已从 GPU
动画算法转移到作者体验、身体部件处理与材质转换 —— 这正是 P1/P2/P4 的方向。
