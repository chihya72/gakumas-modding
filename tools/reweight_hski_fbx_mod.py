"""Transfer HSKI reference weights to an aligned FBX and export a GPU Mod."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix
from mathutils.kdtree import KDTree


args = sys.argv[sys.argv.index("--") + 1 :]
if len(args) < 7:
    raise SystemExit(
        "usage: blender -b --python reweight_hski_fbx_mod.py -- "
        "FBX PROFILE MESH_JSON SKELETON_JSON OUTPUT PACKAGE_ID TEXTURE"
    )
fbx, profile, mesh_json, skeleton_json, output = map(
    lambda value: Path(value).resolve(), args[:5]
)
package_id = args[5]
texture = Path(args[6]).resolve()
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))
import gakumas_mi  # noqa: E402
from gakumas_mi import core, operators  # noqa: E402


bpy.ops.wm.read_factory_settings(use_empty=True)
gakumas_mi.register()

# Build the authoritative HSKI mesh with its original four-weight skin.
scene = bpy.context.scene
scene.gmi_profile_dir = str(profile)
scene.gmi_component_id = "body"
scene.gmi_source_mesh_json = str(mesh_json)
scene.gmi_skeleton_json = str(skeleton_json)
result = bpy.ops.gmi.import_weighted_reference()
if "FINISHED" not in result:
    raise RuntimeError(f"HSKI weighted reference import failed: {result}")
reference = bpy.context.active_object
reference.name = "HSKI_WEIGHT_SOURCE"

# Import and normalize the author-provided clothing mesh. The FBX stores its
# centimeter conversion on the armature parent, so scaling that parent applies
# the conversion to the child mesh exactly once.
bpy.ops.import_scene.fbx(filepath=str(fbx))
targets = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj != reference]
if len(targets) != 1:
    raise RuntimeError(f"Expected one target mesh, found {len(targets)}")
target = targets[0]
for armature in (obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and obj != reference.parent):
    armature.matrix_world = Matrix.Scale(100.0, 4) @ armature.matrix_world

bone_map = core.inverse_skin_bone_map(profile, skeleton_json)
original_group_names = {group.index: group.name for group in target.vertex_groups}
original_dominant = []
for vertex in target.data.vertices:
    weighted = [
        (float(item.weight), original_group_names[item.group])
        for item in vertex.groups if item.weight > 0.0
    ]
    original_dominant.append(max(weighted)[1] if weighted else "")
for modifier in list(target.modifiers):
    if modifier.type == "ARMATURE":
        target.modifiers.remove(modifier)

# Standard GIMI/EFMI authoring contract: the target geometry keeps its UVs and
# topology, while all skin weights are replaced by weights interpolated from
# the target game's reference body.
target.vertex_groups.clear()
for group in reference.vertex_groups:
    target.vertex_groups.new(name=group.name)
transfer = target.modifiers.new(name="GMI Transfer HSKI Weights", type="DATA_TRANSFER")
transfer.object = reference
transfer.use_vert_data = True
transfer.data_types_verts = {"VGROUP_WEIGHTS"}
transfer.vert_mapping = "POLYINTERP_NEAREST"
transfer.layers_vgroup_select_src = "ALL"
transfer.layers_vgroup_select_dst = "NAME"
transfer.mix_mode = "REPLACE"
transfer.mix_factor = 1.0
bpy.context.view_layer.objects.active = target
target.select_set(True)
reference.select_set(False)
bpy.ops.object.modifier_apply(modifier=transfer.name)

# Correct anatomy where unrestricted closest-face interpolation is ambiguous.
# Adjacent fingers are only millimetres apart, so classify the target region by
# its old rig, then copy weights from the nearest HSKI vertex influenced by the
# same semantic bone. No TTMR weight value or bind matrix is reused here.
semantic_bones = {
    name for name in bone_map
    if any(token in name for token in (
        "HandThumb", "HandIndex", "HandMiddle", "HandRing", "HandPinky",
    ))
} | {"Neck"}
reference_group_names = {group.index: group.name for group in reference.vertex_groups}
reference_weights = []
semantic_candidates = {name: [] for name in semantic_bones}
for vertex in reference.data.vertices:
    weights = {
        reference_group_names[item.group]: float(item.weight)
        for item in vertex.groups if item.weight > 0.0
    }
    reference_weights.append(weights)
    for name in semantic_bones:
        if weights.get(name, 0.0) > 0.05:
            semantic_candidates[name].append(vertex.index)
semantic_trees = {}
for name, candidates in semantic_candidates.items():
    if not candidates:
        continue
    tree = KDTree(len(candidates))
    for slot, vertex_index in enumerate(candidates):
        tree.insert(reference.matrix_world @ reference.data.vertices[vertex_index].co, slot)
    tree.balance()
    semantic_trees[name] = (tree, candidates)
target_groups = {group.name: group for group in target.vertex_groups}
semantic_corrected = {name: 0 for name in semantic_bones}
for vertex in target.data.vertices:
    semantic = original_dominant[vertex.index]
    if semantic not in semantic_trees:
        continue
    tree, candidates = semantic_trees[semantic]
    _, slot, _ = tree.find(target.matrix_world @ vertex.co)
    source_weights = reference_weights[candidates[slot]]
    for group in target.vertex_groups:
        group.remove([vertex.index])
    for name, weight in source_weights.items():
        target_groups[name].add([vertex.index], weight, "REPLACE")
    semantic_corrected[semantic] += 1

# Triangulate before expanding loops for GPU export.
triangulate = target.modifiers.new(name="GMI Triangulate", type="TRIANGULATE")
bpy.ops.object.modifier_apply(modifier=triangulate.name)

data = operators._inverse_skin_export_data(
    target, bone_map, {}, source_rig_weights=True
)
package = core.write_inverse_skin_package(
    profile, output, package_id, "TTMR Outfit on HSKI", "GakumasMI", "body",
    data["vertices"], data["normals"], data["tangents"], data["uv0"],
    data["uv1"], data["colors"], data["faces"], data["skin"], data["corrections"],
)

weighted_vertices = sum(
    1 for vertex in target.data.vertices
    if any(item.weight > 0.0 for item in vertex.groups)
)
report = {
    "method": "POLYINTERP_NEAREST",
    "source": "HSKI Geo_Body",
    "target": target.name,
    "targetVertices": len(target.data.vertices),
    "weightedVertices": weighted_vertices,
    "profileBoneGroups": len(target.vertex_groups),
    "semanticCorrections": {name: count for name, count in semantic_corrected.items() if count},
    "textureSource": str(texture),
    "truncatedWeightTotal": data["truncated_weight"],
}
(package / "reweight-report.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
print(f"GMI_REWEIGHT_REPORT={json.dumps(report)}")
print(f"GMI_INVERSE_SKIN_PACKAGE={package}")
