"""P0 回归：逆解导出 buffer 打包契约 + 0.5.30 类 UV/COLOR/NaN 防错。

直接按文件加载 core.py（绕过 import bpy 的包 __init__），因此可在 CI 无 Blender 跑。
锁定 _pack_inverse_skin_buffers 与 _validate_export_uv 的行为，防止历史踩过的
导出 bug（首次导出 UV/COLOR 错乱、NaN、fp16 溢出、材质串 draw）回退。
"""

import importlib.util
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

BIND_FMT = "<3f3f4f4I4I4f"   # pos3 normal3 tangent4 bones4 corr4 weights4
VB1_FMT = "<4B4e"            # rgba8 + (u0, 1-v0, u1, 1-v1) fp16


def _approx(a, b, tol=1e-3):
    return abs(a - b) <= tol


# ---- 一份最小可控网格：4 顶点 / 2 三角 / 2 材质 ---------------------------------
def _mesh():
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    normals = [(0.0, 0.0, 1.0)] * 4
    tangents = [(1.0, 0.0, 0.0, 1.0)] * 4
    uv0 = [(0.25, 0.0)] * 4        # 存储应为 (0.25, 1-0=1.0)，fp16 精确可表示
    uv1 = [(0.5, 0.5)] * 4         # 存储应为 (0.5, 0.5)
    colors = [(1.0, 0.0, 0.0, 1.0)] * 4
    faces = [(0, 1, 2), (2, 3, 0)]
    # 顶点权重：第 0 个顶点用未归一化权重 [1,3] → 应归一化为 [0.25,0.75]
    skin = [
        [(3, 0, 1.0), (4, 0, 3.0)],
        [(5, 0, 1.0)],
        [(6, 0, 1.0)],
        [(7, 0, 1.0)],
    ]
    materials = [0, 0, 1, 1]       # face0→材质0, face1(face[0]=v2)→材质1
    return vertices, normals, tangents, uv0, uv1, colors, faces, skin, materials


def test_roundtrip_and_layout():
    v, n, t, uv0, uv1, colors, faces, skin, materials = _mesh()
    bind, vb1, ib, draw_ranges, index_format = core._pack_inverse_skin_buffers(
        v, n, t, uv0, uv1, colors, faces, skin, expected_indices=8, materials=materials
    )

    # bind/vb1 stride 与游戏一致
    assert len(bind) == 4 * struct.calcsize(BIND_FMT), len(bind)
    assert len(vb1) == 4 * 12, ("VB1 stride 必须 12", len(vb1))

    # 顶点 0：位置回读 + 权重归一化 + 骨骼索引
    b0 = struct.unpack_from(BIND_FMT, bind, 0)
    assert b0[0:3] == (0.0, 0.0, 0.0)
    bones = b0[10:14]
    weights = b0[18:22]
    assert bones[:2] == (3, 4) and bones[2:] == (0, 0), bones
    assert _approx(weights[0], 0.25) and _approx(weights[1], 0.75), weights
    assert _approx(weights[2], 0.0) and _approx(weights[3], 0.0), weights

    # VB1 顶点 0：颜色 + UV（含 v = 1-v 翻转）
    r, g, bch, a, su0, sv0, su1, sv1 = struct.unpack_from(VB1_FMT, vb1, 0)
    assert (r, g, bch, a) == (255, 0, 0, 255), (r, g, bch, a)
    assert _approx(su0, 0.25) and _approx(sv0, 1.0), (su0, sv0)   # 1 - 0.0
    assert _approx(su1, 0.5) and _approx(sv1, 0.5), (su1, sv1)

    # 材质分组 → 连续 draw_ranges
    assert index_format == "R16_UINT", index_format
    assert [r["material"] for r in draw_ranges] == [0, 1], draw_ranges
    assert draw_ranges[0] == {"start": 0, "count": 3, "material": 0}, draw_ranges[0]
    assert draw_ranges[1] == {"start": 3, "count": 3, "material": 1}, draw_ranges[1]

    # IB：face0 后接 face1，再补零到 expected_indices=8
    idx = list(struct.unpack(f"<{len(ib)//2}H", ib))
    assert idx == [0, 1, 2, 2, 3, 0, 0, 0], idx

    print("roundtrip_and_layout OK")


