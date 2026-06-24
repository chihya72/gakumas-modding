# GakumasMI

面向《学园偶像大师》（学马仕 / Gakumas）的 **Blender + 3DMigoto 视觉 Mod 工具链**。

目标：让 Mod 作者只用 Blender 和本项目的导出插件就能换装 / 换模，**不需要安装
Unity、不制作 AssetBundle、不手写 3DMigoto 配置**。

> 当前处于 `hski-cstm-0000 / Body` 单配置档验证阶段，不是面向普通作者的正式版。

---

## 1. 这个项目解决的核心难题

学马仕是 **Unity 引擎、CPU 蒙皮** 的游戏。这带来一个和原神 / 星铁 / 鸣潮等
完全不同的约束：

- 3DMigoto 在 Draw 处抓到的顶点缓冲 `VB0` 是 **已经蒙皮变形后的当前姿势**
  （40 字节：position / normal / tangent）；
- 这个 `VB0` 里 **没有骨骼索引、没有权重、没有 T-pose**；
- Draw 之前也 **没有暴露任何 GPU 骨骼矩阵**。

因此不能照搬 GIMI/WWMI 那种「替换未蒙皮 VB + 让游戏自己蒙皮」的做法。直接替换
静态 T-pose 也不行——它不会跟随动画。

### 解法：三层数据模型

| 层 | 提供什么 | 来源 | 何时 |
|---|---|---|---|
| **静态结构** | bind pose 几何、权重、bindpose、骨骼身份 | **AssetStudio** 导出的 `Geo_Body.json` | 离线（建配置档时一次） |
| **每帧动画** | 当前帧的 152 个骨骼矩阵 | **3DMigoto 实时 `VB0`** + 离线逆算子，由 `RecoverMatricesCS` 反解 | 运行时（每帧） |
| **注入** | 把作者网格按原格式喂回游戏 | **3DMigoto hash 覆盖** + `SkinCustomCS` 重蒙皮 → 原格式 40 字节 `VB0` | 运行时（每帧） |

关键点：

- **骨骼 / 权重 / T-pose 全部来自 `Geo_Body.json`，不需要、也无法从抓帧重建。**
- **每帧动画只能来自实时 `VB0`**——它是 `RecoverMatricesCS` 的输入，缺它整个模型
  会冻结在 T-pose。AssetStudio 永远拿不到当前姿势。
- 这条链已实机验证：同源重建与游戏原动态 `VB0` 逐字节一致，误差 RMS ≈ 1e-6。
  详见 [`research/inverse-skin-matrix-recovery.md`](research/inverse-skin-matrix-recovery.md)。

### 已排除的路线（不要重蹈）

| 路线 | 为什么不可行 |
|---|---|
| 用抓帧「重建骨骼 / 权重」 | 抓到的 `VB0` 里根本没有骨骼 / 权重，无中生有 |
| 用抓帧反解「T-pose 几何」 | 数学上病态（同时求几何和矩阵），噪声放大，效果差 |
| 静态 T-pose `VB` 直接替换 | 游戏 Draw 输入已是 CPU 蒙皮结果，不跟随动画 |
| 表面驱动 / SurfaceMap 自定义 VS | 几何可见但材质退化；已删除（见 git 历史） |
| 进程内 IL2CPP Runtime 替换 Mesh | 违反「不进程内 Runtime」边界，且不稳定；已删除（见 git 历史） |

---

## 2. 仓库结构

```text
blender_addon/gakumas_mi/   作者用 Blender 插件（导入 / 转权 / 校验 / 导出）
  ├─ core.py                数据读写、缓冲打包、配置档解析
  ├─ operators.py           Blender 操作器
  ├─ ui.py                  侧边栏面板
  └─ shaders/               RecoverMatricesCS（恢复矩阵）/ SkinCustomCS（重蒙皮）
experiments/inverse-skin/   逆解蒙皮的原始验证 Compute Shader（参考）
tools/                      离线脚本：AssetStudio 批量导出、逆算子构建、配置档抽取、审计、打包
profiles/                   各角色 / 服装的配置档（drawcall / 材质 / 贴图映射）
spec/                       配置档与 manifest 的 JSON Schema
tests/                      冒烟测试与数据契约测试
research/                   研究记录与路线（含已排除路线的历史证据）
```

