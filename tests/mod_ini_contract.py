"""P0 回归：逆解模组 mod.ini 生成契约（0.5.1 多 pass + 原生 co 透明路径）。

用一份完全合成的最小 profile（不依赖真实游戏数据）驱动 core.write_inverse_skin_package，
锁定 mod.ini 关键结构，防止运行时替换链/原生 co 路径悄悄回退。CI 无 Blender 可跑。

注：0.6.x 的自建镂空(ALPHA_CLIP)/半透明(ALPHA_BLEND)路径已整体移除，只保留把第二材质段
交给游戏原生 m_bdyco draw 的 NATIVE_CO 一条路径。
"""

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def _write_synthetic_profile(profile_dir: Path, native_section=False):
    component = {
        "id": "body",
        "ibHash": "4d5dfe7b",
        "indices": 12,
        "mainFirstIndex": 6,
        "tailFirstIndices": [9],
    }
    if native_section:
        component["materialSections"] = [
            {"id": "body.section0", "role": "main", "firstIndex": 6, "indexCount": 12},
            {"id": "body.section1", "role": "secondary", "firstIndex": 9, "indexCount": 3},
        ]
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
        "components": [component],
    }
    (profile_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    body_drawcalls = {
        "passBindings": {
            "p0": {"draw": 1, "vertexShader": "aaaa1111"},
            "p1": {"draw": 2, "vertexShader": "bbbb2222"},
        }
    }
    if native_section:
        body_drawcalls["sectionBindings"] = {
            "body.section1": {
                "role": "secondary",
                "firstIndex": 9,
                "indexCount": 3,
                "representativeDraw": 3,
                "passBindings": {
                    "draw_000003": {"draw": 3, "vertexShader": "cccc3333", "pixelShader": "dddd4444"}
                },
            }
        }
    drawcalls = {
        "components": {
            "body": body_drawcalls
        }
    }
    (profile_dir / "drawcall_map.json").write_text(json.dumps(drawcalls), encoding="utf-8")
    textures = {}
    if native_section:
        textures = {
            "body.section1.baseColor": {"slot": "ps-t0", "hash": "base0001"},
            "body.section1.packedMask": {"slot": "ps-t1", "hash": "mask0001"},
            "body.section1.shadeColor": {"slot": "ps-t2", "hash": "shade001"},
        }
    (profile_dir / "texture_map.json").write_text(json.dumps({"textures": textures}), encoding="utf-8")
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


def _build(tmp, native_section=False, **kwargs):
    profile_dir = Path(tmp) / "profile"
    profile_dir.mkdir()
    _write_synthetic_profile(profile_dir, native_section=native_section)
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


def test_native_co_ini_contract():
    """原生 co：透明材质段挪到 secondary material section，继承游戏 co shader/state。"""
    with tempfile.TemporaryDirectory() as tmp:
        opacity = Path(tmp) / "opacity.dds"
        core.write_solid_rgba8_dds(opacity, (255, 255, 255, 255), size=4, srgb=False)
        ini, pkg = _build(
            tmp,
            native_section=True,
            alpha_modes={1: "NATIVE_CO"},
            opacity_texture=str(opacity),
        )

        # 主 body 只画不透明材质段，NATIVE_CO 材质段不进入主 G-buffer 自建透明路径。
        main_sec = ini[ini.index("[TextureOverrideTestModBody]"):]
        main_sec = main_sec[:main_sec.index("\n[TextureOverrideTestModBodyNativeCo]")]
        assert "drawindexed = 3, 0, 0" in main_sec, main_sec
        assert "drawindexed = 3, 3, 0" not in main_sec, main_sec
        assert "AlphaClip" not in ini and "AlphaBlend" not in ini and "InheritMask" not in ini

        # co 段独立 hook secondary section，并在该 draw 上重新取当前 vb0 做 compute。
        assert "[TextureOverrideTestModBodyNativeCo]" in ini, ini
        native_sec = ini[ini.index("[TextureOverrideTestModBodyNativeCo]"):]
        native_sec = native_sec[:native_sec.index("\n[", 1)] if "\n[" in native_sec[1:] else native_sec
        assert "match_first_index = 9" in native_sec, native_sec
        assert "ResourceTestModPosedVB = copy vb0" in native_sec, native_sec
        assert "run = CustomShaderTestModRecoverMatrices" in native_sec, native_sec
        assert "run = CustomShaderTestModSkinCustom" in native_sec, native_sec
        assert "drawindexed = 3, 3, 0" in native_sec, native_sec
        assert "handling = skip" in native_sec, native_sec

        # 贴图槽来自 body.section1；shadeColor 在本 synthetic co section 中是 ps-t2。
        assert "ps-t0 = ResourceTestModOpacityBaseColor" in native_sec, native_sec
        assert "ps-t1 = ResourceTestModPackedmask" in native_sec, native_sec
        assert "ps-t2 = ResourceTestModShadecolor" in native_sec, native_sec

        # co section 自己的 VS 也要挂 checktextureoverride；native co 接管后不再生成尾部 skip。
        assert ini.count("checktextureoverride = ib") == 3, ini
        assert "[TextureOverrideTestModBodyTail0]" not in ini, ini

        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["nativeCoRanges"] == [{"start": 3, "count": 3, "material": 1, "mode": "NATIVE_CO"}]
        assert manifest["nativeCoSection"]["id"] == "body.section1"
    print("native_co_ini_contract OK")


def test_native_co_without_t0_rejected():
    """原生 co 材质但没给 t0（基础色/透明图）→ 必须报错，不能静默导出。"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _build(tmp, native_section=True, alpha_modes={1: "NATIVE_CO"})
        except ValueError:
            pass
        else:
            raise AssertionError("原生 co 材质缺 t0 应导出失败")
    print("native_co_without_t0_rejected OK")


def test_legacy_alpha_modes_fall_back_to_opaque():
    """旧工程里的 ALPHA_CLIP/ALPHA_BLEND 值已废弃 → 当成不透明，不再生成自建透明 pass。"""
    with tempfile.TemporaryDirectory() as tmp:
        ini, _ = _build(tmp, alpha_modes={1: "ALPHA_BLEND"})
        # 旧值被忽略：材质 1 仍按不透明 drawindexed 画，没有任何透明/co override。
        assert "drawindexed = 3, 3, 0" in ini, ini
        assert "AlphaClip" not in ini and "AlphaBlend" not in ini and "InheritMask" not in ini
        assert "NativeCo" not in ini, ini
    print("legacy_alpha_modes_fall_back_to_opaque OK")


if __name__ == "__main__":
    test_opaque_ini_contract()
    test_native_co_ini_contract()
    test_native_co_without_t0_rejected()
    test_legacy_alpha_modes_fall_back_to_opaque()
    print("ALL mod_ini_contract OK")
