# -*- coding: utf-8 -*-
"""骨名一个都不认识时，扫描还能不能认出人形骨（`topology_map` 兜底接没接上）。

八张预设表只覆盖 MMD / mixamo / rigify / vrm / biped / auto-rig-pro / scsp / unity。
名字落在这八家之外，`build_bone_remap` 一根也映射不上——而这**不会报错**：后面所有按
游戏骨名索引的尺子（对齐、跨关节带、镜像）都会匹配到零根骨，然后安静地报全绿。
这个冒烟就是钉住那条兜底：骨名全是 `b_00` 这种废名，但骨架形状是正常人体。

跑法：blender --background --factory-startup --python-exit-code 1 --python tests/blender_topology_fallback_smoke.py
"""
import sys
import types
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gakumas_mi import core, operators, topology_map

# 目标骨架：学马身上这条兜底要落到的那些骨（够 REQUIRED + 肩趾颈即可，不必是全部 70 根）。
GAME_BONES = [
    "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand",
    "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
]

# (骨名, head, tail, 父)。名字刻意全是废名；形状是正常人体，Blender Z-up。
# 头下面挂四根（发/眼/眼/颌）不是凑数：`topology_map` 认头靠「直接子骨最多」，
# 也靠它让脖子那一支的子树大过手臂，否则量"上"的那条最长链会拐进胳膊里。
SKELETON = [
    ("b_00", (0.00, 0.0, 1.00), (0.00, 0.0, 1.05), None),      # 胯
    ("b_01", (0.10, 0.0, 1.00), (0.10, 0.0, 0.55), "b_00"),    # 左腿
    ("b_02", (0.10, 0.0, 0.55), (0.10, 0.0, 0.10), "b_01"),
    ("b_03", (0.10, 0.0, 0.10), (0.10, 0.08, 0.05), "b_02"),
    ("b_04", (0.10, 0.08, 0.05), (0.10, 0.16, 0.05), "b_03"),
    ("b_05", (-0.10, 0.0, 1.00), (-0.10, 0.0, 0.55), "b_00"),  # 右腿
    ("b_06", (-0.10, 0.0, 0.55), (-0.10, 0.0, 0.10), "b_05"),
    ("b_07", (-0.10, 0.0, 0.10), (-0.10, 0.08, 0.05), "b_06"),
    ("b_08", (-0.10, 0.08, 0.05), (-0.10, 0.16, 0.05), "b_07"),
    ("b_09", (0.00, 0.0, 1.05), (0.00, 0.0, 1.20), "b_00"),    # 脊椎三节
    ("b_10", (0.00, 0.0, 1.20), (0.00, 0.0, 1.35), "b_09"),
    ("b_11", (0.00, 0.0, 1.35), (0.00, 0.0, 1.50), "b_10"),
    # 锁骨认得出来靠「第一节明显比第二节短」，所以两段长度不能瞎填：0.12 vs 0.30。
    ("b_25", (0.03, 0.0, 1.45), (0.15, 0.0, 1.45), "b_11"),    # 左锁骨
    ("b_12", (0.15, 0.0, 1.45), (0.45, 0.0, 1.45), "b_25"),    # 左臂
    ("b_13", (0.45, 0.0, 1.45), (0.70, 0.0, 1.45), "b_12"),
    ("b_14", (0.70, 0.0, 1.45), (0.85, 0.0, 1.45), "b_13"),
    ("b_26", (-0.03, 0.0, 1.45), (-0.15, 0.0, 1.45), "b_11"),  # 右锁骨
    ("b_16", (-0.15, 0.0, 1.45), (-0.45, 0.0, 1.45), "b_26"),  # 右臂
    ("b_17", (-0.45, 0.0, 1.45), (-0.70, 0.0, 1.45), "b_16"),
    ("b_18", (-0.70, 0.0, 1.45), (-0.85, 0.0, 1.45), "b_17"),
    ("b_19", (0.00, 0.0, 1.50), (0.00, 0.0, 1.60), "b_11"),    # 脖
    ("b_20", (0.00, 0.0, 1.60), (0.00, 0.0, 1.75), "b_19"),    # 头
    ("b_21", (0.00, 0.0, 1.75), (0.00, 0.0, 1.85), "b_20"),    # 头发
    ("b_22", (0.04, -0.06, 1.66), (0.04, -0.10, 1.66), "b_20"),
    ("b_23", (-0.04, -0.06, 1.66), (-0.04, -0.10, 1.66), "b_20"),
    ("b_24", (0.00, -0.04, 1.62), (0.00, -0.08, 1.60), "b_20"),
]

