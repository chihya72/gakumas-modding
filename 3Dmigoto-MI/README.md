# 3Dmigoto-MI

GakumasMI 定制化 3DMigoto 运行时(基于 3DMigoto **v1.4.9**),从可正常工作的游戏
目录整理而来,作为本项目运行时部分的版本化基线。

## 目录内容

| 文件/目录 | 说明 | 是否入库 |
|---|---|---|
| `d3dx.ini` | **开发配置**:`hunting=1`、Frame Analysis / Dump 全开 | ✅ 跟踪 |
| `d3dx-release.ini` | **发布配置**:`hunting=0`、关 HUD / Dump / 多余日志,只保留 mod 加载 | ✅ 跟踪 |
| `install.ps1` | 一键安装/卸载到游戏目录(可选 dev/release 配置) | ✅ 跟踪 |
| `ShaderFixes/` | 游戏专属着色器修复 / 替换(`*-vs_replace.txt` 等)与 3DMigoto 自带修复 | ✅ 跟踪 |
| `Mods/` | mod 安装目录(作者导出的 mod 放这里) | ⬜ 仅 README |
| `d3d11.dll` / `nvapi64.dll` / `d3dcompiler_47.dll` | 3DMigoto v1.4.9 二进制 | ❌ 不入库(见 `.gitignore`) |
| `ShaderCache/` | 运行时生成缓存 | ❌ 不入库 |

> 二进制不入库遵循项目既有策略(第三方二进制单独下载,不 vendoring)。克隆后需要
> 从 3DMigoto v1.4.9 发行版补齐这三个 DLL,或直接从可工作的游戏目录拷贝。

## 安装到游戏

**推荐用安装脚本**(自动选择配置、复制二进制 + ShaderFixes、建 Mods 目录):

```powershell
# 发布配置(默认,给玩家)
./install.ps1 -GameDir "D:\Games\gakumas"
# 开发配置(给核心维护者:开 Hunting / Frame Analysis)
./install.ps1 -GameDir "D:\Games\gakumas" -Config dev
# 卸载
./install.ps1 -GameDir "D:\Games\gakumas" -Uninstall
```

安装后用 `-force-d3d11` 启动游戏即可。

手动安装:把 `d3d11.dll`、`nvapi64.dll`、`d3dcompiler_47.dll`、所选 `d3dx*.ini`
(复制为 `d3dx.ini`)和 `ShaderFixes/` 拷到 `gakumas.exe` 同级目录。

## 开发 / 发布配置区别

| 配置 | 文件 | 用途 | 关键区别 |
|---|---|---|---|
| 开发 | `d3dx.ini` | 核心维护者建配置档 / 抓帧 | `hunting=1`、`calls=1`、`verbose_overlay=1`、Frame Analysis 全开 |
| 发布 | `d3dx-release.ini` | 玩家 | `hunting=0`、`calls=0`、`input=0`、`verbose_overlay=0`,只留 mod 加载 |

两者的 `include_recursive=Mods`、`override_directory=ShaderFixes` 与设备/注入设置一致,
只有 Hunting / 日志 / HUD 不同。安装脚本会把所选配置复制为游戏目录的 `d3dx.ini`。

## 与项目其它部分的关系

- 作者用 [`../blender_addon`](../blender_addon) 导出 mod → 放入本目录 `Mods/`;
- mod 内的 Compute Shader(`RecoverMatricesCS` / `SkinCustomCS`)由运行时执行,
  逆解每帧矩阵并重蒙皮,详见 [`../README.md`](../README.md) 的三层数据模型。
