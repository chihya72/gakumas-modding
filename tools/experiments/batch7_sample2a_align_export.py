from pathlib import Path
import json
import sys
import bpy

blend = Path(sys.argv[-1])
repo = Path(r"D:\GIT\gakumas-modding\gakumas-modding")
project = blend.parents[1]
profile = project / "profile"
library = repo / "libraries" / "assetstudio-body-json"
remap_path = project / "inputs" / "bone-remap.json"
physics_path = project / "inputs" / "physics-override.json"
package_root = Path(r"D:\GIT\gakumas-modding\mod-workspace\experiments\batch7-sample2a-hmsz")
package_id = "batch7-sample2a-hmsz-source-skirt"
package_root.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(repo))
import gakumas_mi
from gakumas_mi import core, operators

if not hasattr(bpy.types.Scene, "gmi_profile_dir"):
    gakumas_mi.register()
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
scene.gmi_profile_dir = str(profile)
scene.gmi_body_json_library_dir = str(library)
scene.gmi_body_resource = "mdl_chr_hmsz-cstm-0059_body"
scene.gmi_component_id = "body"
scene.gmi_source_rig = "scsp"
scene.gmi_bone_remap_file = str(remap_path)
scene.gmi_physics_override_file = str(physics_path)
scene.gmi_output_dir = str(package_root)
scene.gmi_package_id = package_id
scene.gmi_package_name = "batch7 sample2a hmsz source skirt"
scene.gmi_author = "pm"
scene.gmi_unmapped_bone_fallback = "Hips"
scene.gmi_outline_width_mode = "KEEP"
scene.gmi_vertex_color_mode = "MATERIAL_PRESET"

texture_dir = project / "package" / "bundle-src"
scene.gmi_base_color_file = str(texture_dir / "body_slot0_t0.png")
scene.gmi_packed_mask_file = str(texture_dir / "body_slot0_t1.png")
scene.gmi_shade_color_file = str(texture_dir / "body_slot0_t4.png")
scene.gmi_opacity_texture_file = str(texture_dir / "body_slot1_t0.png")
scene.gmi_opacity_packed_mask_file = str(texture_dir / "body_slot1_t1.png")
scene.gmi_opacity_shade_color_file = str(texture_dir / "body_slot1_t4.png")

obj = bpy.data.objects.get("dress_2219_full_combined")
source_arm = bpy.data.objects.get("dress_2219_full_armature")
target_arm = bpy.data.objects.get("Geo_Body_Armature.001")
if obj is None or source_arm is None or target_arm is None:
    raise RuntimeError("缺少 hmsz 作者网格或两副骨架")
for selected in bpy.context.selected_objects:
    selected.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

resolved = operators._resolve_body_json_library(scene, "body")
skeleton = core.load_json(Path(resolved["skeletonJson"]))
bone_map = core.inverse_skin_bone_map(str(profile), Path(resolved["skeletonJson"]), "body")
remap, remap_report = operators._resolve_source_bone_remap(obj, bone_map, scene, skeleton)
body_names = list(remap_report.get("bodyBones") or [])
direct = {}
for source_name in body_names:
    target_name = remap.get(source_name)
    if target_name and target_arm.data.bones.get(target_name) and source_arm.data.bones.get(source_name):
        direct[source_name] = target_name
if not direct:
    raise RuntimeError("没有解析出 direct 身体骨映射")

old = {bone.name: source_arm.matrix_world @ bone.matrix_local for bone in source_arm.data.bones}
new = {}
for source_name, target_name in direct.items():
    target_bone = target_arm.data.bones[target_name]
    new[source_name] = source_arm.matrix_world.inverted() @ target_arm.matrix_world @ target_bone.matrix_local

def depth(bone):
    value = 0
    while bone.parent:
        value += 1
        bone = bone.parent
    return value

for bone in sorted(source_arm.data.bones, key=depth):
    if bone.name in new:
        continue
    parent = bone.parent
    while parent and parent.name not in new:
        parent = parent.parent
    if parent is not None:
        delta = new[parent.name] @ old[parent.name].inverted()
        new[bone.name] = delta @ old[bone.name]

bpy.context.view_layer.objects.active = source_arm
source_arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for edit_bone in source_arm.data.edit_bones:
    matrix = new.get(edit_bone.name)
    if matrix is not None:
        edit_bone.matrix = matrix
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.update()

aligned_blend = package_root / "aligned-authoring.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(aligned_blend))

obj.select_set(True)
bpy.context.view_layer.objects.active = obj
alignment_result = bpy.ops.gmi.report_rig_alignment()
alignment = json.loads(scene.gmi_rig_report)
print("ALIGN_RESULT", alignment_result)
print("ALIGN_SUMMARY", json.dumps({
    "direct": len(direct),
    "alignedBones": len(new),
    "worst": alignment["alignment"][:8],
    "bands": alignment["bands"],
}, ensure_ascii=False))
if "FINISHED" not in alignment_result:
    raise RuntimeError(str(alignment_result))

export_result = bpy.ops.gmi.export_bundle_source()
print("EXPORT_RESULT", export_result)
print("EXPORT_SUMMARY", json.dumps({
    "packageRoot": str(package_root),
    "package": str(package_root / package_id),
    "alignedBlend": str(aligned_blend),
    "direct": len(direct),
    "alignedBones": len(new),
}, ensure_ascii=False))
if "FINISHED" not in export_result:
    raise RuntimeError(str(export_result))