EXPECTED = {
    "b_00": "Hips", "b_09": "Spine", "b_10": "Spine1", "b_11": "Spine2",
    "b_19": "Neck", "b_20": "Head",
    "b_25": "LeftShoulder", "b_12": "LeftArm", "b_13": "LeftForeArm", "b_14": "LeftHand",
    "b_26": "RightShoulder", "b_16": "RightArm", "b_17": "RightForeArm", "b_18": "RightHand",
    "b_01": "LeftUpLeg", "b_02": "LeftLeg", "b_03": "LeftFoot", "b_04": "LeftToeBase",
    "b_05": "RightUpLeg", "b_06": "RightLeg", "b_07": "RightFoot", "b_08": "RightToeBase",
}


def build_rig(rename=None):
    """废名人形骨架 + 每根骨一个顶点组的作者网格。`rename` 改写个别骨名。"""
    for existing in list(bpy.data.objects):
        bpy.data.objects.remove(existing, do_unlink=True)
    rename = rename or {}
    data = bpy.data.armatures.new("Rig")
    rig = bpy.data.objects.new("Rig", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, tail, parent in SKELETON:
        bone = data.edit_bones.new(rename.get(name, name))
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = data.edit_bones[rename.get(parent, parent)]
    bpy.ops.object.mode_set(mode="OBJECT")

    names = [rename.get(name, name) for name, *_rest in SKELETON]
    mesh = bpy.data.meshes.new("AuthorMesh")
    mesh.from_pydata([(0.0, 0.0, index * 0.01) for index in range(len(names))], [], [])
    obj = bpy.data.objects.new("AuthorMesh", mesh)
    bpy.context.collection.objects.link(obj)
    for index, name in enumerate(names):
        obj.vertex_groups.new(name=name).add([index], 1.0, "REPLACE")
    obj.modifiers.new("Armature", "ARMATURE").object = rig
    return obj


scene = types.SimpleNamespace(gmi_source_rig="auto")

# ① 先证明这副骨架**真的**打穿了八张预设表 —— 否则下面全是白测。
obj = build_rig()
by_name_only = core.build_bone_remap(
    [group.name for group in obj.vertex_groups], GAME_BONES,
    parent_by_name=operators._source_bone_parents(obj))
assert not by_name_only["bones"], f"预设表居然认出了废名骨：{by_name_only['bones']}"

# ② 接上兜底之后，15 根必需骨一根不少，而且如实标成 topology。
report = operators._preset_bone_remap(obj, GAME_BONES, scene)
covered = set(report["bones"].values())
missing = [name for name in topology_map.REQUIRED if name not in covered]
assert not missing, f"结构识别没认出：{missing}"
assert report["bones"] == EXPECTED, report["bones"]
assert set(report["methods"].values()) == {"topology"}, report["methods"]
assert not core.critical_coverage_error(list(EXPECTED), report["bones"], GAME_BONES)

# ③ 名字有据时结构猜测必须让位：把左大臂改成一个游戏骨名，direct 命中，
#    结构识别既不许改写它，也不许拿它去顶 LeftArm。
obj = build_rig(rename={"b_12": "LeftForeArm"})
report = operators._preset_bone_remap(obj, GAME_BONES, scene)
assert report["bones"]["LeftForeArm"] == "LeftForeArm"
assert report["methods"]["LeftForeArm"] == "direct"
assert "b_12" not in report["bones"]

print(f"GMI_TOPOLOGY_FALLBACK_OK {bpy.app.version_string} "
      f"{len(EXPECTED)} 根废名骨全部按结构认出")
