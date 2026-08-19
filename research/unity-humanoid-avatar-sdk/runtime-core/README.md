# Runtime core

This is the engine-independent contract layer for the Windows BepInEx route. It
does not reference `UnityEngine`, `Il2CppInterop` or Harmony, so the same package
binding and descriptor validation can be tested without launching the game.

The eventual BepInEx adapter will be responsible for:

1. locating the game actor and its `AvatarHost`/renderer hierarchy;
2. loading the configured AssetBundle and descriptor;
3. creating the replacement visual root while retaining the game's Animator;
4. applying expression weights and spring-chain updates each frame; and
5. rolling back cleanly if any live contract check fails.

Build the current slice with:

```powershell
dotnet build .\AvatarRuntime.Core.csproj --configuration Release
```
