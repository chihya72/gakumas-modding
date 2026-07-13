# 3dmigoto-gkms — GakumasMI 游戏 mod 插件

面向《学园偶像大师》的定制 3DMigoto 游戏 mod 插件(基于 **v1.4.9**)。负责把作者导出的
mod 注入游戏渲染、并运行逆解蒙皮 Compute Shader。

> ⚠️ 本仓库的 `d3d11.dll` 是**自编译的补丁版**,修了游戏竖屏↔横屏 live 切换时的
> 黑屏/闪烁(FLIP swap chain 的 `ResizeBuffers` 丢失 WAITABLE flag)。**官方
> 3DMigoto / 各 fork 均无此修复,直接换它们会复现该 bug。** 补丁原理、源码改动与
> 重编译步骤见 [`FLIP-RESIZE-PATCH.md`](FLIP-RESIZE-PATCH.md)。

## 安装(直接复制即可)

把以下文件/文件夹复制到游戏 `gakumas.exe` 同级目录:

| 复制 | 说明 |
|---|---|
| `d3d11.dll`、`nvapi64.dll`、`d3dcompiler_47.dll` | 3DMigoto 二进制(必须) |
| `d3dx.ini` | 插件配置(必须) |
| `ShaderFixes/` | 着色器修复(整个文件夹,必须) |
| `Mods/` | mod 安装目录(没有就建一个空的) |

然后用 `-force-d3d11` 启动游戏即可。

> 仓库**已包含自编译的补丁版 `d3d11.dll`**(直接可用);第三方 `nvapi64.dll`、
> `d3dcompiler_47.dll` 不入库,可从 3DMigoto v1.4.9 发行版或可工作的游戏目录补齐。
> **务必使用本仓库的 `d3d11.dll`**——官方版会犯横竖屏切换 bug(见
> [`FLIP-RESIZE-PATCH.md`](FLIP-RESIZE-PATCH.md))。发布 zip 里已带好补丁版三件套。

## 用法

- 把作者导出的 mod 文件夹整体放进 `Mods/`（每个 mod 一个子文件夹）；
- 文件夹名以 `DISABLED_` 开头会被忽略,可用来临时禁用某个 mod;
- **改动 mod 后按 `F10` 重载即可,不用重启游戏**;
- 调试 HUD 默认隐藏；开发者可用小键盘 `0` 切换。

## 按键说明

| 按键 | 作用 | 谁会用 |
|---|---|---|
| **F10** | 重新加载全部 mod / 配置(加了或改了 mod 后按它生效) | 所有人,最常用 |
| **F9** | 按住临时显示原版,松开恢复 mod —— 用来对比前后 | 所有人 |
| **PrtSc** | 截图 | 所有人 |
| F8 | 帧分析:转储当前帧的模型/贴图/缓冲(给开发者建配置档用) | 开发者 |
| 小键盘 `0` | 开/关绿色 Hunting HUD | 开发者 |
| 小键盘 `+` 及其它键 | Hunting 调试(循环/标记着色器、顶点/索引缓冲) | 开发者 |
| Ctrl+F9 | 性能监视 | 开发者 |

> 普通用户基本只用到 **F10**(加 mod 后重载)。F8 和小键盘那些是开发者抓帧/调试用的,
> 平时不用按。

## 和项目其它部分的关系

- 作者用 [`../gakumas_mi`](../gakumas_mi) 的插件导出 mod → 放进本目录 `Mods/`;
- mod 内的 Compute Shader 由本插件执行(逆解每帧矩阵 + 重蒙皮);
- 整体数据流见 [`../README.md`](../README.md)。
