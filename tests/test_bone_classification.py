# -*- coding: utf-8 -*-
"""装饰骨怎么分类、归哪组、走什么策略 —— 这一层出错的代价全是静默的。

四个来源合并而来，每一节的开头保留了它当初是被哪个实机 bug 逼出来的：

- 名字规则的作用域（左右不对称的根因）
- 结构分组（一行一组）
- 五档状态与几何判部件类型
- 按几何判类别

合并只是把同一子系统的用例放到一起，断言一条没动（2026-08-20）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


# ==========================================================================
# 来自 test_name_rule_scope.py
# 内置的名字规则不许泄漏到同组的邻居身上（左右不对称的根因）。
#
# 实测：`Lace_R_*` 与 `Leg_pendant_R_*` 都挂 `RightLeg`、都两节，被结构分组并成一组，
# 于是 lace 的 `follow_skirt` 把腿上的挂坠也送去蹭裙摆末端摇物骨，实机满天飞；
# 而左边的挂坠是三节、没跟 lace 并组，走的是刚性。同一件东西左右两种结果。
# ==========================================================================
def _scene():
    """左右镜像的腿部挂坠；右边额外有一段花边，和挂坠同锚点、同链长。"""
    source = {
        "Leg_pendant_L_A0": (-0.10, 0.60, 0.05),
        "Leg_pendant_L_A1": (-0.10, 0.50, 0.05),
        "Leg_pendant_L_Aend": (-0.10, 0.40, 0.05),
        "Leg_pendant_R_A0": (0.10, 0.60, 0.05),
        "Leg_pendant_R_Aend": (0.10, 0.50, 0.05),
        "Lace_R_A0": (0.12, 0.62, 0.02),
        "Lace_R_Aend": (0.12, 0.52, 0.02),
    }
    parents = {
        "Leg_pendant_L_A0": "LeftUpLeg", "Leg_pendant_L_A1": "Leg_pendant_L_A0",
        "Leg_pendant_L_Aend": "Leg_pendant_L_A1",
        "Leg_pendant_R_A0": "RightLeg", "Leg_pendant_R_Aend": "Leg_pendant_R_A0",
        "Lace_R_A0": "RightLeg", "Lace_R_Aend": "Lace_R_A0",
    }
    target = {
        "LeftUpLeg": (-0.09, 0.75, 0.0), "RightLeg": (0.09, 0.45, 0.0),
        # 裙摆末端摇物骨就在挂坠边上 —— 泄漏时它就是被蹭上的那根
        "RightBackSideSkirt4_S": (0.13, 0.55, 0.03),
        "LeftBackSideSkirt4_S": (-0.13, 0.55, 0.03),
    }
    body = {"LeftUpLeg": "LeftUpLeg", "RightLeg": "RightLeg"}
    # 结构分组的实测结果：右边花边与挂坠同锚点同链长 → 并成一组
    group = {
        "Leg_pendant_L_A0": "LeftUpLeg|L3", "Leg_pendant_L_A1": "LeftUpLeg|L3",
        "Leg_pendant_L_Aend": "LeftUpLeg|L3",
        "Leg_pendant_R_A0": "RightLeg|L2", "Leg_pendant_R_Aend": "RightLeg|L2",
        "Lace_R_A0": "RightLeg|L2", "Lace_R_Aend": "RightLeg|L2",
    }
    return source, target, parents, body, group


def _run(**kwargs):
    source, target, parents, body, group = _scene()
    return core.build_accessory_physics_remap(
        [{"name": n, "position": p} for n, p in source.items()],
        [{"name": n, "position": p} for n, p in target.items()],
        list(source), parent_by_name=parents, body_remap=body,
        group_by_name=group, **kwargs)


def test_lace_semantic_does_not_leak_onto_the_co_grouped_pendant():
    report = _run()
    # 花边照常蹭裙摆摇物骨 —— 这是它自己的语义，不能一起废掉
    assert report["bones"].get("Lace_R_A0") == "RightBackSideSkirt4_S"
    # 挂坠必须刚性跟腿，不许跟着花边去蹭裙摆
    assert "Leg_pendant_R_A0" not in report["bones"], report["bones"]
    assert report["rigidParent"].get("Leg_pendant_R_A0") == "RightLeg"
    assert report["rigidParent"].get("Leg_pendant_R_Aend") == "RightLeg"


def test_left_and_right_land_the_same_way():
    """镜像的同一件东西必须走同一条分支 —— 左右不对称本身就是 bug 的指纹。"""
    report = _run()
    left = {report["strategies"][n] for n in
            ("Leg_pendant_L_A0", "Leg_pendant_L_A1", "Leg_pendant_L_Aend")}
    right = {report["strategies"][n] for n in ("Leg_pendant_R_A0", "Leg_pendant_R_Aend")}
    assert left == right == {"source_parent"}, (left, right)


def test_author_override_scopes_to_its_own_chain():
    """作者覆盖只作用在自己那条链上，不许顺着结构组跑到邻居身上。

    结构分组在真模型上一组能装下整条下半身（实测 `Hips_1|L2` 一组 57 根骨：裙板 + 腰带 +
    飘带 + 挂坠 + 蝴蝶结）。旧实现是"整组一个指令、第一个带覆盖的骨说了算"，于是把
    `Bag_R/Chain_R/Key_R` 点成刚性会被同组 `Spine_Bow_L_B0` 的 integrate 吞掉，
    把 `Spine2_Bow_*` 点成刚性会让同组的 `OPAI_*` 一起变刚性、骨直接消失。
    """
    report = _run(overrides={"Lace": "follow_nearest"})
    assert report["strategies"]["Lace_R_A0"] == "override_nearest"
    # 同组、不同链的挂坠不受影响
    assert report["strategies"]["Leg_pendant_R_A0"] == "source_parent"
    assert report["rigidParent"]["Leg_pendant_R_A0"] == "RightLeg"


def test_two_overrides_in_one_group_each_keep_their_own_chain():
    """同一个结构组里两条链各自点了不同的策略，必须各归各的。"""
    report = _run(overrides={"Lace_R_A0": "follow_nearest", "Leg_pendant_R_A0": "rigid"})
    assert report["strategies"]["Lace_R_A0"] == "override_nearest"
    assert report["strategies"]["Leg_pendant_R_A0"] == "rigid_parent"
    assert report["rigidParent"]["Leg_pendant_R_A0"] == "RightLeg"


def test_source_chain_stays_whole():
    """源链整条一起 integrate，不能因为组里混了别的骨就被劈开。"""
    source = {"Streamer_L_A0": (0.0, 0.9, -0.1), "Streamer_L_A1": (0.0, 0.8, -0.15),
              "Deco_L_A0": (0.02, 0.9, -0.08)}
    parents = {"Streamer_L_A0": "Hips", "Streamer_L_A1": "Streamer_L_A0",
               "Deco_L_A0": "Hips"}
    report = core.build_accessory_physics_remap(
        [{"name": n, "position": p} for n, p in source.items()],
        [{"name": "Hips", "position": (0.0, 1.0, 0.0)}],
        list(source), parent_by_name=parents, body_remap={"Hips": "Hips"},
        group_by_name={n: "Hips|L2" for n in source})
    # 链整条一起进 —— 拆开等于劈断链
    assert {"Streamer_L_A0", "Streamer_L_A1"} <= set(report["newBones"])
    # 但同组的另一条链不许被拖进来
    assert "Deco_L_A0" not in report["newBones"], report["newBones"]
    assert report["strategies"]["Deco_L_A0"] == "source_parent"


# ==========================================================================
# 来自 test_structural_bone_groups.py

# ==========================================================================
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


# ==========================================================================
# 来自 test_five_states_and_geometry.py

# ==========================================================================
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


# ==========================================================================
# 来自 test_swing_category_geometry.py

# ==========================================================================
def test_anchor_decides_without_reading_the_name():
    """外语骨名 + 正确锚点 → 仍然判对；这正是按名字判做不到的。"""
    assert core.swing_category_by_geometry("Hips", siblings=6, fallback_name="スカート") == "skirt"
    assert core.swing_category_by_geometry("LeftShoulder", fallback_name="Bone_HemA01_L") == "sleeve"
    assert core.swing_category_by_geometry("Head", fallback_name="謎の飾り") == "ribbon"
    assert core.swing_category_by_geometry("LeftFoot", fallback_name="xxx") == "skirt"


def test_a_hem_must_be_a_ring():
    """原版一个锚点挂 4–8 片才算裙摆；只挂一两条的是围裙/尾巴/腰带。"""
    assert core.swing_category_by_geometry("Hips", siblings=6) == "skirt"
    assert core.swing_category_by_geometry("Hips", siblings=2) == "cloth"
    assert core.swing_category_by_geometry("Hips", siblings=None) == "skirt"   # 不给就不做这个判定


def test_chest_family_splits_by_direction():
    assert core.swing_category_by_geometry("Spine2", direction=(0, -0.9, 0)) == "cloth"   # 向下垂=披挂
    assert core.swing_category_by_geometry("Spine2", direction=(0, 0.1, 0.8)) == "ribbon"  # 朝前
    assert core.swing_category_by_geometry("Spine2", direction=(0.8, 0.1, -0.5)) == "ribbon"  # 朝外/后


def test_falls_back_to_the_name_when_geometry_is_missing():
    """锚点认不出、又没有方向时，词表总比什么都不判强。"""
    assert core.swing_category_by_geometry("SomeProp", fallback_name="LeftSkirt01") == "skirt"
    assert core.swing_category_by_geometry("", fallback_name="ribbon_tail") == "ribbon"


def test_spine_anchor_is_a_skirt_not_a_ribbon():
    """裙摆挂在哪节脊椎上是美术自由，锚点表把 Spine 也算进胯部一族。"""
    assert core.swing_category_by_geometry("Spine", siblings=5) == "skirt"



if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("装饰骨分类自检全过")
