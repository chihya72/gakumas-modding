import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def test_bundle_source_contract():
    skeleton = {"nodes": [
        {"name": "Root", "parent": -1, "weightedIndex": None},
        {"name": "Child", "parent": 2, "weightedIndex": 1,
         "localPosition": [1, 0, 0], "localRotation": [0, 0, 0, 1], "localScale": [1, 1, 1]},
        {"name": "Hips", "parent": 0, "weightedIndex": 0,
         "localPosition": [0, 0, 0], "localRotation": [0, 0, 0, 1], "localScale": [1, 1, 1]},
    ]}
    data = {
        "vertices": [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        "normals": [(0, 0, 1)] * 3,
        "tangents": [(1, 0, 0, 1)] * 3,
        "uv0": [(0, 0), (1, 0), (0, 1)],
        "colors": [(0, 0, 1, 0)] * 3,
        "faces": [(0, 1, 2)],
        "materials": [0, 0, 0],
        "skin": [[(1, 0, 1.0)], [(0, 0, 1.0)], [(1, 0, 1.0)]],
    }
    source_mesh = {"m_BindPose": [{"id": "bone0"}, {"id": "bone1"}], "m_Name": "Test"}
    geo, bones = core._bundle_geojson(data, source_mesh, skeleton, 1)
    assert [bone["name"] for bone in bones] == ["Hips", "Child"]
    assert bones[1]["parentIndex"] == 0
    assert geo["m_Skin"][0]["boneIndex"][0] == 1
    assert geo["m_SubMeshes"][0]["firstByte"] == 0

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        mesh_path = root / "mesh.json"
        skeleton_path = root / "skeleton.json"
        mesh_path.write_text(json.dumps(source_mesh), encoding="utf-8")
        skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
        bundle_dir = root / "test.mod" / "bundle-src"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "slot0_t0.png").write_bytes(b"png")
        output = core.write_bundle_source(
            root, "test.mod", "mdl_test_body", "body", "Test", "Author", data,
            mesh_path, skeleton_path,
            [{"materialSlot": 0, "property": "_BaseMap", "filename": "slot0_t0.png"}],
        )
        manifest = json.loads((output / "mod.json").read_text(encoding="utf-8"))
        assert manifest["replacements"][0]["textures"][0]["asset"] == (
            "Assets/Mods/test.mod/slot0_t0.png"
        )
        # rootBone 回退：无 rootBonePathId → weightedIndex==0 的骨名
        sidecar = json.loads((output / "test.mod_bones.json.txt").read_text(encoding="utf-8"))
        assert sidecar["rootBone"] == "Hips"


def test_bundle_root_bone_authoritative():
    # rootBonePathId 权威：即使 weightedIndex==0 是别的骨，也用 pathId 指向的骨
    skeleton = {
        "rootBonePathId": 99,
        "nodes": [
            {"name": "Pelvis", "pathId": 99, "parent": -1, "weightedIndex": 1,
             "localPosition": [0, 0, 0], "localRotation": [0, 0, 0, 1], "localScale": [1, 1, 1]},
            {"name": "Hips", "pathId": 5, "parent": 0, "weightedIndex": 0,
             "localPosition": [0, 0, 0], "localRotation": [0, 0, 0, 1], "localScale": [1, 1, 1]},
        ],
    }
    names = {"Pelvis", "Hips"}
    assert core._bundle_root_bone(skeleton, names) == "Pelvis"
    # pathId 指向的骨不在加权集 → 回退 weightedIndex==0
    assert core._bundle_root_bone(skeleton, {"Hips"}) == "Hips"
    # 全缺 → "Hips"
    assert core._bundle_root_bone({"nodes": []}, set()) == "Hips"


def test_merge_material_groups():
    # 9 材质全不透明 + 目标 1 段 → 全归并到 bdy(组 0)
    materials = [0, 3, 8, 5, 1, 7, 2, 4, 6]
    assert core.merge_material_groups(set(), 1, materials) == [0] * 9
    # co 槽(2,5)在目标 2 段里 → 组 1(bdyco)，其余 → 组 0
    merged = core.merge_material_groups({2, 5}, 2, [0, 2, 5, 1, 3])
    assert merged == [0, 1, 1, 0, 0]
    # 目标只有 1 段却含 co → 报错
    try:
        core.merge_material_groups({2}, 1, [0, 2])
        assert False, "应因目标无 bdyco 段而报错"
    except ValueError:
        pass
    # 空材质 → 全 bdy
    assert core.merge_material_groups(set(), 1, []) == []


if __name__ == "__main__":
    test_bundle_source_contract()
    test_bundle_root_bone_authoritative()
    test_merge_material_groups()
    print("bundle source contract OK")
