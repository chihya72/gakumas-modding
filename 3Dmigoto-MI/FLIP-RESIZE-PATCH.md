# 自定义补丁:FLIP swap chain 横竖屏切换修复

> 适用问题:《学园偶像大师》在 **竖屏(1080×1920)↔ 横屏 live(1920×1080)** 切换时
> 黑屏 / 画面只渲染在一角 / 绿色噪点 / 闪烁。**与 mod 无关**——禁用所有 mod、原生
> 模型同样犯。本仓库的 `d3d11.dll` 是打了本补丁的**自编译版**,不是 3DMigoto 官方发行版。

## 根因(已用 `calls=1` 日志钉死)

游戏的 swap chain 是 **FLIP 模型**(`SwapEffect=3`),创建时 `Flags = 0x842`,其中:

| 位 | 含义 |
|---|---|
| `0x800` | `DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING` |
| `0x40`  | `DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT` |
| `0x02`  | `DXGI_SWAP_CHAIN_FLAG_ALLOW_MODE_SWITCH` |

切方向时游戏调用 `IDXGISwapChain::ResizeBuffers`,但 **`SwapChainFlags` 只传了
`0x802`——丢掉了 `0x40`(WAITABLE)位**。DXGI 硬性规定:用 WAITABLE 标志创建的
swap chain,每次 `ResizeBuffers` 都必须带同一个 `0x40`,否则返回
`0x80070057 (E_INVALIDARG)`。于是:

```
ResizeBuffers 1280x720  flags=0x842  -> 0          (同尺寸空操作，碰巧成功)
ResizeBuffers 720x1280  flags=0x802  -> 0x80070057 (失败)
```

resize 失败 → swap chain 卡在旧尺寸 → 游戏按新尺寸渲染到错位子区域 → 黑/噪/闪。

> 注意:这**不是**「back buffer 引用未释放」问题。试过 `OMSetRenderTargets(0,…)` +
> `ClearState()` + `Flush()` 全部无效;改 flag 才是正解。官方 bo3b 与各 fork 的
> `ResizeBuffers` 都是纯转发、均无此修复。

## 补丁

文件:`DirectX11/HackerDXGI.cpp`,函数 `HackerSwapChain::ResizeBuffers`。
在转发给 `mOrigSwapChain1->ResizeBuffers(...)` 之前,把创建时的 WAITABLE 位补回去:

```cpp
  // FIX (flip swap chain orientation change): DXGI requires ResizeBuffers to
  // preserve the FRAME_LATENCY_WAITABLE_OBJECT (0x40) flag the swap chain was
  // created with. This game drops that flag on portrait<->landscape resizes
  // (passes 0x802 instead of the creation 0x842), so ResizeBuffers fails with
  // E_INVALIDARG (0x80070057) and the swap chain freezes at its old size.
  DXGI_SWAP_CHAIN_DESC1 gkms_scd;
  if (SUCCEEDED(mOrigSwapChain1->GetDesc1(&gkms_scd)))
    SwapChainFlags |=
        (gkms_scd.Flags & DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT);

  HRESULT hr = mOrigSwapChain1->ResizeBuffers(BufferCount, Width, Height,
                                              NewFormat, SwapChainFlags);
```

即在原本那行 `HRESULT hr = mOrigSwapChain1->ResizeBuffers(...)` 前插入那段
`DXGI_SWAP_CHAIN_DESC1` 取描述 + 补 flag 的代码。其余不动。

## 重新编译

源码用 bo3b 结构的 3DMigoto(`StereovisionHacks.sln`)。注意两个坑:

1. **必须通过 `.sln` 构建 `DirectX11` 目标**,不能直接编 `DirectX11.vcxproj`——
   否则 `$(SolutionDir)` 缺失,子项目找不到 `log.h`。
2. 若本机没有项目默认的 Windows SDK(如 `10.0.19041.0`),用参数重定向到已装版本,
   不必改项目文件。

示例(VS 2022 + SDK 10.0.26100 + v143):

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" `
  StereovisionHacks.sln /t:DirectX11 `
  /p:Configuration=Release /p:Platform=x64 `
  /p:WindowsTargetPlatformVersion=10.0.26100.0 /p:PlatformToolset=v143
```

产出:`builds\x64\Release\d3d11.dll` → 复制到游戏目录(及本仓库 `3Dmigoto-MI/`)。

## 验证

游戏目录 `d3dx.ini` 临时设 `[Logging] calls=1`、`unbuffered=1`,进 live 切横屏后看
`d3d11_log.txt`:所有 `ResizeBuffers ... returns result = 0`、横屏 flags 为 `0x842`
即修复成功。验证完改回 `calls=0`。
