"""Offline check of the AB skinning path: does a posed joint deform the mod mesh sanely?

In-game the bundle mesh is driven by `Σ w · gameBoneAnimated · gameBindpose · v`. Static
always looks right (at rest that product is identity), so mis-assigned/mis-placed weights
only show up once a joint rotates — which used to mean one full in-game round trip per
guess. This reproduces that math in Blender: pose the GAME armature, skin the mod mesh
with the exported weights (source vertex groups relabeled through the remap JSON), and
report edge-stretch. The game's own reference body, skinned the same way with its native
weights, is the known-good baseline: sane bends keep stretch near 1.0, an exploding region
shows up as a large p99/max.

Objects are discovered from the scene, so this runs on any project's blend:
the reference body carries `gmi_weighted_reference` (else a `GMI_*参考*` name), the game
armature is the one it is bound to, and the mod mesh is the largest other skinned mesh.

Two things this metric cannot do — measured, not assumed (see the plan doc §6.8):
it is relative to rest, so breaking the rest itself makes it look *better*; and structural
absolute thresholds (bone-to-geometry distance over bone length, or "is the dominant bone
the nearest one") do NOT separate healthy from broken binds, because twist/helper bones and
duplicated `_1` chains confound them. Always compare against the reference body in the same
scene, and confirm visually.

Run: blender --background <blend> --python tools/simulate_ab_skinning.py -- [remap.json]
"""
import json
import sys
from math import radians

import bpy
from mathutils import Matrix, Vector

FINGERS = ("HandIndex", "HandMiddle", "HandRing", "HandPinky", "HandThumb")
# MMD 导入器给**每一个**顶点都写 mmd_edge_scale / mmd_vertex_order，权重常年 1.0 —— 按主导
# 顶点组分区时它会赢下全部 55108 个顶点，于是每个区都是空的、体检整个静默失效（只剩一句
# "无法评估"）。与 operators.NON_BONE_GROUPS 同一份名单；这个脚本要能独立 blender --python
# 跑，所以不 import 插件。
NON_BONE_GROUPS = frozenset({"mmd_edge_scale", "mmd_vertex_order"})
BEND_DEGREES = 45.0
# Above this multiple of the reference body's stretch the region is called broken. fuyuko's
# shredded fingers measured p99 2.99 vs the reference's 1.62 (1.8x) and max 7.12 vs 4.07.
FAIL_RATIO = 1.5


def skinned_meshes():
    return [obj for obj in bpy.data.objects
            if obj.type == "MESH"
            and any(m.type == "ARMATURE" and m.object for m in obj.modifiers)
            and obj.data.vertices]


def find_objects():
    """(mod mesh, reference body, game armature) discovered from the scene."""
    meshes = skinned_meshes()
    reference = next((obj for obj in meshes if obj.get("gmi_weighted_reference")), None)
    if reference is None:
        reference = next((obj for obj in meshes
                          if obj.name.startswith("GMI_") and "参考" in obj.name), None)
    if reference is None:
        raise SystemExit("场景里没有 GMI 带权重参考体,无法建立已知正确基线")
    game = next(m.object for m in reference.modifiers
                if m.type == "ARMATURE" and m.object)
    candidates = [obj for obj in meshes if obj is not reference
                  and not obj.name.startswith("GMI_")]
    if not candidates:
        raise SystemExit("场景里找不到作者网格")
    mod = max(candidates, key=lambda obj: len(obj.data.vertices))
    return mod, reference, game


def load_remap(path):
    if not path:
        return {}
    data = json.load(open(path, encoding="utf-8"))
    return data.get("bones", data)


def bone_matrices(armature, posed_bones, degrees):
    """Return {bone: gameBoneAnimated @ gameBindpose} in world space for one test pose."""
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)
    for name in posed_bones:
        pose_bone = armature.pose.bones.get(name)
        if pose_bone:
            # Local X is the curl axis for these chains; any consistent rotation works as a
            # stress test since both meshes get the identical pose.
            pose_bone.matrix_basis = Matrix.Rotation(radians(degrees), 4, "X")
    bpy.context.view_layer.update()
    world = armature.matrix_world
    result = {}
    for bone in armature.data.bones:
        pose_bone = armature.pose.bones.get(bone.name)
        if not pose_bone:
            continue
        rest_inverse = (world @ bone.matrix_local).inverted()
        result[bone.name] = (world @ pose_bone.matrix) @ rest_inverse
    return result


