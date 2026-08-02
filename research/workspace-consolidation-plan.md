# 工作区归并与清理计划

更新：2026-07-29  
状态：**执行中；P0～P4 已完成，P5 Blend 审核进行中**

## 当前进度快照（2026-07-28）

| 阶段 | 当前状态 | 本轮已落实 | 后续门槛 |
|---|---|---|---|
| P0–P3 | 已完成 | 冻结/备份、专用插件数据核查、外层工作区建立、DLL 独立仓库重建 | 仅在最终验收时复核 |
| P4 | 已完成 | IP/SCSP 目录与流程已分析；`99-legacy-experiments` 已删除；Blend 目录、候选成品与恢复副本已登记；9 个确认候选已按项目归档并完成资源打包、独立打开验证 | 仅在最终验收时复核归档完整性 |
| P5 | 用户审核中 | 9 个候选已按正式结构归档到 `mod-workspace/mods/work/<项目>`，每个项目仅保留 blend/textures/materials/source；Blend 已通过 Blender 4.2.7 独立打开验证；B053/B054 暂并列为候选 | 用户完成 B053/B054 实测，并确认剩余候选的去留后再决定历史 source-only 项目的处理 |
| P6 | 未开始 | — | 以本计划和用户审核结果为唯一事实源，合并重复文档 |
| P7 | 未开始 | — | 代表案例、DLL、Unity、Blender 四链路验收通过后再最终删除隔离区 |

### 当前 Blend 审核基线

- 已按范围重新扫描 `D:\GIT`、用户 Desktop（明确排除 `%USERPROFILE%\Desktop\MOD`）、Documents、`D:\Games` 和 `D:\chinosk6`。
- 当前磁盘共有 20 个相关 `.blend`：9 个已整理的 MOD 候选、9 个集中保存的原始未打包备份、2 个内容完全相同的 `weighted.recovered-20260727.blend` 恢复副本；后 11 个均已核验且不纳入 MOD 候选。
- 当前权威清单为 `mod-workspace/blend-catalog.md`：9 个已整理候选、共 170,323,412 字节；原始文件哈希和大小见 `mod-workspace/backups/blend-originals/original-migration-manifest.json`。旧 P5 中间分析快照不再保留。
- `B053` 与 `B054` 均保留为百万现场演出服 Blend 候选，实测说明见 `mod-workspace/mods/work/dress-2609-mltd-stage/README.md`；在实测前不删除或合并。
- 9 个候选的可用副本位于 `mod-workspace/mods/work/<项目>/blend/`，各项目按 `textures/`、`materials/`、`source/` 保存长期资产；可重建的 exports、QA 和 build 报告已清理。原始未打包文件集中在 `mod-workspace/backups/blend-originals/`，可回退清理。结构索引见 `mod-workspace/mods/work/README.md`。
- `hair-21-hmsz-mod` 的 `hair_21_default_complete.blend` 来源缺失，原 B029 作者 Blend 已删除；该项目来源链暂列为待修复项。

## 目标

以 `D:\GIT\gakumas-modding` 作为总工作区，形成三个相互独立的一级目录：

- `D:\GIT\gakumas-modding\gakumas-modding`：当前主项目 Git 仓库；
- `D:\GIT\gakumas-modding\mod-workspace`：IP/SCSP 解包信息、制作流程、Blender 工作文件和成品 Mod；
- `D:\GIT\gakumas-modding\gakumas-mod-runtime`：从当前权威 DLL 插件实现清洗、改名后重建的独立 Git 仓库。

最终只保留权威源码、不可再生成的输入、可继续编辑的 Blender 文件、必要贴图、验证记录和发布产物。
缓存、重复副本和可重建中间产物在通过验收后删除。

## 已确认决定

1. `D:\GIT\git.chinosk6.cn\gkms-localify-dmm` 是当前最新、权威的 AB 游戏 DLL 插件实现，不是旧实现。
   需要清理的是仓库内部的废弃 Mod 包、旧业务内容、旧目录和旧命名。
2. DLL 插件不再作为主项目 submodule；以当前最新分支为源码基准，重建为独立的
   `gakumas-mod-runtime` Git 仓库。
3. `%USERPROFILE%\Desktop\MOD` 与本项目完全无关，扫描、分类、迁移和删除均不得触碰。
4. `D:\GIT\IP\99-legacy-experiments` 已确认废弃，清单和安全检查已完成，并已整体永久删除，不进入长期归档。
5. Blender 文件先由工具全面盘点、去重建议和初步分类，生成目录清单；用户逐个确认分类后，
   才从确认正确的 Blend 中提取 t0/t1/t4、抓帧路径和哈希并反查资源。
