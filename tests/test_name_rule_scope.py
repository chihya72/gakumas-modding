# -*- coding: utf-8 -*-
"""内置的名字规则不许泄漏到同组的邻居身上（左右不对称的根因）。

实测：`Lace_R_*` 与 `Leg_pendant_R_*` 都挂 `RightLeg`、都两节，被结构分组并成一组，
于是 lace 的 `follow_skirt` 把腿上的挂坠也送去蹭裙摆末端摇物骨，实机满天飞；
而左边的挂坠是三节、没跟 lace 并组，走的是刚性。同一件东西左右两种结果。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


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


def test_author_override_still_applies_to_the_whole_group():
    """作者覆盖是显式意图，整组生效 —— 这条不能被上面的收窄改掉。"""
    report = _run(overrides={"Lace": "follow_nearest"})
    assert report["strategies"]["Leg_pendant_R_A0"] == "override_nearest"
    assert report["strategies"]["Lace_R_A0"] == "override_nearest"


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
    assert set(report["newBones"]) == set(source), report["newBones"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("名字规则作用域自检全过")
