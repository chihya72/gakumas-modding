# GakumasMM — Mod 包管理器规划草案

日期：2026-07-03。2026-07-04 调整：**移除抓帧/槽位补全路线**（gakumas-mi 0.7.2
运行时全局布局探测后不再需要），范围收敛为纯包管理 + ini 控制。状态：开发中。

作为 `3dmigoto-gkms`（游戏侧插件 0.5.x）的后续更新内容推进，不单独拆第三条产品线；
版本号、Release tag 与 `3dmigoto-gkms` 保持一致。`gakumas_mi`（Blender 插件 0.7.x）
仍按 Blender 插件自身节奏独立演进。

GUI 参考图与开发拆解见：[`gui-light-orange-reference.png`](gui-light-orange-reference.png)、
[`gui-development-flow.md`](gui-development-flow.md)。

## 1. 定位

面向**使用者**（不是 mod 作者）的桌面工具：管理游戏 `Mods` 目录里的 GakumasMI 包，
不打开 Blender 就能启用/禁用/重载 mod、调 3DMigoto 配置（d3dx.ini / mod.ini）。

Blender 插件继续只负责"作者产出包"；管理器负责"包的启停、校验与配置"。
不做抓帧、不做槽位补全、不做任何逆向分析功能。

## 2. 技术选型

- **WPF + XAML + C#**（GUI），作为 Windows 桌面工具随 `3dmigoto-gkms` 发布。
  界面层使用 `Views/*.xaml` + `.xaml.cs`，资源拆到 `Res/Theme.xaml` / `Res/Style.xaml`。
- **Stylet MVVM / IoC**：启动点是 `Bootstrapper : Bootstrapper<RootViewModel>`；
  ViewModel 只处理状态和命令，文件操作与核心逻辑放到 service 层。
- **控件与视觉库**：用 HandyControl 作基础皮肤；其余工具库按实际需要再引，不预挂未用依赖
  （拖拽用原生 `AllowDrop`/`Drop` 即可，无需第三方）。
- **不引入原生核心 DLL**：范围收敛后全部功能（扫描、启停改名、ini 读写、F10 重载）
  用 C# service 层直接实现即可；`Core/NativeMethods.cs` 只保留 F10 重载所需的
  Win32 P/Invoke。`AsstProxy` 作为 ViewModel 调用的业务门面保留。

## 3. 包格式约定（现状 + 扩展）

Blender 插件导出的包已有（`manifest.json`，schemaVersion 1）：

| 字段 | 现状 | 管理器用途 |
|---|---|---|
| `id` / `name` / `author` | ✅ 已写入 | 列表展示 |
| `version` | ⚠️ 硬编码 `"0.1.0"`（core.py:2705） | 展示；需要插件侧开放填写 |
| `profile` / `targets` / `conflicts` | ✅ | 冲突检测 |
| `materials`（语义 → slot/原贴图 hash/文件） | ✅ | 完整性校验（引用文件是否存在） |
| `alphaModes` / `nativeCoRanges` / `nativeCoSection` | ✅ | ini 重生成 |

**扩展（schemaVersion 2，向后兼容 v1）**：

- `cover`：封面图约定——包根目录 `cover.png`（建议 4:3 或 16:9，≤1MB），
  manifest 可选 `"cover": "cover.png"` 字段；没有则管理器显示占位图。
- `description`：一句话简介。
- Blender 插件侧配套小改动（0.7.x 后续版本）：导出面板加「模组版本」「封面图」
  「简介」三个可选字段；不填不报错。

## 4. 核心功能设计

### 4.1 Mods 目录扫描与列表

- 让用户指定游戏目录（记住配置），扫描 `Mods/` 下含 `manifest.json` 的目录为
  GakumasMI 包，其余含 `.ini` 的目录识别为"通用 3DMigoto 包"（只支持启用/禁用）。
- 列表列：封面缩略图、名称、作者、版本、目标（actor/costume）、状态（启用/禁用/损坏）。
- 完整性校验：manifest 引用的 Textures/Buffers 文件是否存在、DDS 尺寸格式是否
  匹配（复用 `inspect_dds`）。

### 4.2 启用 / 禁用 / 重载

- **禁用 = 目录改名加 `DISABLED` 前缀**。d3dx.ini 已内置
  `exclude_recursive = DISABLED*`（d3dx.ini:14），零 ini 编辑、与手工操作习惯兼容、
  游戏运行中也安全。启用 = 去前缀。
- **重载 = 向游戏窗口发送 F10**。d3dx.ini 已配 `reload_fixes = no_modifiers VK_F10`
  且默认 `hunting=1`（就是为了保住 F10/F8）。实现用 Win32 `FindWindow` + `SendInput`
  （需要游戏前台）；找不到窗口时降级为提示"切回游戏按 F10"。
- 启用/禁用后自动询问是否重载。

### 4.3 d3dx.ini 直接操纵

注意：配置文件是 **d3dx.ini**（`dxgi.dll` 是加载器 DLL 本身，没有 dxgi.ini）。

- 结构化编辑常用项，不让用户碰原文件：
  - `[Hunting]` hunting=0/1/2 开关（发布时想省性能可关）；
  - `[Include]` include/exclude 规则查看；
  - 常用键位重绑定（F10 重载键等）。
- **每次写入前自动备份**到 `d3dx.ini.bak.<时间戳>`，保留最近 N 份，一键回滚。
- 提供只读的原文查看 + "在编辑器中打开"兜底；不做全量 ini 语法编辑器。

### 4.4 冲突检测（低优先级）

manifest 已有 `conflicts` 字段（`actor.costume.component.mesh`）：同时启用两个
声明相同冲突键的包时在列表上标黄提示。

## 5. 里程碑

| 版本 | 内容 |
|---|---|
| 阶段 1 ✅ | 目录扫描、包列表（封面/作者/版本/状态）、启用/禁用（DISABLED 前缀）、完整性校验 |
| 阶段 2 ✅ | F10 重载触发、d3dx.ini 结构化编辑 + 备份回滚 |
| 阶段 3 ✅ | 冲突检测（同 conflict key 聚合并标名对方包）、打包发布：`3dmigoto-gkms-v*` release 由 windows-latest 单作业产出 **Inno Setup 安装包** `GakumasModManager-Setup-<版本>.exe`——冒烟测试→框架依赖单文件 publish（约 3MB，需 .NET 8 Desktop Runtime）→装配（加载器平铺 + `GakumasModManager\` 子目录）→ISCC 编译。安装时选游戏根目录：加载器平铺进根目录、管理器装到 `GakumasModManager\` 子目录并可建桌面快捷方式；`d3dx.ini`/`Mods` 已存在不覆盖 |

> 原「阶段 3 抓帧槽位补全」已于 2026-07-04 移出范围：gakumas-mi 0.7.2 运行时全局
> 布局探测后不再有"新 PS 错位"，详见
> [`research/archive/session-20260704-gmi-global-layout-and-mirror.md`](../../research/archive/session-20260704-gmi-global-layout-and-mirror.md)。

配套的 Blender 插件侧小改动（随 gakumas_mi 正常排期，不阻塞管理器阶段 1）：
manifest schemaVersion 2（version/cover/description 可填）、导出面板对应字段。
