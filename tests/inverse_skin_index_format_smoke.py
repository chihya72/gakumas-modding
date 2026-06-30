"""Smoke checks for inverse-skin index buffer selection.

This loads core.py directly so the test stays Blender-independent.
"""

import importlib.util
import json
import struct
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "gmi_core", ROOT / "gakumas_mi" / "core.py"
)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def test_inverse_skin_uses_r32_for_large_expanded_vertex_stream():
    vertex_count = 65537
    vertices = [(0.0, 0.0, 0.0)] * vertex_count
    normals = [(0.0, 1.0, 0.0)] * vertex_count
    tangents = [(1.0, 0.0, 0.0, 1.0)] * vertex_count
    uv0 = [(0.0, 0.0)] * vertex_count
    uv1 = [(0.0, 0.0)] * vertex_count
    colors = [(1.0, 1.0, 1.0, 1.0)] * vertex_count
    skin = [[(0, 0, 1.0)]] * vertex_count
    faces = [(0, 1, 2), (65534, 65535, 65536)]

    _, _, ib, draw_ranges, index_format = core._pack_inverse_skin_buffers(
        vertices, normals, tangents, uv0, uv1, colors, faces, skin,
        expected_indices=3,
    )

    assert index_format == "R32_UINT"
    assert len(ib) == len(faces) * 3 * 4
    assert draw_ranges == [{"start": 0, "count": 6, "material": 0}]


def test_inverse_skin_keeps_r16_for_small_meshes():
    vertices = [(0.0, 0.0, 0.0)] * 3
    normals = [(0.0, 1.0, 0.0)] * 3
    tangents = [(1.0, 0.0, 0.0, 1.0)] * 3
    uv0 = [(0.0, 0.0)] * 3
    uv1 = [(0.0, 0.0)] * 3
    colors = [(1.0, 1.0, 1.0, 1.0)] * 3
    skin = [[(0, 0, 1.0)]] * 3

    _, _, ib, draw_ranges, index_format = core._pack_inverse_skin_buffers(
        vertices, normals, tangents, uv0, uv1, colors, [(0, 1, 2)], skin,
        expected_indices=6,
    )

    assert index_format == "R16_UINT"
    assert len(ib) == 6 * 2
    assert draw_ranges == [{"start": 0, "count": 3, "material": 0}]


def test_inverse_skin_groups_draw_ranges_by_material():
    vertices = [(0.0, 0.0, 0.0)] * 6
    normals = [(0.0, 1.0, 0.0)] * 6
    tangents = [(1.0, 0.0, 0.0, 1.0)] * 6
    uv0 = [(0.0, 0.0)] * 6
    uv1 = [(0.0, 0.0)] * 6
    colors = [(1.0, 1.0, 1.0, 1.0)] * 6
    skin = [[(0, 0, 1.0)]] * 6
    faces = [(0, 1, 2), (3, 4, 5)]
    materials = [1, 1, 1, 4, 4, 4]

    _, _, _, draw_ranges, _ = core._pack_inverse_skin_buffers(
        vertices, normals, tangents, uv0, uv1, colors, faces, skin,
        expected_indices=6, materials=materials,
    )

    assert draw_ranges == [
        {"start": 0, "count": 3, "material": 1},
        {"start": 3, "count": 3, "material": 4},
    ]


if __name__ == "__main__":
    test_inverse_skin_uses_r32_for_large_expanded_vertex_stream()
    test_inverse_skin_keeps_r16_for_small_meshes()
    test_inverse_skin_groups_draw_ranges_by_material()
    print("inverse_skin_index_format_smoke OK")