def test_nan_color_is_safe():
    """0.5.30：COLOR 转 0-255 时 NaN/Inf 不得崩溃，落为 0。"""
    v, n, t, uv0, uv1, _c, faces, skin, materials = _mesh()
    colors = [(float("nan"), float("inf"), 0.5, 1.0)] * 4
    bind, vb1, ib, _r, _f = core._pack_inverse_skin_buffers(
        v, n, t, uv0, uv1, colors, faces, skin, expected_indices=6, materials=materials
    )
    r, g, bch, a, *_ = struct.unpack_from(VB1_FMT, vb1, 0)
    assert r == 0 and g == 255, (r, g)        # NaN→0；inf 走 >=1.0 分支→255
    assert bch == round(0.5 * 255.0) and a == 255, (bch, a)
    print("nan_color_is_safe OK")


def test_invalid_uv_rejected():
    """0.5.30：非法 UV 直接停止导出，而非静默写 fallback。"""
    for bad in (float("nan"), float("inf"), 9.0, -9.0):
        try:
            core._validate_export_uv(bad, "UV0.u")
        except ValueError:
            pass
        else:
            raise AssertionError(f"非法 UV {bad} 应该被拒绝")
    # 合法值放行
    assert _approx(core._validate_export_uv(0.5, "x"), 0.5)
    assert _approx(core._validate_export_uv(-2.0, "x"), -2.0)

    # 端到端：mesh 里塞 NaN UV → 打包应抛错
    v, n, t, _uv0, uv1, c, faces, skin, materials = _mesh()
    uv0 = [(float("nan"), 0.0)] * 4
    try:
        core._pack_inverse_skin_buffers(v, n, t, uv0, uv1, c, faces, skin, 6, materials)
    except ValueError:
        pass
    else:
        raise AssertionError("含 NaN UV 的网格应导出失败")
    print("invalid_uv_rejected OK")


def test_structural_guards():
    v, n, t, uv0, uv1, c, faces, skin, materials = _mesh()
    # 非三角面
    try:
        core._pack_inverse_skin_buffers(v, n, t, uv0, uv1, c, [(0, 1, 2, 3)], skin, 6, materials)
    except ValueError:
        pass
    else:
        raise AssertionError("非三角面应被拒绝")
    # 索引越界
    try:
        core._pack_inverse_skin_buffers(v, n, t, uv0, uv1, c, [(0, 1, 99)], skin, 6, materials)
    except ValueError:
        pass
    else:
        raise AssertionError("越界索引应被拒绝")
    # 权重全 0
    bad_skin = [[(0, 0, 0.0)], [(1, 0, 1.0)], [(2, 0, 1.0)], [(3, 0, 1.0)]]
    try:
        core._pack_inverse_skin_buffers(v, n, t, uv0, uv1, c, faces, bad_skin, 6, materials)
    except ValueError:
        pass
    else:
        raise AssertionError("权重总和为 0 应被拒绝")
    print("structural_guards OK")


def test_safe_half_clamps_fp16():
    assert core._safe_half(1e9) == core._FP16_MAX
    assert core._safe_half(-1e9) == -core._FP16_MAX
    assert core._safe_half(float("nan")) == 0.0
    assert _approx(core._safe_half(0.5), 0.5)
    print("safe_half_clamps_fp16 OK")


if __name__ == "__main__":
    test_roundtrip_and_layout()
    test_nan_color_is_safe()
    test_invalid_uv_rejected()
    test_structural_guards()
    test_safe_half_clamps_fp16()
    print("ALL export_buffers_regression OK")
