import importlib.util
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_ab_package", ROOT / "tools" / "verify_ab_package.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_verify_ab_package_passes_minimal_contract(tmp_path):
    # 19 根 Avatar 必备骨（HumanBodyBones 0–18，读自 IsValidHumanDescription）——
    # 少一根 Avatar 就无效、动画一帧都不播，所以"最小合格包"必须包含它们。
    critical = list(dict.fromkeys(list(verify.CRITICAL_BONES) + list(verify.REQUIRED_HUMANOID_BONES)))
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
            # 字段照 swing_presets.json 的 ribbon/mid 档写全：少 pendulumRange/wind
            # 这类字段时骨"参数齐全"却不下垂也不受风，verify 必须能拦住。
            "swing": {"damping": 0.5, "stiffness": 0.008, "spring": 0.3, "mass": 0.7,
                      "useWindGlobalForce": True, "pendulum": 0.003,
                      "pendulumRange": 1.0, "wind": 1.0, "rootWeight": 0.3,
                      "colliderRadius": 0.018, "colliderType": 0, "collisionMask": -1},
        }, {
            "name": "Streamer_R_A0",
            "parentIndex": 2,
            "localPosition": [0, 0, 0],
            "localRotation": [0, 0, 0, 1],
            "localScale": [1, 1, 1],
            # 字段照 swing_presets.json 的 ribbon/mid 档写全：少 pendulumRange/wind
            # 这类字段时骨"参数齐全"却不下垂也不受风，verify 必须能拦住。
            "swing": {"damping": 0.5, "stiffness": 0.008, "spring": 0.3, "mass": 0.7,
                      "useWindGlobalForce": True, "pendulum": 0.003,
                      "pendulumRange": 1.0, "wind": 1.0, "rootWeight": 0.3,
                      "colliderRadius": 0.018, "colliderType": 0, "collisionMask": -1},
        }],
        "sourceRigRemap": {"bones": {name: name for name in critical}},
    }
    # 一个**能进游戏**的最小包，不只是 schema 合法：矫正骨必须真的承重。
    # 原版 49 套实测 `*_H` 承重 min 6.02% / 中位 11.28%，为 0 的一套都没有，
    # 而四个已出货成品全是 0.00% —— 这正是 G1 要拦的东西，所以 fixture 也得给它权重，
    # 否则这份"最小契约"描述的是一个肩肘会剪切的包。
    roll_index = len(critical)          # LeftArm_Roll_H
    geo = {
        "m_VertexCount": len(critical) + 1,
        # 纯白 = 网格没有顶点色时的默认值，进游戏就是"没有描边"（原版 22 套实测 0 个纯白顶点）。
        # 这里用原版皮肤的实测值 (81,0,15,144)/255。
        "m_Colors": [81 / 255, 0.0, 15 / 255, 144 / 255] * (len(critical) + 1),
        "m_Skin": [{"boneIndex": [index, 0, 0, 0], "weight": [1.0, 0, 0, 0]}
                   for index in range(len(critical))]
                  + [{"boneIndex": [roll_index, 0, 0, 0], "weight": [1.0, 0, 0, 0]}],
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
    assert report["weights"]["activeBoneCount"] == len(critical) + 1
    assert report["geometries"][0]["helperRig"]["weightShare"] > 0.0
    assert report["swing"] == {
        "total": 2,
        "left": 1,
        "right": 1,
        "unclassified": 0,
        "runtimeCreated": 0,
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


def test_verify_checks_runtime_created_bones_too():
    """链尾走顶层 `extraSwingBones`，运行时同样会把它们建成 ActorSwingDynamicBone。

    验证器只查 `bones[]` 时，给链尾一个空 `swing` 会得到 0 错 0 警 —— 而那些骨在游戏里
    落进 `SetDefaultValues` 的惰性默认值，正是"日志全绿画面不动"那一类的源头。
    """
    sidecar = {"bones": [], "extraSwingBones": [
        {"name": "Bow_A_End", "parentName": "Bow_A", "swing": {}}]}
    report = {"errors": [], "warnings": []}
    verify._check_swing(report, sidecar)
    assert report["swing"]["runtimeCreated"] == 1
    assert report["swing"]["missingParameterCount"] == 1
    assert report["errors"]

    sidecar["extraSwingBones"][0]["swing"] = {
        "damping": 0.5, "stiffness": 0.008, "spring": 0.3, "mass": 0.7,
        "useWindGlobalForce": True, "pendulum": 0.003, "pendulumRange": 1.0,
        "wind": 1.0, "rootWeight": 0.3,
        "colliderRadius": 0.018, "colliderType": 0, "collisionMask": -1,
    }
    report = {"errors": [], "warnings": []}
    verify._check_swing(report, sidecar)
    assert report["swing"]["missingParameterCount"] == 0
    assert not report["errors"]


def _write_hair_contract(tmp_path, sidecar, geometries):
    (tmp_path / "mod.json").write_text(json.dumps({
        "runtimeProtocol": 1,
        "buildId": "test-build",
        "replacements": [{
            "part": "hair",
            "skeleton": "Assets/Mods/test/test_bones.json.txt",
        }],
    }), encoding="utf-8")
    payload = {"runtimeProtocol": 1, "buildId": "test-build", **sidecar}
    (tmp_path / "test_bones.json.txt").write_text(json.dumps(payload), encoding="utf-8")
    for name, geometry in geometries.items():
        (tmp_path / name).write_text(json.dumps(geometry), encoding="utf-8")


def test_verify_rejects_missing_runtime_bone_physics_in_final_result(tmp_path):
    _write_hair_contract(tmp_path, {
        "bones": [{"name": "Hips", "parentIndex": -1}],
        "extraSwingBones": [{"name": "Bow_A_End", "parentName": "Hips", "swing": {}}],
    }, {
        "hair.geojson.txt": {"m_VertexCount": 0, "m_Colors": [], "m_Skin": []},
    })

    report = verify.verify_package(tmp_path)

    assert not report["ok"]
    assert any("摇物骨缺少物理参数" in message for message in report["errors"])


def test_verify_checks_every_renderer_geometry(tmp_path):
    _write_hair_contract(tmp_path, {"bones": []}, {
        "Geo_Hair.geojson.txt": {"m_VertexCount": 0, "m_Colors": [], "m_Skin": []},
        "Geo_HairProp.geojson.txt": {"m_VertexCount": 1, "m_Colors": [], "m_Skin": []},
    })

    report = verify.verify_package(tmp_path)

    assert not report["ok"]
    assert len(report["geometries"]) == 2
    assert any("Geo_HairProp.geojson.txt" in message for message in report["errors"])


def test_verify_rejects_non_integer_chain_length():
    """`chainLength: "2"` 以前被跳过（验证器 0 错），而运行时按整数读。"""
    sidecar = {
        "bones": [{"name": "Hips"}],
        "extraSwingBones": [{"name": "Bow_A", "parentName": "Hips"}],
        "swingChains": [{"host": "Hips", "rootBones": ["Bow_A"], "chainLength": "2"}],
    }
    report = {"errors": [], "warnings": []}
    verify._check_swing(report, sidecar)
    assert any("chainLength" in problem for problem in report["swingChains"]["problems"])
    assert report["errors"]


def test_verify_reports_bad_bones_container_instead_of_crashing(tmp_path):
    """`bones: 7` 以前让核包工具抛 TypeError('int' object is not iterable)。"""
    (tmp_path / "mod.json").write_text(json.dumps({
        "runtimeProtocol": 1,
        "buildId": "test-build",
        "replacements": [{"part": "hair", "skeleton": "Assets/Mods/test/test_bones.json.txt"}],
    }), encoding="utf-8")
    (tmp_path / "test_bones.json.txt").write_text(
        json.dumps({"runtimeProtocol": 1, "buildId": "test-build", "bones": 7}), encoding="utf-8")
    (tmp_path / "test.geojson.txt").write_text(
        json.dumps({"m_VertexCount": 0, "m_Colors": [], "m_Skin": []}), encoding="utf-8")

    report = verify.verify_package(tmp_path)
    assert not report["ok"]
    assert any("bones 必须是数组" in message for message in report["errors"])
