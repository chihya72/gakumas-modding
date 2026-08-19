"""缺骨三分法与「从相邻骨劈权重」（§7.3 / §8.2）。

源模型没有锁骨（MMD/Biped 常见：Spine2 直接接 UpperArm）时，那块几何在游戏里跟着别的骨乱跑。
劈权重的规矩是**只对这几根**做，不重绘全身：原版只决定"分给缺骨多少"，剩下的按作者自己的
比例分回捐赠骨（要求 2 保留源权重）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def test_missing_critical_bones_lists_only_real_gaps():
    target = list(core.CRITICAL_TARGET_BONES)
    remap = {name: name for name in target if name != "LeftShoulder"}
    assert core.missing_critical_bones(list(remap), remap, target) == ["LeftShoulder"]
    # 骨很少的局部骨架不误报（与目标骨架取交集）
    assert core.missing_critical_bones(["Hips"], {"Hips": "Hips"}, ["Hips"]) == []


def test_error_text_gives_both_exits():
    """「去表单指定」和「从相邻骨劈」是两种情形的两条出路，只给前一条会让作者卡死。"""
    target = list(core.CRITICAL_TARGET_BONES)
    remap = {name: name for name in target if name != "Neck"}
    message = core.critical_coverage_error(list(remap), remap, target)
    assert "Neck" in message
    assert "骨骼映射表" in message and "从相邻骨劈权重" in message


def test_split_takes_the_vanilla_share_and_keeps_donor_proportions():
    """原版说这点 60% 归锁骨；作者的 Spine2:Arm = 3:1 这个比例必须原样留着。"""
    author = {"Spine2": 0.75, "LeftArm": 0.25}
    vanilla = {"LeftShoulder": 0.6, "Spine2": 0.3, "LeftArm": 0.1}
    result = core.redistribute_family_weight(author, vanilla, "LeftShoulder")
    assert abs(sum(result.values()) - 1.0) < 1e-9          # 总量守恒
    assert abs(result["LeftShoulder"] - 0.6) < 1e-9        # 原版的占比
    assert abs(result["Spine2"] / result["LeftArm"] - 3.0) < 1e-9   # 作者的比例


def test_bones_the_vanilla_body_does_not_have_here_are_left_alone():
    """作者有权重、原版在这一点上没有的骨不进族 —— 那是作者自己的画法，不许动。"""
    author = {"Spine2": 0.5, "Hips": 0.5}
    vanilla = {"LeftShoulder": 0.5, "Spine2": 0.5}
    result = core.redistribute_family_weight(author, vanilla, "LeftShoulder")
    assert "Hips" not in result
    assert abs(sum(result.values()) - 0.5) < 1e-9          # 只重分了族内那 0.5
    assert abs(result["LeftShoulder"] - 0.25) < 1e-9


def test_nothing_happens_outside_the_missing_bone_territory():
    """原版在这点上没有缺骨的权重 = 这个顶点不是它的地盘，一点都不动。"""
    author = {"Spine2": 1.0}
    assert core.redistribute_family_weight(author, {"Spine2": 1.0}, "LeftShoulder") == {}
    assert core.redistribute_family_weight({}, {"LeftShoulder": 1.0}, "LeftShoulder") == {}


def test_no_common_bone_means_no_change_at_all():
    """原版在这点上只认锁骨、作者只画了 Spine2 —— 两边没有共同的骨，就一点都不动。

    这是"只在作者和原版都认的骨之间重分"的边界：宁可不劈，也不把作者的权重整块抢走。
    """
    assert core.redistribute_family_weight(
        {"Spine2": 0.4}, {"LeftShoulder": 0.9, "Spine2": 0.0}, "LeftShoulder") == {}
    # 捐赠骨在原版那儿只有一点点权重时，才会几乎全给缺骨（平滑过渡，不是硬抢）
    result = core.redistribute_family_weight(
        {"Spine2": 0.4}, {"LeftShoulder": 0.9, "Spine2": 0.01}, "LeftShoulder")
    assert abs(result["LeftShoulder"] - 0.4 * 0.9 / 0.91) < 1e-9
    assert abs(sum(result.values()) - 0.4) < 1e-9


def test_weight_state_summary_is_measurable_not_a_guess():
    mass = {"Hip": 40.0, "Spine01": 20.0, "Spine02": 10.0, "Ribbon_A": 20.0, "Mystery": 10.0}
    remap = {"Hip": "Hips", "Spine01": "Spine", "Spine02": "Spine", "Ribbon_A": "Hips"}
    summary = core.weight_state_summary(
        mass, remap, new_bones=["Ribbon_A"], unmapped=["Mystery"])
    assert summary["direct"] == 40.0                    # Hip 独占 Hips
    assert summary["merge"] == 30.0                     # 两节脊椎挤 Spine
    assert summary["helper"] == 20.0                    # 新建辅助骨
    assert summary["undecided"] == 10.0                 # 连目标都没有


def test_weight_sum_errors_flags_zero_and_unnormalised():
    bad = core.weight_sum_errors([1.0, 0.999999, 0.5, 0.0, 1.4])
    assert [index for index, _value in bad] == [3, 2, 4]   # 最偏的排前面（1.0 / 0.5 / 0.4）
    assert core.weight_sum_errors([1.0, 1.0]) == []
