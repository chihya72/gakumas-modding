import importlib.util
import json
from pathlib import Path
import shutil


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
        } for index, name in enumerate(critical)] + [{
            "name": "LeftArm_Roll_H",
            "parentIndex": 2,
            "localPosition": [0, 0, 0],
            "localRotation": [0, 0, 0, 1],
            "localScale": [1, 1, 1],
        }, {
            "name": "Spine2",
            "parentIndex": 1,
            "localPosition": [0, 0, 0],
            "localRotation": [0, 0, 0, 1],
            "localScale": [1, 1, 1],
        }, {
            "name": "Streamer_L_A0",
            "parentIndex": 2,
            "localPosition": [0, 0, 0],
            "localRotation": [0, 0, 0, 1],
            "localScale": [1, 1, 1],
            "swing": {"damping": 0.5, "stiffness": 0.02, "spring": 0.5,
                      "mass": 0.15, "useWindGlobalForce": True},
        }, {
            "name": "Streamer_R_A0",
            "parentIndex": 2,
            "localPosition": [0, 0, 0],
            "localRotation": [0, 0, 0, 1],
            "localScale": [1, 1, 1],
            "swing": {"damping": 0.5, "stiffness": 0.02, "spring": 0.5,
                      "mass": 0.15, "useWindGlobalForce": True},
        }],
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
    assert report["swing"] == {
        "total": 2,
        "left": 1,
        "right": 1,
        "unclassified": 0,
        "invalidParentCount": 0,
        "missingParameterCount": 0,
    }

    # 正式 release 目录同时有部署用顶层 mod.json 和完整 bundle-src；验证器必须检查
    # bundle-src，不能被顶层精简部署清单截走。
    release_root = tmp_path / "release"
    bundle_src = release_root / "bundle-src"
    bundle_src.mkdir(parents=True)
    for name in ("mod.json", "test_bones.json.txt", "test.geojson.txt", "t4.png"):
        shutil.copy2(tmp_path / name, bundle_src / name)
    (release_root / "mod.json").write_text(
        json.dumps({"runtimeProtocol": 1, "buildId": "stale-top-level"}),
        encoding="utf-8",
    )
    packaged_report = verify.verify_package(release_root)
    assert packaged_report["ok"]
    assert Path(packaged_report["bundleSource"]) == bundle_src.resolve()
