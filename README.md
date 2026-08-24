# GakumasMI

面向《学园偶像大师》（学马仕 / Gakumas）的 **Blender 视觉 Mod 工具链**：Mod 作者只用
Blender + 本项目插件就能换装 / 换模，**不装 Unity、不写 3DMigoto 配置**。只做视觉 Mod
（模型 / 贴图 / 材质 / 显隐），不碰文本汉化、逻辑、数值。

> **状态（插件 v1.3.0，正式版）**：插件只做 **AB（AssetBundle）路线**，3DMigoto 逆蒙皮的传权与导出
> 已整体移除。身体与发型（含 co/配套发饰）的换模 + 贴图 + 骨映射闭环已实机验证；插件现采用
> 目标、作者模型、材质、骨架、检查导出的五阶段单页工作流。当前 AB 路线已从发布 ZIP
> 全新安装走通，并产出了 **7 个进游戏的成品 mod**（6 件服装 + 1 个发型，覆盖
> `atbm-cstm-0140` / `fktn-cstm-0119` / `fktn-othr-0002` / `hmsz-cstm-0059` / `ttmr-cstm-0111`
> / `ttmr-cstm-0119` / `ttmr-hair-0002`）。八家骨名预设里 MMD 与 SCSP 有真实模型样本，另外
> 六家只按公开命名规范写成、没拿到对应模型，认不出来时走面板逐行点选。**自建摇物骨已于
> 2026-08-11 用 `hmsz-fuyuko-icu` 取得第一个稳定画面级案例**；幅度手感仍需逐件目视调整。逐项验证等级见
> [research/ab-target-rig-route-2026-08-17.md](research/ab-target-rig-route-2026-08-17.md) §0。

> **维护与排障必读**：本仓 Blender 插件、离线工具和制作流程的审计结论、已知风险与按现象
> 排查入口见 [research/lessons-learned.md](research/lessons-learned.md)。遇到导入、烘焙、导出或打包异常时
> 先查这份台账。

## 核心思路

学马仕角色网格是 Unity **CPU 蒙皮**，抓帧拿到的 `VB0` 是已蒙皮的当前姿势，没有骨骼/权重/
T-pose，所以不能照搬 GIMI/WWMI。现在的解法**不去逆解**：把作者的网格作为真正的 Unity 资产
打成 AssetBundle 交给游戏，让**引擎自己蒙皮**。

- **作者模型自带的权重原样保留**，插件只把骨名换成游戏骨名，不做权重传递；
- 骨架以游戏原版那套为准：同名骨不改 bindpose（实测逐元素偏差 0）；源模型自带的装饰骨
  （蝴蝶结、缎带）可作为**源专属新增骨**由运行时按 sidecar 在 prefab graft 阶段新建；
  `hmsz-fuyuko-icu` 的飘带/长链已画面级验证；
- 骨名认不出来时由作者在「骨骼映射表」里点选，覆盖率不取决于插件认识多少种命名规范；
- 导出前查 21 个承重关节有没有拿到权重，缺任一根拒绝导出并点名。

3DMigoto 在本工具链里**只剩抓帧工具**这一个角色——做配置档必须用它抓帧。原理、验证与
已排除路线见 [research/ab-target-rig-route-2026-08-17.md](research/ab-target-rig-route-2026-08-17.md) §13「明确不做」。

## 仓库结构

```text
gakumas_mi/     作者用 Blender 插件（导入 / 骨映射 / 材质 / 导出 AB bundle）
tools/          离线脚本（AssetStudio 导出、模板构建、配置档抽取、bundle 补丁、打包）
profiles/       各角色/服装配置档    tests/  冒烟与契约测试    research/  研究记录与路线
3dmigoto_gkms/  抓帧环境（自编译补丁版 d3d11.dll + d3dx.ini + ShaderFixes）
docs/wiki/      面向 mod 作者的使用手册（GitHub Wiki 镜像）
```

## 怎么拿

Release 里只有一个包 **`gakumas-mod-toolkit-<版本>.zip`**，解开是：

```text
安装说明.txt
blender-addon/gakumas_mi-<版本>.zip   Blender「从磁盘安装」选它
3dmigoto_gkms/                        整个拷进游戏根目录，进游戏按 F8 抓帧
```

还需要自己装 Python 3.10+ 并 `pip install UnityPy Pillow`（导出时打包 bundle 用，
不能用 Blender 自带的）。完整步骤见 [docs/wiki/Home.md](docs/wiki/Home.md)。

## 同级仓库（不属于本仓库，独立 Git）

游戏侧运行时在父目录下的一个独立仓库，本仓库不做 submodule、不复制其源码：

| 目录 | 产物 | 职责 |
|---|---|---|
| `../gakumas-mod-runtime/` | `xinput1_3.dll` | 扫描本地 Mod、拦截资源加载、替换 Mesh/骨架/贴图，提供 Runtime API v1，并内含游戏内 Mod 管理 UI |

游戏内管理 UI 曾经是独立的 `xinput9_1_0.dll`，现已并进同一个 `xinput1_3.dll`，玩家只装一个文件。

插件导出的 `.bundle` + `mod.json` 放进 `gakumas-mod/mods/<mod-id>/`；
`gakumas-mod-runtime` 另外要求骨架 sidecar 带匹配的 `runtimeProtocol` 与 `buildId`。旧插件导出的
无协议包或协议不匹配包会被新版 Runtime 拒绝完整替换；这是防止错误骨架数据混用的预期行为，
应从原 `.blend` 用当前插件重新导出，不要手改 sidecar 冒充兼容。
chinosk6 的 `gkms-localify-dmm` 读的是它自己的 `gakumas-local/local-files/mods/<mod-id>/`，
两个目录互不读取，具体放哪个见 [gakumas_mi/README.md](gakumas_mi/README.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/wiki/Home.md](docs/wiki/Home.md) | **作者使用手册**：环境、概念、五阶段工作流、发型/透明专题、排错 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 仓库规范（新建文件前必读） |
| [research/ab-route-notes.md](research/ab-route-notes.md) | AB 路线的数据侧脚本与新骨摆动物理记录 |
| [research/lessons-learned.md](research/lessons-learned.md) | **反面教训汇总**：已排除的路线、作废的做法、被推翻的结论 |
| [gakumas_mi/README.md](gakumas_mi/README.md) · [3dmigoto_gkms/README.md](3dmigoto_gkms/README.md) | 两个子项目各自的安装与用法 |

## 许可

本仓库自有代码见 [LICENSE](LICENSE)；第三方组件与再分发的二进制见
[third-party-notices.md](third-party-notices.md)。

游戏注入层基于开源项目 **3DMigoto**（[bo3b/3Dmigoto](https://github.com/bo3b/3Dmigoto)）：
`3dmigoto_gkms/d3d11.dll` 是基于其 **v1.4.9** 自编译的补丁版（修学马仕竖横屏 live 切换闪屏，
补丁源码与重编译步骤见 [FLIP-RESIZE-PATCH.md](3dmigoto_gkms/FLIP-RESIZE-PATCH.md)）；
`nvapi64.dll`/`d3dcompiler_47.dll` 与 `ShaderFixes/` 亦取自其 v1.4.9 / 生态。
感谢 3DMigoto 社区与 AssetStudio 等上游工具。

## 风险声明

第三方视觉修改工具，仅供学习与个人使用、风险自负：不承诺不触发封禁；不改数值/抽卡/货币/网络/
服务端逻辑；不绕过反作弊；不读取或上传账号/密码/Token；尽量不重分发完整官方模型/贴图。
