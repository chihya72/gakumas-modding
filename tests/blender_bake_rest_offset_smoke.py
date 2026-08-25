"""B 类：`bake` 算子必须**可见 / 可关 / 可量化 / 可撤销**（INV-7），且真的把形变消掉。

判据用原版身体搭一个已知答案的样本：复制一份原版身体，加一根装饰骨、把一片顶点绑上去，
然后**给它摆 5cm 的姿势** —— 那正是这条路线里真实存在的"静止形变"：导出器读 `mesh.vertices`
（静止），作者在视图里看到的是摆过姿势的样子，摆了姿势直接导出，出包的是没摆的那个形状。
烘一次要把这 5cm 写进网格；点回退，网格要逐顶点回到烘之前。

顺带钉住 2026-08-17 量出来的一件事：**装饰骨自己偏多少与"并到父骨"的静止形变无关** ——
并过去之后那些顶点按父目标骨摆，公式里根本没有装饰骨的变换。给装饰骨加 5cm 静止偏移，
这一项仍然是 0.000mm。所以 bake 真正要处理的是姿势（和父骨自己的错位）。

跑法：blender --background --factory-startup --python-exit-code 1 --python tests/blender_bake_rest_offset_smoke.py
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gakumas_mi
from gakumas_mi import core, operators

PROFILE = ROOT / "profiles" / "atbm-cstm-0140"
REFERENCE_FILES = (PROFILE / "Reference" / "Geo_Body.json",
                   PROFILE / "Reference" / "Geo_Body.skeleton.json")
DECOR = "Decor_A"                      # 源专属装饰骨，游戏里没有
HOST = "Spine1"                        # 它挂在这根身体骨下
OFFSET = Vector((0.0, 0.0, 0.05))      # 装饰骨的静止偏移：**不该**产生任何静止形变
POSE = Vector((0.0, 0.0, 0.05))        # 给它摆 5cm 的姿势：这才是要烘进网格的那一下

if not all(path.is_file() for path in REFERENCE_FILES):
    print("GMI_BAKE_SKIPPED 本机没有 gitignored 的原版 Reference，跳过")
    raise SystemExit(0)


def rest_positions(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


gakumas_mi.register()
try:
    scene = bpy.context.scene
    scene.gmi_component_id = "body"
    scene.gmi_profile_dir = str(PROFILE)
    assert bpy.ops.gmi.import_weighted_reference() == {"FINISHED"}
    reference = operators._profile_weight_reference(bpy.context, "body")
    armature = next(modifier.object for modifier in reference.modifiers
                    if modifier.type == "ARMATURE" and modifier.object)

    author = reference.copy()
    author.data = reference.data.copy()
    bpy.context.collection.objects.link(author)
    author.name = "AuthorBody"
    del author["gmi_weighted_reference"]
    author["gmi_component_id"] = "body"

    # 加一根偏移的装饰骨，挂在 HOST 下
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    host = armature.data.edit_bones[HOST]
    decor = armature.data.edit_bones.new(DECOR)
    decor.head = host.head + OFFSET
    decor.tail = host.tail + OFFSET
    decor.parent = host
    bpy.ops.object.mode_set(mode="OBJECT")

    # 把 HOST 那一片权重整段搬到装饰骨上（这样它有实打实的权重要处理）
    host_group = author.vertex_groups[HOST]
    decor_group = author.vertex_groups.new(name=DECOR)
    moved = [vertex.index for vertex in author.data.vertices
             for item in vertex.groups
             if item.group == host_group.index and item.weight > 0.5]
    assert len(moved) > 100, f"样本太小：{len(moved)} 个顶点"
    weights = {}
    for index in moved:
        weight = next(item.weight for item in author.data.vertices[index].groups
                      if item.group == host_group.index)
        weights[index] = weight
        decor_group.add([index], weight, "REPLACE")
        host_group.remove([index])
    heaviest = max(weights.values())

    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    author.select_set(True)
    bpy.context.view_layer.objects.active = author

    row = scene.gmi_bone_map.add()
    row.source = DECOR
    row.members = DECOR
    row.strategy = "bake"
    assert core.row_state(row.target, row.strategy) == "bake"

    # 先证明"装饰骨自己偏了"不算形变：这一步必须报"没有形变"，网格一个顶点都不动
    untouched = rest_positions(author)
    assert bpy.ops.gmi.bake_rest_offset() == {"FINISHED"}
    assert not author.get("gmi_pre_bake"), "静止偏移不该被当成形变去改网格"
    assert max((a - b).length for a, b in zip(untouched, rest_positions(author))) < 1e-9

    # 再给装饰骨摆一个 5cm 的姿势 —— 这才是导出会静默丢掉的那部分
    pose_bone = armature.pose.bones[DECOR]
    pose_bone.location = pose_bone.bone.matrix_local.inverted().to_3x3() @ POSE
    bpy.context.view_layer.update()
    author["gmi_baked_rest_offset"] = 0

    before = rest_positions(author)
    assert bpy.ops.gmi.bake_rest_offset() == {"FINISHED"}
    assert author.get("gmi_pre_bake"), "破坏性操作必须留下回退记录"
    assert author.get("gmi_baked_rest_offset") == 1

    after = rest_positions(author)
    changed = [index for index, (old, new) in enumerate(zip(before, after))
               if (old - new).length > 1e-6]
    shift = max((before[index] - after[index]).length for index in changed) * 1000.0
    assert changed, "摆了姿势的装饰骨必须被烘出位移来"
    # 位移按**权重**缩放（这批顶点权重 0.5~1.0），所以期望值是 5cm × 最重的那个权重，
    # 不是硬写 50mm —— 写死会把"按权重缩放"这条正确行为判成错。
    expected = POSE.length * 1000.0 * heaviest
    assert abs(shift - expected) < 1.0, f"位移应当≈{expected:.2f}mm，实际 {shift:.2f}mm"
    assert set(changed) <= set(moved), "只该动这根骨影响的顶点"

    # 可撤销：逐顶点回到烘之前
    assert bpy.ops.gmi.bake_rest_offset(revert=True) == {"FINISHED"}
    reverted = rest_positions(author)
    worst = max((a - b).length for a, b in zip(before, reverted)) * 1000.0
    assert worst < 1e-3, f"回退后最差还差 {worst}mm"
    assert not author.get("gmi_pre_bake")

    # 没烘就导出必须被拦（闸门 9 的另一半）；标 reject 同样拦
    scene.gmi_bone_map.clear()
    reject_row = scene.gmi_bone_map.add()
    reject_row.source, reject_row.members = DECOR, DECOR
    reject_row.strategy = "reject"
    assert core.row_state("", "reject") == "reject"
    # bake / reject 对下游按 rigid 解析，别掉进"蹭最近摇物骨"那条兜底
    assert operators._form_physics_overrides(scene) == {DECOR: "rigid"}

    print(f"GMI_BAKE_OK {bpy.app.version_string} "
          f"{len(changed)} 个顶点，位移 {shift:.1f}mm"
          f"（5cm × 最重权重 {heaviest:.2f}），回退残差 {worst:.2e}mm")
finally:
    gakumas_mi.unregister()