仅本地、不入库的工作数据（已在 `.gitignore` 中）：
`all_body/`（游戏资源）、`build/`（AssetStudio 导出）、`dist/`、`mods/`、
`checkpoints/`、`blender_addon/gakumas_mi/resources/assetstudio-body-json/`。

---

## 3. 两类工作流

### 作者侧（只用 Blender）

```text
导入配置档对象（带权重参考）
→ 在 Blender 制作 / 放置衣服并蒙皮到配置档骨架
→ 蒙皮转权（从参考身体传递权重）
→ 校验并导出模组
```

详见 [`blender_addon/README.md`](blender_addon/README.md)。

### 核心维护者侧（建配置档）

```text
AssetStudio 从 .unity3d 导出 Geo_Body.json   → 静态结构（骨骼 / 权重 / bindpose）
3DMigoto Frame Analysis 抓一次               → IB/VB hash、stride、贴图槽（注入信息）
tools/build_inverse_skin_operator.py         → 由 bind + 权重生成逆算子
```

> 提示：`Geo_Body.json` 自带 `m_Skin`（权重）/ `m_BindPose` / `m_BoneNameHashes`，
> 逆解链不依赖 `skeleton.json`（骨架层级仅用于可读性）。

---

## 4. 文档索引

### 当前文档（与当前实现一致）

| 文档 | 内容 |
|---|---|
| [README.md](README.md) | 项目总览（本文） |
| [GakumasMI_开发路线_当前草案.md](GakumasMI_开发路线_当前草案.md) | 总体产品架构与路线 |
| [research/current-status-and-roadmap.md](research/current-status-and-roadmap.md) | 当前进度、能力对比、后续计划（**最新状态以此为准**） |
| [blender_addon/README.md](blender_addon/README.md) | 作者插件：安装与一键工作流（0.4.6） |
| [3Dmigoto-MI/README.md](3Dmigoto-MI/README.md) | 运行时：安装、dev/release 配置 |
| [spec/README.md](spec/README.md) | 配置档 / manifest 的 JSON Schema |
| [research/inverse-skin-matrix-recovery.md](research/inverse-skin-matrix-recovery.md) | 逆解矩阵方案与游戏内验证报告 |

### 历史记录（保留证据，不代表当前实现）

| 文档 | 为何保留 |
|---|---|
| [research/reference-framework-comparison.md](research/reference-framework-comparison.md) | 矩阵恢复成功前的同类工具调查 |
| [research/runtime-skinning-bridge.md](research/runtime-skinning-bridge.md) | 已放弃的进程内 Runtime 路线（代码已删） |
| [research/ttmr-cstm-0119-body-plan.md](research/ttmr-cstm-0119-body-plan.md) | 已排除的骨架重定向实验 |
| [research/blender-plugin-ui-reference.md](research/blender-plugin-ui-reference.md) | 其它工具（GIMI/WWMI/EFMI）UI 参考 |
| [research/baseline/](research/baseline/) · [research/hunting/](research/hunting/) | 基准场景与 Hunting 环境记录 |

---

## 5. 风险声明

本项目是第三方视觉修改工具，用于学习与个人使用：

- 仅限用户自行承担风险，不承诺不会触发封禁；
- 不修改数值、抽卡、货币、网络或服务端逻辑；
- 不绕过反作弊或服务器校验；
- 不读取、保存或上传账号、密码与登录 Token；
- 尽量不重新分发完整官方模型 / 贴图，优先发布差异化 Buffer 与作者原创资源。
