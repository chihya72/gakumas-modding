"""PMX -> FBX for the Gakumas SDK, headless.

    blender --background --factory-startup --python pmx_to_fbx.py -- --pmx <file> --out <dir>

Only two things happen here, and both are the ones Unity cannot do for itself: mmd_tools reads the
PMX, and the humanoid bones get names Unity's avatar mapper recognises (the addon's own
`mmd-standard` table, 78 entries). The T-pose bake, the rig and the packing all stay in the SDK.
"""
import json
import os
import re
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
options = dict(zip(argv[::2], argv[1::2]))
pmx = options["--pmx"]
out = options["--out"]
presets = options.get("--presets")

# Empty the scene first: read_factory_settings resets addon state, so enabling has to come after it.
bpy.ops.wm.read_factory_settings(use_empty=True)
# 4.2 ships mmd_tools as an extension rather than a legacy addon.
for module in ("bl_ext.blender_org.mmd_tools", "mmd_tools"):
    try:
        bpy.ops.preferences.addon_enable(module=module)
        print(f"[PMX] enabled {module}")
    except Exception as error:
        print(f"[PMX] {module}: {error}")
if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
    raise SystemExit("[PMX] mmd_tools 没注册上，import_model 不可用")
# 0.08 is mmd_tools' own default and puts a standard PMX at roughly human height in metres.
bpy.ops.mmd_tools.import_model(filepath=pmx, scale=0.08, types={"MESH", "ARMATURE"},
                               clean_model=True, remove_doubles=False)

armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not armatures or not meshes:
    raise SystemExit(f"[PMX] 导入失败：骨架 {len(armatures)}，网格 {len(meshes)}")
armature = armatures[0]
print(f"[PMX] 骨架 {armature.name}：{len(armature.data.bones)} 根骨；网格 {len(meshes)} 个，"
      f"顶点 {sum(len(m.data.vertices) for m in meshes)}")


def fold(name):
    """mmd_tools writes PMX 右腕 as 腕.R; fold it back to look the table up."""
    sided = re.fullmatch(r"(.+)\.([LR])", name)
    return ("左" if sided.group(2) == "L" else "右") + sided.group(1) if sided else None


table = json.load(open(presets, encoding="utf-8"))["presets"]["mmd-standard"]
table = table.get("bones", table)
renamed, taken = 0, {b.name for b in armature.data.bones}
for bone in armature.data.bones:
    target = table.get(bone.name) or (table.get(fold(bone.name)) if fold(bone.name) else None)
    if not target or target == bone.name or target in taken:
        continue
    taken.discard(bone.name)
    taken.add(target)
    print(f"[PMX] {bone.name} -> {target}")
    bone.name = target
    renamed += 1
print(f"[PMX] 骨名映射 {renamed} 根")

# mmd_tools wires the base texture into its own `mmd_shader` group, and Blender's FBX exporter only
# follows a Principled BSDF's Base Color — so the FBX comes out with no texture references at all and
# every material lands in Unity with no main texture ("这一段会没有底色"). Re-link it.
wired = 0
for material in bpy.data.materials:
    if not material.use_nodes:
        continue
    tex = material.node_tree.nodes.get("mmd_base_tex")
    if tex is None or tex.image is None:
        continue
    bsdf = next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = next((n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if output is not None:
        material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    wired += 1
print(f"[PMX] 基础贴图接到 Principled 上：{wired} 个材质")

height = max((armature.matrix_world @ b.head_local).z for b in armature.data.bones)
print(f"[PMX] 骨架高度 {height:.3f} m（Blender 里 z 朝上；学马原版约 1.58 m）")

os.makedirs(out, exist_ok=True)
target = os.path.join(out, "kth_qinye.fbx")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.fbx(
    filepath=target,
    use_selection=True,
    # Without FBX_SCALE_UNITS the metre/centimetre conversion lands on node scales and every
    # downstream bind pose reads garbage — the audit's "×100 scale" failure.
    apply_scale_options="FBX_SCALE_UNITS",
    add_leaf_bones=False,
    bake_anim=False,
    path_mode="STRIP",
    embed_textures=False,
    mesh_smooth_type="FACE",
)
print(f"[PMX] 已导出 {target}  ({os.path.getsize(target)} bytes)")
