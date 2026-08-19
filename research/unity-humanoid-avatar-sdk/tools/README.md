# P0 tools

`build_avatar_reference_inventory.py` consumes the existing AssetStudio JSON dumps under
`mod-workspace/libraries` and writes an asset-level reference inventory. It intentionally marks
live-only fields (`animator`, `face`, `pose`) as `not_observed`; the result is evidence for the
BepInEx probe, not a substitute for a live scene dump.

```powershell
python tools/build_avatar_reference_inventory.py `
  --data-root ..\..\..\mod-workspace\libraries `
  --output ..\reference\asset-inventory.json
```

默认只读取 skeleton JSON，适合快速建立骨骼覆盖 inventory。需要额外审计顶点数、submesh 和 blendshape 时，加上 `--include-mesh-stats`；该模式会读取较大的 mesh JSON，速度会明显变慢。

`validate_avatar_descriptor.py` checks the offline portion of a descriptor before an eventual
Unity bundle build. It verifies paths, renderer uniqueness, expression targets, spring chains,
protocol fields and finite numeric parameters. It cannot inspect the prefab until the Unity SDK
builder exists.

`validate_manifest.py` checks package identity, normalized bundle/asset paths and unique target
character IDs:

```powershell
python tools/validate_manifest.py example-mod.json
```

The same descriptor validator can check the SDK sample output:

```powershell
python tools/validate_avatar_descriptor.py example-avatar.avatar.json
```

`scan_clip_bindings.py` tells humanoid (muscle) clips from generic (by-path) clips in any Unity
file. It is the evidence behind `docs/rest-pose-dead-end.md` §零 — the shipped body clips bind
nothing but Animator muscles, so the body is driven purely by Humanoid retargeting:

```powershell
python tools/scan_clip_bindings.py D:\Games\gakumas\gakumas_Data\data.unity3d
```

Re-run it on any motion bundle that gets decrypted: only the two common idles in `data.unity3d`
have been checked, never a live/dance clip.

The matching offline test bench is `Editor/AvatarBench.cs` in the Unity project — it builds the
Avatar the way the game does and measures where the limbs land, so a model can be rejected without
a game run:

```powershell
& .local\Unity6000.0.77f1\Editor\Unity.exe -batchmode -quit -nographics `
  -projectPath GakumasAvatarSdk -executeMethod GakumasSdk.AvatarBench.RunFromArgs `
  -logFile bench.log
```
