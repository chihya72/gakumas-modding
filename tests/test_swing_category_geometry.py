"""按几何判部件类型（锚点 / 同锚点条数 / 垂向），名字只作兜底。

按名字判的硬伤：只对恰好用本作命名习惯的源有效。原神 rip 的裙摆叫 `Bone_HemA01_L`、
MMD 叫 `スカート`，词表两个都不认 → 整条链拿不到物理。判据与 SDK 侧 ChainClassifier 同源
（381 套原版量过；原版 1537 条链的锚点分布 Pelvis 758 / Spine2 86 / Spine 82 / UpLeg_H 80）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


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
