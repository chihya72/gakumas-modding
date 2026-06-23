import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "blender_addon" / "gakumas_mi" / "core.py"


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


if __name__ == "__main__":
    test_extract_frame_profile()
