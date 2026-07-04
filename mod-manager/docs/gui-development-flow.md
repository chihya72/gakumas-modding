# Gakumas Mod Manager GUI 稳定开发流程规划

日期：2026-07-03。来源参考图：[`gui-light-orange-reference.png`](gui-light-orange-reference.png)。

本文把白色 + 橙黄色主题 GUI 参考图拆成可持续开发的工程流程。目标不是一次性复刻整张图，
而是按稳定的产品骨架逐步推进：每个阶段都有可运行界面、可测试的数据层、可回退的文件操作。

> **当前实现进度**统一记录在 [`../README.md`](../README.md)（唯一进度出处，本文只管
> 界面拆解与阶段规划，不再维护进度流水账）。总体规划见 [`plan.md`](plan.md)。

## 1. 界面拆解

界面拆成以下长期维护模块（单页布局，无多页导航）：

| 区域 | 用户价值 | 工程模块 |
|---|---|---|
| 顶部工具栏 | 选择游戏目录、刷新、F10 重载 | `workspace_state` / `game_path` |
| Mod 列表 | 管理 Mods 目录里的所有包 | `mod_scanner` / `mod_table_model` |
| 右侧详情 | 查看 manifest、完整性、冲突、启停操作 | `package_detail` / `package_actions` |
| 底部日志 | 让用户知道工具做了什么、失败在哪里；按级别筛选 | `app_log` |

> 早期参考图里的左侧导航、筛选标签、搜索框、抓帧补全卡片均为占位，从未接线且已随范围收敛移除
> （单页工具不需要多页导航；抓帧补全 2026-07-04 移出范围）。本表只列真正实现的模块。

开发原则：先让每个模块拥有稳定的数据接口，再逐步替换 UI 细节。UI 可以重画，数据契约不要频繁漂移。

## 2. 推荐目录结构

仓库内新增 `mod-manager/`，作为 `3dmigoto-gkms` 后续更新的一部分维护；包管理器代码、测试、启动脚本都收拢在这个目录下。

```text
mod-manager/
  GakumasModManager.sln
  run_gakumas_mm.bat
  src/GakumasModManager/
    App.xaml
    Bootstrapper.cs           # Stylet Bootstrapper<RootViewModel>
    Views/
      RootView.xaml
      RootView.xaml.cs
    ViewModels/
      RootViewModel.cs
    Models/
      ModPackage.cs           # ModPackage / ValidationIssue / PackageStatus
      LogEntry.cs
    Services/
      AsstProxy.cs            # ViewModel 调用的业务门面（含打开日志/键位说明）
      ScannerService.cs       # 扫描 Mods 目录 + conflict key 检测
      PackageActionsService.cs # 启用/禁用（DISABLED 前缀改名）
      PackageInstallService.cs # 拖拽安装（文件夹/zip 进 Mods）
      SettingsService.cs      # 游戏路径记忆（settings.json）
      ReloadGameService.cs    # F10 重载
      AppLogService.cs        # 日志文件写入
    Converters/
      CoverImageConverter.cs  # 封面图 OnLoad 读入（不锁文件）
    Core/
      NativeMethods.cs        # LibraryImport 原生 DLL 边界
    Res/
      Theme.xaml              # 白色 + 橙黄色主题 token
      Style.xaml              # 控件样式
  tests/GakumasModManager.ScannerSmoke/
```

规则：

- `Views/` 只负责 XAML 展示和极薄的 `.xaml.cs` 初始化，不直接读写真实文件。
- `ViewModels/` 只维护绑定状态和命令，不直接调用 Win32 或修改文件。
- `Services/` 可以操作文件，但必须通过可测试的小对象组织。
- `Core/NativeMethods.cs` 只放 `LibraryImport` 原生边界；`AsstProxy` 负责把 native/core 能力包装成 ViewModel 能用的方法。

## 3. 先定义稳定数据模型

第一批模型只覆盖图上已经出现的状态，避免过早设计大而全的抽象。

