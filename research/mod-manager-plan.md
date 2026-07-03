# GakumasMM — Mod 包管理器规划草案

日期：2026-07-03。状态：规划中，未开工。

第三条产品线，与 `3dmigoto-gkms`（游戏侧插件 0.4.x）、`gakumas_mi`（Blender 插件 0.7.x）
**版本号完全独立**，从 0.1.0 起步；Release tag 前缀 `gakumas-mm-vX`。

## 1. 定位

面向**使用者**（不是 mod 作者）的桌面工具：管理游戏 `Mods` 目录里的 GakumasMI 包，
不打开 Blender 就能启用/禁用/重载 mod、调 3DMigoto 配置，以及——最重要的——
**在新场景出现贴图错位时，用一次抓帧就地补全 mod 的槽位变体（slotVariants）**，
不需要作者重新导出。

Blender 插件继续只负责"作者产出包"；管理器负责"包的全生命周期"。
槽位补全功能**只在管理器实现**，插件侧不做。

## 2. 技术选型

- **Python + PySide6**（GUI），PyInstaller 打包单 exe 发布。
- **直接复用 `gakumas_mi/core.py`**：它不依赖 bpy（CI 测试就是裸 Python 跑的），
  抓帧解析（`extract_profile_from_frame_dump` 一族）、ini 槽位块生成
  （`_section_slot_variant_ini` / `_section_material_binding_block`）、DDS 校验
  （`inspect_dds`）全部现成。仓库内新建 `gakumas_mm/` 目录，按包引用 `gakumas_mi.core`；
  只有当两边耦合造成发版互相牵制时才拆共享库，先不预制抽象。

## 3. 包格式约定（现状 + 扩展）

Blender 插件导出的包已有（`manifest.json`，schemaVersion 1）：

| 字段 | 现状 | 管理器用途 |
|---|---|---|
| `id` / `name` / `author` | ✅ 已写入 | 列表展示 |
| `version` | ⚠️ 硬编码 `"0.1.0"`（core.py:2705） | 展示；需要插件侧开放填写 |
| `profile` / `targets` / `conflicts` | ✅ | 冲突检测 |
| `materials`（语义 → slot/**原贴图 hash**/文件） | ✅ | **槽位补全的匹配依据** |
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
  - 抓帧相关（frame analysis 选项、按键绑定）；
  - 常用键位重绑定。
- **每次写入前自动备份**到 `d3dx.ini.bak.<时间戳>`，保留最近 N 份，一键回滚。
- 提供只读的原文查看 + "在编辑器中打开"兜底；不做全量 ini 语法编辑器。

### 4.4 抓帧补全新槽位（核心功能）

**问题**：游戏在某些场景（如低亮度）换 pixel shader，贴图槽位布局改变；mod 的
`mod.ini` 只认识导出时 profile 里已知的 PS，遇到新变体就错位（0.7.1 的
`50b619789b23bd7a` 就是手工补的）。

**目标**：使用者在出问题的场景按 F8 抓一帧，管理器自动学会新 PS 的槽位并更新 mod。

流程：

1. 用户选择：出问题的 mod 包 + `FrameAnalysis-*` 目录。
2. **管理器先临时禁用该 mod 并提示重抓**（或校验抓帧里没有该 mod 的注入痕迹）：
   槽位匹配靠**原版贴图 hash**（manifest `materials[*].hash`），mod 启用时贴图已被
   替换成我们自己的资源，hash 对不上。禁用后抓帧最可靠。
3. 解析抓帧（复用 core.py）：找到与该 mod 目标 body 同 IB/VB 流的 draw 组，
   遍历其中 PS ≠ 已知变体的 draw。
4. 按 hash 匹配：原 baseColor/packedMask/shadeColor 的 hash 出现在新 PS 的哪个槽 →
   得到 `slotVariants[<新PS>] = {semantic: slot}`。用抓帧 descriptor 做 sanity check
   （例如变体里 ps-t4 应是深度类格式 → 确认是深度比较槽，拒绝把语义贴图写进去）。
5. 写回：
   - 更新包内 profile 副本 / manifest 的 slotVariants 记录；
   - **重新渲染 mod.ini 的槽位相关段**（`[ShaderOverride...SlotVariant...]` 全局变量
     块 + TextureOverride 里的 `if $var == N` 条件绑定块），不做文本 patch——
     需要在 core.py 加一个高层入口 `update_package_slot_variants(package_dir,
     capture_dir)`，内部复用现有 `_section_slot_variant_ini` /
     `_section_material_binding_block`；
   - 修改前备份 mod.ini。
6. 重新启用 mod，触发 F10 重载，用户回场景验证。
7. （可选回馈闭环）导出学到的 `slotVariants` 片段为 JSON，方便贡献回仓库
   `profiles/` 让后续导出直接带上。

风险与对策：

| 风险 | 对策 |
|---|---|
| 抓帧里没有目标 body 的 draw（角色不在画面） | 匹配不到时明确报"没找到目标 body"，不写任何东西 |
| 同 hash 绑到多个槽 | 用主 PS 的槽位集合做差异消歧；仍歧义则列出候选让用户选 |
| mod.ini 被作者手工改过 | 重生成前 diff 提示；只重写槽位相关段之外做不到就整体重生成并保留备份 |
| 未来第三种布局 | 数据问题，无法预判；本功能就是让它变成"抓一帧"级别的修复成本 |

### 4.5 冲突检测（低优先级）

manifest 已有 `conflicts` 字段（`actor.costume.component.mesh`）：同时启用两个
声明相同冲突键的包时在列表上标黄提示。

## 5. 里程碑

| 版本 | 内容 |
|---|---|
| 0.1 | 目录扫描、包列表（封面/作者/版本/状态）、启用/禁用（DISABLED 前缀）、完整性校验 |
| 0.2 | F10 重载触发、d3dx.ini 结构化编辑 + 备份回滚 |
| 0.3 | **抓帧槽位补全**（含 core.py 的 `update_package_slot_variants` 入口） |
| 0.4 | 冲突检测、slotVariants 回馈导出、打包发布（PyInstaller + Release CI） |

配套的 Blender 插件侧小改动（随 gakumas_mi 正常排期，不阻塞管理器 0.1）：
manifest schemaVersion 2（version/cover/description 可填）、导出面板对应字段。
