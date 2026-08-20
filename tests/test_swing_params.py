# -*- coding: utf-8 -*-
"""新骨的摇物/驱动器参数：取哪一档、谁自己摆、作用域到哪。

三个来源合并而来：

- 链根扛着几何时的降档与空链闸门
- 驱动器的作用域（一行=一组=一条链）
- 驱动器参数块

合并只是把同一子系统的用例放到一起，断言一条没动（2026-08-20）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


# ==========================================================================
# 来自 test_anchor_geometry.py
# 链根扛着几何时要让它自己摆，以及"整条链没有几何"要拦下来。
#
# 实测的坏形状：`Chain_R_A0` 66 个带权顶点全在链根、`Chain_R_Aend` 一个都没有。
# 链根按原版是惰性锚（spring/mass 近 0，自身不摆），照拓扑出参数就是
# 「摆的骨没有几何、有几何的骨不摆」—— 画面纹丝不动，而 swingPrepared /
# modBonesRegistered 全绿，闸门一条都不报。
# ==========================================================================
def _records(*names):
    return [{"name": n, "localPosition": [0.0, -0.05, 0.0], "length": 0.05} for n in names]


def _build(names, weights, parents, dominant=None, swing_anchor=None):
    """`weights` = 任意权重（判空链），`dominant` = 主导顶点（判几何归属）。默认两者一致。"""
    return core.build_source_extra_bones(
        _records(*names), list(names), parent_by_name=parents,
        body_remap={"Hips": "Hips"}, weight_by_name=weights,
        dominant_by_name=weights if dominant is None else dominant,
        swing_anchor_bones=names if swing_anchor is None else swing_anchor,
        categories={n: "ribbon" for n in names})


def test_anchor_downgrade_is_off_by_default():
    """默认只报不改 —— 让链根自己摆是在替作者决定物理。

    实机验过：开了之后腰侧挂坠 / 腰包 / 胸前蝴蝶结全晃起来，而作者要的是它们别动。
    """
    names = ["Chain_R_A0", "Chain_R_Aend"]
    parents = {"Chain_R_A0": "Hips", "Chain_R_Aend": "Chain_R_A0"}
    report = _build(names, {"Chain_R_A0": 0.9}, parents, swing_anchor=())
    root = next(b for b in report["newBones"] if b["name"] == "Chain_R_A0")
    presets = core.load_swing_presets()["ribbon"]["roles"]
    assert "swingParamRole" not in root
    assert root["swing"]["mass"] == presets["root"]["mass"], "默认不许动参数"
    # 但发现要报出来，作者才知道这条链装了摇物也不会动
    assert report["anchorOnlyChains"] == ["Chain_R_A0"]
    note = core.anchor_only_chain_note(report["anchorOnlyChains"])
    assert "也不会动" in note and "Chain_R_A0" in note


def test_root_holding_all_geometry_swings_itself():
    names = ["Chain_R_A0", "Chain_R_Aend"]
    parents = {"Chain_R_A0": "Hips", "Chain_R_Aend": "Chain_R_A0"}
    report = _build(names, {"Chain_R_A0": 0.9}, parents)
    root = next(b for b in report["newBones"] if b["name"] == "Chain_R_A0")

    # 拓扑真值不动 —— build_swing_chains 要靠它找链根
    assert root["swingRole"] == "root"
    # 但参数按链中段出，并且留痕
    assert root["swingParamRole"] == "mid"
    assert report["anchorOnlyChains"] == ["Chain_R_A0"]

    presets = core.load_swing_presets()["ribbon"]["roles"]
    assert root["swing"]["mass"] == presets["mid"]["mass"]
    assert root["swing"]["mass"] != presets["root"]["mass"], "还是惰性锚的话画面不会动"


def test_normal_chain_keeps_the_lazy_anchor():
    """子骨有几何的正常链不许被动手 —— 惰性锚是原版的语义。"""
    names = ["Skirt_L_A0", "Skirt_L_A1"]
    parents = {"Skirt_L_A0": "Hips", "Skirt_L_A1": "Skirt_L_A0"}
    report = _build(names, {"Skirt_L_A0": 0.5, "Skirt_L_A1": 0.4}, parents)
    root = next(b for b in report["newBones"] if b["name"] == "Skirt_L_A0")

    assert root["swingRole"] == "root"
    assert "swingParamRole" not in root
    assert report["anchorOnlyChains"] == []
    presets = core.load_swing_presets()["ribbon"]["roles"]
    assert root["swing"]["mass"] == presets["root"]["mass"]


def test_chain_without_any_weight_is_reported_and_blocked():
    names = ["Ghost_A0", "Ghost_A1"]
    parents = {"Ghost_A0": "Hips", "Ghost_A1": "Ghost_A0"}
    report = _build(names, {"Other": 1.0}, parents)
    assert report["emptyChains"] == ["Ghost_A0"]

    error = core.empty_swing_chain_error(report["emptyChains"])
    assert error and "Ghost_A0" in error
    assert core.empty_swing_chain_error([]) is None


def test_no_weight_data_changes_nothing():
    """没传权重（老调用方）时一切照旧，不许静默改参数。"""
    names = ["Chain_R_A0", "Chain_R_Aend"]
    parents = {"Chain_R_A0": "Hips", "Chain_R_Aend": "Chain_R_A0"}
    report = _build(names, None, parents)
    root = next(b for b in report["newBones"] if b["name"] == "Chain_R_A0")
    assert "swingParamRole" not in root
    assert report["anchorOnlyChains"] == [] and report["emptyChains"] == []


def test_the_switch_is_per_chain():
    """同一个模型里靴口花边要摆、腰侧挂坠要焊死 —— 勾了的那条降档，没勾的不许跟着动。"""
    names = ["Lace_R_A0", "Lace_R_Aend", "Chain_R_A0", "Chain_R_Aend"]
    parents = {"Lace_R_A0": "Hips", "Lace_R_Aend": "Lace_R_A0",
               "Chain_R_A0": "Hips", "Chain_R_Aend": "Chain_R_A0"}
    weights = {"Lace_R_A0": 97, "Chain_R_A0": 30}
    report = _build(names, weights, parents, swing_anchor={"Lace_R_A0"})
    by_name = {b["name"]: b for b in report["newBones"]}
    assert by_name["Lace_R_A0"]["swingParamRole"] == "mid"
    assert "swingParamRole" not in by_name["Chain_R_A0"]
    # 两条链都该被报出来，只有勾了的那条真的降了档
    assert report["anchorOnlyChains"] == ["Chain_R_A0", "Lace_R_A0"]
    assert report["anchorSwingApplied"] == ["Lace_R_A0"]


def test_note_names_the_chains():
    note = core.anchor_only_chain_note(["Chain_R_A0", "Key_R_A0"])
    assert "Chain_R_A0" in note and "Key_R_A0" in note
    assert core.anchor_only_chain_note([]) is None


def test_co_influencer_root_is_left_alone():
    """有权重但一个顶点都不主导的链根不许降档 —— 它改的是别人的形状。

    实测 `Spine_Bow_L_A0` 在 613 个顶点上有权重、主导 0；让它自己摆，
    拖坏的是后裙和大蝴蝶结（2026-08-19 花边被拖出锯齿）。
    """
    names = ["Spine_Bow_L_A0", "Spine_Bow_L_Aend"]
    parents = {"Spine_Bow_L_A0": "Hips", "Spine_Bow_L_Aend": "Spine_Bow_L_A0"}
    report = _build(names, {"Spine_Bow_L_A0": 0.4}, parents, dominant={})
    root = next(b for b in report["newBones"] if b["name"] == "Spine_Bow_L_A0")
    assert "swingParamRole" not in root
    assert report["anchorOnlyChains"] == []
    # 有权重就不算空链 —— 闸门①不许误伤它
    assert report["emptyChains"] == []


# ==========================================================================
# 来自 test_driver_scope.py

# ==========================================================================
# 两条同类别（裙）的链，各自一根骨：作者只点了左边那条。
SOURCE = [
    {"name": "LeftSkirt1_S", "localPosition": [0.1, 0.0, 0.0], "length": 0.1},
    {"name": "RightSkirt1_S", "localPosition": [-0.1, 0.0, 0.0], "length": 0.1},
]
NAMES = ["LeftSkirt1_S", "RightSkirt1_S"]
PARENTS = {"LeftSkirt1_S": "Pelvis", "RightSkirt1_S": "Pelvis"}
BODY = {"Pelvis": "Hips"}


def by_name(result):
    return {item["name"]: item for item in result["newBones"]}


def test_driver_only_lands_on_the_named_bones():
    result = core.build_source_extra_bones(
        SOURCE, NAMES, parent_by_name=PARENTS, body_remap=BODY,
        categories={name: "skirt" for name in NAMES},
        driver_bones={"LeftSkirt1_S": "skirt"})
    bones = by_name(result)
    assert bones["LeftSkirt1_S"].get("driver", {}).get("type") == "Skirt"
    assert "swing" not in bones["LeftSkirt1_S"]          # 驱动器与摇物二选一
    # 同类别但没被点名的那根：一个字都不许变
    assert "driver" not in bones["RightSkirt1_S"]
    assert bones["RightSkirt1_S"].get("swing")


def test_not_naming_anything_changes_nothing():
    """默认空 = 完全不碰这条路径，现有成品重导逐字节一样。"""
    plain = core.build_source_extra_bones(
        SOURCE, NAMES, parent_by_name=PARENTS, body_remap=BODY,
        categories={name: "skirt" for name in NAMES})
    assert all("driver" not in item for item in plain["newBones"])
    assert all(item.get("swing") for item in plain["newBones"])


def test_named_category_overrides_the_guessed_one():
    """点名时给的类别优先于按骨名猜的（猜出来的可能是别的档）。"""
    result = core.build_source_extra_bones(
        SOURCE, NAMES, parent_by_name=PARENTS, body_remap=BODY,
        driver_bones={"LeftSkirt1_S": "sleeve"})
    assert by_name(result)["LeftSkirt1_S"]["driver"]["type"] == "HumanoidSleeve"


def test_only_three_categories_have_drivers():
    """运行时只实现 Skirt / Frill / HumanoidSleeve —— UI 置灰和导出闸门读的就是这张表。"""
    assert set(core.DRIVER_CATEGORIES) == {"skirt", "cloth", "sleeve"}
    for category in core.DRIVER_CATEGORIES:
        assert core.build_driver_block(category, "Left") is not None
    assert core.build_driver_block("ribbon", "Left") is None


def test_unsupported_category_produces_no_silent_driver():
    """真被点名成 ribbon 时导出器不会造出半个驱动器块（闸门在算子层拦，见 _form_driver_gaps）。"""
    result = core.build_source_extra_bones(
        SOURCE, NAMES, parent_by_name=PARENTS, body_remap=BODY,
        driver_bones={"LeftSkirt1_S": "ribbon"})
    bones = by_name(result)
    assert "driver" not in bones["LeftSkirt1_S"]
    # swing 还在 —— 但这个组合在导出前就被算子闸门拦下了，不会走到出包
    assert bones["LeftSkirt1_S"].get("swing")


# ==========================================================================
# 来自 test_driver_blocks.py

# ==========================================================================
def test_skirt_frill_sleeve_get_universal_reference_bones():
    assert core.build_driver_block("skirt", "Left")["bones"] == {"referenceBone": "LeftUpLeg"}
    assert core.build_driver_block("cloth", "Right")["bones"] == {"referenceBone": "RightArm"}
    assert core.build_driver_block("sleeve", "Left")["bones"] == {"referenceBone": "LeftHand"}


def test_driver_types_match_the_game_classes():
    assert core.build_driver_block("skirt", "Left")["type"] == "Skirt"
    assert core.build_driver_block("cloth", "Left")["type"] == "Frill"
    assert core.build_driver_block("sleeve", "Left")["type"] == "HumanoidSleeve"


def test_ribbon_never_gets_a_driver():
    """原版的蝴蝶结/飘带就是裸的 ActorSwingDynamicBone，本来就该走摇物。"""
    assert core.build_driver_block("ribbon", "Left") is None


def test_unknown_side_refuses_rather_than_guessing():
    """参考骨分左右，猜错等于把裙子绑到另一条腿上——宁可不给。"""
    assert core.build_driver_block("skirt", "") is None
    assert core.build_driver_block("skirt", None) is None


def test_setting_is_split_by_type_not_by_json_shape():
    """int / float / vector 分开三张表：JSON 的 0 既可能是枚举也可能是浮点，
    按形状猜会把 rotationOrder 写成浮点，而且这种错在日志里看不出来。"""
    block = core.build_driver_block("skirt", "Left")
    assert isinstance(block["ints"].get("rotationOrder"), int)
    assert all(isinstance(v, list) and len(v) == 3 for v in block["vectors"].values())


def test_bone_side_detection():
    assert core.bone_side("LeftFrontSkirt_A") == "Left"
    assert core.bone_side("skirt_r_01") == "Right"
    assert core.bone_side("左スカート") == "Left"
    assert core.bone_side("Skirt_Center") is None
    # 单字母缩写必须卡边界：这个名字里有个 `_r`，按子串匹配会被判成右侧，
    # 然后袖子绑到另一边，离线完全看不出来。
    assert core.bone_side("Cloth_Ribbon") is None
    assert core.bone_side("Sleeve.L") == "Left"
    assert core.bone_side("skirt_l_02") == "Left"



if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("摇物参数自检全过")
