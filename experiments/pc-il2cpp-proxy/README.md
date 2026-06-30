# PC IL2CPP `.gmim` mesh replacement probe

PC 端 IL2CPP 实验 DLL。通过 `xinput1_3.dll` 代理注入游戏，解析 `GameAssembly.dll`
导出的 il2cpp C API，在主线程创建 Unity `Mesh` 并替换目标 `SkinnedMeshRenderer.sharedMesh`。

这是**研究路线**，不是正式发布路径。正式插件路线仍是 Blender + 3DMigoto。

## 已验证

- 可枚举 live `SkinnedMeshRenderer`、`bones[]`、`sharedMaterials`。
- 可从 `D:\Games\gakumas\yuika.gmim` 读取外部模型：
  - vertices / normals / uv / COLOR；
  - submesh triangles；
  - bone-name top-4 weights；
  - per-submesh `opaque / native-co` mode。
- 可把 `.gmim` 权重按骨名重映射到当前服装的 `bones[]`。
- 可复用原 `Geo_Body` bindposes。
- 可把外部模型装回游戏并跟随动作。
- 可通过 `_BaseMap` property ID 替换 `m_bdy` / `m_bdyco` 的 base atlas。

## 透明结论

透明/镂空必须严格使用目标 `Geo_Body` 自己的原生第二材质槽：

```text
sharedMaterials[0] = m_bdy
sharedMaterials[1] = m_bdyco
opaque submesh -> m_bdy
native-co submesh -> m_bdyco
```

只给 `m_bdy` 换带 alpha 的 `_BaseMap` 会出现黑底；手动改材质状态或几何侧处理 alpha 都不作为方案。
这与已经实机验证成功的 3DMigoto 正式路线一致：**不要自造透明，IL2CPP 也必须复用游戏原生
`m_bdyco` section**。

详细研究记录见：

`D:\GIT\gakumas-modding\research\pc-il2cpp-gmim-runtime-replacement.md`

## 编译

需要 MSVC（VS 2019/2022）+ CMake，x64。

```powershell
cmake -B build -A x64
cmake --build build --config Release
```

本机常用命令：

```powershell
& 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' --build build --config Release
```

产物：

```text
build\Release\xinput1_3.dll
```

## 安装与日志

把 `xinput1_3.dll` 放到游戏 exe 同目录：

```text
D:\Games\gakumas\xinput1_3.dll
```

日志：

```text
D:\Games\gakumas\gkms_meshprobe.log
```

常用热键：

| 热键 | 用途 |
|---|---|
| F5 | dump live material 信息 |
| F6 | quad diagnostic |
| F7 | blank diagnostic |
| F8 | 从 `yuika.gmim` 构建真实 mesh 并替换最佳 `Geo_Body` |
| F9 | restore saved mesh |

## `.gmim` 导出

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" `
  -b "C:\Users\10725\Desktop\yuika.blend" `
  --python "D:\GIT\gakumas-modding\experiments\pc-il2cpp-proxy\export_gmim.py" `
  -- "D:\Games\gakumas\yuika.gmim"
```

`export_gmim.py` 会写入 `.gmim ver=3`，并根据 Blender 材质标记或材质名判断 submesh mode。
`NATIVE_CO` submesh 会在运行时分配给目标 `m_bdyco`。

## 风险

- 这是进程内注入，崩溃风险高。
- Unity/IL2CPP 方法重载、对象生命周期和主线程限制都可能影响稳定性。
- 仅用于研究和验证，不作为普通用户 mod 分发路线。
