# 基准研究环境

> 采集日期：2026-06-21  
> 用途：首个 Drawcall Profile 的环境指纹

## 路径

```text
游戏目录：D:\Games\gakumas
游戏程序：D:\Games\gakumas\gakumas.exe
3DMigoto 配置：D:\Games\gakumas\d3dx.ini
AssetStudio：D:\GIT\AssetStudio-net10.0-win
AssetStudio CLI：D:\GIT\AssetStudio-net10.0-win\AssetStudio.CLI.exe
AssetStudio GUI：D:\GIT\AssetStudio-net10.0-win\AssetStudio.GUI.exe
```

## 已确认状态

- 游戏为 64 位 Unity Player；
- `gakumas.exe` 与 `UnityPlayer.dll` 的产品版本均为 `6000.0.67f1 (78a1c2bbeb6a)`；
- AssetStudio 包含 `6000.0.67f1` 支持目录；
- AssetStudio CLI 版本为 `1.36.00`；
- 游戏根目录已部署 `d3d11.dll`、`d3dcompiler_47.dll`、`nvapi64.dll` 与 `d3dx.ini`；
- 已部署的 `d3d11.dll` 文件版本为 `1.4.9`；
- `d3dx.ini` 当前启用 `hunting=1`、`marking_mode=skip`、`dump_usage=1`；
- AssetStudio CLI 可正常启动并显示帮助；
- 本次检查时游戏未运行，因此尚未生成或复核本次 `d3d11_log.txt`。

## 构建信息

```text
Unity build GUID：32d2b7df08344cb7bc4b1611ee280807
应用标识：gakumas
发行方：BANDAI NAMCO Entertainment Inc.
```

## SHA-256 指纹

```text
gakumas.exe
3B1C6DA16B0D9657DB41EE450E80E3312889CEFAD8C2AA9E684EAF087AEE572C

UnityPlayer.dll
A1A916DADE20C2653CDE3F135E62A15DD4F3A8C928411C7F1675CB4E16341FCB

GameAssembly.dll
1CE1991FA0BE97BFEEFC6F526F6800EDE242B028CC8990D6E00E679519C951E9

gakumas_Data\data.unity3d
831C63F4EC10BAB0CA9D6808CBFC651D9AC198DB241B65267B5E96773B574EAD

d3d11.dll
791AA68B9F8C0742C040F9ED5FA61AA0B4D3F9EE7B9E1865BF82ED6B2254378F
```

上述任一游戏核心文件发生变化时，应重新验证 DX11、3DMigoto 注入与基准场景，再决定是否沿用旧 Profile。
