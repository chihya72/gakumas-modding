# PC IL2CPP probe (xinput1_3.dll proxy)

最小化的 PC 端 IL2CPP 网格检测 DLL。通过劫持 `xinput1_3.dll` 注入学马 PC 客户端，
直接用 `GameAssembly.dll` 导出的 il2cpp C API 解析类型，用 MinHook 挂
`SkinnedMeshRenderer.set_sharedMesh`，把每个被赋值的蒙皮网格打到日志，并标记出
匹配 `FrameAnalysis-2026-06-29-065048` 那套服装的 body 分段（顶点数 20278 / 18037 / 5206 / 2012）。

这是已冻结的**只读检测实验**，不属于当前 3DMigoto 正式路线。

## 编译

需要 MSVC（VS 2019/2022）+ CMake，**x64**。

```bash
# 1) 取 MinHook 源码
git clone https://github.com/TsudaKageyu/minhook third_party/minhook

# 2) 配置 + 编译（x64）
cmake -B build -A x64
cmake --build build --config Release
```

产物：`build/Release/xinput1_3.dll`。

## 安装

把 `xinput1_3.dll` 放到**游戏 exe 同目录**（与 `GameAssembly.dll` 同级）。启动游戏。
- 会弹出一个控制台窗口（"GakumasMI IL2CPP probe"），同时写日志到 **游戏目录\gkms_meshprobe.log**。
- 进入有角色的画面 / 切换服装，应看到一串：
  ```
  [HookMesh] set_sharedMesh renderer='...' mesh='...' verts=20278 submeshes=N  <== MATCH 5b34da41 (body)
  ```

卸载：删掉这个 dll 即可。

## 看什么

1. **有没有 `[HookMesh]` 行** → 证明 `set_sharedMesh` 是有效拦截点（后续换网格就插这里）。
2. **顶点数对不对**（20278 / 18037 / 5206 / 2012）。注意抓帧那是 D3D 拆点后的顶点数，
   Unity `Mesh.vertexCount` 通常一致；个别对不上就按量级 + submesh 数认。
3. **submesh 数 = 材质数**（c1b38296 那段含镂空材质，应有 ≥2）。

## 如果一条都不出现

说明这游戏的 body mesh 不是经 `set_sharedMesh` 属性赋值的（可能 AssetBundle 原生反序列化直接写字段）。
替代调查方向是用 `Resources.FindObjectsOfTypeAll(typeof(SkinnedMeshRenderer))` 全场扫描；
当前实验不继续实现该分支。

## 备注 / 风险

- 默认代理 `xinput1_3.dll`。若该游戏实际导入的是 `xinput1_4.dll`，把目标名和
  `dllmain.cpp` 里的 `#pragma /export` 转发目标一起改成 1_4（系统真 DLL 在 `System32`）。
- il2cpp 方法调用按 x64 ABI `(this, args..., MethodInfo*)`：`get_vertexCount` 这类
  属性 getter 直接调用并把 MethodInfo 作为末参传入。绝大多数版本适用；若崩在取顶点数，
  多半是这套 build 的 il2cpp 版本细节，告诉我我换成 `il2cpp_runtime_invoke`。
- 反作弊：这是单机渲染层注入，仅 hook Unity 渲染对象。是否触发服务器检测自行评估。
- 这份代码与 Android 的 `HookMesh` 检测逻辑等价，只是平台层换成 xinput 代理 + MinHook +
  GameAssembly.dll 导出解析。核心（按类/方法名解析 + set_sharedMesh hook）与你的汉化插件通用。
