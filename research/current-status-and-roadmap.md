# GakumasMI 当前状态、完成度与后续计划

更新时间：2026-06-28 · 插件版本：**0.6.0**

> 本文是项目**当前状态与完成度的权威来源**。产品总体愿景见
> [`../GakumasMI_开发路线_当前草案.md`](../GakumasMI_开发路线_当前草案.md)；
> 版本逐项变更见 [`../CHANGELOG.md`](../CHANGELOG.md)；
> 透明材质专题见 [`transparent-material-status.md`](transparent-material-status.md)。

## 0. 一句话现状

单 t0 身体的 **Blender → 3DMigoto → 游戏**（换模 + 动画 + 贴图 + 多 mod 共存）完整闭环
已达成并跨服装实机验证。一键即可对任意 body 生成完整配置档。当前重心在**作者体验、
材质还原与导出健壮性**，核心 GPU 算法已不是瓶颈。

## 1. 完成度评估（0.6.0）

| 模块 | 完成度 | 说明 |
|---|---:|---|
| GPU 核心（逆解每帧矩阵 + 重蒙皮 + 注入） | ~95% | 同源重建与游戏动态 VB0 逐字节一致，RMS ≈ 1e-6；任意拓扑跨服装实机跑通。已冻结、已审计。 |
| 配置档生成（一键：注入 + 结构 + 逆算子） | ~90% | 抓帧 + Body JSON 资源库一键产出；缺骨架时从 `m_BoneNameHashes` + `m_BindPose` 合成，500+ 套全可用。 |
| 蒙皮转权（作者模型 → 配置档骨架） | ~75% | 全身最近表面传权重稳定、自动限四权重/归一化、风险标记。手指/宽袖/裙摆仍需人工复核，缺可视化精修工具。 |
| 贴图 / 材质（t0 自动 DDS、分材质 t1/t4 烘焙、中性、COLOR/描边） | ~80% | t0/t1/t4 通道语义已实机实测；分材质预设由抓帧标定。缺多套服装持续校准、PNG→DDS 多材质 selector。 |
| 透明材质 | ~50% | 保守路径：A=0 镂空干净 + 投影/遮挡正常；半透明仅在已有 coverage 上可靠。真正伸出轮廓外的前向半透明未做（需窄触发点）。 |
| 健壮性 / 回归测试 | ~75% | 数据契约审计（60/60）+ CI 跑的 6 个测试：buffer 打包契约、mod.ini 契约、抓帧抽取、逆解数值（合成）、材质烘焙等；逆解数值与契约审计另有本地数据档（见 P0）。 |
| 产品化（多组件 / Mod Manager / 发布） | ~40% | 仅 HSKI Body 单组件主线；脸/头发/饰品、Shape Key、LOD、Mod Manager 未做。 |

**已确认边界**：学马所有 body 都是**单 t0**，工具的单 t0 模型与游戏结构一致。多材质身体
导出**不需要**（MMD 移植版的多贴图属作者侧问题，应在 Blender 里合成单图）。

## 2. 插件当前能力（0.6.0 操作器一览）

提取 / 导入：
- `一键生成完整配置档`（注入 + 结构 + 逆算子）、`从抓帧生成配置档`、`匹配 Body JSON 资源库`、
  `更新配置档抓帧源`、`导入配置档对象`、`导入抓帧参考模型`、`导入带权重参考模型`。

蒙皮转权：
- `从配置档传递权重 + 颜色`（含对齐守卫、风险距离标记）、`选择高风险顶点`。

材质模板：
- `创建身体材质模板`、`按材质烘焙 t1/t4`、`应用分材质 COLOR`、`导出贴图模组`。
- 材质属性：材质类型预设、`渲染材质`（不透明/透明）、明暗 / 阴影色微调。

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
  `t4`=RGB 阴影色 / A 叠加强度。
- **顶点 COLOR 是区域/拓扑相关的打包参数，不是普通颜色**：直接复用原版 COLOR 到自定义裙
  子会在错误几何上激活同一 shader 分支，产生移动暗块。安全族见
  [`color-scan-20260627-091033.md`](color-scan-20260627-091033.md)。
- **透明材质架构结论**见 [`transparent-material-status.md`](transparent-material-status.md)。

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

## 5. 后续计划（按优先级）

### P0 — 巩固核心与回归（健壮性 55% → ~75%，基本完成）
进度（CI 已接入，`.github/workflows/ci.yml` 每次 push/PR 跑 6 个测试）：
- ✅ 导出 buffer 打包契约回归 `tests/export_buffers_regression.py`：锁定 VB0/VB1 字节布局、
  权重归一化、材质→连续 draw_range 分组、R16/R32 选择与补齐，以及 0.5.30 类防错
  （UV NaN/Inf/越界停止导出、COLOR NaN→安全、fp16 钳制）。
- ✅ mod.ini 生成契约回归 `tests/mod_ini_contract.py`：用合成 profile 锁定 0.5.1 多 pass
  替换链（全 VS `checktextureoverride`、主体段 `match_first_index`+`drawindexed`、尾部段
  `handling=skip`）与 0.6.0 透明路径（InheritMask/AlphaBlend、反向 Z、不写深度、预乘 alpha、
  缺 t0 报错）。
- ✅ 逆解数值 fixture `tests/inverse_skin_numeric.py`：合成网格 + pinv 算子的恢复算法
  测试（CI 跑，recon≈6e-8）；真实 hski 算子的重建/骨矩阵 RMS 阈值（本地数据，缺失则
  SKIP）——实测 recon 1.8e-5（=README 最大位置误差 1.73e-5）、骨 P95 5.7e-5，并守住
  「不可观测骨数量」不回退。
- 仅 `tests/profile_contract_smoke.py` 仍是纯本地（需游戏抓帧目录），不进 CI。

### P1 — 作者蒙皮体验（转权 75% → 目标 90%）
- 传递距离 / 截断权重 / 未映射组 / 高风险热图的可视化复核工具；
- 手指、宽袖、裙摆的引导式精修流程。

### P2 — 材质与贴图（材质 80% → 目标 90%）
- 多套服装持续校准 `material_presets.json`；
- PNG→DDS 自动化与多材质 selector；
- 描边/COLOR 安全族的 UI 收敛。

### P3 — 透明材质（50% → 看可行性）
- 找角色专属前向透明窄触发点，做真正伸出轮廓的半透明（详见透明专题第 5 节）。

### P4 — 生态扩展（产品化 40%）
- 脸 / 头发 / 饰品多组件（各自也是单 t0）；
- Shape Key / 表情、LOD / 多 Drawcall；
- Mod Manager（安装、启用、冲突检测、版本迁移、安全模式）。

## 6. 与主流 Model Importer 的定位差异

GakumasMI 的独特价值不是作者工具完整度，而是解决了 GIMI/WWMI/EFMI 通常不面对的输入
条件：**从最终 CPU-skinned VB 反解每帧矩阵并重蒙皮自定义拓扑**。当前最大差距已从 GPU
动画算法转移到作者体验、身体部件处理与材质转换 —— 这正是 P1/P2/P4 的方向。
