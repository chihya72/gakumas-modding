"""「沿 X 镜像整个模型」验收：镜像一次要正确，镜像两次要回到原样。

这条测试是为两个实测事故立的：

1. **自定义法线按 loop 顺序写回会全裂。** `flip_normals()` 反转绕序时会把每个面内部的
   loop 顺序也反过来；拿反转前的顺序写回去，等于把每个角的法线安到别的角上。静止看着
   "法线还是朝外的"（所以只量朝向的尺子抓不到），实际是 91092 个共享顶点全部法线分裂，
   进游戏就是整片三角面阴影。判据必须是「共享顶点上相邻面的法线一不一致」。

2. **不能用物体缩放。** 作者网格通常是骨架的子物体，「选中两个 → S X -1 → 应用缩放」
   父子互相抵消，做偶数次等于没做（实测作者手动做了三次，净效果为零）。

跑法：blender --background --factory-startup --python-exit-code 1 --python tests/blender_mirror_model_smoke.py
"""
import sys
from collections import defaultdict
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gakumas_mi
from gakumas_mi import operators  # noqa: F401


def build():
    """一个左右不对称、带自定义法线和形态键的小网格 + 骨架，网格是骨架的子物体。"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    gakumas_mi.register()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.5)
    obj = bpy.context.active_object
    mesh = obj.data
    for vertex in mesh.vertices:            # 捏歪，制造左右不对称
        vertex.co.x += 0.3 * vertex.co.z ** 2
    mesh.shade_smooth()
    # 自定义拆分法线：先用平滑法线灌进去，模拟 MMD 源
    mesh.normals_split_custom_set([tuple(mesh.loops[i].normal) for i in range(len(mesh.loops))])
    obj.shape_key_add(name="Basis")
    key = obj.shape_key_add(name="Morph")
    key.data[0].co.x += 0.11

    armature = bpy.data.armatures.new("rig")
    rig = bpy.data.objects.new("rig", armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, x in (("arm.L", 0.4), ("arm.R", -0.4)):
        bone = armature.edit_bones.new(name)
        bone.head = (x, 0.0, 0.0)
        bone.tail = (x, 0.0, 0.6)
        bone.roll = 0.3
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.parent = rig                        # 关键：网格是骨架的子物体
    obj.modifiers.new("Armature", "ARMATURE").object = rig
    bpy.context.scene.gmi_author_object = obj
    return obj, rig


def measure(obj, rig):
    mesh = obj.data
    volume = 0.0
    for polygon in mesh.polygons:
        points = [mesh.vertices[i].co for i in polygon.vertices]
        for k in range(1, len(points) - 1):
            volume += points[0].dot(points[k].cross(points[k + 1])) / 6.0
    loops_by_vertex = defaultdict(list)
    for polygon in mesh.polygons:
        for loop in polygon.loop_indices:
            loops_by_vertex[mesh.loops[loop].vertex_index].append(loop)
    split = 0
    for loops in loops_by_vertex.values():
        if len(loops) < 2:
            continue
        first = Vector(mesh.loops[loops[0]].normal)
        if not all(Vector(mesh.loops[i].normal).dot(first) > 0.999 for i in loops[1:]):
            split += 1
    return {
        "volume": volume,
        "split": split,
        "armX": rig.data.bones["arm.L"].head_local.x,
        "verts": [tuple(v.co) for v in mesh.vertices],
        "morph": tuple(mesh.shape_keys.key_blocks["Morph"].data[0].co),
    }


def main():
    obj, rig = build()
    before = measure(obj, rig)
    assert before["split"] == 0, f"起始网格就有 {before['split']} 个分裂法线，样本不成立"
    assert before["volume"] > 0, "起始网格面朝里，样本不成立"

    assert bpy.ops.gmi.mirror_model() == {"FINISHED"}
    once = measure(obj, rig)
    assert abs(once["armX"] + before["armX"]) < 1e-6, f"骨没镜像：{once['armX']} vs {before['armX']}"
    assert once["volume"] > 0, f"镜像后面朝里了：{once['volume']:+.4f}"
    assert once["split"] == 0, f"自定义法线裂了 {once['split']} 个顶点（loop 顺序对错号）"
    assert abs(once["morph"][0] + before["morph"][0]) < 1e-6, "形态键没跟着镜像"
    assert any(abs(a[0] - b[0]) > 1e-6 for a, b in zip(once["verts"], before["verts"])), \
        "顶点没动——物体缩放被父子关系抵消了？"

    assert bpy.ops.gmi.mirror_model() == {"FINISHED"}
    twice = measure(obj, rig)
    assert abs(twice["armX"] - before["armX"]) < 1e-6, "镜像两次没回到原位"
    assert twice["split"] == 0, "镜像两次后法线裂了"
    assert all(abs(a[0] - b[0]) < 1e-6 and abs(a[2] - b[2]) < 1e-6
               for a, b in zip(twice["verts"], before["verts"])), "镜像两次顶点没回到原位"
    print(f"OK 镜像验收通过：骨 {before['armX']:+.2f} → {once['armX']:+.2f} → {twice['armX']:+.2f}；"
          f"体积恒为正；法线分裂始终 0")


main()