```csharp
public sealed class ModPackage
{
    public required string Name { get; init; }
    public string? Author { get; init; }
    public string? Version { get; init; }
    public required PackageType Type { get; init; }
    public required PackageStatus Status { get; init; }
    public required bool IsEnabled { get; init; }
    public string? Target { get; init; }
    public string? CoverPath { get; init; }
    public IReadOnlyList<ValidationIssue> Checks { get; init; } = [];
    public IReadOnlyList<string> Conflicts { get; init; } = [];
}
```

```csharp
public sealed record ValidationIssue(string Text, string Severity = "Info");
```

```csharp
public sealed record OperationResult(
    bool Ok,
    string Message,
    IReadOnlyList<string> ChangedPaths,
    IReadOnlyList<LogEntry> LogEvents);
```

这些模型对应 UI 上的几个核心事实：

- 列表行需要 `name / author / version / target / enabled / status`。
- 详情面板需要 `manifest_path / ini_files / issues / cover_path`。
- 操作按钮只接收一个 `ModPackage`，返回 `OperationResult`。
- 底部日志只消费 `LogEvent`，不关心操作来自哪里。

## 4. 开发阶段

### 阶段 A：静态 UI 骨架

目标：复刻参考图的布局，但先使用假数据。

交付：

- 主窗口、顶部工具栏、Mod 列表、右侧详情、底部日志全部可见。
- 白色 + 橙黄色主题 token 固化到 `Res/Theme.xaml` / `Res/Style.xaml`。
- 窗口缩放时布局不崩，列表和详情面板保持可读。

验收：

- 无真实文件操作。
- 选择列表行、右侧详情同步更新。
- 截图对比参考图，确认视觉方向正确。

### 阶段 B：真实扫描，只读模式

目标：从用户选择的游戏目录扫描 `Mods/`，但不修改任何文件。

交付：

- 游戏目录选择和记忆。
- 扫描 GakumasMI 包：含 `manifest.json` 的目录。
- 扫描通用 3DMigoto 包：含 `.ini` 但无 manifest 的目录。
- 列表展示真实包，详情面板展示 manifest 摘要。
- 缺文件、JSON 错误、DDS 检查错误显示为 warning/error。

验收：

- 对测试 fixture 运行扫描测试。
- 损坏包不会让 UI 崩溃，只在状态列显示“损坏”。
- 未识别目录不会被误删或移动。

### 阶段 C：启用 / 禁用 / F10 重载

目标：实现最常用的管理闭环。

交付：

- 禁用：目录名前加 `DISABLED` 前缀。
- 启用：去掉 `DISABLED` 前缀。
- 操作前检测重名冲突。
- 操作完成后刷新列表并写日志。
- F10 重载按钮：能发送则发送，失败则提示用户回游戏手动按 F10。

验收：

- 文件操作有单元测试，覆盖已禁用、重名、路径不存在。
- 不编辑 `d3dx.ini` 就能完成启停。
- 操作失败时不留下半改名状态。

### 阶段 D：d3dx.ini / 键位（已收敛为不做图形化设置页）

> 原计划做 d3dx.ini 快捷设置面板（Hunting/备份/回滚），后废弃：d3dx.ini 有 ~87 项、
> 大半是 mod 作者抓帧快捷键与高级兼容项，图形化暴露风险大于收益，且用户明确不要原文编辑。

现状交付：

- 插件默认 `hunting=2`：F10/F8/F9 可用但绿色调试 HUD 默认关闭（小键盘 0 临时开）。
- 随插件发 `键位说明.txt`（游戏根目录）讲清键位；管理器「键位说明」按钮打开它。
- 「打开 3DMigoto 日志」按钮打开游戏目录 `d3d11_log.txt`（需 `[Logging] calls=1`）。
- 管理器不写 d3dx.ini（无设置面板、无备份/回滚 UI）。

### 阶段 E：右侧详情完善与冲突检测

目标：让图中的详情面板成为用户判断“这个包是否健康”的主入口。

交付：

- 文件完整性 checklist。
- DDS 格式检查。
- `conflicts` key 聚合，同 key 多个启用包标为冲突。
- 详情页 tabs：详情 / 文件 / 配置 / 冲突。

验收：

