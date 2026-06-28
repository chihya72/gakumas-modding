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
    "gmi_core", ROOT / "blender_addon" / "gakumas_mi" / "core.py"
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


def test_inverse_skin_package_writes_alpha_blend_custom_shader():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        profile = tmp / "profile"
        (profile / "Buffers").mkdir(parents=True)
        (profile / "Buffers" / "InverseOperator.R32_FLOAT.buf").write_bytes(struct.pack("<12f", *([0.0] * 12)))
        (profile / "profile.json").write_text(json.dumps({
            "id": "test-profile",
            "target": {"actorId": "ttmr", "costumeId": "test"},
            "skinning": {"inverseSkin": {
                "sourceVertexCount": 6,
                "coefficientCount": 1,
                "inverseOperator": "Buffers/InverseOperator.R32_FLOAT.buf",
            }},
            "components": [{
                "id": "body",
                "ibHash": "deadbeef",
                "vertices": 6,
                "indices": 6,
                "mainFirstIndex": 0,
            }],
        }), encoding="utf-8")
        (profile / "drawcall_map.json").write_text(json.dumps({
            "components": {"body": {"passBindings": {
                "draw_000001": {"draw": 1, "vertexShader": "1111111111111111"}
            }}}
        }), encoding="utf-8")
        (profile / "texture_map.json").write_text(json.dumps({
            "textures": {"body.baseColor": {
                "slot": "ps-t0",
                "hash": "22222222",
                "file": "dummy.dds",
                "size": [2, 2],
            }}
        }), encoding="utf-8")
        base = tmp / "base.dds"
        core.write_rgba8_dds(base, 2, 2, bytes([
            255, 255, 255, 255, 255, 255, 255, 128,
            255, 255, 255, 0, 255, 255, 255, 255,
        ]), srgb=True)

        vertices = [(0.0, 0.0, 0.0)] * 6
        normals = [(0.0, 1.0, 0.0)] * 6
        tangents = [(1.0, 0.0, 0.0, 1.0)] * 6
        uv0 = [(0.0, 0.0)] * 6
        uv1 = [(0.0, 0.0)] * 6
        colors = [(1.0, 1.0, 1.0, 1.0)] * 6
        skin = [[(0, 0, 1.0)]] * 6
        faces = [(0, 1, 2), (3, 4, 5)]
        corrections = [((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0))]

        package = core.write_inverse_skin_package(
            profile, tmp / "out", "author.test.alpha", "Alpha Test", "Tester", "body",
            vertices, normals, tangents, uv0, uv1, colors, faces, skin, corrections,
            material_textures={"body.baseColor": str(base)},
            materials=[0, 0, 0, 1, 1, 1],
            alpha_modes={1: "ALPHA_BLEND"},
            alpha_cutoffs={1: 0.75},
        )

        ini = (package / "mod.ini").read_text(encoding="utf-8")
        assert "drawindexed = 3, 0, 0" in ini
        assert "run = CustomShaderAuthorTestAlphaInheritMask0" in ini
        assert "ResourceAuthorTestAlphaSceneDepth = copy oD" in ini
        assert "run = CustomShaderAuthorTestAlphaAlphaBlend0" in ini
        assert "[CustomShaderAuthorTestAlphaInheritMask0]" in ini
        assert "[CustomShaderAuthorTestAlphaAlphaBlend0]" in ini
        assert "vs = Shaders\\GMIInheritMaskA.hlsl" in ini
        assert "vs = Shaders\\GMIFinal.hlsl" in ini
        assert "depth_write_mask = zero" in ini
        assert "blend[1] = ADD ONE INV_SRC_ALPHA" in ini
        assert "ps-t1 = ResourceAuthorTestAlphaPackedmask" in ini
        assert "ps-t4 = ResourceAuthorTestAlphaShadecolor" in ini
        assert "drawindexed = 3, 3, 0" in ini
        assert (package / "Shaders" / "GMIInheritMaskA.hlsl").is_file()
        alpha_shader = package / "Shaders" / "GMIFinal.hlsl"
        assert alpha_shader.is_file()
        alpha_shader_text = alpha_shader.read_text(encoding="utf-8")
        assert "out float4 o0:SV_Target0, out float4 o1:SV_Target1" in alpha_shader_text
        assert "clip(base.a-GMI_ALPHA_FLOOR);" in alpha_shader_text
        assert "o1=float4(col*base.a, base.a);" in alpha_shader_text
        assert (package / "Textures" / "Body.PackedMask.Neutral.dds").is_file()
        assert (package / "Textures" / "Body.ShadeColor.Neutral.dds").is_file()


if __name__ == "__main__":
    test_inverse_skin_uses_r32_for_large_expanded_vertex_stream()
    test_inverse_skin_keeps_r16_for_small_meshes()
    test_inverse_skin_groups_draw_ranges_by_material()
    test_inverse_skin_package_writes_alpha_blend_custom_shader()
    print("inverse_skin_index_format_smoke OK")
