# 仓库规范（结构 / 命名 / 文档 / 提交 / 发布）

本文是本仓库的**唯一结构与流程规范**。新建任何文件、目录、文档、提交前先对照本文；
规范本身要改，先改本文再改仓库。

## 1. 仓库地图（新文件落点规则）

| 位置 | 职责 | 新文件落点规则 |
|---|---|---|
| `gakumas_mi/` | Blender 作者插件（产品线 1，版本 0.9.x） | 插件代码/着色器/预设只放这里 |
| `3dmigoto-gkms/` | 抓帧环境（产品线 2，版本 0.7.x） | d3d11.dll、d3dx.ini、ShaderFixes、`installer/` 的 Inno Setup 脚本 |
| `tools/` | 离线脚本（导出/构建/审计/打包） | 一个脚本一个文件，snake_case |
| `tests/` | Python 回归/冒烟测试 | `test` 语义文件名，CI 可跑的进 `ci.yml` |
| `profiles/` | 角色/服装配置档 | `<actor>-<costume>/` 一档一目录 |
| `experiments/` | 已验证但非主线的探索代码 | 一条路线一个子目录，必须带 README |
| `research/` | 技术记录与抓帧证据数据 | 见第 3 节文档规范；**先看能不能并进已有文档，别新开** |
| `docs/wiki/` | 面向 mod 作者的使用手册（GitHub Wiki 镜像） | 一页一文件，页间用 `[[页名]]` 互链 |
| 仓库根目录 | **只允许** `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、`LICENSE`、`third-party-notices.md` 与 dot 配置文件 | **禁止新增其它根目录文件**（`LICENSE` 必须在根，GitHub 才能识别） |

产品文档跟产品走：某产品线的设计/使用文档放该产品目录（如
`3dmigoto-gkms/FLIP-RESIZE-PATCH.md`）；跨产品的研究、抓帧证据、路线记录才进 `research/`。

本地数据目录（gitignored，永不入库）：`.local/`、`dist/`、
`gakumas_mi/resources/assetstudio-body-json/`。
`.local/` 只放**可重建的**本机产物（测试输出、UI 预览、抓帧探针、QA 快照）；
体积大又难重建的资源库放仓库外的 `..\mod-workspace\libraries\`，见下节。
根目录 `build/` 禁止使用。作者工作文件（脚本、源文件、中间产物、QA 图、Blend、成品包）
全部放仓库外的 `..\mod-workspace\mods\work\<项目>\`；测试输出与本机临时产物放 `.local/`；
Blender 插件 ZIP 和抓帧环境安装包只放 `dist/`。

### 外层工作区边界

本仓库只占用工作区里的 `gakumas-modding/` 一级目录。其父目录下另外三个一级目录不是本仓库内容：

| 同级目录 | 职责 | 边界 |
|---|---|---|
| `..\mod-workspace\` | 本地 IP/SCSP 解包输入、Mod 工作文件、Blend、成品和受保护数据备份 | 不纳入 Git，不提交游戏提取资产 |
| `..\mod-workspace\libraries\` | AssetStudio 导出的 body / hair Mesh JSON 资源库（约 7.8 GB） | 与 `templates\unity` 同级同待遇：插件与 `build_phase3_templates.py` 直接读，永不入库，清理前须核对备份 |
| `..\gakumas-mod-runtime\` | 游戏运行时 `xinput1_3.dll` 源码与构建 | 独立 Git（GPL-3.0），不复制进本仓库、不设为 submodule |
| `..\gakumas-in-game-mod-manager\` | 游戏内 Mod 管理 UI `xinput9_1_0.dll` 源码与构建 | 独立 Git（GPL-3.0）；编译依赖 `..\gakumas-mod-runtime\` 的 premake 与已编译 `minhook.lib` |

跨目录工具不得假定旧的绝对路径；迁移完成后应通过命令行参数或集中配置定位本地数据。
公开仓库文档只描述接口和工作流，不复制 `mod-workspace` 的私有资产清单。

## 2. 命名规范

- **目录**：产品线与普通目录用 kebab-case（`docs/wiki`、`3dmigoto-gkms`）；
  Python 包用 snake_case（`gakumas_mi`）。
- **文件**：Python `snake_case.py`；PowerShell `kebab-case.ps1`；
  Markdown 一律 **kebab-case 英文文件名**（内容可以是中文）。**禁止中文文件名**。
  - **唯一例外 `docs/wiki/`**：它是 GitHub Wiki 的镜像，文件名就是页面标题，
    `[[页名]]` 按文件名解析。改名会同时改掉页面标题和所有互链，所以保持中文原名。
- **带日期的文档**：会话复盘 `session-YYYYMMDD-<topic>.md`；一次性证据快照
  `<topic>-YYYYMMDD[-HHMMSS].md`。无日期的文件名表示「持续维护的活文档」。

## 3. 文档规范

**四份权威文档**（状态冲突时以此为准，相关事实变化时同步更新）：

| 文档 | 权威范围 |
|---|---|
| `README.md` | 项目总览、仓库结构、工作流入口 |
| `CHANGELOG.md` | Blender 插件（gakumas-mi）逐版本变更；release workflow 从它生成 notes，**不可移动** |
| `research/current-status-and-roadmap.md` | 当前状态、完成度、后续计划 |
| `research/README.md` | research 目录索引 |

规则：

1. **新文档必须登记**：research 下新增文档，同一提交里登记进 `research/README.md` 索引。
2. **进度只有一个出处**：同一事实不得在多份文档维护副本；其它地方只放链接。
   （产品实现进度记录在该产品 README；项目级状态记录在 current-status-and-roadmap。）
3. **完成即删除**：计划、会话复盘和重复说明在结论并入权威文档后删除，历史由 Git 保存。
4. 文档内引用仓库文件用相对路径 Markdown 链接，不写裸路径。

## 4. 提交规范

格式：`type(scope): 中文描述`（scope 单产品时可省略括号仅在 type 后接冒号）。

- **type**：`feat` / `fix` / `docs` / `test` / `refactor` / `ci` / `chore`
- **scope**：`gakumas-mi` · `3dmigoto-gkms` · `tools` · `profiles` · `research` · `repo`
- 一次提交一个主题；文档对齐可以跟随功能提交，不单独拆。
- 发布提交固定为 `Release <产品> X.Y.Z`（例：`Release GakumasMI 0.7.2`）。

## 5. 版本与发布规范

- **版本线独立，绝不同步**：`gakumas_mi`（Blender 插件 0.9.x）与 `3dmigoto-gkms`
  （抓帧环境 0.7.x）各自演进。
- Release tag 用产品前缀：`gakumas-mi-vX.Y.Z` / `3dmigoto-gkms-vX.Y.Z`；
  Release 标题写明组件，不用笼统的 "GakumasMI vX"。
- gakumas-mi 发版三件套：`gakumas_mi/__init__.py` 的 `bl_info["version"]` +
  `CHANGELOG.md` 版本段 + tag，缺一不发。
- Blender tag 必须使用注解格式：首行写简短版本主题，空行后写面向用户的 `- ` 变更列表。
  Release 固定渲染为 `GakumasMI Blender 插件 **X.Y.Z** — 主题` + `本版变动：` + 列表 +
  Full Changelog；禁止直接复制技术型 CHANGELOG、测试流水账或仓库内部链接。
- 抓帧环境 Release 固定为 `本版更新` + `这个包是什么` + `安装`（由 workflow 拼好）+ Full Changelog。
- 发布 zip 只打 git 跟踪文件（`tools/package_blender_addon.py` 已强制），
  防止本地 gitignored 数据混入。
