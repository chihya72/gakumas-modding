"""B 类三项的纯逻辑：几何判部件类型进生产、五档的 bake/reject、节数不同的塌链标注。

三项的共同点：以前都是"看不见"的洞 —— 按名字判类别对外语骨名全废、bake/reject 只有词汇没有
决定、把 4 节手指塌成 3 节之后每根骨都有目标权重也归一（闸门永远抓不到）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


# ---------------------------------------------------------------- 几何判部件类型
def ring(count, links, anchor="Pelvis", prefix="謎の飾り", y=-0.1):
    """`count` 条链、每条 `links` 节，全挂在 anchor 上，往下垂。骨名故意是外语。"""
    parents, positions, names = {anchor: None}, {anchor: (0.0, 1.0, 0.0)}, []
    for panel in range(count):
        previous = anchor
        for link in range(links):
            name = f"{prefix}{panel}_{link}"
            parents[name] = previous
            positions[name] = (0.1 * panel, 1.0 + y * (link + 1), 0.0)
            names.append(name)
            previous = name
    return names, parents, positions


def test_foreign_named_hem_gets_the_skirt_tier():
    """一圈 6 片挂在 Pelvis 上 —— 按名字判会落飘带（不建链），按几何是裙。"""
    names, parents, positions = ring(6, 3)
    result = core.geometric_swing_categories(names, parents, positions,
                                             body_remap={"Pelvis": "Pelvis"})
    assert set(result.values()) == {"skirt"}
    # 反证：同样的骨名按名字判只能拿到最保守的一档
    assert core.swing_category(names[0]) == "ribbon"


def test_one_or_two_panels_on_the_hip_are_not_a_hem():
    """裙摆是一圈（原版一个锚点挂 4–8 片）；胯上只挂一两条的是围裙/尾巴/腰带。"""
    names, parents, positions = ring(2, 3)
    result = core.geometric_swing_categories(names, parents, positions,
                                             body_remap={"Pelvis": "Pelvis"})
    assert set(result.values()) == {"cloth"}


def test_anchor_decides_sleeve_without_reading_names():
    names, parents, positions = ring(1, 2, anchor="LeftForeArm", prefix="そで")
    result = core.geometric_swing_categories(
        names, parents, positions, body_remap={"LeftForeArm": "LeftForeArm"})
    assert set(result.values()) == {"sleeve"}


def test_anchor_is_translated_to_the_game_bone_name():
    """锚点表按**游戏骨名**匹配，所以源骨名要先过 remap，否则永远落兜底。"""
    names, parents, positions = ring(6, 3, anchor="下半身")
    without = core.geometric_swing_categories(names, parents, positions)
    mapped = core.geometric_swing_categories(names, parents, positions,
                                             body_remap={"下半身": "Hips"})
    assert set(mapped.values()) == {"skirt"}
    assert set(without.values()) != {"skirt"}          # 没映射时判不出锚点


# ---------------------------------------------------------------------- 五档
def test_bake_and_reject_are_decisions_not_physics():
    assert core.row_state("", "bake") == "bake"
    assert core.row_state("", "reject") == "reject"
    # 比"填了目标骨"更强：作者说了拒绝/烘焙，就不该被 direct 盖掉
    assert core.row_state("Hips", "reject") == "reject"
    assert core.row_state("Hips", "bake") == "bake"
    # 其余四档不受影响
    assert core.row_state("Hips") == "direct"
    assert core.row_state("", "integrate") == "helper"
    assert core.row_state("", "auto") == "undecided"
    assert set(core.ROW_STATE_LABELS) == {
        "direct", "merge", "helper", "bake", "reject", "undecided"}


# ------------------------------------------------------------------ 塌链标注
def test_collapsed_finger_chain_is_reported():
    """源有 4 节手指、游戏只有 3 节 —— 末两节塌进同一根骨，这一处必须被标出来。"""
    remap = {"Index1": "LeftHandIndex1", "Index2": "LeftHandIndex2",
             "Index3": "LeftHandIndex3", "Index4": "LeftHandIndex3"}
    parents = {"Index1": "Hand", "Index2": "Index1", "Index3": "Index2", "Index4": "Index3"}
    rows = core.collapsed_chains(remap, parents, {"Index3": 0.3, "Index4": 0.1})
    assert len(rows) == 1
    assert rows[0]["target"] == "LeftHandIndex3"
    assert rows[0]["sources"] == ["Index3", "Index4"]
    assert abs(rows[0]["mass"] - 0.4) < 1e-9


def test_left_right_merge_is_not_a_collapsed_chain():
    """左右两根骨并到一根不是"链被压短"（它们不是父子），别混进这份清单。"""
    remap = {"Bow_L": "Hips", "Bow_R": "Hips"}
    parents = {"Bow_L": "Spine", "Bow_R": "Spine"}
    assert core.collapsed_chains(remap, parents) == []


def test_heaviest_collapse_comes_first():
    remap = {"A1": "Spine", "A2": "Spine", "B1": "Neck", "B2": "Neck"}
    parents = {"A2": "A1", "B2": "B1"}
    rows = core.collapsed_chains(remap, parents, {"A1": 1.0, "A2": 1.0, "B1": 9.0, "B2": 1.0})
    assert [row["target"] for row in rows] == ["Neck", "Spine"]
