"""Move the mod's finger geometry onto the GAME skeleton's finger joints.

AB skinning drives mod geometry with the GAME joints (`Σ w · gameBone · gameBindpose · v`).
At rest that product is identity, so geometry sitting away from the game joints still looks
right standing still — but once a joint rotates, those vertices swing about the wrong pivot.
On limbs the offset (~30 mm on a 150-300 mm bone) reads as a slight slide; on ~20-25 mm
finger segments a 40-50 mm offset is larger than the segment itself, which is what shreds
the fingers in game.

So the fingers are re-planted on the game joints with the same retarget the working 3Dmigoto
package applies per influence at runtime (`gameRest · sourceRest⁻¹`, see
operators._inverse_skin_export_data), blended by each vertex's weights. Only hand weight
drives the move (`h`), so the wrist fades out smoothly instead of tearing, and everything
else — clothes, skirt, decorations — is left untouched. Weights are NOT modified: the
relabel-preserve path stays intact (a nearest-surface weight transfer was measured to be
much worse here, because unaligned fingers pick up weights from the neighbouring finger).

Run: blender --background <in.blend> --python tools/retarget_hand_geometry.py -- <remap.json> <out.blend>
"""
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import simulate_ab_skinning as sim

FINGER_TOKENS = sim.FINGERS


def corrections(source_armature, game_armature, remap):
    """{source bone: gameRest · sourceRest⁻¹} for bones that reach a game bone."""
    result = {}
    for bone in source_armature.data.bones:
        game_bone = game_armature.data.bones.get(remap.get(bone.name, bone.name))
        if not game_bone:
            continue
        source_rest = source_armature.matrix_world @ bone.matrix_local
        game_rest = game_armature.matrix_world @ game_bone.matrix_local
        result[bone.name] = game_rest @ source_rest.inverted()
    return result


def retarget(mesh_object, correction_by_bone, tokens):
    group_names = {group.index: group.name for group in mesh_object.vertex_groups}
    world = mesh_object.matrix_world
    world_inverse = world.inverted()
    moved = 0
    largest = 0.0
    for vertex in mesh_object.data.vertices:
        weights = [(group_names.get(item.group, ""), item.weight)
                   for item in vertex.groups if item.weight > 0.0]
        total = sum(weight for _name, weight in weights)
        if total <= 0.0:
            continue
        hand = [(name, weight) for name, weight in weights
                if name in correction_by_bone and any(token in name for token in tokens)]
        blend = sum(weight for _name, weight in hand) / total
        if blend <= 1e-4:
            continue
        influences = sorted(hand, key=lambda item: item[1], reverse=True)[:4]
        hand_total = sum(weight for _name, weight in influences)
        if hand_total <= 0.0:
            continue
        rest = world @ vertex.co
        accumulated = Vector((0.0, 0.0, 0.0))
        for name, weight in influences:
            accumulated += (weight / hand_total) * (correction_by_bone[name] @ rest)
        # ponytail: lerp by hand weight is the falloff — no separate blend map needed.
        target = rest.lerp(accumulated, blend)
        largest = max(largest, (target - rest).length)
        vertex.co = world_inverse @ target
        moved += 1
    return moved, largest


def finger_stretch(mesh_object, matrices, remap):
    posed = sim.skin(mesh_object, matrices, remap)
    region = sim.region_vertices(mesh_object, sim.FINGERS, remap)
    return sim.stretch(mesh_object, posed, region)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    remap = sim.load_remap(argv[0])
    output = argv[1]
    mesh_object = bpy.data.objects[sim.MOD_MESH]
    game_armature = bpy.data.objects[sim.GAME_ARMATURE]
    source_armature = next(modifier.object for modifier in mesh_object.modifiers
                           if modifier.type == "ARMATURE" and modifier.object)
    reference = bpy.data.objects.get(sim.REF_MESH)

    posed_bones = [bone.name for bone in game_armature.data.bones
                   if any(token in bone.name for token in sim.FINGERS)]
    matrices = sim.bone_matrices(game_armature, posed_bones, sim.BEND_DEGREES)
    before = finger_stretch(mesh_object, matrices, remap)
    baseline = finger_stretch(reference, matrices, {}) if reference else None

    moved, largest = retarget(mesh_object, corrections(source_armature, game_armature, remap),
                              FINGER_TOKENS)
    # Rest changed, so the pose matrices are re-derived against the same test pose.
    matrices = sim.bone_matrices(game_armature, posed_bones, sim.BEND_DEGREES)
    after = finger_stretch(mesh_object, matrices, remap)

    show = lambda label, r: print(
        f"  {label:34} mean={r['mean']:.2f} p99={r['p99']:.2f} max={r['max']:.2f}"
        if r else f"  {label:34} no data")
    print(f"moved {moved} vertices, largest displacement {largest * 1000:.0f} mm")
    show("finger stretch before", before)
    show("finger stretch after", after)
    if baseline:
        show("reference body (known good)", baseline)
    bpy.ops.wm.save_as_mainfile(filepath=output)
    print(f"saved {output}")


if __name__ == "__main__":
    main()
