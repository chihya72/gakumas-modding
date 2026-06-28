import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "gakumas_mi" / "core.py"


def load_core():
    spec = importlib.util.spec_from_file_location("gakumas_mi_core", CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_resource(root, draw, binding, resource_hash, vs, ps, byte_width):
    stem = f"{draw:06d}-{binding}={resource_hash}-vs={vs}-ps={ps}"
    (root / f"{stem}.buf").write_bytes(bytes(byte_width))
    (root / f"{stem}.dsc").write_text(
        f'type=Buffer byte_width={byte_width} usage="DEFAULT" bind_flags="vertex_buffer" '
        "cpu_access_flags=0 misc_flags=0 stride=0\n",
        encoding="utf-8",
    )


def test_extract_frame_profile():
    core = load_core()
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        capture = base / "FrameAnalysis-2026-06-22-123456"
        output = base / "generated-profile"
        capture.mkdir()

        log = "\n".join([
            "000010 VSSetShader(hash=aaaaaaaaaaaaaaaa)",
            "000010 PSSetShader(hash=bbbbbbbbbbbbbbbb)",
            "000010 IASetIndexBuffer(format=R16_UINT, hash=11111111)",
            "000010 DrawIndexedInstanced(IndexCountPerInstance:120, InstanceCount:1, StartIndexLocation:0, BaseVertexLocation:0, StartInstanceLocation:0)",
            "000020 VSSetShader(hash=cccccccccccccccc)",
            "000020 PSSetShader(hash=dddddddddddddddd)",
            "000020 IASetIndexBuffer(format=R16_UINT, hash=22222222)",
            "000020 DrawIndexedInstanced(IndexCountPerInstance:300, InstanceCount:1, StartIndexLocation:0, BaseVertexLocation:0, StartInstanceLocation:0)",
            "000030 VSSetShader(hash=eeeeeeeeeeeeeeee)",
            "000030 PSSetShader(hash=ffffffffffffffff)",
            "000030 IASetIndexBuffer(format=R16_UINT, hash=22222222)",
            "000030 DrawIndexedInstanced(IndexCountPerInstance:300, InstanceCount:1, StartIndexLocation:0, BaseVertexLocation:0, StartInstanceLocation:0)",
            "000040 VSSetShader(hash=9999999999999999)",
            "000040 PSSetShader(hash=8888888888888888)",
            "000040 IASetIndexBuffer(format=R16_UINT, hash=22222222)",
            "000040 DrawIndexedInstanced(IndexCountPerInstance:300, InstanceCount:1, StartIndexLocation:0, BaseVertexLocation:0, StartInstanceLocation:0)",
        ])
        (capture / "log.txt").write_text(log, encoding="utf-8")

        write_resource(capture, 10, "ib", "11111111", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", 120 * 2)
        write_resource(capture, 10, "vb0", "abababab", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", 20 * 40)
        write_resource(capture, 10, "vb1", "cdcdcdcd", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", 20 * 12)
        for draw, vs, ps in (
            (20, "cccccccccccccccc", "dddddddddddddddd"),
            (30, "eeeeeeeeeeeeeeee", "ffffffffffffffff"),
            (40, "9999999999999999", "8888888888888888"),
        ):
            write_resource(capture, draw, "ib", "22222222", vs, ps, 300 * 2)
            write_resource(capture, draw, "vb0", "33333333", vs, ps, 100 * 40)
            write_resource(capture, draw, "vb1", "44444444", vs, ps, 100 * 12)

        report = core.extract_profile_from_frame_dump(capture, output)
        assert report["selected"]["draw"] == 30
        assert report["selected"]["vertices"] == 100
        assert (output / "profile.json").is_file()
        profile = core.load_json(output / "profile.json")
        component = profile["components"][0]
        assert component["mainDraw"] == 30
        assert component["vbHashes"]["positionNormalTangent"] == "33333333"
        assert component["draws"] == [20, 30, 40]


def test_resolve_body_json_exact_match_must_match_vertex_count():
    core = load_core()
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        profile_dir = base / "profile"
        library = base / "library"
        bad_body = library / "mdl_chr_hmsz-cstm-0128_body"
        profile_dir.mkdir()
        bad_body.mkdir(parents=True)

        (profile_dir / "drawcall_map.json").write_text("{}", encoding="utf-8")
        (profile_dir / "texture_map.json").write_text('{"textures":{}}', encoding="utf-8")
        (profile_dir / "profile.json").write_text(json.dumps({
            "schemaVersion": 1,
            "id": "test-profile",
            "target": {"bodyResource": "mdl_chr_hmsz-cstm-0128_body"},
            "components": [{
                "id": "body",
                "vertices": 19040,
                "indices": 77304,
            }],
        }), encoding="utf-8")
        (bad_body / "Geo_Body.json").write_text(json.dumps({
            "m_Name": "Geo_Body",
            "m_VertexCount": 16,
            "m_Indices": [0, 1, 2],
            "m_BindPose": [],
        }), encoding="utf-8")

        try:
            core.resolve_body_json_resource(profile_dir, library)
        except ValueError as exc:
            message = str(exc)
            assert "16 顶点" in message
            assert "19040 顶点" in message
        else:
            raise AssertionError("expected vertex-count mismatch to be rejected")


def test_extract_prefers_complete_body_over_repeated_tiny_helpers():
    core = load_core()
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        capture = base / "FrameAnalysis-2026-06-25-015839"
        output = base / "generated-profile"
        capture.mkdir()

        lines = []
        for draw in range(70, 93):
            lines.extend([
                f"{draw:06d} VSSetShader(hash=15751eb080b9bcfc)",
                f"{draw:06d} PSSetShader(hash=ae4e6fdc09590dc5)",
                f"{draw:06d} IASetIndexBuffer(format=R16_UINT, hash=dbd82e34)",
                f"{draw:06d} DrawIndexedInstanced(IndexCountPerInstance:120, InstanceCount:1, StartIndexLocation:0, BaseVertexLocation:0, StartInstanceLocation:0)",
            ])
            write_resource(capture, draw, "ib", "dbd82e34", "15751eb080b9bcfc", "ae4e6fdc09590dc5", 120 * 2)
            write_resource(capture, draw, "vb0", "aaaa1111", "15751eb080b9bcfc", "ae4e6fdc09590dc5", 64 * 40)

        for draw, vs, ps in (
            (263, "5b7fff8ecccaf579", "cf02c2d50d3f2230"),
            (290, "5b7fff8ecccaf579", "cf02c2d50d3f2230"),
            (325, "fe50b7a82b0f37be", "f872756c910a6eb7"),
            (338, "e0ceaa854f457e74", "58352a72263d897c"),
        ):
            lines.extend([
                f"{draw:06d} VSSetShader(hash={vs})",
                f"{draw:06d} PSSetShader(hash={ps})",
                f"{draw:06d} IASetIndexBuffer(format=R16_UINT, hash=398a5635)",
                f"{draw:06d} DrawIndexedInstanced(IndexCountPerInstance:69108, InstanceCount:1, StartIndexLocation:1302, BaseVertexLocation:0, StartInstanceLocation:0)",
            ])
            write_resource(capture, draw, "ib", "398a5635", vs, ps, 70008 * 2)
            write_resource(capture, draw, "vb0", "bbbb2222", vs, ps, 16766 * 40)
            write_resource(capture, draw, "vb1", "cccc3333", vs, ps, 16766 * 12)

        (capture / "log.txt").write_text("\n".join(lines), encoding="utf-8")
        report = core.extract_profile_from_frame_dump(capture, output)
        assert report["selected"]["ibHash"] == "398a5635"
        assert report["selected"]["vertices"] == 16766
        assert report["selected"]["indices"] == 69108


def test_records_first_index_tails_and_all_vs():
    """冻结运行时替换链修复:主体 first_index、尾部段、全部 body VS。

    回归对象:游戏把同一 body IB 分多段多 pass 画(主体可能不在偏移 0,另有尾部配件)。
    生成器需据此 match_first_index + drawindexed 主体、skip 尾部、为每个 VS 生成
    checktextureoverride，否则会出现“matched 但不替换 / 叠原版 / 配件漏出”。
    """
    core = load_core()
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        capture = base / "FrameAnalysis-2026-06-25-999999"
        output = base / "generated-profile"
        capture.mkdir()

        body_ib = "abcd1234"
        main_passes = (
            ("5b7fff8ecccaf579", "cf02c2d50d3f2230"),
            ("fe50b7a82b0f37be", "f872756c910a6eb7"),
            ("436f9c16af3b54cf", "a04da6e49886b206"),
        )
        lines = []
        for draw, (vs, ps) in zip((200, 210, 220), main_passes):
            lines += [
                f"{draw:06d} VSSetShader(hash={vs})",
                f"{draw:06d} PSSetShader(hash={ps})",
                f"{draw:06d} IASetIndexBuffer(format=R16_UINT, hash={body_ib})",
                f"{draw:06d} DrawIndexedInstanced(IndexCountPerInstance:1000, InstanceCount:1, "
                "StartIndexLocation:64, BaseVertexLocation:0, StartInstanceLocation:0)",
            ]
            write_resource(capture, draw, "ib", body_ib, vs, ps, 1100 * 2)
            write_resource(capture, draw, "vb0", "11110000", vs, ps, 500 * 40)
            write_resource(capture, draw, "vb1", "22220000", vs, ps, 500 * 12)
        # 尾部小段(原版配件):同 IB、不同 StartIndex，仅日志里出现
        for draw, start in ((230, 1064), (231, 1080)):
            lines += [
                f"{draw:06d} VSSetShader(hash=5b7fff8ecccaf579)",
                f"{draw:06d} PSSetShader(hash=cf02c2d50d3f2230)",
                f"{draw:06d} IASetIndexBuffer(format=R16_UINT, hash={body_ib})",
                f"{draw:06d} DrawIndexedInstanced(IndexCountPerInstance:16, InstanceCount:1, "
                f"StartIndexLocation:{start}, BaseVertexLocation:0, StartInstanceLocation:0)",
            ]
        (capture / "log.txt").write_text("\n".join(lines), encoding="utf-8")

        core.extract_profile_from_frame_dump(capture, output)
        profile = core.load_json(output / "profile.json")
        component = profile["components"][0]
        assert component["ibHash"] == body_ib
        assert component["mainFirstIndex"] == 64, component.get("mainFirstIndex")
        assert component["tailFirstIndices"] == [1064, 1080], component.get("tailFirstIndices")

        drawcalls = core.load_json(output / "drawcall_map.json")
        vs_set = {p.get("vertexShader") for p in drawcalls["components"]["body"]["passBindings"].values()}
        assert {"5b7fff8ecccaf579", "fe50b7a82b0f37be", "436f9c16af3b54cf"} <= vs_set, vs_set

        checks = core._shader_check_overrides("Test", "body", drawcalls)
        assert checks.count("checktextureoverride = ib") == 3, checks
        for vs in ("5b7fff8ecccaf579", "fe50b7a82b0f37be", "436f9c16af3b54cf"):
            assert vs in checks
    print("test_records_first_index_tails_and_all_vs OK")


if __name__ == "__main__":
    test_extract_frame_profile()
    test_resolve_body_json_exact_match_must_match_vertex_count()
    test_extract_prefers_complete_body_over_repeated_tiny_helpers()
    test_records_first_index_tails_and_all_vs()
