from pathlib import Path
import sys
import bpy

blend = Path(sys.argv[-1])
bpy.ops.wm.open_mainfile(filepath=str(blend))
for name in ("dress_2219_full_combined", "GMI_Geo_Body_body_带权重参考"):
    obj = bpy.data.objects.get(name)
    if obj is None:
        continue
    print("OBJECT", name, "matrix", tuple(round(v, 6) for row in obj.matrix_world for v in row))
    for mod in obj.modifiers:
        print("MOD", name, mod.name, mod.type, getattr(getattr(mod, "object", None), "name", None))
    print("PARENT", name, getattr(obj.parent, "name", None))
for name in ("dress_2219_full_armature", "Geo_Body_Armature.001"):
    arm = bpy.data.objects.get(name)
    if arm is None:
        continue
    print("ARM", name, "matrix", tuple(round(v, 6) for row in arm.matrix_world for v in row), "parent", getattr(arm.parent, "name", None))
