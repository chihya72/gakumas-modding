"""只读报告:关节对齐到什么程度了。不修改任何东西。

"关节对齐"= 你的骨 head 和游戏同名骨 head 重合(顶点绕 head 转,head 对上转轴才对)。
但只有**绑定健康**(骨长在它所驱动的肉里)时,骨对齐才等于几何对齐;骨肉分家时只看骨会误判。
所以这里两个都量:

  骨偏差   你的骨 head → 游戏骨 head。绑定健康时这就是判据。
  肉偏差   该骨主导顶点的质心 → 游戏骨 head。真正决定游戏里形变对不对的是它。
           拿游戏参考体的同一项做基线——那是"正确"长什么样。

判据是**相对骨节长度**的:手指骨节 20~25mm,错几十毫米就撕碎;四肢骨节 150~300mm,
同样偏差只占 10~20%,看不出来。所以按部位分开看,别用一个绝对毫米数卡всё。

用法: blender --background <blend> --python tools/report_joint_alignment.py -- [remap.json]
"""
import json
import sys

import bpy
from mathutils import Vector

FINGER_TOKENS = ("HandIndex", "HandMiddle", "HandRing", "HandPinky", "HandThumb")
TOE_TOKENS = ("Toe",)


def load_remap(path):
    if not path:
        return {}
    data = json.load(open(path, encoding="utf-8"))
    return data.get("bones", data)


def find_objects():
    skinned = [obj for obj in bpy.data.objects
               if obj.type == "MESH"
               and any(m.type == "ARMATURE" and m.object for m in obj.modifiers)
               and obj.data.vertices]
    reference = next((obj for obj in skinned if obj.get("gmi_weighted_reference")), None)
    if reference is None:
        reference = next((obj for obj in skinned
                          if obj.name.startswith("GMI_") and "参考" in obj.name), None)
    if reference is None:
        raise SystemExit("场景里没有 GMI 带权重参考体")
    game = next(m.object for m in reference.modifiers if m.type == "ARMATURE" and m.object)
    mod = max((obj for obj in skinned
               if obj is not reference and not obj.name.startswith("GMI_")),
              key=lambda obj: len(obj.data.vertices))
    return mod, reference, game


def dominated_centroid(mesh, group_index):
    points = [mesh.matrix_world @ vertex.co for vertex in mesh.data.vertices
              for item in vertex.groups
              if item.group == group_index and item.weight > 0.5]
    return (sum(points, Vector()) / len(points), len(points)) if points else (None, 0)


def collect(mesh, armature, game, remap):
    """{游戏骨名: (骨偏差 mm 或 None, 肉偏差 mm, 顶点数)}"""
    game_head = {bone.name: game.matrix_world @ bone.head_local for bone in game.data.bones}
    result = {}
    for group in mesh.vertex_groups:
        target = remap.get(group.name, group.name)
        if target not in game_head:
            continue
        centroid, count = dominated_centroid(mesh, group.index)
        if centroid is None:
            continue
        bone = armature.data.bones.get(group.name) if armature else None
        bone_delta = None
        if bone:
            bone_delta = ((armature.matrix_world @ bone.head_local) - game_head[target]).length * 1000.0
        flesh_delta = (centroid - game_head[target]).length * 1000.0
        previous = result.get(target)
        if previous is None or count > previous[2]:
            result[target] = (bone_delta, flesh_delta, count)
    return result


def summarize(label, rows, tokens):
    picked = [(name, values) for name, values in rows.items()
              if any(token in name for token in tokens)] if tokens else [
              (name, values) for name, values in rows.items()
              if not any(token in name for token in FINGER_TOKENS + TOE_TOKENS)]
    if not picked:
        print(f"  {label:10} 无数据")
        return None
    flesh = sorted(values[1] for _name, values in picked)
    bone = sorted(values[0] for _name, values in picked if values[0] is not None)
    worst = max(picked, key=lambda item: item[1][1])
    print(f"  {label:10} 骨数={len(picked):3} "
          f"肉偏差 中位={flesh[len(flesh) // 2]:6.1f}mm 最差={flesh[-1]:6.1f}mm"
          + (f" | 骨偏差 中位={bone[len(bone) // 2]:6.1f}mm" if bone else "")
          + f" | 最差骨 {worst[0]}")
    return flesh[len(flesh) // 2]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    remap = load_remap(argv[0] if argv else "")
    mod, reference, game = find_objects()
    source = next(m.object for m in mod.modifiers if m.type == "ARMATURE" and m.object)
    print(f"mod={mod.name} reference={reference.name} game={game.name}")

    for title, mesh, armature, mapping in (
            ("你的模型", mod, source, remap),
            ("游戏参考体(正确基线)", reference, game, {})):
        print(title)
        rows = collect(mesh, armature, game, mapping)
        for label, tokens in (("手指", FINGER_TOKENS), ("脚趾", TOE_TOKENS), ("其它", None)):
            summarize(label, rows, tokens)
    print("\n判读:手指的「肉偏差」中位数应接近参考体那一行;明显高出(比如 2 倍)就是没对齐。"
          "\n其它部位容差大得多,高一些不要紧。骨偏差只在绑定健康(骨长在肉里)时才有意义。")


if __name__ == "__main__":
    main()