def skin(mesh_object, matrices, remap):
    """Blend-skin world-space vertices; returns {index: posed position}."""
    group_names = {group.index: group.name for group in mesh_object.vertex_groups}
    world = mesh_object.matrix_world
    posed = {}
    for vertex in mesh_object.data.vertices:
        influences = []
        for item in vertex.groups:
            name = group_names.get(item.group, "")
            target = remap.get(name, name)
            matrix = matrices.get(target)
            if matrix and item.weight > 0.0:
                influences.append((matrix, item.weight))
        if not influences:
            continue
        influences.sort(key=lambda item: item[1], reverse=True)
        influences = influences[:4]
        total = sum(weight for _matrix, weight in influences)
        if total <= 0.0:
            continue
        source = world @ vertex.co
        accumulated = Vector((0.0, 0.0, 0.0))
        for matrix, weight in influences:
            accumulated += (weight / total) * (matrix @ source)
        posed[vertex.index] = accumulated
    return posed


def region_vertices(mesh_object, tokens, remap):
    group_names = {group.index: group.name for group in mesh_object.vertex_groups}
    selected = set()
    for vertex in mesh_object.data.vertices:
        if not vertex.groups:
            continue
        bone_groups = [item for item in vertex.groups
                       if group_names.get(item.group, "") not in NON_BONE_GROUPS]
        if not bone_groups:
            continue
        dominant = max(bone_groups, key=lambda item: item.weight)
        if dominant.weight <= 0.0:
            continue
        name = group_names.get(dominant.group, "")
        target = remap.get(name, name)
        if any(token in target for token in tokens):
            selected.add(vertex.index)
    return selected


def stretch(mesh_object, posed, region):
    world = mesh_object.matrix_world
    ratios = []
    for edge in mesh_object.data.edges:
        a, b = edge.vertices
        if a not in region or b not in region or a not in posed or b not in posed:
            continue
        rest = (world @ mesh_object.data.vertices[b].co) - (world @ mesh_object.data.vertices[a].co)
        length = rest.length
        if length < 1e-6:
            continue
        ratios.append((posed[b] - posed[a]).length / length)
    if not ratios:
        return None
    ratios.sort()
    return {
        "edges": len(ratios),
        "mean": sum(ratios) / len(ratios),
        "p99": ratios[int(len(ratios) * 0.99) - 1],
        "max": ratios[-1],
    }


def measure(mod, reference, game, remap):
    """{region: {"mod": stats, "reference": stats, "ratio": p99 multiple}}."""
    posed_bones = [bone.name for bone in game.data.bones
                   if any(token in bone.name for token in FINGERS)]
    matrices = bone_matrices(game, posed_bones, BEND_DEGREES)
    report = {"posedBones": len(posed_bones)}
    for region_label, tokens in (("fingers", FINGERS), ("forearm", ("ForeArm",))):
        entry = {}
        for key, mesh_object, mesh_remap in (("mod", mod, remap), ("reference", reference, {})):
            posed = skin(mesh_object, matrices, mesh_remap)
            region = region_vertices(mesh_object, tokens, mesh_remap)
            entry[key] = stretch(mesh_object, posed, region)
        if entry["mod"] and entry["reference"] and entry["reference"]["p99"] > 1e-6:
            entry["ratio"] = entry["mod"]["p99"] / entry["reference"]["p99"]
        report[region_label] = entry
    return report


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    remap = load_remap(argv[0] if argv else "")
    mod, reference, game = find_objects()
    print(f"mod={mod.name} reference={reference.name} game={game.name}")
    report = measure(mod, reference, game, remap)
    print(f"posed {report['posedBones']} finger bones by {BEND_DEGREES:.0f}deg")
    failed = []
    unmeasured = []
    for region_label in ("fingers", "forearm"):
        entry = report[region_label]
        for key in ("mod", "reference"):
            stats = entry.get(key)
            print(f"  {region_label:9} {key:9} " + (
                f"edges={stats['edges']:5} mean={stats['mean']:.2f} "
                f"p99={stats['p99']:.2f} max={stats['max']:.2f}" if stats else "no edges"))
        ratio = entry.get("ratio")
        if ratio is None:
            # No mod edges in the region means nothing was measured — usually the mod's bone
            # names don't reach game names without a remap. Never let that read as a pass.
            unmeasured.append(region_label)
            continue
        verdict = "FAIL" if ratio > FAIL_RATIO else "ok"
        print(f"  {region_label:9} p99 是基线的 {ratio:.2f}x -> {verdict}")
        if ratio > FAIL_RATIO:
            failed.append(f"{region_label} {ratio:.2f}x")
    if failed:
        print("VERDICT FAIL: " + ", ".join(failed)
              + " —— 绑定/权重与游戏骨架不一致,回上游重做 prep(导出侧补不了)")
    elif unmeasured:
        print(f"VERDICT UNKNOWN: {', '.join(unmeasured)} 没有可测顶点"
              " —— 传 remap.json,或作者骨名没有映射到游戏骨名;**不能当通过**")
    else:
        print("VERDICT OK")
    return failed, unmeasured


if __name__ == "__main__":
    main()
