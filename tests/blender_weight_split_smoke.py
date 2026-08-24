"""批次 3 验收：「从相邻骨劈权重」能把删掉的权重按原版分布劈回来。

判据用的是**原版自己的身体**：把 `LeftShoulder` 那一组权重整个删掉再归一化 —— 那正是
MMD/Biped 源模型的样子（Spine2 直接接 UpperArm，压根没有锁骨）—— 然后劈回来，和删之前的
真值逐顶点比。算法或写回哪一步错了，这里立刻显形。

同时钉两个方向（贯穿规矩 2）：删掉之后承重关节闸门必须报，劈回来之后必须不报。

跑法：blender --background --factory-startup --python-exit-code 1 --python tests/blender_weight_split_smoke.py
"""
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gakumas_mi
from gakumas_mi import core, operators

PROFILE = ROOT / "profiles" / "atbm-cstm-0140"
VICTIM = "LeftShoulder"

reference_files = (
    PROFILE / "Reference" / "Geo_Body.json",
    PROFILE / "Reference" / "Geo_Body.skeleton.json",
)
if not all(path.is_file() for path in reference_files):
    print("GMI_WEIGHT_SPLIT_SKIP：仓库不分发原版 Reference；本地有资源时运行完整权重真值验收")
    raise SystemExit(0)


def group_weights(obj, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        return {}
    # 不用 VertexGroup.weight()：对不在组里的顶点它会抛异常并往日志里刷 "Vertex not in group"
    return {vertex.index: item.weight for vertex in obj.data.vertices
            for item in vertex.groups if item.group == group.index}


def vertex_sums(obj):
    return [sum(item.weight for item in vertex.groups) for vertex in obj.data.vertices]


gakumas_mi.register()
try:
    scene = bpy.context.scene
    scene.gmi_component_id = "body"
    scene.gmi_profile_dir = str(PROFILE)
    assert bpy.ops.gmi.import_weighted_reference() == {"FINISHED"}
    reference = operators._profile_weight_reference(bpy.context, "body")

    # 作者网格 = 原版身体的副本（同一副骨架），只是"没有锁骨"
    author = reference.copy()
    author.data = reference.data.copy()
    bpy.context.collection.objects.link(author)
    author.name = "AuthorBody"
    del author["gmi_weighted_reference"]
    author["gmi_component_id"] = "body"
    truth = group_weights(author, VICTIM)
    assert len(truth) > 200, f"原版 {VICTIM} 只有 {len(truth)} 个顶点，样本不成立"

    author.vertex_groups.remove(author.vertex_groups[VICTIM])
    # 删完要归一化：真实的"没有锁骨的源模型"权重是归一的，不归一会让判据虚高
    zero_vertices, truncated = operators._normalize_profile_weights(author)
    assert not zero_vertices, f"{len(zero_vertices)} 个顶点归一化后全零"
    sums_before = vertex_sums(author)
    assert max(abs(value - 1.0) for value in sums_before) < 1e-5

    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    author.select_set(True)
    bpy.context.view_layer.objects.active = author

    # 方向一：坏样本必须报
    bone_map = core.inverse_skin_bone_map(str(PROFILE), None, "body")
    weighted = [name for name, _mass in operators._weighted_group_mass(author)]
    remap = {name: name for name in weighted}
    assert VICTIM in core.missing_critical_bones(weighted, remap, bone_map)
    assert VICTIM in (core.critical_coverage_error(weighted, remap, bone_map) or "")

    assert bpy.ops.gmi.split_weight_from_neighbours() == {"FINISHED"}

    # 方向二：劈完必须不报，且权重要和真值对得上
    weighted = [name for name, _mass in operators._weighted_group_mass(author)]
    remap = {name: name for name in weighted}
    assert not core.missing_critical_bones(weighted, remap, bone_map)
    assert core.critical_coverage_error(weighted, remap, bone_map) is None

    recovered = group_weights(author, VICTIM)
    missed = [index for index, weight in truth.items()
              if weight > 0.01 and recovered.get(index, 0.0) <= 0.0]
    errors = [abs(recovered.get(index, 0.0) - weight) for index, weight in truth.items()]
    errors.sort()
    worst = errors[-1]
    mean = sum(errors) / len(errors)
    extra = [index for index in recovered
             if index not in truth and recovered[index] > 0.01]
    sums_after = vertex_sums(author)
    worst_sum = max(abs(value - 1.0) for value in sums_after)

    assert not missed, f"{len(missed)} 个本该有权重的顶点没劈到"
    assert worst < 0.01, f"最差顶点差 {worst}"
    assert mean < 1e-4, f"平均差 {mean}"
    assert not extra, f"{len(extra)} 个原版没有权重的顶点被劈上了权重"
    assert worst_sum < 1e-5, f"劈完权重和偏了 {worst_sum}"

    print(f"GMI_WEIGHT_SPLIT_OK {bpy.app.version_string} "
          f"{VICTIM} {len(truth)} 个顶点：最差差 {worst:.2e} 平均 {mean:.2e}，"
          f"权重和最差偏 {worst_sum:.2e}")
finally:
    gakumas_mi.unregister()
