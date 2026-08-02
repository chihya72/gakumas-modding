# 3dmigoto-gkms — 抓帧环境

面向《学园偶像大师》的定制 3DMigoto 构建（基于 **v1.4.9**）。**0.7.0 起它只做一件事：
给 mod 作者抓帧（F8 Frame Analysis）**，用来生成 GakumasMI 插件的配置档。

> **不加载 mod。**换模已整体转到 AB bundle 路线：由同级仓库
> [`gakumas-mod-runtime`](../README.md#同级仓库不属于本仓库各自独立-git) 的
> `xinput1_3.dll` 加载，游戏内开关由 `xinput9_1_0.dll` 提供，都与本加载器无关。
> `d3dx.ini` 里的 `include_recursive = Mods` 已注释掉，`Mods/` 目录也已删除。
>
> 一并废弃的还有旧的 WPF Mod 管理器（原 `mod-manager/`），它管的是 3DMigoto 包格式，
> 插件 0.9.0 之后不再产出那种包。

> ⚠️ 本仓库的 `d3d11.dll` 是**自编译的补丁版**，修了游戏竖屏↔横屏 live 切换时的
> 黑屏/闪烁（FLIP swap chain 的 `ResizeBuffers` 丢失 WAITABLE flag）。**官方
> 3DMigoto / 各 fork 均无此修复，直接换它们会复现该 bug。** 补丁原理、源码改动与
> 重编译步骤见 [`FLIP-RESIZE-PATCH.md`](FLIP-RESIZE-PATCH.md)。

## 安装

推荐用 Release 里的 `Gakumas3DMigotoCapture-Setup-<版本>.exe`，选游戏根目录即可。

手动安装则把以下文件复制到 `gakumas.exe` 同级目录：

| 复制 | 说明 |
|---|---|
| `d3d11.dll`、`nvapi64.dll`、`d3dcompiler_47.dll` | 3DMigoto 二进制（必须） |
| `d3dx.ini` | 配置（必须） |
| `ShaderFixes/` | 着色器修复（整个文件夹，必须） |
| `键位说明.txt` | 键位速查（可选） |

然后用 `-force-d3d11` 启动游戏。

> 仓库**已包含自编译的补丁版 `d3d11.dll`**（直接可用）；第三方 `nvapi64.dll`、
> `d3dcompiler_47.dll` 不入库，可从 3DMigoto v1.4.9 发行版或可工作的游戏目录补齐
> （发布安装包由 CI 从上游 Release 取，已带好三件套）。
> **务必使用本仓库的 `d3d11.dll`** —— 官方版会犯横竖屏切换 bug。

## 用法：抓一帧

1. 进游戏，走到目标角色/服装出现的画面；
2. 按 **F8**；
3. 结果落在游戏目录的 `FrameAnalysis-<日期时间>\`；
4. 把该目录填进 GakumasMI 插件的「抓帧目录」，生成配置档。

`d3dx.ini` 的 `analyse_options` 已配好 `dump_vb dump_ib dump_cb dump_tex dds buf txt desc
mono share_dupes`，插件需要的 buffer / 贴图 / 描述都会导出。

## 按键说明

| 按键 | 作用 |
|---|---|
| **F8** | 帧分析：转储当前帧的模型/贴图/缓冲 —— 本包的主要用途 |
| F10 | 重载 `d3dx.ini` 与 `ShaderFixes`，不用重启游戏 |
| F9 | 按住临时显示原始画面（本包不加载 mod，一般看不出差别） |
| PrtSc | 截图 |
| 小键盘 `0` | 开/关绿色 Hunting HUD（默认关，`hunting=2`） |
| 小键盘其它键 | Hunting 调试：循环/标记着色器、顶点/索引缓冲 |
| Ctrl+F9 | 性能监视 |

完整说明随包发一份 [`键位说明.txt`](键位说明.txt)。

## 和项目其它部分的关系

- 作者用本包抓帧 → [`../gakumas_mi`](../gakumas_mi) 插件生成配置档 → 导出 AB bundle；
- 成品 bundle 交给 `gakumas-mod-runtime`，**不经过本加载器**；
- 整体数据流见 [`../README.md`](../README.md)。

## 发布

`.github/workflows/release-3dmigoto-gkms.yml`，触发 tag `3dmigoto-gkms-vX.Y.Z`。
Inno Setup 脚本在 [`installer/Gakumas3DMigotoCapture.iss`](installer/Gakumas3DMigotoCapture.iss)。
workflow 里有守卫：`d3dx.ini` 若重新启用 `include_recursive = Mods`、或丢失 `analyse_frame`
绑定，构建直接失败。
