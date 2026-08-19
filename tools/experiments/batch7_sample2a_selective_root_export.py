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
package_root = Path(r"D:\GIT\gakumas-modding\mod-workspace\experiments\batch7-sample2a-hmsz-selective-root")
package_id = "batch7-sample2a-hmsz-selective-root"
if package_root.exists():
    raise RuntimeError(f"实验输出已存在，拒绝覆盖：{package_root}")
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
scene.gmi_package_name = "batch7 sample2a hmsz selective root"
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

# This list is copied from D's final sidecar. E may move only declared chain roots.
chain_roots = [
    "Bag_R_A0", "Chain_R_A0", "Key_R_A0", "Spine_Bow_L_A0", "Spine_Bow_R_A0",
    "Belt_L_A0", "Skirt_L_A0", "Skirt_L_B0", "Skirt_L_C0", "Skirt_L_D0", "Skirt_L_E0",
    "Skirt_R_A0", "Skirt_R_B0", "Skirt_R_C0", "Skirt_R_D0", "Skirt_R_E0",
    "OPAI_L0_1", "OPAI_R0_1", "Spine2_Bow_L_A0", "Spine2_Bow_L_B0",
    "Spine2_Bow_R_A0", "Spine2_Bow_R_B0",
]

old_local = {bone.name: bone.matrix_local.copy() for bone in source_arm.data.bones}
old_world = {bone.name: source_arm.matrix_world @ bone.matrix_local for bone in source_arm.data.bones}
new_local = dict(old_local)
new_world = {}
for source_name, target_name in direct.items():
    target_bone = target_arm.data.bones[target_name]
    new_world[source_name] = target_arm.matrix_world @ target_bone.matrix_local
    new_local[source_name] = source_arm.matrix_world.inverted() @ new_world[source_name]

missing_roots = [name for name in chain_roots if source_arm.data.bones.get(name) is None]
if missing_roots:
    raise RuntimeError("D 链根在作者骨架中不存在: " + ", ".join(missing_roots))

# Move only each chain root by its nearest direct-parent frame delta. Children
# retain their old local matrices, so their segment lengths and local shape stay unchanged.
root_deltas = {}
for root_name in chain_roots:
    bone = source_arm.data.bones[root_name]
    parent = bone.parent
    while parent and parent.name not in new_world:
        parent = parent.parent
    if parent is None:
        raise RuntimeError(f"链根没有 direct 祖先: {root_name}")
    delta = new_world[parent.name] @ old_world[parent.name].inverted()
    new_world[root_name] = delta @ old_world[root_name]
    new_local[root_name] = source_arm.matrix_world.inverted() @ new_world[root_name]
    root_deltas[root_name] = {
        "parent": parent.name,
        "translationMm": [
            (new_world[root_name].translation[i] - old_world[root_name].translation[i]) * 1000.0
            for i in range(3)
        ],
    }

bpy.context.view_layer.objects.active = source_arm
source_arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for edit_bone in source_arm.data.edit_bones:
    edit_bone.use_connect = False
    matrix = new_local.get(edit_bone.name)
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
    "chainRoots": len(chain_roots),
    "rootDeltas": root_deltas,
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
    "chainRoots": len(chain_roots),
}, ensure_ascii=False))
if "FINISHED" not in export_result:
    raise RuntimeError(str(export_result))
