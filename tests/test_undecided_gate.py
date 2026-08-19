# -*- coding: utf-8 -*-
"""闸门 9（§8.1 第 9 条）：`undecided` 不许静默进导出。

两个方向都要证：有未决定的包必须被拦；决定完的包不许误报。
外加第三件：显式放行之后必须留痕 —— 不然放行过的包和"逐组决定过"的包长得一模一样。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def _rows(*pairs):
    return [(name, core.row_state(target, strategy))
            for name, target, strategy in pairs]


def test_undecided_rows_block_the_export():
    rows = _rows(
        ("Skirt_L_A0 等 30 根", "", "integrate"),   # helper，已决定
        ("Deco_A0", "", "auto"),                    # 没目标没策略 = undecided
        ("Hips", "Hips", "auto"),                   # direct
    )
    error = core.undecided_export_error(rows)
    assert error, "有未决定的组却放行了"
    assert "Deco_A0" in error, "报错必须点名是哪一组，别让作者自己找"
    assert "允许未决定的骨导出" in error, "必须给出显式放行这条出路"
    # 已决定的组不该被点名
    assert "Hips" not in error and "Skirt_L_A0" not in error


def test_decided_rows_do_not_false_alarm():
    rows = _rows(
        ("Hips", "Hips", "auto"),
        ("Skirt_L_A0 等 30 根", "", "integrate"),
        ("Lace_A0", "", "follow_skirt"),
        ("Static_A0", "", "rigid"),
        ("Old_A0", "", "bake"),
    )
    assert core.undecided_export_error(rows) is None


def test_explicit_opt_out_passes_but_leaves_a_record():
    rows = _rows(("Deco_A0", "", "auto"), ("Hips", "Hips", "auto"))
    assert core.undecided_export_error(rows, allow=True) is None

    record = core.undecided_export_record(rows, allow=True)
    assert record == {"count": 1, "allowed": True, "bones": ["Deco_A0"]}

    # 没放行时也留痕，值是 allowed=False —— sidecar 里永远看得出这一版是哪种
    blocked = core.undecided_export_record(rows, allow=False)
    assert blocked["allowed"] is False and blocked["count"] == 1


def test_clean_package_records_zero():
    rows = _rows(("Hips", "Hips", "auto"))
    assert core.undecided_export_record(rows) == {
        "count": 0, "allowed": False, "bones": []}


def test_long_lists_are_truncated_but_counted():
    rows = _rows(*[(f"Deco_{i}", "", "auto") for i in range(30)])
    error = core.undecided_export_error(rows, limit=5)
    assert error.startswith("30 组骨还没决定")
    assert "…" in error
    assert "Deco_6" not in error


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("闸门 9 自检全过")
