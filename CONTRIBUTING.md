# 仓库规范（结构 / 命名 / 文档 / 提交 / 发布）

本文是本仓库的**唯一结构与流程规范**。新建任何文件、目录、文档、提交前先对照本文；
规范本身要改，先改本文再改仓库。

## 1. 仓库地图（新文件落点规则）

| 位置 | 职责 | 新文件落点规则 |
|---|---|---|
| `gakumas_mi/` | Blender 作者插件（产品线 1，版本 0.7.x） | 插件代码/着色器/预设只放这里 |
| `3dmigoto-gkms/` | 游戏 mod 插件（产品线 2，版本 0.4.x） | d3d11.dll、d3dx.ini、ShaderFixes |
| `mod-manager/` | 使用者侧包管理器（随产品线 2 发布） | `src/` C# 代码、`tests/` smoke、使用说明放 README |
| `tools/` | 离线脚本（导出/构建/审计/打包） | 一个脚本一个文件，snake_case |
| `tests/` | Python 回归/冒烟测试 | `test` 语义文件名，CI 可跑的进 `ci.yml` |
| `profiles/` | 角色/服装配置档 | `<actor>-<costume>/` 一档一目录 |
| `experiments/` | 已验证但非主线的探索代码 | 一条路线一个子目录，必须带 README |
| `research/` | 研究文档与抓帧证据数据 | 见第 3 节文档规范 |
| 仓库根目录 | **只允许** `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md` 与 dot 配置文件 | **禁止新增其它根目录文件** |

产品文档跟产品走：某产品线的设计/使用文档放该产品目录（如
`3dmigoto-gkms/FLIP-RESIZE-PATCH.md`）；跨产品的研究、抓帧证据、路线记录才进 `research/`。

本地数据目录（gitignored，永不入库）：`all_body/`、`build/`、`dist/`、`checkpoints/`、
`ai-model-workspace/`、`.local/`、`gakumas_mi/resources/assetstudio-body-json/`。
AI 会话产物、临时脚本一律进 `ai-model-workspace/` 或系统临时目录，不落仓库。

## 2. 命名规范

- **目录**：产品线与普通目录用 kebab-case（`mod-manager`、`3dmigoto-gkms`）；
  Python 包用 snake_case（`gakumas_mi`）；C# 项目用 PascalCase（`GakumasModManager`）。
- **文件**：Python `snake_case.py`；PowerShell `kebab-case.ps1`；C# 跟 .NET 惯例 PascalCase；
  Markdown 一律 **kebab-case 英文文件名**（内容可以是中文）。**禁止中文文件名**。
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
- **scope**：`gakumas-mi` · `3dmigoto-gkms` · `mod-manager` · `tools` · `profiles` · `research` · `repo`
- 一次提交一个主题；文档对齐可以跟随功能提交，不单独拆。
- 发布提交固定为 `Release <产品> X.Y.Z`（例：`Release GakumasMI 0.7.2`）。

## 5. 版本与发布规范

- **版本线独立，绝不同步**：`gakumas_mi`（Blender 插件 0.7.x）与 `3dmigoto-gkms`
  （游戏插件 0.4.x）各自演进；`mod-manager` 跟随 `3dmigoto-gkms` 的版本与 tag。
- Release tag 用产品前缀：`gakumas-mi-vX.Y.Z` / `3dmigoto-gkms-vX.Y.Z`；
  Release 标题写明组件，不用笼统的 "GakumasMI vX"。
- gakumas-mi 发版三件套：`gakumas_mi/__init__.py` 的 `bl_info["version"]` +
  `CHANGELOG.md` 版本段 + tag，缺一不发。
- 发布 zip 只打 git 跟踪文件（`tools/package_blender_addon.py` 已强制），
  防止本地 gitignored 数据混入。
