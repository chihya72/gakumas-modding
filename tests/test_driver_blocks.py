"""P3 导出器侧：链类别 → 学马自己的布料驱动器。

只有参考骨是**通用身体骨**的三种能装到任意目标上（530 套原版实测）：
    Skirt.referenceBone          → Left/RightUpLeg
    Frill.referenceBone          → Left/RightArm
    HumanoidSleeve.referenceBone → Left/RightHand
Waist / Furisode / Poncho 的引用全是每套服装自己的 `*_O` 偏移骨，装到别的服装上只会得到
空引用（表现是"这块布不动"、日志全绿），所以明确不支持。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


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