6. 下列三处是专门为插件流程准备的数据，不能按普通缓存删除，必须先查明来源和用途并独立备份：
   - `mod-workspace\libraries\assetstudio-body-json`；
   - `mod-workspace\libraries\assetstudio-hair-json`；
   - `D:\GIT\IP\06-ab-route-handoff\GakumasModeBundle_0119_Build\AssetBundles\Windows`。

   > 前两处 2026-08-02 已从 `gakumas-modding\.local\` 移入 `mod-workspace\libraries\`，
   > 与 `templates\unity` 同待遇。移动后文件数与字节数逐项核对一致。

## 安全原则

1. 先清点、备份、算哈希，再移动；先验证新位置，再删除旧位置。
2. P0 已保存当时主仓库的全部未提交工作，并逐项备份、核对 SHA-256；后续文档修改在原工作树上继续记录。
3. 未经用户确认的删除分两步：先移入隔离区，最终删除需要用户确认；用户明确授权并完成路径、大小和哈希复核后，可直接永久删除指定文件。
4. 游戏提取资产和含游戏资产的 Blender 文件保持本地忽略，不推入公开仓库。
5. 每类源码只保留一个权威副本；历史由 Git 保存，不在目录中维护多个快照。
6. Blender 文件必须在脱离原目录后仍能完整打开。
7. `.blend1` 默认不能批量删除；先检查是否存在比主文件更新或没有主文件的版本。用户明确授权并完成逐项复核后，才可批量永久删除。
8. `Desktop\MOD` 是明确排除目录；任何递归命令都必须显式排除并在结果中证明没有命中。
9. 三处专用插件数据完成来源说明、文件清单、SHA-256 和独立备份前，禁止移动或删除。
10. 用户确认 Blend 分类前，只允许读取、算哈希和生成目录，不搜索或搬运其外部资源。

## 盘点基线

| 范围 | 规模 | 当前结论 |
|---|---:|---|
| 当前主项目 | Git 根已迁入 `D:\GIT\gakumas-modding\gakumas-modding` | HEAD、分支、remote 和 P0 未提交文件哈希在迁移前后核对一致 |
| 主仓库 `.local` | 约 20.0 GiB | body/hair JSON 是受保护流程数据，其余内容另行判断 |
| 主仓库 `all_body` | 4.57 GiB | 526 个文件与 AB 解密仓库完全相同；另 4 个在源仓库有不同版本 |
| `ai-model-workspace` | 约 1.38 GiB | 源文件、构建文件和成品混放 |
| IP | 约 16.76 GiB | Unity `AssetBundles` 约 11.9 GiB，`Library` 约 3.72 GiB |
| SCSP | 约 0.90 GiB | `output` 约 0.78 GiB，共 10,326 个无扩展名输入包 |
| 权威 DLL 插件 | 独立 Git 仓库 | 当前最新 AB runtime；工作区干净，本地分支领先远端 `main` 3 个提交 |
| Blender 初次扫描 | 57 个 `.blend`、35 个备份 | 结果包含无关的 `Desktop\MOD`，必须排除后重新统计 |

历史初次扫描覆盖用户常用目录、D: 和 Z:；C: 系统目录补充扫描曾超时。当前复查已对项目相关的 `D:\GIT`、用户 Desktop（排除 `Desktop\MOD`）、Documents、`D:\Games` 和 `D:\chinosk6` 完成；如后续扩大到整个 C: 系统盘，仍需另行安排扫描。

高风险文件：

- `%USERPROFILE%\Desktop\weighted.blend1` 已恢复为 `weighted.recovered-20260727.blend`，桌面与 P0 备份各保留一份，SHA-256 已核对；原 `.blend1` 已不存在；
- 桌面 `aligned.blend`、`dress_2219_gakumas_work.blend` 仍是现存候选；`无标题.blend`（B003）已永久删除，不再列为高风险文件；
- 主仓库、IP 和 DLL 仓库中的三份 `ModRuntime.cpp` 哈希不同；
- 根 `README.md` 仍描述 v0.7.8/3DMigoto 主路线，与当前 0.9.0 AB-only 状态冲突。

### 受保护流程数据的初步判断

| 数据 | 初步用途与来源 | 本计划要求 |
|---|---|---|
| `mod-workspace\libraries\assetstudio-body-json` | `tools/export_all_body_json.py` 从 body AB 导出的 Mesh/骨架 JSON，供 Blender 插件和模板构建使用 | 查清输入目录、生成参数、AssetStudio 版本和消费者后完整备份 |
| `mod-workspace\libraries\assetstudio-hair-json` | 同一导出工具针对 hair/hairprop AB 生成的 Mesh/骨架 JSON | 查清原始 hair AB、后缀参数和缺失 sidecar 情况后完整备份 |
| `AssetBundles/Windows` | Unity 工程生成的 Windows AB，包含插件流程所需模板和测试/成品 bundle | 按 bundle 类型、生成脚本、源 commit 和可重建性分类后完整备份 |

以上只是从现有脚本得到的初步证据；正式来源说明必须用输入文件、生成命令和哈希验证。

## 目标结构

```text
D:\GIT\gakumas-modding\
├─ gakumas-modding\             # 当前主项目，保留原 Git 历史
├─ mod-workspace\               # 本地 Mod 资源工作区
│  ├─ unpack\
│  │  ├─ ip\
│  │  └─ scsp\
│  ├─ pipelines\
│  │  ├─ ip\
│  │  └─ scsp\
│  ├─ mods\
│  │  ├─ work\
│  │  └─ release\
│  ├─ backups\
│  │  └─ pipeline-resources\
│  └─ blend-catalog.md
└─ gakumas-mod-runtime\         # 清洗、改名后的独立 DLL 插件 Git 仓库
```

模型案例统一为：

```text
case-name/
├─ README.md
├─ blend/
│  └─ authoring.blend
├─ textures/
├─ materials/
└─ source/
```

## 文件分类

### 必须保留

- Git 跟踪的权威源码和配置；
- 不可重新下载或重新生成的源文件；
- 最终可编辑 Blender 文件及其源贴图；
- 生成最终结果所需的脚本、参数和清单；
- 已验证的发布包、哈希和代表性验收证据；
- 第三方项目的许可证和 Git 历史。
- 三处受保护插件流程数据及其来源说明、清单和备份。

### 验证后删除

- Unity `Library/`、`Logs/`、自动生成的 `.sln/.csproj`；
- SCSP `output/`、AssetRipper export、`_intermediate.pkl`；
- `.local/p3-textures` 等确认可重建且不属于受保护清单的缓存；
- `bin/`、`obj/`、`build/`、缓存、测试输出和普通构建日志；
- 已由权威副本取代的 handoff、插件源码和文档快照；
- 已验证无独立价值的 `.blend1`、临时 FBX/GLB 和旧导出。
- DLL 权威仓库内部已确认废弃的旧 AB Mod 包、旧业务代码和无关资源。
- `D:\GIT\IP\99-legacy-experiments`。

### 先隔离再决定

- 名称不明确的 Blender 文件；
- 事故现场、抓帧数据和旧版本 Mod；
- 与权威版本内容不同但用途尚未确认的文件。
- `AssetBundles\Windows` 中尚未确认来源或无法证明可重建的 bundle。

## 执行流程

### P0：冻结现场与抢救

状态：**已完成**。验证记录见
[`migration-p0-snapshot.md`](migration-p0-snapshot.md)。

- 保存主仓库当前未提交工作；
- 记录四个工作区的 Git 状态、分支和 commit；
- 为计划迁移的文件生成路径、大小、修改时间和 SHA-256 清单；
- 将孤立的 `weighted.blend1` 恢复为正式 `.blend`；
- 为权威 DLL 仓库和本地 3 个提交建立 `git bundle` 恢复点；
- 建立隔离区，本阶段不删除文件。

完成条件：所有现有工作都有清单和至少两份可恢复副本。

### P1：查明并备份专用插件数据

状态：**已完成**。来源、消费者、异常清单和三份逐文件哈希见
`..\..\mod-workspace\backups\pipeline-resources\inventory.md`。三组原件均保留。

- 分别统计 body JSON、hair JSON 和 Windows AssetBundles 的文件数、大小、结构和 SHA-256；
- 追踪生成脚本、输入 AB、命令参数、工具版本、Unity 版本和消费方；
- 判断每项是唯一输入、派生资源、模板、测试包还是成品包；
- 写入 `mod-workspace\backups\pipeline-resources\inventory.md`；
- 保持原目录结构建立完整备份，并对备份重算哈希；
- 原件删除前必须再有一份位于不同磁盘或用户指定位置的副本，不用硬链接代替备份。

完成条件：三处数据都能回答“是什么、从哪里来、如何生成、谁在使用、如何恢复”。

### P2：建立外层工作区

状态：**已完成**。主仓库迁移前后 HEAD、分支、remote 和未提交状态一致；外层三个一级目录已建立。

- 将当前整个 Git 仓库安全迁入 `D:\GIT\gakumas-modding\gakumas-modding`；
- 迁移前后比较 HEAD、分支、remote、Git 状态和未提交文件哈希；
- 创建 `mod-workspace` 目录骨架；
- 创建 DLL 新仓库的目标目录 `gakumas-mod-runtime`；
- 更新主项目 `CONTRIBUTING.md`，说明代码仓库与本地 Mod 资源工作区的边界。

完成条件：内层主项目 Git 状态与迁移前完全一致，三个一级目录互不嵌套 Git 状态。

### P3：清洗并重建 DLL 插件仓库

状态：**已完成**。旧运行时基线快照已按后续决定删除，
不再把可由权威 Git 仓库和构建流程恢复的副本放进 Mod workspace。

- 新仓库：`D:\GIT\gakumas-modding\gakumas-mod-runtime`；
- 初始 commit：`ba8ea793887044694262e571b314d2597962626b`；
- D/C 两份 Git bundle 均通过 `git bundle verify`；
- 9 个第一方运行时文件逐个与权威仓库匹配；
- Release DLL 构建、x64 架构和 8 个 XInput 导出均通过核查；
- 新源码树旧仓库/旧品牌关键词 0 命中；
- 原权威仓库和另一套较旧、带未提交修改的 localify 工作树均保留不动。

- 以 `D:\GIT\git.chinosk6.cn\gkms-localify-dmm` 当前最新本地分支为唯一实现基准；
- 先编译并记录基准 DLL、日志和 SHA-256；
- 只迁移当前 runtime 所需源码、依赖、构建脚本、测试和仍有效文档；
- 删除仓库内部废弃的旧 AB Mod 包、旧 GUI/汉化业务、过时样例和生成目录；
- 将目录、工程、文档、构建产物和代码标识统一改为 `gakumas-mod-runtime`；
- 清除 `git.chinosk6.cn`、`gkms-localify-dmm` 等旧仓库/旧品牌关键词；
- 在 `D:\GIT\gakumas-modding\gakumas-mod-runtime` 初始化全新 Git 仓库并建立首个干净提交；
- 新仓库构建通过后，主仓库中的旧 `ModRuntime.cpp` 快照已删除；运行时只维护 `gakumas-mod-runtime` 权威副本。

完成条件：新仓库搜索不到旧关键词和废弃 Mod 包，Release DLL 构建并通过基准回归。

### P4：分析并整理 IP/SCSP

状态：**收尾中**。目录级内容分析、废弃项判断和 Blend 关联核查已完成；尚未完成所有代表性资源迁移与重建验收。

不整体复制两个旧目录。先给每个顶层目录和关键文件登记以下分类：

- 有用的解包输入与解包流程；
- 有用的模型/Mod 制作流程；
- 可继续编辑的 Mod 项目；
- 已验证的成品 Mod；
- 受保护插件流程数据；
- 可重建缓存或构建产物；
- 重复副本；
- 已确认废弃内容；
- 暂时无法判断的内容。

处理内容：

- 把 IP/SCSP 解包信息归入 `mod-workspace\unpack`；
- 把仍有效的制作脚本归入 `mod-workspace\pipelines`；
- 把工作项目和成品分别归入 `mods\work` 与 `mods\release`；
- 保留必要 Unity `Assets/Packages/ProjectSettings`、输入、配置、许可证和不可再现证据；
- `AssetBundles\Windows` 按 P1 清单迁移和备份，不视为普通构建垃圾；
- 从 05 handoff 中提取仍然唯一的证据，移除已确认重复内容；
- 收口 03 成品、04 工作流和 06 AB handoff 的重复副本；
- HoshimiToolkit 保留许可证和可恢复的 Git 历史；
- `99-legacy-experiments` 已按废弃项目决定整体永久删除并验证不存在；
- 合并 `full_mod_export_sop.md` 与旧需求总结，解决 atlas 规则冲突；
- 判断 SCSP `output` 是唯一输入还是可从其他资源库恢复，再决定备份或删除；
- 验证后处理 Unity `Library`、普通 export、PKL、日志、备份和临时交换格式。

完成条件：每个旧目录都有明确分类和去向，并用迁移后的流程重建一个 IP 和一个 SCSP 代表案例。

### P5：Blend 初步分类、用户确认与资源反查

状态：**用户审核中**。初次盘点和多轮用户确认已完成；当前进入“确认结果固化、剩余候选逐项判断”阶段，尚未开始批量反查外部贴图和抓帧资源。

第一阶段只处理项目相关位置，显式排除 `%USERPROFILE%\Desktop\MOD`：

- 重新扫描 `.blend/.blend1/.blend2`；
- 记录 SHA-256、时间、Blender 版本、场景、对象、骨架、贴图引用和重复组；
- 给每份文件提出项目名、用途、权威版本和处理建议；
- 生成 `mod-workspace\blend-catalog.md`，保留“用户判断”空列；
- 在用户逐项确认前，不删除、不打包、不反查外部贴图；用户确认后才进入资源反查和打包阶段。

本轮已固化的用户决定：

- B016、B031：游戏参考体，已永久删除；
- B029：`hair-21-hmsz-mod` 作者/导出 Blend，已永久删除；其声明的 `hair_21_default_complete.blend` 来源缺失；
- B055、B056：`hair_21_001` SCSP 合并前/后工作文件，已永久删除；
- B053、B054：均列为“百万现场演出服”成品 Blend 候选，等待用户分别实测导出；
- `99-legacy-experiments`：已按废弃项目决定整体永久删除；
- 当前用户清单为 9 个候选，另有 2 个已核验的恢复副本不纳入候选。

用户确认后，只对判定正确的 Blend 执行：

1. 从 Blend 数据块、材质、脚本和项目记录中提取 t0/t1/t4 名称、路径、哈希和抓帧线索；
2. 按这些确定线索反查抓帧、贴图和源 AB，不用模糊猜测批量搬文件；
3. 找回 Missing Files，将路径改为相对路径；
4. 执行 Blender `Pack Resources`；
5. 复制到临时位置，脱离原目录重新打开；
6. 检查贴图、对象、骨架、材质和关键导出；
7. 只保留一份权威 authoring Blend、一份验证产物和必要输入；
8. 用户再次确认后处理备份与旧版本。

完成条件：用户确认分类，所有权威 Blend 的资源来源可追溯且在脱离旧目录后完整打开。

### P6：清理文档

- 更新根 `README.md` 的项目定位、版本和子项目地图；
- 精简 `research/current-status-and-roadmap.md`；
- 从 `universal-mod-automation-plan.md` 提取仍有效的结论和任务；
- 合并重复的 bundle roadmap；
- 插件状态文档只保留 `gakumas-mod-runtime` 仓库版本；
- 合并 SCSP 两份规范；
- 保留带日期的 RC/事故证据，完成计划由 Git 历史保存；
- 修复所有迁移后的相对链接和命令。

完成条件：同一事实只有一个权威文档，其他文档只引用它。

### P7：验收与最终删除

- 运行 Python 测试；
- 对所有权威 Blend 做 headless 外部资源审计；
- 构建 DLL Release；
- 构建一个代表性 Unity bundle；
- 核对三处受保护流程数据的原件、异盘备份，以及正式插件模板库的哈希；
- 检查 Markdown 链接、绝对路径和 Git 状态；
- 输出保留、迁移、隔离、删除和空间变化清单；
- 用户确认后永久删除隔离区。

完成条件：代码、DLL、Unity 和 Blender 四条链路都通过代表性验证。

## 计划中的文档权威关系

| 内容 | 权威位置 |
|---|---|
| 主项目总览 | `gakumas-modding/README.md` |
| 主项目仓库规则 | `gakumas-modding/CONTRIBUTING.md` |
| 当前能力和后续路线 | `gakumas-modding/research/current-status-and-roadmap.md` |
| 本次工作区归并流程 | 本文 |
| IP 游戏数据解包 | `mod-workspace/unpack/ip/README.md` |
| IP Unity 模板批量生成 | `mod-workspace/pipelines/ip/README.md` |
| SCSP 游戏数据解包 | `mod-workspace/unpack/scsp/README.md` |
| SCSP 模型整理 | `mod-workspace/pipelines/scsp/README.md` |
| Blend 候选清单和用户判断 | `mod-workspace/blend-catalog.md`、`mod-workspace/manual-validation.md` |
| DLL 实现、构建与状态 | `gakumas-mod-runtime/README.md` 及其 `docs/` |
| 单个 Mod 的输入和结果 | `mod-workspace/mods/work/<项目>/README.md` |
| Release 候选清单 | `mod-workspace/mods/release/README.md` |
| 专用插件数据来源与备份 | `mod-workspace/backups/pipeline-resources/inventory.md` |

## 待用户确认或修改

- 依次人工检查 9 个 Blend 的造型、权重、材质和实际导出效果；
- 依次人工检查 4 个 release 候选的游戏内结果；
- 9 个整理版 Blend 全部确认后，决定是否删除 `backups/blend-originals` 回退副本。

后续修改本计划时，先更新上述决定和对应阶段，再开始实际迁移。
