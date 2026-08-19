# BepInEx adapter (P1 scaffold)

## Bootstrap status

The current Windows game build is Unity `6000.0.77f1`. Its protected on-disk
`GameAssembly.dll` cannot be used as Cpp2IL input: code registration is absent
on disk, and an in-process memory capture still leaves runtime `Il2CppType`
pointers that Cpp2IL incorrectly interprets as metadata indices. Capturing more
heap pages does not repair that semantic mismatch.

The bootstrap blocker is resolved without unpacking the game binary. A clean,
exact-version Unity `6000.0.77f1` Windows IL2CPP player preserves the standard
Unity API surface and supplies a valid Cpp2IL input. BepInEx generates the
`UnityEngine*` and `Il2Cpp*` interop proxies from that player once, offline. The
game deployment contains only those standard proxies, disables automatic
interop generation and omits blank-player-specific `Assembly-CSharp.dll`,
`__Generated.dll` and xref/address databases. The cache hash is computed from
the real game `GameAssembly.dll`, Unity base libraries and fixed generator
versions, so startup does not attempt Cpp2IL or network access.

The reproducible evidence and release gates are recorded in
[`../P0-OFFLINE-BOOTSTRAP.md`](../P0-OFFLINE-BOOTSTRAP.md).

This folder is the Windows runtime entry point planned for the Unity route. It
is intentionally kept separate from `runtime-core`: the adapter will reference
the game, BepInEx, UnityEngine and Il2CppInterop assemblies supplied by a local
game installation, while the core contract remains buildable in CI.

The current source is a lifecycle/configuration scaffold only. It does not
replace a renderer until the P0 live probe has recorded the actual actor,
Animator and renderer paths. That boundary prevents a guessed path from
silently hiding the original character or leaking objects across scene loads.

`AvatarProbePlugin.cs` is the companion P0 probe. It writes JSON snapshots under
`BepInEx/config/gakumas-avatar-probe/`. It records Animator/Humanoid state,
controller settings, complete transform hierarchy and local rest transforms,
HumanBodyBones, renderer paths, bones/root bone, mesh statistics, materials and
BlendShape names/current weights. It takes an initial scene snapshot and then
checks every 120 frames; an asynchronously spawned or replaced character
therefore produces a new snapshot automatically. `F6` remains a forced manual
snapshot. The probe deliberately does not mutate the scene.

Expected local build inputs (not checked in):

- BepInEx 6 IL2CPP core assemblies;
- Unity `6000.0.77f1` Windows IL2CPP build support;
- the game's downloaded `UnityEngine*.dll` base libraries;
- the exact-version offline-generated standard proxy assemblies;
- `Il2CppInterop.Runtime.dll`;
- the built `AvatarRuntime.Core.dll`.

Once the probe artifacts exist, add a local `.csproj` that references those
assemblies and wire `AvatarRuntimePlugin` to the validated live binder.

For the current installation, the offline probe project is
`AvatarProbe.Local.csproj`; its compiled output is copied to
`D:\Games\gakumas\BepInEx\plugins\GakumasAvatarProbe\GakumasAvatarProbe.dll`.
The current P0 probe is `0.2.0-p0`. Before a game launch it must pass the clean
synthetic-player test with `UpdateInteropAssemblies = false`, no Cpp2IL/xref
run, no blank `Assembly-CSharp.dll`, and a validated JSON snapshot.
