"""Headless Blender smoke exporter for a weighted FBX -> inverse-skin Mod."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Matrix


args = sys.argv[sys.argv.index("--") + 1 :]
if len(args) < 6:
    raise SystemExit(
        "usage: blender -b --python export_inverse_skin_fbx_mod.py -- "
        "FBX PROFILE SKELETON OUTPUT PACKAGE_ID FALLBACK_BONE"
    )
source, profile, skeleton, output = map(lambda value: Path(value).resolve(), args[:4])
package_id, fallback = args[4:6]
remap_file = Path(args[6]).resolve() if len(args) > 6 and args[6] else None
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "blender_addon"))
import gakumas_mi  # noqa: E402


bpy.ops.wm.read_factory_settings(use_empty=True)
gakumas_mi.register()
bpy.ops.import_scene.fbx(filepath=str(source))
meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if len(meshes) != 1:
    raise RuntimeError(f"Expected one mesh, found {len(meshes)}")
obj = meshes[0]
# Blender's FBX importer retains the source centimeter unit on the parent
# armature. Scaling the armature also updates its child mesh exactly once.
for armature in (candidate for candidate in bpy.context.scene.objects if candidate.type == "ARMATURE"):
    armature.matrix_world = Matrix.Scale(100.0, 4) @ armature.matrix_world
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
scene = bpy.context.scene
scene.gmi_profile_dir = str(profile)
scene.gmi_skeleton_json = str(skeleton)
scene.gmi_output_dir = str(output)
scene.gmi_component_id = "body"
scene.gmi_package_id = package_id
scene.gmi_package_name = "TTMR 0119 Inverse Skin Test"
scene.gmi_author = "GakumasMI"
scene.gmi_unmapped_bone_fallback = fallback
scene.gmi_bone_remap_file = str(remap_file) if remap_file else ""
result = bpy.ops.gmi.export_inverse_skin_mod()
if "FINISHED" not in result:
    raise RuntimeError(f"Inverse-skin export failed: {result}")
package = output / package_id
print(f"GMI_INVERSE_SKIN_PACKAGE={package}")
