# Gakumas Mod Manager

面向**使用者**的 GakumasMI Mod 包管理器（WPF / XAML / Stylet MVVM）。作为
`3dmigoto-gkms` 后续更新的一部分维护与发布，版本号、Release tag 与其保持一致。

## 目录

- `src/GakumasModManager/`：WPF 桌面应用。
  - 界面层：`Views/` + `Res/Theme.xaml` / `Res/Style.xaml`（白色 + 橙黄色主题）。
  - MVVM / IoC：Stylet，启动点 `Bootstrapper : Bootstrapper<RootViewModel>`。
  - 控件与视觉库：`HandyControl`（其余按需再引，避免空挂未用依赖）。
  - `Services/`：文件操作与核心逻辑（扫描/启停/重载/d3dx.ini）；
    `Core/NativeMethods.cs` 只放 Win32 边界，`Services/AsstProxy.cs` 包装给 ViewModel。
- `tests/GakumasModManager.ScannerSmoke/`：扫描、启停、d3dx.ini 备份的 smoke 测试。
- `GakumasModManager.sln`：包管理器专用解决方案。
- `run_gakumas_mm.bat`：本地启动脚本。

## 运行

```powershell
cd mod-manager
dotnet run --project src\GakumasModManager\GakumasModManager.csproj
```

或从仓库根目录双击 `mod-manager\run_gakumas_mm.bat`。

## 验证

```powershell
dotnet build mod-manager\GakumasModManager.sln
dotnet run --project mod-manager\tests\GakumasModManager.ScannerSmoke\GakumasModManager.ScannerSmoke.csproj
```

## 当前进度（唯一进度出处）

已实现：

- 只读扫描 `GamePath/Mods`：含 `manifest.json` 的目录识别为 GakumasMI 包；
  只含 `.ini` 的识别为通用 3DMigoto 包；`DISABLED*` 前缀识别为已禁用；损坏 manifest 有基础识别。
- 完整性校验：`manifest.materials[*].file` / `opacityTexture.file` 文件存在性检查、
  `.dds` 轻量文件头校验、同一 conflict key 多个启用包聚合标记为真实冲突。
- 启用/禁用：`DISABLED` 前缀改名，操作前检查重名冲突，操作后刷新列表并写日志。
- F10 重载：按游戏目录、窗口标题、进程名寻找候选窗口，切前台后发送 F10；失败写日志提示手动按。
  程序 manifest 已设 `requireAdministrator`（F10 自动重载需与游戏同权限级别）。
- 重载可靠性：**启动时自动确保 d3dx.ini `[System] check_foreground_window=0`**（`D3dxReloadService`），
  让 3DMigoto 在游戏非前台时也响应 F10 —— 否则外部 F10 必须先抢前台，而 Windows 抢前台不可靠会导致
  「概率重载」。该写入对已运行的游戏需下次启动生效；插件出厂 d3dx.ini 已默认 0。
- 不做 d3dx.ini 图形化设置页（选项太多且多为 mod 作者抓帧快捷键/高级兼容项，暴露风险大）。
  改为随插件发一份 `键位说明.txt`（游戏根目录）讲清键位；管理器「键位说明」按钮直接打开它。
  插件默认 `hunting=2`：F10/F8/F9 仍可用，但屏幕左上角绿色调试 HUD 默认关闭（按小键盘 0 临时开）。
- 日志：管理器自身操作日志同步写 `%LOCALAPPDATA%\GakumasModManager\logs\gakumas-mm-YYYYMMDD.log`
  并显示在底部面板；「打开 3DMigoto 日志」直接打开游戏目录 `d3d11_log.txt`（需在 d3dx.ini 设
  `[Logging] calls=1` 并重进游戏）。不做日志级别筛选 —— 3DMigoto 日志是无分级的纯文本流。
- 游戏路径记忆：`%LOCALAPPDATA%\GakumasModManager\settings.json` 存上次使用路径，启动自动读取；
  工具栏「浏览…」用 `OpenFolderDialog` 选目录。未保存/目录失效时回退到默认探测。
- 封面缩略图：详情面板把 `manifest.cover`/`cover.png` 渲染为图片（`CoverImageConverter` 用
  `OnLoad` 缓存读入，不占文件句柄，避免启停改名时被锁）；无封面则显示占位。
- 打开目录：详情面板「打开目录」按钮用资源管理器打开选中包所在文件夹。
- 拖拽安装：把 mod 文件夹或 `.zip` 拖进窗口即复制/解压进 `Mods/`（`PackageInstallService`：
  zip 单顶层文件夹自动去重嵌套、跨盘用复制而非移动、目标已存在则跳过不覆盖），完成后自动刷新。
- 默认测试目录 `D:\Games\gakumas\Mods`（仅在无保存路径时作为回退之一）。
- 冲突检测：同一 conflict key 多个启用包聚合为真实冲突，详情面板标出与哪些包冲突。
- 角色分类与筛选：从 manifest `conflicts` 键前缀（回退到 `targets`）识别角色代号，列表按固定角色
  顺序分组并显示可折叠分组标题（`花海咲季 → 月村手毬 → … → 其他`）；工具栏「角色」下拉只列出当前存在的
  角色，选中即筛选该组。分组折叠状态在刷新/启停/装包重扫后保留（进程内记忆）。识别不到代号的包归入「其他」。
- 打包发布：`release-3dmigoto-gkms` workflow（`windows-latest` 单作业）产出 **Inno Setup 安装包**
  `GakumasModManager-Setup-<版本>.exe`。流程：取上游匹配版第三方 dll → 冒烟测试 →
  `dotnet publish` 框架依赖单文件（约 3MB，需 .NET 8 Desktop Runtime）→ 装配（加载器平铺 +
  `GakumasModManager\` 子目录）→ ISCC 编译。安装时选游戏根目录：加载器平铺进根目录、管理器装到
  `GakumasModManager\` 子目录并可建桌面快捷方式，`d3dx.ini`/`Mods` 已存在不覆盖。
  安装脚本见 [`installer/GakumasModManager.iss`](installer/GakumasModManager.iss)。

当前功能已落地，后续只做缺陷修复和明确需求。
