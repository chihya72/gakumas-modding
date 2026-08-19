# Reference data

This directory stores generated, reviewable reference artifacts for the next-generation route.

The first artifact is `asset-inventory.json`. It is built from the checked-in AssetStudio dumps and
contains body/hair resource names, mesh file evidence, skeleton node names and weighted-bone sets.
The checked-in fast inventory leaves vertex/submesh/blendshape statistics as `not_collected`; pass
`--include-mesh-stats` when doing that slower audit. It does **not** contain a live Animator, face
controller or HumanPose reference. Those fields remain `not_observed` until the BepInEx P0 probe
captures them from the running game.

Regenerate it from the repository root with:

```powershell
python tools/build_avatar_reference_inventory.py `
  --data-root ..\..\..\mod-workspace\libraries `
  --output reference\asset-inventory.json
```
