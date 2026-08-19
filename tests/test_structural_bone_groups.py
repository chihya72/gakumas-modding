"""结构分组：一行一组，**一个骨名都不读**。

痛点是表单一行一根骨 —— chisaki 那条 MMD 裙子作者手点了几十次。分组信号只有三个：
锚点（沿父链第一根身体骨）、链（分叉即断）、链长 ±1。原来的 `group_key()` 正则剥 left/right，
在日语/中文/乱码骨名下全废，所以验收的第一条就是"外语样本与英文样本分组结果一致"。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

BODY = ["Hips", "Spine", "Spine1", "LeftArm", "LeftForeArm"]


def skirt_rig(panel_name, links=3, panels=12):
    """`panels` 片裙摆，每片 `links` 节，全部挂在 Hips 上。"""
    parents, bones = {name: None for name in BODY}, []
    parents["Spine"], parents["Spine1"] = "Hips", "Spine"
    parents["LeftForeArm"] = "LeftArm"
    for panel in range(panels):
        previous = "Hips"
        for link in range(links):
            name = panel_name(panel, link)
            parents[name] = previous
            bones.append(name)
            previous = name
    return bones, parents


def test_a_twelve_panel_skirt_collapses_to_one_row():
    bones, parents = skirt_rig(lambda panel, link: f"Skirt_{panel:02d}_{link}")
    groups = core.structural_bone_groups(bones, parents, BODY)
    assert len(groups) == 1
    assert groups[0]["chains"] == 12 and groups[0]["depth"] == 3
    assert len(groups[0]["members"]) == 36
    assert groups[0]["anchor"] == "Hips"


def test_japanese_and_mojibake_names_group_the_same_as_english():
    """验收条件：日语/乱码骨名样本的分组结果与英文样本一致。"""
    english, parents_en = skirt_rig(lambda panel, link: f"Skirt_{panel:02d}_{link}")
    japanese, parents_jp = skirt_rig(lambda panel, link: f"スカート{panel}_{link}")
    mojibake, parents_mb = skirt_rig(lambda panel, link: f"�X�J�[�g{panel}_{link}")
    shapes = [
        [(group["anchor"], group["chains"], group["depth"], len(group["members"]))
         for group in core.structural_bone_groups(bones, parents, BODY)]
        for bones, parents in ((english, parents_en), (japanese, parents_jp),
                               (mojibake, parents_mb))
    ]
    assert shapes[0] == shapes[1] == shapes[2]


def test_anchor_separates_skirt_from_sleeve():
    """挂 Hips 的裙和挂 ForeArm 的袖必须分开 —— 名字一样长一样，只有锚点不同。"""
    bones, parents = skirt_rig(lambda panel, link: f"Cloth_{panel}_{link}", links=3, panels=4)
    for index in range(3):
        name = f"Cuff_{index}"
        parents[name] = "LeftForeArm" if index == 0 else f"Cuff_{index - 1}"
        bones.append(name)
    groups = {group["anchor"]: group for group in
              core.structural_bone_groups(bones, parents, BODY)}
    assert set(groups) == {"Hips", "LeftForeArm"}
    assert groups["Hips"]["chains"] == 4
    assert groups["LeftForeArm"]["chains"] == 1


def test_a_fork_breaks_the_chain():
    """分叉即断（与"不建分叉链"的规矩对齐）：分叉后的两支各算一条链。"""
    parents = {"Hips": None, "Belt": "Hips", "Left": "Belt", "Right": "Belt",
               "LeftEnd": "Left", "RightEnd": "Right"}
    groups = core.structural_bone_groups(
        ["Belt", "Left", "Right", "LeftEnd", "RightEnd"], parents, ["Hips"])
    chains = sum(group["chains"] for group in groups)
    assert chains == 3          # Belt 一条 + 分叉出来的两支
    assert sum(len(group["members"]) for group in groups) == 5


def test_unweighted_middle_bones_do_not_split_a_chain():
    """父链上有没权重的中间骨时按最近的在册祖先接，否则一个空骨就把裙摆劈成两组。"""
    parents = {"Hips": None, "Skirt_0": "Hips", "Skirt_gap": "Skirt_0",
               "Skirt_1": "Skirt_gap"}
    groups = core.structural_bone_groups(["Skirt_0", "Skirt_1"], parents, ["Hips"])
    assert len(groups) == 1 and groups[0]["chains"] == 1
    assert groups[0]["members"] == ["Skirt_0", "Skirt_1"]


def test_group_keys_are_unique_and_stable():
    bones, parents = skirt_rig(lambda panel, link: f"Skirt_{panel}_{link}", panels=3)
    for index in range(6):                    # 更长的一条链：链长差 >1，必须另起一组
        name = f"Tail_{index}"
        parents[name] = "Hips" if index == 0 else f"Tail_{index - 1}"
        bones.append(name)
    groups = core.structural_bone_groups(bones, parents, BODY)
    keys = [group["key"] for group in groups]
    assert len(keys) == len(set(keys)) == 2
    assert keys == [group["key"] for group in
                    core.structural_bone_groups(bones, parents, BODY)]


def test_ring_of_panels_maps_per_bone_not_by_centroid():
    """外语命名的裙摆：结构分组进去之后，每片蹭自己那边的摇物骨，不再 40 根挤一根。

    这正是原来按 skirt/dress/cloth 词表判 kind 漏掉的情形。
    """
    source, parents, accessory = [], {"Hips": None}, []
    for index, x in enumerate((-0.2, 0.2)):
        name = f"スカート{index}"
        source.append({"name": name, "position": [x, 0.0, 0.0]})
        parents[name] = "Hips"
        accessory.append(name)
    target = [{"name": "LeftSkirt1_S", "position": [-0.2, 0.0, 0.0]},
              {"name": "RightSkirt1_S", "position": [0.2, 0.0, 0.0]}]
    ring = core.build_accessory_physics_remap(
        source, target, accessory, parent_by_name=parents,
        body_remap={"Hips": "Hips"},
        group_by_name={name: "Hips|L1" for name in accessory},   # 两条链一组
        overrides={name: "follow_skirt" for name in accessory},
    )
    assert ring["bones"] == {"スカート0": "LeftSkirt1_S", "スカート1": "RightSkirt1_S"}
    assert set(ring["strategies"].values()) == {"segment_nearest"}

    # 对照：整组只有一条链时仍按质心蹭（一条飘带不该逐节各找各的）。
    chain_parents = {"Hips": None, "リボン0": "Hips", "リボン1": "リボン0"}
    chain = core.build_accessory_physics_remap(
        [{"name": "リボン0", "position": [-0.2, 0.0, 0.0]},
         {"name": "リボン1", "position": [0.2, 0.0, 0.0]}],
        target, ["リボン0", "リボン1"], parent_by_name=chain_parents,
        body_remap={"Hips": "Hips"},
        group_by_name={"リボン0": "Hips|L2", "リボン1": "Hips|L2"},
        overrides={"リボン0": "follow_skirt"},
    )
    assert len(set(chain["bones"].values())) == 1
    assert set(chain["strategies"].values()) == {"group_centroid"}


def test_row_state_is_a_decision_not_a_guess():
    assert core.row_state("Hips") == "direct"
    assert core.row_state("Hips", shared_target=True) == "merge"     # 多对一
    assert core.row_state("", "integrate") == "helper"
    assert core.row_state("", "rigid") == "merge"
    assert core.row_state("", "follow:LeftSkirt1_S") == "merge"
    assert core.row_state("", "auto") == "undecided"                 # 装饰骨的正常起点
