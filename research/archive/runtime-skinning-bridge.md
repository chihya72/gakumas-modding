# Runtime Skinning Bridge 研究记录

> **历史记录（2026-06-24）**：本文记录的「进程内 IL2CPP Runtime 替换 Mesh」路线已放弃，
> 相关代码（`runtime/native/`、`tools/inject-runtime.ps1`）已删除。项目锁定为逆解每帧矩阵
> + 重蒙皮（路线 C），最新状态见
> [current-status-and-roadmap.md](current-status-and-roadmap.md)。保留本文用于记录当时的
> 证据与放弃原因。

起点检查点：`checkpoints/2026-06-22_031942_runtime-pivot`

## 2026-06-22 启动崩溃诊断

- 0.1.1 探针成功进入 IL2CPP domain，并成功解析全部定点 Unity Mesh/SkinnedMeshRenderer API。
- 随后在遍历 Assembly-CSharp 全部类和方法时触发 `0xc0000005`；日志中没有出现扫描完成标记。
- 这否定的是当前 Unity 版本上的“实时全量元数据枚举”，不是 Runtime 路线。
- 全量枚举已经停用；后续只使用定点 `il2cpp_class_from_name` 查询或离线元数据定位。

## 2026-06-22 D3D11 链加载结论

- 收窄后的探针两次都完整执行到 `Runtime probe complete`，证明定点 IL2CPP 查询本身没有导致崩溃。
- 3Dmigoto 日志随后连续出现 `Unexpected call back into D3D11CreateDevice`。
- 根因是把 Runtime DLL 配置为 `proxy_d3d11` 后，它再次加载并调用系统 D3D11，调用又被 3Dmigoto 钩回，形成代理递归。
- `proxy_d3d11` 不再作为 Runtime 加载入口。后续只考虑独立加载器或其他经过验证的进程内入口。

## 2026-06-22 初始结论

- 游戏使用 Unity `6000.0.67f1`。
- `GameAssembly.dll`：154,263,552 bytes。
- `global-metadata.dat`：43,968,988 bytes，metadata version 31.1。
- `GameAssembly.dll` 导出所需 IL2CPP 元数据 API，包括 class/image/method enumeration、`runtime_invoke`、array/type/object API。
- 旧版只读探针曾成功附加 IL2CPP domain（186 assemblies）并解析 `UnityEngine.Mesh`。
- Cpp2IL `2022.1.0-pre-release.21` 能识别 Unity 与 metadata 版本，但由于游戏没有可定位的 code/metadata registration structs，无法生成 Dummy DLL。后续以游戏自身导出的 IL2CPP enumeration API 为准。
- Metadata 字符串确认存在 `SkinnedMeshRenderer`、`get_sharedMesh`、`SetBoneWeights`、`GetAllBoneWeights`，以及游戏方法 `SetBodyCostume`、`get_BodyAssetId`、`get_CostumeAssetNames` 等。

## 已完成的只读探针扩展

`runtime/native/il2cpp_diagnostics.cpp` 现在只解析、不调用以下 API：

- `SkinnedMeshRenderer.get_sharedMesh/set_sharedMesh`
- `SkinnedMeshRenderer.get_bones/set_bones/get_rootBone`
- `Mesh.get_vertexCount/get_bindposes/get_boneWeights`
- `Mesh.GetBonesPerVertex/GetAllBoneWeights/SetBoneWeights`
- `Transform.get_localToWorldMatrix/get_worldToLocalMatrix`

探针还会通过 `il2cpp_image_get_class*` 与 `il2cpp_class_get_methods` 定位关键服装方法的实际程序集和所属类。

编译产物：`dist/runtime/GakumasMIRuntime.dll`

## 安全边界

当前版本不执行 `runtime_invoke`，不枚举 Unity 对象实例，不挂钩函数，不修改 Mesh。后台线程只访问 IL2CPP 元数据。

当前游戏进程拒绝 `OpenProcess`，因此未进行热注入。下一次验证必须通过游戏启动时链加载，或由同权限环境加载；不得尝试绕过进程保护。

## 候选实现路线

优先级 A：在游戏加载/设置 Body costume 的主线程调用链中观察 `SkinnedMeshRenderer` 和原始 `Mesh`，创建或替换一个带自定义 vertices/indices/bone weights/bindposes 的运行时 Mesh，继续使用 Unity 自身 CPU skinning。

优先级 B：只读取 renderer bones 的 `localToWorldMatrix`，由 Runtime 上传骨骼矩阵并运行统一 Compute Skinning，输出与游戏 Body Draw 相同的 40-byte VB0。

优先尝试 A，因为它更完整地保留 Unity 的 BlendShape、bounds、渲染器生命周期和既有动画；如果 Unity 6 Mesh 写入接口或资源生命周期不稳定，再退到 B。

## 下一次实机验证

1. 通过可回退的链加载方式启用只读探针。
2. 正常启动并进入任意角色场景。
3. 检查日志中的 Unity API 地址和关键游戏方法所属类。
4. 探针稳定后，才增加主线程上的只读对象观察；仍不替换 Mesh。
