"""批次 2 验收：参考骨架与原版资产**逐骨 diff 为零**（离线，不进游戏）。

参考资产是作者在 Blender 里对齐时的唯一基准，所以它自己必须和原版逐骨一致 —— 位置、
**朝向**、层级、节点数。旧版只按 head→tail 摆骨、roll 留默认值，实测 104 根里 69 根
（镜像那一侧）与原版差整整 180°：作者照着它对齐，看到的轴向是错的。

跑法：blender --background --factory-startup --python-exit-code 1 --python tests/blender_reference_rig_smoke.py
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gakumas_mi
from gakumas_mi import core, operators

PROFILE = ROOT / "profiles" / "atbm-cstm-0140"
POSITION_TOLERANCE_MM = 1e-3
ANGLE_TOLERANCE_DEG = 1e-3


def unity_local(node):
    x, y, z, w = node.get("localRotation") or [0.0, 0.0, 0.0, 1.0]
    return Matrix.LocRotScale(
        Vector(node.get("localPosition") or (0.0, 0.0, 0.0)),
        Quaternion((w, x, y, z)),
        Vector(node.get("localScale") or (1.0, 1.0, 1.0)))


def expected_world(nodes):
    """独立复算一遍原版静止世界矩阵（Unity 空间）：带权重的用 bindPose 求逆，其余按 local 链。

    刻意不调用 `operators.reference_rest_world()` —— 那是被测对象，拿它当期望值等于什么都没查。
    """
    cache = {}

    def world(index):
        if index in cache:
            return cache[index]
        node = nodes[index]
        if node.get("bindPose"):
            matrix = operators._bind_pose_matrix(node["bindPose"]).inverted()
        else:
            matrix = unity_local(node)
            parent = int(node.get("parent", -1))
            if parent >= 0:
                matrix = world(parent) @ matrix
        cache[index] = matrix
        return matrix

    return {index: world(index) for index in range(len(nodes))}


def angle_between_frames(a, b):
    """两个 3x3 的朝向差（度）。四元数 w<0 时 angle 会 >180°，必须折回 [0,180]。"""
    delta = (a.to_quaternion().rotation_difference(b.to_quaternion())).angle
    return math.degrees(min(delta, 2.0 * math.pi - delta))


def check_profile(scene, label):
    """把当前 profile 的参考体导进来，逐骨 diff 原版资产。返回 (骨数, 无权重节点数, 最差值)。"""
    reference = operators._profile_weight_reference(bpy.context, "body")
    armature = next(modifier.object for modifier in reference.modifiers
                    if modifier.type == "ARMATURE" and modifier.object)

    skeleton = core.load_json(Path(bpy.path.abspath(scene.gmi_skeleton_json)))
    nodes = skeleton["nodes"]
    expected = expected_world(nodes)

    # 1. 节点覆盖：除了"没有父节点又没有 bindPose"的那个模型根对象，一根都不许漏。
    #    动态链锚点 `*_A` / `*_O` 和摇物链根 `*_S` 没有权重，正是旧版整批丢掉的那些。
    should_exist = {node["name"] for index, node in enumerate(nodes)
                    if int(node.get("parent", -1)) >= 0 or node.get("bindPose")}
    actual = {bone.name for bone in armature.data.bones}
    assert should_exist <= actual, sorted(should_exist - actual)[:10]
    assert not (actual - should_exist), sorted(actual - should_exist)[:10]

    # 2. 逐骨 diff：位置 + 朝向 + 父子关系
    worst_mm = worst_deg = 0.0
    worst_names = ("", "")
    unweighted = 0
    for index, node in enumerate(nodes):
        bone = armature.data.bones.get(node["name"])
        if bone is None:
            continue
        if not node.get("bindPose"):
            unweighted += 1
        want = operators.C_UNITY.inverted() @ expected[index] @ operators.C_UNITY
        got = armature.matrix_world @ bone.matrix_local
        millimetres = (got.translation - want.translation).length * 1000.0
        degrees = angle_between_frames(got.to_3x3(), want.to_3x3())
        if millimetres > worst_mm:
            worst_mm, worst_names = millimetres, (node["name"], worst_names[1])
        if degrees > worst_deg:
            worst_deg, worst_names = degrees, (worst_names[0], node["name"])
        # 层级：跳过被略掉的根对象之后，父子关系必须一致
        parent = int(node.get("parent", -1))
        while parent >= 0 and nodes[parent]["name"] not in actual:
            parent = int(nodes[parent].get("parent", -1))
        expected_parent = nodes[parent]["name"] if parent >= 0 else None
        assert (bone.parent.name if bone.parent else None) == expected_parent, (
            node["name"], bone.parent.name if bone.parent else None, expected_parent)

    assert worst_mm < POSITION_TOLERANCE_MM, f"位置最差 {worst_mm}mm @ {worst_names[0]}"
    assert worst_deg < ANGLE_TOLERANCE_DEG, f"朝向最差 {worst_deg}° @ {worst_names[1]}"

    # 3. 权重分布也在参考体里（P3 劈权重的来源），且顶点组名就是游戏骨名
    groups = {group.name for group in reference.vertex_groups}
    weighted_names = {node["name"] for node in nodes if node.get("weightedIndex") is not None}
    assert groups == weighted_names, sorted(groups ^ weighted_names)[:10]

    print(f"  {label}: 骨 {len(armature.data.bones)}（无权重节点 {unweighted}）"
          f" 位置最差 {worst_mm:.6f}mm 朝向最差 {worst_deg:.6f}°")
    return len(armature.data.bones), unweighted


def check_unweighted_node_composition():
    """没有 bindPose 的节点：世界位置必须按**完整 local 矩阵**合成。

    只累加 `localPosition` 的话，父骨带旋转时子节点就落在错地方（151 个节点里 57 个带非单位
    localRotation）。这里父骨绕 Unity 的 Y 轴转 90°，子节点在父的局部 +Z 上 —— 手算世界位置
    是父位置 + (1,0,0)：转 90° 之后局部 +Z 指向世界 +X。累加位置会算成 (0,0,1)，差 1.4m。
    """
    turn = Quaternion((0.0, 1.0, 0.0), math.radians(90.0))     # Unity 空间，绕 Y
    parent_world = Matrix.LocRotScale(Vector((0.0, 1.0, 0.0)), turn, Vector((1.0, 1.0, 1.0)))
    nodes = [
        {"name": "Hips", "parent": -1, "weightedIndex": 0,
         "bindPose": operators._matrix_json(parent_world.inverted())},
        {"name": "Skirt_A", "parent": 0, "weightedIndex": None,
         "localPosition": [0.0, 0.0, 1.0],
         "localRotation": [0.0, 0.0, 0.0, 1.0], "localScale": [1.0, 1.0, 1.0]},
    ]
    world = operators.reference_rest_world(nodes)
    got_unity = (operators.C_UNITY @ world[1] @ operators.C_UNITY.inverted()).translation
    assert (got_unity - Vector((1.0, 1.0, 0.0))).length < 1e-5, got_unity
    # 父骨自己仍然由 bindPose 求逆决定
    parent_unity = (operators.C_UNITY @ world[0] @ operators.C_UNITY.inverted())
    assert (parent_unity.translation - Vector((0.0, 1.0, 0.0))).length < 1e-5


gakumas_mi.register()
try:
    check_unweighted_node_composition()
    scene = bpy.context.scene
    scene.gmi_component_id = "body"
    scene.gmi_profile_dir = str(PROFILE)
    assert bpy.ops.gmi.import_weighted_reference() == {"FINISHED"}
    bones, unweighted = check_profile(scene, "仓内 profile（synthetic 骨架）")

    # 真数据：资源库里的骨架带 19 个无权重节点（`Reference` / `Pelvis` / 动态链锚点 `*_A`
    # `*_O` / 摇物链根 `*_S`）—— 那才是旧版整批丢掉的东西。仓里这份 profile 是 mesh-only
    # 时代合成的（只有 132 根带权重骨）；今天新建的 profile 会把资源库骨架整份复制进来
    # （`complete_inverse_skin_profile` 走 `bone_naming="skeleton"` 那条），所以这里就照那个
    # 形态搭一份临时 profile 来查。资源库 7.8GB 不在仓里，CI 上跳过这一段。
    library = Path(gakumas_mi._default_body_json_dir() or "")
    library_skeleton = library / "mdl_chr_atbm-cstm-0140_body" / "Geo_Body.skeleton.json"
    if library_skeleton.is_file():
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory(prefix="gmi-reference-rig-") as tmp:
            staged = Path(tmp) / "profile"
            shutil.copytree(PROFILE, staged)
            shutil.copy2(library_skeleton, staged / "Reference" / "Geo_Body.skeleton.json")
            for obj in list(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            scene.gmi_profile_dir = str(staged)
            scene.gmi_skeleton_json = ""
            assert bpy.ops.gmi.import_weighted_reference() == {"FINISHED"}
            _bones, library_unweighted = check_profile(scene, "资源库骨架（真数据）")
            assert library_unweighted > 0, "资源库骨架应当带无权重节点，一个都没量到"
    else:
        print("  资源库骨架：跳过（本机没有 assetstudio-body-json）")

    print(f"GMI_REFERENCE_RIG_OK {bpy.app.version_string}")
finally:
    gakumas_mi.unregister()
