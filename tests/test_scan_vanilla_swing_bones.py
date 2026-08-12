# -*- coding: utf-8 -*-
"""`--limit N` 的局部样本不保证四档齐全 —— 这条回归过两次（KeyError: 'cloth'）。"""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "scan_vanilla_swing_bones", ROOT / "tools" / "scan_vanilla_swing_bones.py")
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)


def _role_stats():
    quantiles = {"median": 0.1, "p10": 0.0, "p90": 0.2, "min": 0.0, "max": 0.2}
    entry = {key: dict(quantiles) for key in scan.PLUGIN_SCALARS + ("colliderRadius",)}
    entry["colliderRadiusSub"] = dict(quantiles)
    entry.update({key: {"mode": 0, "counts": {}} for key in
                  ("useWindGlobalForce", "useLimit", "colliderType", "dynamicType")})
    entry.update({axis: {"mode": [0, 0]} for axis in ("limitX", "limitY", "limitZ")})
    entry["samples"] = 3
    return entry


def _summary(*categories):
    return {
        "presets": {name: {role: _role_stats() for role in ("root", "mid", "tip")}
                    for name in categories},
        "chainUsage": {name: {"useChain": True, "chainRatio": 0.9} for name in categories},
    }


def test_partial_scan_skips_missing_categories():
    out = scan.build_plugin_presets(_summary("skirt"))
    assert sorted(out["categories"]) == ["skirt"]


def test_full_scan_keeps_all_plugin_categories():
    out = scan.build_plugin_presets(_summary(*scan.PLUGIN_CATEGORIES))
    assert sorted(out["categories"]) == sorted(scan.PLUGIN_CATEGORIES)
    assert all(len(item["roles"]) == 3 for item in out["categories"].values())
