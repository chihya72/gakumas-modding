# Third-party notices

本仓库自有代码以 [GPL-3.0](LICENSE) 发布。选 GPL-3.0 不是偏好问题：仓库内再分发的
`3dmigoto_gkms/d3d11.dll` 是 GPL-3.0 项目 3DMigoto 的修改版二进制，其许可要求整体以
同一许可分发。

## 仓库内再分发的二进制

| 组件 | 位置 | 许可证 | 来源 |
|---|---|---|---|
| 3DMigoto v1.4.9（**修改版**） | `3dmigoto_gkms/d3d11.dll` | GPL-3.0 | <https://github.com/bo3b/3Dmigoto> |
| 3DMigoto ShaderFixes | `3dmigoto_gkms/ShaderFixes/` | GPL-3.0 | 同上 |

### 修改版 `d3d11.dll` 的源码

GPL-3.0 要求随二进制提供对应的完整源码。本仓库的 `d3d11.dll` 相对上游 v1.4.9 只有一处
改动：`DirectX11/HackerDXGI.cpp` 的 `HackerSwapChain::ResizeBuffers` 补回 FLIP swap chain
的 `FRAME_LATENCY_WAITABLE_OBJECT` 标志。**完整补丁内容、插入位置与重编译命令见**
[`3dmigoto_gkms/FLIP-RESIZE-PATCH.md`](3dmigoto_gkms/FLIP-RESIZE-PATCH.md)，
按该文档在上游 v1.4.9 源码树上可逐字复现本二进制。

> ⚠ **发布前待办**：GPL-3.0 更规范的做法是提供可直接取用的源码分支（fork 仓库或
> 完整 source tarball），而不是只给补丁说明。公开发布前应补上 fork 链接。

## 发布包在构建时取用、不入库的二进制

由 [`.github/workflows/release.yml`](.github/workflows/release.yml) 在 CI 上从上游
Release 下载后打进 `gakumas-mod-toolkit-<版本>.zip`，本仓库不提交这两个文件：

| 组件 | 许可证 | 来源 |
|---|---|---|
| `nvapi64.dll`（3DMigoto v1.4.9 附带） | 见上游仓库 | <https://github.com/bo3b/3Dmigoto> |
| `d3dcompiler_47.dll`（3DMigoto v1.4.9 附带） | Microsoft 可再分发组件 | 同上 |

## 已移除的依赖

0.7.0 起 WPF Mod 管理器整体废弃，随之不再需要 Stylet / HandyControl
这两个 NuGet 包，也不再需要 .NET 构建：

| 组件 | 版本 | 许可证 | 来源 |
|---|---|---|---|
| Stylet | 1.3.7 | MIT | <https://github.com/canton7/Stylet> |
| HandyControl | 3.5.1 | MIT | <https://github.com/HandyOrg/HandyControl> |

## 只调用、不再分发的外部工具

| 组件 | 用途 |
|---|---|
| AssetStudio (CLI) | 从游戏包导出 `Geo_*.json` 与贴图；由作者本机安装，路径经 `--assetstudio` 传入 |
| Blender 4.2 LTS / 4.5 LTS | 插件宿主 |
| UnityPy | `tools/patch_unity_bundle.py` 的 bundle 补丁依赖，由作者自行 `pip install` |

## 同级仓库

`../gakumas-mod-runtime/` 是独立仓库，自带 LICENSE 与 third-party notices，
其依赖不在本文范围内。
