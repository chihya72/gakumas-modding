# GakumasMI 当前状态与路线

更新：2026-07-13 · Blender 插件：**0.7.5**

本文只记录当前事实和未完成事项。逐版本变化见 [`../CHANGELOG.md`](../CHANGELOG.md)，
使用方法见 [`../gakumas_mi/README.md`](../gakumas_mi/README.md)。

## 当前交付能力

GakumasMI 已打通 Blender → 3DMigoto → 游戏的换模闭环：

- 身体与发型任意拓扑网格导入、转权、校验和导出；`m_bdyco` 是身体包可选段，`Geo_HairProp`
  是发型包内可选组件，启用时与 `Geo_Hair` 合并发布；
- 从抓帧与 AssetStudio Mesh JSON 一键生成配置档和逆蒙皮算子；
- GPU 每帧恢复骨骼矩阵并重蒙皮，动态 VB 实测 RMS 约 `1e-6`；
- `t0/t1/t4` 材质烘焙，body 原生 `m_bdyco` 镂空材质；
- hair 专用 t1/t4 与顶点 COLOR 语义，hairprop 按材质类型生成描边；
- manifest、封面、冲突目标与 Mod Manager 完整兼容。

默认示例只保留两档：

- `profiles/atbm-cstm-0140`：带原生 `bdyco` 的 body；
- `profiles/hmsz-hair-0023-hair`：hair。

## 已冻结的核心结论

- 游戏角色网格使用 CPU 蒙皮；静态结构来自 Mesh JSON，动画矩阵从实时 VB0 反解。
- 逆解与重蒙皮链已实机验证，不再探索进程注入、手/颈拆件等替代路线。
- 材质槽位由运行时地标自动判布局，不维护逐 PS hash 列表。
- body 的 `t1.A` 是 AO/间接光；hair 的 `t1.A` 必须为 0，二者不可混用。
- `m_bdyco` 是 cutout/alpha-test，不是连续半透明；薄纱和玻璃不在正式支持范围。
- hair 与 hairprop 是同一发型道具的两个独立 drawcall，由同一发型 profile 和 UI 流程管理。

数学验证见 [`inverse-skin-matrix-recovery.md`](inverse-skin-matrix-recovery.md)，材质边界见
[`transparent-material-status.md`](transparent-material-status.md)，发型语义见
[`hair-replacement.md`](hair-replacement.md)。

## 当前维护项

| 优先级 | 事项 | 完成条件 |
|---|---|---|
| P0 | 回归与发布维护 | 现有 smoke、契约测试和打包流程持续通过 |
| P1 | 材质实机校准 | 遇到新组件语义时补最小预设与回归用例 |
| P2 | 作者体验 | 仅处理会阻断主流程的 UI、报错和兼容问题 |

## 暂不开展

- 连续半透明、Shape Key/表情、脸部替换、LOD/多 drawcall 自动编排；
- 自建 shader/state 透明路线；
- 为单个样本增加通用抽象或长期维护的 PS 枚举。

这些需求只有在出现可复现样本和明确用户需求时再恢复。
