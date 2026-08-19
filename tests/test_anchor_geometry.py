# -*- coding: utf-8 -*-
"""链根扛着几何时要让它自己摆，以及"整条链没有几何"要拦下来。

实测的坏形状：`Chain_R_A0` 66 个带权顶点全在链根、`Chain_R_Aend` 一个都没有。
链根按原版是惰性锚（spring/mass 近 0，自身不摆），照拓扑出参数就是
「摆的骨没有几何、有几何的骨不摆」—— 画面纹丝不动，而 swingPrepared /
modBonesRegistered 全绿，闸门一条都不报。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def _records(*names):
    return [{"name": n, "localPosition": [0.0, -0.05, 0.0], "length": 0.05} for n in names]


def _build(names, weights, parents, dominant=None, swing_anchor=True):
    """`weights` = 任意权重（判空链），`dominant` = 主导顶点（判几何归属）。默认两者一致。"""
    return core.build_source_extra_bones(
        _records(*names), list(names), parent_by_name=parents,
        body_remap={"Hips": "Hips"}, weight_by_name=weights,
        dominant_by_name=weights if dominant is None else dominant,
        swing_anchor_geometry=swing_anchor,
        categories={n: "ribbon" for n in names})


def test_anchor_downgrade_is_off_by_default():
    """默认只报不改 —— 让链根自己摆是在替作者决定物理。

    实机验过：开了之后腰侧挂坠 / 腰包 / 胸前蝴蝶结全晃起来，而作者要的是它们别动。
    """
    names = ["Chain_R_A0", "Chain_R_Aend"]
    parents = {"Chain_R_A0": "Hips", "Chain_R_Aend": "Chain_R_A0"}
    report = _build(names, {"Chain_R_A0": 0.9}, parents, swing_anchor=False)
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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("链根几何自检全过")
