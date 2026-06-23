# GakumasMI Native Runtime 0.1

This x64 DLL is an experimental read-only IL2CPP diagnostic runtime. Do not
chain-load it through 3DMigoto's `proxy_d3d11`: that route recursively re-enters
3DMigoto's D3D11 hook in this game. A separate, validated loader is required.

The diagnostic stage locates the IL2CPP domain, UnityEngine Core/AssetBundle images, and the `Mesh`, `SkinnedMeshRenderer`, `Renderer`, `Transform`, and `Component` classes. It resolves candidate mesh, bone, bind-pose, and transform methods required for a future in-memory skinning bridge. It does not invoke Unity object APIs, hook functions, or mutate game objects yet.

Build:

```powershell
& 'C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe' runtime\native\GakumasMIRuntime.vcxproj /p:Configuration=Release /p:Platform=x64
```
