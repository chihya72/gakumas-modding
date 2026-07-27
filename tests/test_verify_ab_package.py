import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_ab_package", ROOT / "tools" / "verify_ab_package.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_verify_ab_package_passes_minimal_contract(tmp_path):
    critical = list(verify.CRITICAL_BONES)
    sidecar = {
        "runtimeProtocol": 1,
        "buildId": "test-build",
        "bones": [{
            "name": name,
            "parentIndex": index - 1,
            "localPosition": [0, 0, 0],
            "localRotation": [0, 0, 0, 1],
            "localScale": [1, 1, 1],
        } for index, name in enumerate(critical)],
        "sourceRigRemap": {"bones": {name: name for name in critical}},
    }
    geo = {
        "m_VertexCount": len(critical),
        "m_Colors": [1.0, 1.0, 1.0, 1.0] * len(critical),
        "m_Skin": [{"boneIndex": [index, 0, 0, 0], "weight": [1.0, 0, 0, 0]}
                   for index in range(len(critical))],
    }
    (tmp_path / "mod.json").write_text(json.dumps({
        "runtimeProtocol": 1,
        "buildId": "test-build",
        "replacements": [{
            "part": "body",
            "skeleton": "Assets/Mods/test/test_bones.json.txt",
            "textures": [{"property": "_ShadeMap", "asset": "Assets/Mods/test/t4.png"}],
        }],
    }), encoding="utf-8")
    (tmp_path / "test_bones.json.txt").write_text(json.dumps(sidecar), encoding="utf-8")
    (tmp_path / "test.geojson.txt").write_text(json.dumps(geo), encoding="utf-8")
    (tmp_path / "t4.png").write_bytes(b"0" * 1_000_000)

    report = verify.verify_package(tmp_path)
    assert report["ok"]
    assert report["t4"]["mbLevel"]
    assert report["weights"]["activeBoneCount"] == len(critical)
