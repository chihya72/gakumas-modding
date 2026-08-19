"""批次 1 的两把尺子：逐骨静止对齐（位置 + **朝向**）与跨关节权重带。

朝向是作者唯一自查不到的东西 —— 绕骨自身轴的滚转差在静止截图里完全正常，转身之后手臂整个
炸开、手指变面条（实机三次坐实，肩差 172°）。所以这里的判据里必须有"172° 报红"这一条。

跨关节带是唯一能**预判**"肩膀会不会崩"的数字：原版肩 13.3%，作者那副 rip 只有 4.9%。
"""
import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


# 一副对齐好的胳膊：肩 → 大臂 → 小臂 → 手，都在 Unity 空间（y 向上、x 向侧）。
GAME = {
    "LeftShoulder": (0.05, 1.40, 0.0),
    "LeftArm": (0.15, 1.40, 0.0),
    "LeftForeArm": (0.40, 1.40, 0.0),
    "LeftHand": (0.62, 1.40, 0.0),
}
CHILDREN = {"LeftShoulder": ["LeftArm"], "LeftArm": ["LeftForeArm"],
            "LeftForeArm": ["LeftHand"]}
LENGTHS = {"LeftShoulder": 0.10, "LeftArm": 0.25, "LeftForeArm": 0.22, "LeftHand": 0.08}


def test_self_consistent_rig_is_all_green():
    """源就是目标自己时必须 0.0mm / 0.0° 全绿 —— 尺子在正常样本上不许误报（INV-8）。"""
    rows = core.rest_alignment(dict(GAME), GAME, CHILDREN, LENGTHS)
    assert [row["grade"] for row in rows] == ["green"] * 4
    assert max(row["mm"] for row in rows) < 1e-9
    assert max(row["deg"] or 0.0 for row in rows) < 1e-9


def test_shoulder_off_by_172_degrees_is_red():
    """已知坏样本：源的大臂从肩上朝身后长（Claymore rip 实测肩 172.5°）。

    肩**本身的位置**完全对上 —— 只量位置的尺子看不见它，这正是作者自查不到的那一种。
    """
    source = dict(GAME)
    source["LeftArm"] = (0.05 - 0.099, 1.40, -0.014)      # 从肩点朝身后偏 172°
    rows = {row["bone"]: row for row in
            core.rest_alignment(source, GAME, CHILDREN, LENGTHS)}
    assert rows["LeftShoulder"]["grade"] == "red"
    assert abs(rows["LeftShoulder"]["deg"] - 172.0) < 1.0
    assert rows["LeftShoulder"]["mm"] < 1e-9     # 肩自己一点没偏
    assert rows["LeftShoulder"]["child"] == "LeftArm"


def test_roll_about_the_bone_axis_is_not_flagged():
    """绕骨轴的 roll 不算朝向差 —— 2026-08-17 拿原版自己的身体标定过。

    插件重建参考骨架时 roll 就没保留（`_create_armature` 只按 head→tail + 默认 roll 建骨）：
    104 根里 69 根整体转角正好 180°、骨轴向差 0.00°。按整体转角判，**原版自己全红**。
    这个判据只看位移方向，所以对 roll 免疫。
    """
    rows = core.rest_alignment(dict(GAME), GAME, CHILDREN, LENGTHS)
    assert {row["grade"] for row in rows} == {"green"}


def test_only_humanoid_children_count():
    """脊椎下面挂一堆下垂的衣物骨会把方向拽反（实测报 154°）—— children 只给人形子骨。"""
    source = dict(GAME)
    source["LeftSkirt1"] = (0.05, 1.00, 0.0)     # 从肩往下垂的装饰骨，不该参与判定
    target = dict(GAME)
    target["LeftSkirt1"] = (0.05, 1.00, 0.0)
    clean = core.rest_alignment(source, target, CHILDREN, LENGTHS)
    assert {row["grade"] for row in clean} == {"green"}
    polluted = core.rest_alignment(
        source, target, dict(CHILDREN, LeftShoulder=["LeftArm", "LeftSkirt1"]), LENGTHS)
    assert {row["grade"] for row in polluted} == {"green"}   # 位置都对，只是多量一个方向


