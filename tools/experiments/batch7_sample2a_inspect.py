from pathlib import Path
import json
import sys
import bpy

blend = Path(sys.argv[-1])
repo = Path(r"D:\GIT\gakumas-modding\gakumas-modding")
sys.path.insert(0, str(repo))
import gakumas_mi

if not hasattr(bpy.types.Scene, "gmi_profile_dir"):
    gakumas_mi.register()
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
print("SCENE", scene.name)
for name in (
    "gmi_profile_dir", "gmi_body_json_library_dir", "gmi_body_resource",
    "gmi_component_id", "gmi_bone_remap_file", "gmi_physics_override_file",
    "gmi_output_dir", "gmi_package_id", "gmi_template_bundle_file",
):
    if hasattr(scene, name):
        print("SCENE_PROP", name, repr(getattr(scene, name)))

for obj in sorted(bpy.data.objects, key=lambda item: item.name):
    if obj.type not in {"ARMATURE", "MESH"}:
        continue
    print(
        "OBJECT",
        obj.name,
        obj.type,
        "verts=" + str(len(obj.data.vertices)) if obj.type == "MESH" else
        "bones=" + str(len(obj.data.bones)),
        "props=" + json.dumps(dict(obj.items()), ensure_ascii=False, default=str),
    )
    if obj.type == "ARMATURE":
        names = [bone.name for bone in obj.data.bones]
        skirt = [name for name in names if any(token in name.lower() for token in ("skirt", "streamer", "hem", "下摆", "裙"))]
        print("ARMATURE_SKIRT_NAMES", obj.name, json.dumps(skirt, ensure_ascii=False))

for material_file in (
    blend.parent.parent / "inputs" / "bone-remap.json",
    blend.parent.parent / "inputs" / "physics-override.json",
    blend.parent.parent / "materials" / "bone-remap.json",
    blend.parent.parent / "materials" / "physics-override.json",
):
    if material_file.is_file():
        print("EXTERNAL_JSON", material_file, material_file.read_text(encoding="utf-8"))
