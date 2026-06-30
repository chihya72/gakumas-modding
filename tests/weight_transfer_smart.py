"""回归：智能转权（法线闸门 + Laplacian inpaint）胜过朴素最近表面。

合成「薄缝跨面」场景：目标面在语义上属于 A 面（法线同向），但欧氏最近却是贴得更近、
法线相反的 B 面。朴素最近 → 抄成 B 的骨（错）；智能转权靠法线闸门拒掉 B，再 inpaint
出 A 的骨（对）。另有一簇远离所有 source 的「塔尖」顶点，验证 inpaint 能把权重沿网格
补进去而不是留零。

按文件路径加载模块（绕过 import bpy 的包 __init__），可在 CI 无 Blender 跑。
"""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "gmi_weight_transfer", ROOT / "gakumas_mi" / "weight_transfer.py"
)
wt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wt)


def _plane(z, g=11):
    """g×g 栅格平面，返回 (verts, faces, base_index_grid)。"""
    xs = np.linspace(0.0, 1.0, g)
    verts, grid = [], np.empty((g, g), dtype=np.int64)
    for i in range(g):
        for j in range(g):
            grid[i, j] = len(verts)
            verts.append((xs[i], xs[j], z))
    faces = []
    for i in range(g - 1):
        for j in range(g - 1):
            a, b, c, d = grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]
            faces.append((a, b, c))
            faces.append((a, c, d))
    return np.array(verts, dtype=np.float64), faces, grid


def _build_case():
    g = 11
    # --- source：A 面 (z=0, 法线+z, bone0)；B 面 (z=0.01, 法线-z, bone1) ---
    a_pos, _, _ = _plane(0.0, g)
    b_pos, _, _ = _plane(0.01, g)
    source_pos = np.concatenate([a_pos, b_pos])
    source_nrm = np.concatenate([
        np.tile([0, 0, 1.0], (len(a_pos), 1)),
        np.tile([0, 0, -1.0], (len(b_pos), 1)),
    ])
    source_weights = np.concatenate([
        np.tile([1.0, 0.0], (len(a_pos), 1)),   # A -> bone0
        np.tile([0.0, 1.0], (len(b_pos), 1)),   # B -> bone1
    ])

    # --- target：平面在 z=0.008（离 B=0.002 更近、离 A=0.008，但法线同 A）---
    t_pos, t_faces, t_grid = _plane(0.008, g)
    t_nrm = np.tile([0, 0, 1.0], (len(t_pos), 1)).astype(np.float64)
    plane_count = len(t_pos)

    # --- 塔尖：5 个 z=0.6 的远顶点，各与平面顶点连边（远离所有 source → 需 inpaint）---
    t_pos = list(map(tuple, t_pos))
    t_nrm = list(map(tuple, t_nrm))
    tower_idx = []
    for k, (i, j) in enumerate([(2, 2), (8, 8), (5, 5), (2, 8), (8, 2)]):
        spike = len(t_pos)
        x, y, _ = t_pos[t_grid[i, j]]
        t_pos.append((x, y, 0.6))
        t_nrm.append((0.0, 0.0, 1.0))
        tower_idx.append(spike)
        # 用一个三角把塔尖挂到平面（建立图上的边）
        t_faces.append((spike, int(t_grid[i, j]), int(t_grid[i, j + 1])))

    return {
        "target_pos": np.array(t_pos), "target_nrm": np.array(t_nrm),
        "faces": np.array(t_faces, dtype=np.int64),
        "source_pos": source_pos, "source_nrm": source_nrm,
        "source_weights": source_weights,
        "plane_count": plane_count, "tower_idx": tower_idx,
    }


def test_naive_nearest_picks_wrong_bone():
    """基线：不带法线闸门的纯最近，会把属于 A 的目标面错抄成 B 的骨。"""
    c = _build_case()
    idx, _ = wt.chunked_nearest(c["target_pos"][:c["plane_count"]], c["source_pos"])
    naive = c["source_weights"][idx]
    dominant = np.argmax(naive, axis=1)
    assert (dominant == 1).mean() > 0.9, "薄缝场景下朴素最近应当大面积抄成 B(bone1)"


def test_smart_transfer_fixes_cross_gap_and_inpaints():
    c = _build_case()
    res = wt.smart_weight_transfer(
        c["target_pos"], c["target_nrm"], c["faces"],
        c["source_pos"], c["source_nrm"], c["source_weights"],
        max_distance=0.02, normal_cos_threshold=0.0,
    )
    w = res["weights"]
    plane = slice(0, c["plane_count"])

    # 1) 平面顶点应当被法线闸门救回到 A(bone0)
    plane_dom = np.argmax(w[plane], axis=1)
    assert (plane_dom == 0).mean() > 0.95, "法线闸门应把目标面转回 A(bone0)"

    # 2) 法线闸门确实把更近的 B 改写成了 A
    assert res["stats"]["normalRedirected"] > 0

    # 3) 塔尖（远离所有 source）应被 inpaint 成 A，而不是留零
    for ti in c["tower_idx"]:
        assert abs(w[ti].sum() - 1.0) < 1e-6, "塔尖顶点必须有归一权重（inpaint 补全）"
        assert np.argmax(w[ti]) == 0, "塔尖应沿网格从邻居 inpaint 出 A(bone0)"

    # 4) 全局：无零权重、每行和为 1、不超过 4 个影响
    sums = w.sum(axis=1)
    assert np.allclose(sums, 1.0, atol=1e-6)
    assert (w > 0).sum(axis=1).max() <= 4


if __name__ == "__main__":
    test_naive_nearest_picks_wrong_bone()
    test_smart_transfer_fixes_cross_gap_and_inpaints()
    print("OK: smart weight transfer beats naive nearest on thin-gap + inpaints holes")