def test_leaf_bones_report_unmeasurable_not_zero():
    """末节骨没有人形子骨 —— 报"量不了"，别显示成 0°（那是"已对齐"的意思）。"""
    row = {item["bone"]: item for item in
           core.rest_alignment(dict(GAME), GAME, CHILDREN, LENGTHS)}["LeftHand"]
    assert row["deg"] is None and row["grade"] == "green"
    assert core.format_degrees(row["deg"]) == "量不了"
    assert core.format_degrees(172.0) == "172.0°"


def test_position_is_judged_against_bone_length_and_never_red():
    """8mm 在手指骨节上要报，在大腿上不用；但位置最高只判黄 —— 会炸的是朝向，不是位置。

    lossless 蒙皮把静止位置差当重定向吸收（"免的是位置"），所以位置差是"该对齐"不是"会炸"。
    """
    finger = core.rest_alignment({"LeftHandIndex1": (0.008, 0, 0)},
                                 {"LeftHandIndex1": (0.0, 0, 0)},
                                 {}, {"LeftHandIndex1": 0.022})
    thigh = core.rest_alignment({"LeftUpLeg": (0.008, 0, 0)}, {"LeftUpLeg": (0.0, 0, 0)},
                                {}, {"LeftUpLeg": 0.30})
    huge = core.rest_alignment({"Hips": (0.20, 0, 0)}, {"Hips": (0.0, 0, 0)},
                               {}, {"Hips": 0.10})
    assert finger[0]["grade"] == "yellow"
    assert thigh[0]["grade"] == "green"
    assert huge[0]["grade"] == "yellow"       # 20cm 也只是黄


PARENTS = {
    "Hips": None, "Spine": "Hips", "Spine1": "Spine",
    "LeftShoulder": "Spine1", "LeftArm": "LeftShoulder",
    "LeftForeArm": "LeftArm", "LeftHand": "LeftForeArm",
    "LeftHandIndex1": "LeftHand",
}


def test_cross_joint_band_counts_only_vertices_that_span_the_joint():
    sides = core.joint_band_sides(PARENTS)
    # 远侧包含整条子树：手指也算"肩关节的远侧"
    assert sides["肩"]["LeftHandIndex1"] == 2
    assert sides["肩"]["LeftShoulder"] == 1
    assert sides["肩"].get("Hips") is None        # 近端骨的子树之外，两侧都不算

    vertices = [
        {"LeftShoulder": 0.6, "LeftArm": 0.4},    # 跨肩
        {"LeftShoulder": 1.0},                    # 只在近侧
        {"LeftArm": 1.0},                         # 只在远侧
        {"LeftShoulder": 0.999, "LeftArm": 0.001},  # 权重低于阈值 → 不算跨
        {"Hips": 1.0},                            # 与肩无关，不进分母
    ]
    band = core.cross_joint_bands(vertices, sides)["肩"]
    assert (band["cross"], band["total"]) == (1, 4)
    assert abs(band["share"] - 0.25) < 1e-9


def test_shoulder_band_far_below_vanilla_is_red():
    """作者那副 rip 的真值：跨肩带 4.9% vs 原版 13.3% → 报红（原版的四成以下）。"""
    mod = {"肩": {"cross": 49, "total": 1000, "share": 0.049},
           "肘": {"cross": 35, "total": 1000, "share": 0.035}}
    rows = {row["joint"]: row for row in core.cross_joint_band_findings(mod)}
    assert rows["肩"]["grade"] == "red"
    assert abs(rows["肩"]["vanilla"] - 0.133) < 1e-9
    # 肘 3.5% vs 原版 3.9%：低于原版但没到四成以下 —— 值得看，不是崩
    assert rows["肘"]["grade"] == "yellow"


def test_vanilla_reference_bands_beat_the_table():
    """场景里有带权重参考体时用它现算的基线，而不是写死的真值表。"""
    mod = {"肩": {"cross": 100, "total": 1000, "share": 0.10}}
    vanilla = {"肩": {"cross": 110, "total": 1000, "share": 0.11}}
    row = core.cross_joint_band_findings(mod, vanilla)[0]
    assert abs(row["vanilla"] - 0.11) < 1e-9
    assert row["grade"] == "yellow"       # 按真值表 13.3% 也是黄，但基线得是参考体那个数
