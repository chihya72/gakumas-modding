# GakumasMI

面向《学园偶像大师》（学马仕 / Gakumas）的 **Blender + 3DMigoto 视觉 Mod 工具链**：Mod 作者
只用 Blender + 本项目插件就能换装 / 换模，**不装 Unity、不做 AssetBundle、不写 3DMigoto 配置**；
玩家侧只需装运行环境（`3dmigoto-gkms` + `mod-manager`，一个安装包搞定）。只做视觉 Mod（模型 /
贴图 / 材质 / 显隐），不碰文本汉化、逻辑、数值。

> **状态（v0.7.8，收敛/维护态）**：身体与发型（含 co/配套发饰）的换模 + 动画 + 贴图 + 多 mod
> 共存完整闭环已实机验证，Mod Manager 已发布。核心算法冻结；真半透明、表情和 LOD 暂不开展。状态与
> 计划见 [research/current-status-and-roadmap.md](research/current-status-and-roadmap.md)，
> 版本变更见 [CHANGELOG.md](CHANGELOG.md)。

## 核心思路

学马仕是 Unity **CPU 蒙皮** 游戏：抓帧拿到的 `VB0` 是已蒙皮的当前姿势，没有骨骼/权重/T-pose，
所以不能照搬 GIMI/WWMI。解法是三层数据：**静态结构**（骨骼/权重/bindpose，来自 AssetStudio
`Geo_Body.json`）+ **每帧动画**（实时 `VB0` 经 `RecoverMatricesCS` 反解 152 个矩阵）+ **注入**
（hash 覆盖 + `SkinCustomCS` 重蒙皮回原格式）。已实机验证与游戏动态 `VB0` 逐字节一致（RMS ≈ 1e-6）。
原理、验证与已排除路线见
[research/current-status-and-roadmap.md](research/current-status-and-roadmap.md) 与
[research/inverse-skin-matrix-recovery.md](research/inverse-skin-matrix-recovery.md)。

## 仓库结构

```text
gakumas_mi/     作者用 Blender 插件（导入 / 转权 / 校验 / 导出）
tools/          离线脚本（AssetStudio 导出、逆算子构建、配置档抽取、打包）
profiles/       各角色/服装配置档    tests/  冒烟与契约测试    research/  研究记录与路线
3dmigoto-gkms/  游戏 mod 插件（自编译补丁版 d3d11.dll + d3dx.ini + ShaderFixes）
mod-manager/    使用者侧 Mod 包管理器（WPF/Stylet，随 3dmigoto-gkms 发布）
```

## 文档

| 文档 | 内容 |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 仓库规范（新建文件前必读） |
| [research/current-status-and-roadmap.md](research/current-status-and-roadmap.md) | 进度 / 完成度 / 计划（**最新状态以此为准**） |
| [research/step3-texture-input-guide.md](research/step3-texture-input-guide.md) | 步骤③ Body / Hair / HairProp 贴图路径、通道和准备要求 |
| [gakumas_mi/README.md](gakumas_mi/README.md) · [3dmigoto-gkms/README.md](3dmigoto-gkms/README.md) · [mod-manager/README.md](mod-manager/README.md) | 三个子项目各自的安装与用法 |

## 致谢与上游开源

游戏注入层基于开源项目 **3DMigoto**（[bo3b/3Dmigoto](https://github.com/bo3b/3Dmigoto)）：
`3dmigoto-gkms/d3d11.dll` 是基于其 **v1.4.9** 自编译的补丁版（修学马仕竖横屏 live 切换闪屏，见
[FLIP-RESIZE-PATCH.md](3dmigoto-gkms/FLIP-RESIZE-PATCH.md)）；`nvapi64.dll`/`d3dcompiler_47.dll`
与 `ShaderFixes/` 亦取自其 v1.4.9 / 生态。许可以其[官方仓库](https://github.com/bo3b/3Dmigoto)为准。
感谢 3DMigoto 社区与 AssetStudio 等上游工具。

## 风险声明

第三方视觉修改工具，仅供学习与个人使用、风险自负：不承诺不触发封禁；不改数值/抽卡/货币/网络/
服务端逻辑；不绕过反作弊；不读取或上传账号/密码/Token；尽量不重分发完整官方模型/贴图。