- 同时启用两个相同 conflict key 的包，列表和详情均提示。
- 通用 3DMigoto 包不强行要求 manifest。
- 检查耗时长时 UI 不冻结。

> 原「阶段 F：抓帧补全 slotVariants」已于 2026-07-04 移出范围（gakumas-mi 0.7.2
> 运行时全局布局探测后不再需要），阶段 E 即为最后一个功能阶段。

## 5. UI 细节实现顺序

不要先追求像素级还原。建议按下面顺序落地：

1. 布局稳定：顶部栏、主列表、右详情、底部日志。
2. 状态稳定：扫描中、空列表、损坏包、无游戏目录、操作失败。
3. 操作稳定：启用、禁用、刷新、F10、备份。
4. 视觉完善：封面、橙黄色选中态、状态标签、图标按钮。
5. 高级流程：d3dx.ini 写入、冲突检测。

视觉 token 建议：

| 用途 | 颜色 |
|---|---|
| 主操作 / 当前选中 | `#ff9f00` |
| hover / 浅选中背景 | `#fff3df` |
| 页面背景 | `#f7f8fa` |
| 面板背景 | `#ffffff` |
| 边框 | `#e5e7eb` |
| 主文本 | `#1f2937` |
| 次级文本 | `#6b7280` |
| 成功 | `#22a06b` |
| 警告 | `#f59e0b` |
| 错误 | `#dc2626` |

## 6. 每次迭代的固定流程

每个功能都按同一套小循环推进：

1. 写 fixture：准备最小真实目录样本。
2. 写服务层测试：先验证扫描、改名、ini 写入。
3. 接 UI：让按钮调用服务层，不在 UI 中实现业务逻辑。
4. 加日志：成功、失败、跳过都进入底部日志。
5. 手动验收：用一份真实 Mods 目录跑一遍。
6. 截图检查：确认布局没有因为新字段变形。
7. 记录边界：把发现的特殊包、特殊 d3dx.ini 写成新 fixture。

这套流程的重点是：每次新增 GUI 功能时，都同时沉淀一个 fixture 和一个服务层测试。
这样界面可以持续改，但核心文件操作不会越改越怕。

## 7. 测试矩阵

| 模块 | 必测场景 |
|---|---|
| 扫描 | 空 Mods、正常 GakumasMI、通用 3DMigoto、损坏 JSON、DISABLED 前缀 |
| 启停 | 启用、禁用、重名冲突、路径不存在、重复操作 |
| manifest | v1/v2、目标为游戏资源名、缺 cover（旧包/手工包）、缺 version、materials 文件缺失 |
| DDS | 正常 DDS、缺失 DDS、格式不匹配、读取失败 |
| d3dx.ini | 正常写入、字段缺失、注释保留、备份清理、回滚 |
| 冲突 | 无冲突、两个包冲突、禁用包不参与冲突 |
| UI | 无目录、扫描中、选中项消失、窗口缩放 |

## 8. 发布前稳定性清单

每个阶段合并前检查：

- 没有不可逆文件操作；写入前必须有备份或可证明是安全改名。
- UI 线程不做长时间扫描或 DDS 检查。
- 所有失败都返回用户可理解的错误信息。
- 操作后列表状态刷新，不依赖用户手动重启应用。
- 日志能说明“做了什么、改了哪里、失败原因是什么”。
- 新增功能至少有一个 fixture 覆盖。

## 9. 推荐第一轮任务拆分

第一轮先把管理器变成一个可靠的“只读 + 启停”工具。

1. 建 `mod-manager/src/GakumasModManager/` WPF 基础工程和 Stylet 启动入口。
2. 实现 `Views/RootView.xaml` 与白色 + 橙黄色主题资源。
3. 用假数据完成参考图布局。
4. 实现 `ModPackage` / `ValidationIssue` / `OperationResult`。
5. 实现 Mods 目录扫描。
6. 接入真实列表和详情面板。
7. 实现 DISABLED 前缀启用/禁用。
8. 加 fixture 和单元测试。

完成后，用户已经能稳定管理 Mods 目录；后续再叠加 d3dx.ini 写入和冲突检测，风险会小很多。
