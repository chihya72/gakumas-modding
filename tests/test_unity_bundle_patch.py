import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.patch_unity_bundle import _pack_vertex_data, _resolve_hash_bone_names


def test_hash_bone_name_resolution():
    sidecar = {
        "rootBone": "bone_101",
        "bones": [
            {"name": "bone_101", "parentIndex": -1},
            {"name": "bone_202", "parentName": "bone_101"},
            {"name": "Hips", "parentIndex": -1},
        ],
        "extraSwingBones": [
            {"name": "bone_202_End", "parentName": "bone_202"},
        ],
    }
    assert _resolve_hash_bone_names(
        sidecar, {101: "DressRoot", 202: "DressTip"}
    ) == 2
    assert sidecar["rootBone"] == "DressRoot"
    assert [item["name"] for item in sidecar["bones"]] == [
        "DressRoot", "DressTip", "Hips"
    ]
    assert sidecar["bones"][1]["parentName"] == "DressRoot"
    assert sidecar["extraSwingBones"][0]["parentName"] == "DressTip"


def test_template_stream_pack():
    channels = [{"stream": 0, "offset": 0, "format": 0, "dimension": 3},
                {"stream": 0, "offset": 12, "format": 0, "dimension": 3},
                {"stream": 0, "offset": 24, "format": 0, "dimension": 4},
                {"stream": 1, "offset": 0, "format": 2, "dimension": 4},
                {"stream": 1, "offset": 4, "format": 0, "dimension": 2},
                *({"stream": 0, "offset": 0, "format": 0, "dimension": 0} for _ in range(7)),
                {"stream": 2, "offset": 0, "format": 0, "dimension": 4},
                {"stream": 2, "offset": 16, "format": 10, "dimension": 4}]
    geo = {
        "m_VertexCount": 1,
        "m_Vertices": [1, 2, 3], "m_Normals": [0, 1, 0],
        "m_Tangents": [1, 0, 0, 1], "m_Colors": [0, 0.5, 1, 0],
        "m_UV0": [0.25, 0.75],
        "m_Skin": [{"weight": [0.75, 0.25, 0, 0], "boneIndex": [4, 2, 0, 0]}],
    }
    packed = _pack_vertex_data(channels, geo)
    assert len(packed) == 96
    assert packed[48:52] == bytes([0, 128, 255, 0])


if __name__ == "__main__":
    test_template_stream_pack()
    test_hash_bone_name_resolution()
    print("unity bundle patch contract OK")
