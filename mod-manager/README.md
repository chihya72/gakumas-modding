# Gakumas Mod Manager

面向**使用者**的 GakumasMI Mod 包管理器（WPF / XAML / Stylet MVVM）。作为
`3dmigoto-gkms` 后续更新的一部分维护与发布，版本号、Release tag 与其保持一致。

规划与设计文档见 [`docs/plan.md`](docs/plan.md)（范围、包格式、里程碑）与
[`docs/gui-development-flow.md`](docs/gui-development-flow.md)（界面拆解与开发流程）。

## 目录

- `src/GakumasModManager/`：WPF 桌面应用。
  - 界面层：`Views/` + `Res/Theme.xaml` / `Res/Style.xaml`（白色 + 橙黄色主题）。
  - MVVM / IoC：Stylet，启动点 `Bootstrapper : Bootstrapper<RootViewModel>`。
  - 控件与视觉库：`HandyControl`、`gong-wpf-dragdrop`、`MdXaml`、`Notification.Wpf`。
  - `Services/`：文件操作与核心逻辑（扫描/启停/重载/d3dx.ini）；
    `Core/NativeMethods.cs` 只放 Win32 边界，`Services/AsstProxy.cs` 包装给 ViewModel。
- `tests/GakumasModManager.ScannerSmoke/`：扫描、启停、d3dx.ini 备份的 smoke 测试。
- `docs/`：规划、GUI 开发流程与参考图。
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
- d3dx.ini 快捷设置读取（`[Hunting] hunting` / `analyse_frame` / `reload_fixes`）与手动备份
  （`d3dx.ini.bak.YYYYMMDD-HHMMSS-fff`，按保留数量清理）。
- 日志同步写入 `%LOCALAPPDATA%\GakumasModManager\logs\gakumas-mm-YYYYMMDD.log`。
- 默认测试目录 `D:\Games\gakumas\Mods`。

下一步：d3dx.ini 设置写入与备份回滚列表；之后按 [`docs/plan.md`](docs/plan.md)
里程碑推进（冲突检测细化、打包发布）。
