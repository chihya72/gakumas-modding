from pathlib import Path
import json
import sys
import bpy

blend = Path(sys.argv[-1])
repo = Path(r"D:\GIT\gakumas-modding\gakumas-modding")
project = blend.parents[1]
profile = project / "profile"
library = repo / "libraries" / "assetstudio-body-json"
remap = project / "inputs" / "bone-remap.json"
physics = project / "inputs" / "physics-override.json"
sys.path.insert(0, str(repo))
import gakumas_mi

if not hasattr(bpy.types.Scene, "gmi_profile_dir"):
    gakumas_mi.register()
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
scene.gmi_profile_dir = str(profile)
scene.gmi_body_json_library_dir = str(library)
scene.gmi_body_resource = "mdl_chr_hmsz-cstm-0059_body"
scene.gmi_component_id = "body"
scene.gmi_bone_remap_file = str(remap)
scene.gmi_physics_override_file = str(physics)
obj = bpy.data.objects.get("dress_2219_full_combined")
if obj is None:
    raise RuntimeError("作者网格 dress_2219_full_combined 不存在")
for selected in bpy.context.selected_objects:
    selected.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
result = bpy.ops.gmi.report_rig_alignment()
print("REPORT_RESULT", result)
print("REPORT_JSON", scene.gmi_rig_report)
report_path = Path(r"D:\GIT\gakumas-modding\mod-workspace\experiments\batch7-sample2a-rig-report.json")
report_path.write_text(scene.gmi_rig_report + "\n", encoding="utf-8")
if "FINISHED" not in result:
    raise RuntimeError(str(result))
report = json.loads(scene.gmi_rig_report)
print(json.dumps({
    "measured": report["measured"],
    "skipped": report["skipped"],
    "alignment": report["alignment"][:5],
    "bands": report["bands"],
    "collapsed": report["collapsed"],
}, ensure_ascii=False))
