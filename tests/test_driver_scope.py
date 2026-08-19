"""原版布料驱动器的**作用域**：只装在作者点名的那几根骨上（§14 的"全局类别泄漏"）。

以前导出器收的是"类别集合"：作者在表单一行上选了裙，全模型每一根 skirt 类别的新骨都跟着改走
驱动器 —— 他点的是一条链，拿到的是整件衣服。现在按骨名限定（一行=一组=一条链）。

另一半是"选了驱动器但那个类别没有驱动器"这种组合：运行时只实现三类，ribbon 落进去就是
既没驱动器也没摇物的哑骨，所以 UI 标红、导出拦下。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

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
