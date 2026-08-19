import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_tool(name: str):
    path = ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reference_inventory_uses_existing_assetstudio_data():
    tool = load_tool("build_avatar_reference_inventory.py")
    data_root = ROOT.parents[2] / "mod-workspace" / "libraries"
    inventory = tool.build_inventory(data_root)
    assert inventory["referenceKind"] == "asset_inventory"
    assert inventory["status"]["animator"] == "not_observed"
    assert inventory["counts"]["bodyResources"] >= 500
    # The directory dump contains more hair folders, but only these have the
    # primary Geo_Hair skeleton required by the SDK inventory contract.
    assert inventory["counts"]["hairResources"] >= 200
    fktn = next(item for item in inventory["characters"] if item["characterId"] == "fktn")
    assert fktn["resourceCount"] > 0
    assert "Hips" in fktn["weightedBoneUnion"]


def _valid_descriptor():
    return {
        "protocol": 1,
        "sdkVersion": "0.1.0",
        "unityVersion": "6000.0.67f1",
        "buildId": "test-build",
        "avatarRoot": ".",
        "animator": ".",
        "renderers": [
            {
                "path": "Body",
                "role": "body",
                "rendererType": "SkinnedMeshRenderer",
                "blendShapes": ["Smile"],
            },
            {
                "path": "Face",
                "role": "face",
                "rendererType": "SkinnedMeshRenderer",
                "blendShapes": ["Smile", "Blink"],
            },
        ],
        "expressions": [
            {
                "channel": "smile",
                "outputs": [
                    {
                        "rendererPath": "Face",
                        "blendShape": "Smile",
                        "scale": 1.0,
                        "mode": "max",
                    }
                ],
            }
        ],
        "springChains": [
            {
                "id": "hair.main",
                "nodes": ["Armature/Hair0", "Armature/Hair0/Hair1"],
                "stiffness": 0.5,
                "damping": 0.2,
                "gravity": 1.0,
            }
        ],
        "colliders": [],
        "rootMotion": {"mode": "actorAnchored", "groundOffset": 0.0, "scaleMode": "author"},
        "materials": {"mode": "standard"},
    }


def test_descriptor_validator_accepts_minimum_shape():
    tool = load_tool("validate_avatar_descriptor.py")
    assert tool.validate_descriptor(_valid_descriptor()) == []


def test_descriptor_validator_rejects_duplicate_renderer_and_unknown_expression_target():
    tool = load_tool("validate_avatar_descriptor.py")
    descriptor = _valid_descriptor()
    descriptor["renderers"].append({
        "path": "Face",
        "role": "hair",
        "rendererType": "SkinnedMeshRenderer",
    })
    descriptor["expressions"][0]["outputs"][0]["rendererPath"] = "Missing"
    errors = tool.validate_descriptor(descriptor)
    assert any("duplicates another renderer path" in error for error in errors)
    assert any("does not name a declared renderer" in error for error in errors)


def test_descriptor_validator_rejects_windows_and_parent_paths():
    tool = load_tool("validate_avatar_descriptor.py")
    descriptor = _valid_descriptor()
    descriptor["avatarRoot"] = r"C:\avatar"
    descriptor["renderers"][0]["path"] = "../Outside"
    errors = tool.validate_descriptor(descriptor)
    assert any("avatarRoot" in error for error in errors)
    assert any("renderers[0].path" in error for error in errors)


def test_manifest_validator_accepts_example_and_rejects_duplicate_targets():
    tool = load_tool("validate_manifest.py")
    example = json.loads((ROOT / "example-mod.json").read_text(encoding="utf-8"))
    assert tool.validate_manifest(example) == []
    example["targets"].append({"characterId": "fktn"})
    errors = tool.validate_manifest(example)
    assert any("duplicate target" in error for error in errors)
