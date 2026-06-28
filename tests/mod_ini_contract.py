"""P0 回归：逆解模组 mod.ini 生成契约（0.5.1 多 pass + 0.6.0 透明路径）。

用一份完全合成的最小 profile（不依赖真实游戏数据）驱动 core.write_inverse_skin_package，
锁定 mod.ini 关键结构，防止运行时替换链/透明路径悄悄回退。CI 无 Blender 可跑。
"""

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def _write_synthetic_profile(profile_dir: Path):
    profile = {
        "schemaVersion": 1,
        "id": "test-profile",
        "status": "synthetic",
        "target": {"actorId": "test", "costumeId": "cstm-0000"},
        "skinning": {
            "inverseSkin": {
                "sourceVertexCount": 4,
                "coefficientCount": 8,
                "inverseOperator": "Buffers/InverseOperator.R32_FLOAT.buf",
            }
        },
        "components": [
            {
                "id": "body",
                "ibHash": "4d5dfe7b",
                "indices": 12,
                "mainFirstIndex": 6,
                "tailFirstIndices": [9],
            }
        ],
    }
    (profile_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    drawcalls = {
        "components": {
            "body": {
                "passBindings": {
                    "p0": {"draw": 1, "vertexShader": "aaaa1111"},
                    "p1": {"draw": 2, "vertexShader": "bbbb2222"},
                }
            }
        }
    }
    (profile_dir / "drawcall_map.json").write_text(json.dumps(drawcalls), encoding="utf-8")
    (profile_dir / "texture_map.json").write_text(json.dumps({"textures": {}}), encoding="utf-8")
    (profile_dir / "Buffers").mkdir(exist_ok=True)
    (profile_dir / "Buffers" / "InverseOperator.R32_FLOAT.buf").write_bytes(b"\x00" * 16)


def _mesh():
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    normals = [(0.0, 0.0, 1.0)] * 4
    tangents = [(1.0, 0.0, 0.0, 1.0)] * 4
    uv0 = [(0.25, 0.0)] * 4
    uv1 = [(0.5, 0.5)] * 4
    colors = [(1.0, 1.0, 1.0, 1.0)] * 4
    faces = [(0, 1, 2), (2, 3, 0)]
    skin = [[(i, 0, 1.0)] for i in range(4)]
    materials = [0, 0, 1, 1]   # face0→mat0, face1→mat1
    return vertices, normals, tangents, uv0, uv1, colors, faces, skin, materials


def _build(tmp, **kwargs):
    profile_dir = Path(tmp) / "profile"
    profile_dir.mkdir()
    _write_synthetic_profile(profile_dir)
    out = Path(tmp) / "out"
    v, n, t, uv0, uv1, c, faces, skin, materials = _mesh()
    pkg = core.write_inverse_skin_package(
        profile_dir, out, "test.mod", "Test", "Author", "body",
        v, n, t, uv0, uv1, c, faces, skin, corrections=[],
        materials=materials, **kwargs,
    )
    return (pkg / "mod.ini").read_text(encoding="utf-8"), pkg


def test_opaque_ini_contract():
    with tempfile.TemporaryDirectory() as tmp:
        ini, pkg = _build(tmp)

        # 0.5.1 全 VS 触发：每个 VS 一个 ShaderOverride + checktextureoverride = ib
        assert ini.count("checktextureoverride = ib") == 2, ini
        assert "hash = aaaa1111" in ini and "hash = bbbb2222" in ini

        # 主 TextureOverride：IB hash + 主体段偏移 + 跳过原 draw
        assert "hash = 4d5dfe7b" in ini
        assert "match_first_index = 6" in ini       # mainFirstIndex
        assert "handling = skip" in ini

        # 0.5.1 每材质一段 drawindexed（2 个不透明材质区间）
        assert "drawindexed = 3, 0, 0" in ini, ini
        assert "drawindexed = 3, 3, 0" in ini, ini

        # 0.5.1 尾部段跳过
        assert "match_first_index = 9" in ini

        # compute dispatch：恢复矩阵=coefficientCount，蒙皮=ceil(v/64)
        assert "dispatch = 8, 1, 1" in ini          # RecoverMatrices
        assert "dispatch = 1, 1, 1" in ini          # SkinCustom (4 顶点)

        # IB 资源格式
        assert "format = DXGI_FORMAT_R16_UINT" in ini

        # 不透明路径不应出现任何透明段
        assert "InheritMask" not in ini and "AlphaBlend" not in ini and "GMIFinal" not in ini

        # 着色器按本配置档替换了顶点/系数数
        recover = (pkg / "Shaders" / "RecoverMatricesCS.hlsl").read_text(encoding="utf-8")
        assert "SOURCE_VERTEX_COUNT 4" in recover and "COEFFICIENT_COUNT 8" in recover
        skin = (pkg / "Shaders" / "SkinCustomCS.hlsl").read_text(encoding="utf-8")
        assert "TARGET_VERTEX_COUNT 4" in skin
    print("opaque_ini_contract OK")


def test_transparent_ini_contract():
    with tempfile.TemporaryDirectory() as tmp:
        opacity = Path(tmp) / "opacity.dds"
        core.write_solid_rgba8_dds(opacity, (255, 255, 255, 128), size=4, srgb=False)
        ini, pkg = _build(tmp, alpha_modes={1: "ALPHA_BLEND"}, opacity_texture=str(opacity))

        # 材质 1 走透明路径 → 拆出 InheritMask + AlphaBlend，主体里 run 这两段
        assert "run = CustomShaderTestModInheritMask0" in ini, ini
        assert "run = CustomShaderTestModAlphaBlend0" in ini, ini
        assert "SceneDepth = copy oD" in ini

        # 0.6.0 透明 pass 关键状态：反向 Z + 不写深度 + 预乘 alpha
        assert "depth_func = greater_equal" in ini
        assert "depth_write_mask = zero" in ini
        assert "blend[1] = ADD ONE INV_SRC_ALPHA" in ini
        assert "Shaders\\GMIFinal.hlsl" in ini and "Shaders\\GMIInheritMaskA.hlsl" in ini

        # 材质 0 仍走不透明 drawindexed；材质 1 的段移到透明 pass
        assert "drawindexed = 3, 0, 0" in ini       # opaque mat0
        assert "drawindexed = 3, 3, 0" in ini       # mat1 in transparent pass

        # 透明 shader 实际写入包内
        assert (pkg / "Shaders" / "GMIFinal.hlsl").is_file()
        assert (pkg / "Shaders" / "GMIInheritMaskA.hlsl").is_file()
    print("transparent_ini_contract OK")


def test_transparent_without_t0_rejected():
    """透明材质但没给 t0（基础色/透明图）→ 必须报错，不能静默导出。"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _build(tmp, alpha_modes={1: "ALPHA_BLEND"})
        except ValueError:
            pass
        else:
            raise AssertionError("透明材质缺 t0 应导出失败")
    print("transparent_without_t0_rejected OK")


if __name__ == "__main__":
    test_opaque_ini_contract()
    test_transparent_ini_contract()
    test_transparent_without_t0_rejected()
    print("ALL mod_ini_contract OK")
