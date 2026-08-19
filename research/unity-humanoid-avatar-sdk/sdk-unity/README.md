# Unity SDK editor package (P1)

Copy `Editor/GakumasAvatarSdkBuilder.cs` into the Unity 6000 SDK project under
`Assets/GakumasAvatarSdk/Editor/`. The builder provides the first author-side
vertical slice:

1. select a prefab containing a valid Humanoid `Animator`;
2. scan all child renderers and classify them as body/face/hair/accessory;
3. hard-fail on missing required Humanoid bones, duplicate paths or invalid
   blendshape references;
4. write a descriptor matching `contracts/avatar-descriptor.schema.json`;
5. assign the prefab and descriptor to an AssetBundle and build a Windows AB.

The builder intentionally does not retarget a mesh or invent a rest-pose
correction. Unity's imported Humanoid Avatar is the author-side contract. Pose
bridging and game lifecycle binding remain runtime responsibilities until the P0
probe confirms the game's Animator behavior.

## Usage

Open **Gakumas / Avatar SDK / Build Selected Avatar Bundle**, fill in the package
metadata and output directory, then build. The descriptor and bundle are emitted
under `Assets/GakumasAvatarSdk/Build/<package-id>/` and the selected prefab is
marked with the requested bundle name.

For headless/CI builds, invoke Unity with
`-executeMethod Gakumas.AvatarSdk.Editor.GakumasAvatarSdkBuilder.BuildAvatarBundleFromArgs`
and pass `-avatarPrefab Assets/.../Avatar.prefab -avatarOutput <directory> -avatarTarget fktn`.

For author overrides, add the components from `AvatarAuthoringComponents.cs`:

- `AvatarRendererAuthoring` overrides automatic body/face/hair/accessory role detection;
- `AvatarExpressionAuthoring` maps game channels to exact BlendShape names;
- `AvatarSpringAuthoring` records manually selected skirt, ribbon or hair chains.
- `AvatarColliderAuthoring` records sphere/capsule collider anchors for those chains.

Explicit expression mappings replace the conservative alias scan, so a typo or a
missing BlendShape fails the export instead of silently producing a dead channel.

The source is mirrored into the local template project at
`mod-workspace/pipelines/ip/unity-template-builder/Assets/GakumasAvatarSdk/` for
Unity compilation. The `research/unity-humanoid-avatar-sdk/sdk-unity/` copy is
the canonical source to review and carry into the eventual standalone SDK
package.
