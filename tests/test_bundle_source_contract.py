import importlib.util
import json
import tempfile
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def test_scsp_body_remap_does_not_use_cloth_bones():
    report = core.build_bone_remap(
        ["LeftShoulder_rot", "LeftArm1_rot", "LeftElbow", "RightForeArm_rot", "LeftArm_1"],
        {"LeftShoulder", "LeftArm", "LeftForeArm", "RightForeArm", "LeftSleeve2_S"},
        preset_name="auto",
    )
    assert report["sourceRig"] == "scsp"
    assert report["bones"] == {
        "LeftShoulder_rot": "LeftShoulder",
        "LeftArm1_rot": "LeftArm",
        "LeftElbow": "LeftForeArm",
        "RightForeArm_rot": "RightForeArm",
        "LeftArm_1": "LeftArm",
    }


def test_accessory_remap_cannot_override_body_preset():
    merged = core.merge_accessory_bone_remap(
        {"LeftElbow": "LeftForeArm", "Hips": "Hips"},
        {"LeftElbow": "LeftSleeve2_S", "Bow_A": "LeftBackRibbon1_S"},
    )
    assert merged == {
        "LeftElbow": "LeftForeArm",
        "Hips": "Hips",
        "Bow_A": "LeftBackRibbon1_S",
    }


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
        "source_rig_report": {
            "newBones": {
                "newBones": [{"name": "Bow_A", "parentName": "Hips"}],
                "extraSwingBones": [{"name": "Bow_A_End", "parentName": "Bow_A"}],
            },
        },
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
        assert sidecar["schemaVersion"] == 4
        assert sidecar["runtimeProtocol"] == core.AB_RUNTIME_PROTOCOL
        assert sidecar["buildId"] == manifest["buildId"]
        assert sidecar["newBones"][0]["parentName"] == "Hips"
        assert sidecar["extraSwingBones"][0]["parentName"] == "Bow_A"


def test_bundle_new_bone_index_and_weight_contract():
    skeleton = {
        "nodes": [
            {"name": "Root", "parent": -1, "weightedIndex": None},
            {"name": "Hips", "parent": 0, "weightedIndex": 0},
            {"name": "Bow_A", "parent": 1, "weightedIndex": 1},
        ]
    }
    source_mesh = {"m_BindPose": [{"id": "hips"}], "m_Name": "Test"}
    data = {
        "vertices": [(0, 0, 0)] * 3,
        "normals": [(0, 0, 1)] * 3,
        "tangents": [(1, 0, 0, 1)] * 3,
        "uv0": [(0, 0)] * 3,
        "colors": [(0, 0, 1, 0)] * 3,
        "faces": [(0, 1, 2)],
        "materials": [0, 0, 0],
        "skin": [[(1, 0.25), (0, 0.75)]] * 3,
        "bundle_extra_bind_poses": [{"id": "bow"}],
    }
    geo, bones = core._bundle_geojson(data, source_mesh, skeleton, 1)
    assert [bone["name"] for bone in bones] == ["Hips", "Bow_A"]
    assert len(geo["m_BindPose"]) == 2
    assert dict(zip(
        geo["m_Skin"][0]["boneIndex"][:2], geo["m_Skin"][0]["weight"][:2]
    )) == {0: 0.75, 1: 0.25}


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
    # 合成骨架的 weightedIndex 顺序来自 m_BoneNameHashes，不可当作根骨依据。
    synthetic = {
        "synthetic": "mesh m_BindPose + m_BoneNameHashes",
        "nodes": [
            {"name": "Finger", "weightedIndex": 0},
            {"name": "Hips", "weightedIndex": 7},
        ],
    }
    assert core._bundle_root_bone(synthetic, {"Finger", "Hips"}) == "Hips"
    # 全缺 → "Hips"
    assert core._bundle_root_bone({"nodes": []}, set()) == "Hips"


def test_rgba8_dds_roundtrip():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "texture.dds"
        pixels = bytes((1, 2, 3, 4, 5, 6, 7, 8))
        core.write_rgba8_dds(path, 2, 1, pixels)
        assert core.read_rgba8_dds(path) == (2, 1, pixels)


def test_source_rig_detection():
    target = {"Hips", "Spine"}
    assert core.detect_source_rig(["mixamorig:Hips"]) == "mixamo"
    assert core.detect_source_rig(["def-spine"]) == "rigify"
    assert core.detect_source_rig(["センター"]) == "mmd-standard"
    assert core.detect_source_rig(["Spine_1"], target) == "scsp"
    assert core.detect_source_rig(["pelvis_ctrl"], target) == "custom"


def test_bone_remap_presets():
    target = {"Hips", "Spine", "Spine1", "Head", "LeftArm", "LeftForeArm"}
    result = core.build_bone_remap(
        ["mixamorig:Hips", "mixamorig:Spine1", "mixamorig:Head",
         "裙摆_1", "LeftArm_1"],
        target,
        parent_by_name={"裙摆_1": "mixamorig:Hips"},
        preset_name="mixamo",
    )
    assert result["sourceRig"] == "mixamo"
    assert result["bones"] == {
        "mixamorig:Hips": "Hips", "mixamorig:Spine1": "Spine1",
        "mixamorig:Head": "Head", "LeftArm_1": "LeftArm",
    }
    assert "裙摆_1" in result["accessoryBones"]
    assert result["parentFallback"]["裙摆_1"] == "Hips"


def test_common_presets_cover_finger_bones():
    target = {
        "LeftHandThumb1", "LeftHandIndex2", "RightHandMiddle3",
        "RightHandPinky1", "LeftArm", "RightForeArm",
    }
    cases = [
        ("mmd-standard", ["左親指０", "左人指２", "右中指３", "右小指１"]),
        ("mixamo", ["mixamorig:LeftHandThumb1", "mixamorig:LeftHandIndex2",
                     "mixamorig:RightHandMiddle3", "mixamorig:RightHandPinky1"]),
        ("rigify", ["DEF-thumb.01.L", "DEF-f_index.02.L", "DEF-f_middle.03.R",
                     "DEF-f_pinky.01.R"]),
    ]
    for preset, source in cases:
        result = core.build_bone_remap(source, target, preset_name=preset)
        assert len(result["bones"]) == len(source)
        assert not result["unmapped"]


def test_bone_remap_resolution_rules():
    result = core.build_bone_remap(
        ["Hips", "Spine_1", "左腕", "hair_ctrl"],
        {"Hips", "Spine", "LeftArm"},
        parent_by_name={"hair_ctrl": "Spine_1"},
        preset_name="mmd-standard",
    )
    assert result["bones"] == {
        "Hips": "Hips", "Spine_1": "Spine", "左腕": "LeftArm",
    }
    assert result["methods"] == {
        "Hips": "direct", "Spine_1": "strip_suffix", "左腕": "preset",
    }
    assert result["parentFallback"]["hair_ctrl"] == "Spine"
    assert result["unmapped"] == ["hair_ctrl"]


def test_mmd_tools_side_suffix_folds_into_preset():
    """mmd_tools 把 右腕 导成 腕.R；不折回去整张 mmd 表对任何 PMX 都是空转。"""
    target = {"LeftArm", "LeftForeArm", "LeftHand", "LeftUpLeg", "LeftLeg",
              "LeftFoot", "LeftToeBase", "Spine", "Spine1", "Hips"}
    result = core.build_bone_remap(
        ["上半身", "上半身2", "下半身", "腕.L", "ひじ.L", "手首.L",
         "足D.L", "ひざD.L", "足首D.L", "足先EX.L", "手捩2.L"],
        target,
    )
    assert result["sourceRig"] == "mmd-standard"
    assert result["bones"] == {
        "上半身": "Spine", "上半身2": "Spine1", "下半身": "Hips",
        "腕.L": "LeftArm", "ひじ.L": "LeftForeArm", "手首.L": "LeftHand",
        "足D.L": "LeftUpLeg", "ひざD.L": "LeftLeg", "足首D.L": "LeftFoot",
        "足先EX.L": "LeftToeBase",
        # 捻骨跟前臂,不能跟手掌:跟手掌会让肘后整条小臂吃满手腕旋转 → 肘部撕裂
        "手捩2.L": "LeftForeArm",
    }


GAME_BODY_BONES = (
    "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "LeftUpLeg", "LeftLeg",
    "LeftFoot", "LeftToeBase",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand", "RightUpLeg", "RightLeg",
    "RightFoot", "RightToeBase",
    "LeftHandThumb1", "LeftHandIndex1", "LeftHandMiddle1", "LeftHandRing1", "LeftHandPinky1",
    "RightHandThumb1", "RightHandIndex1", "RightHandMiddle1", "RightHandRing1", "RightHandPinky1",
)

# 各命名家族的身体骨（按各家公开命名规范）。auto 模式必须把它们全部映射掉，
# 少一根就是"导出成功、进游戏废掉"的入口。
NAMING_FAMILIES = {
    "mmd-tools": ["センター", "上半身", "上半身2", "下半身", "首", "頭",
                  "肩.L", "腕.L", "ひじ.L", "手首.L", "足D.L", "ひざD.L", "足首D.L",
                  "足先EX.L", "手捩2.L", "中指１.L"],
    "mmd-japanese": ["センター", "上半身", "上半身2", "下半身", "首", "頭",
                     "左肩", "左腕", "左ひじ", "左手首", "左足D", "左ひざD", "左足首D",
                     "左足先EX", "左手捩2", "左中指１"],
    "vrm": ["J_Bip_C_Hips", "J_Bip_C_Spine", "J_Bip_C_Chest", "J_Bip_C_UpperChest",
            "J_Bip_C_Neck", "J_Bip_C_Head", "J_Bip_L_Shoulder", "J_Bip_L_UpperArm",
            "J_Bip_L_LowerArm", "J_Bip_L_Hand", "J_Bip_L_UpperLeg", "J_Bip_L_LowerLeg",
            "J_Bip_L_Foot", "J_Bip_L_ToeBase", "J_Bip_L_Little1"],
    "biped": ["Bip001 Pelvis", "Bip001 Spine", "Bip001 Spine1", "Bip001 Neck", "Bip001 Head",
              "Bip001 L Clavicle", "Bip001 L UpperArm", "Bip001 L Forearm", "Bip001 L Hand",
              "Bip001 L Thigh", "Bip001 L Calf", "Bip001 L Foot", "Bip001 L Toe0",
              "Bip001 L Finger0"],
    "auto-rig-pro": ["root.x", "spine_01.x", "spine_02.x", "neck.x", "head.x", "shoulder.l",
                     "arm_stretch.l", "forearm_stretch.l", "hand.l", "thigh_stretch.l",
                     "leg_stretch.l", "foot.l", "toes_01.l", "thumb1.l"],
    "unity-humanoid": ["Hips", "Spine", "Chest", "Neck", "Head", "LeftShoulder",
                       "LeftUpperArm", "LeftLowerArm", "LeftHand", "LeftUpperLeg",
                       "LeftLowerLeg", "LeftFoot", "LeftToes"],
    "rigify": ["DEF-pelvis", "DEF-spine", "DEF-spine.001", "DEF-spine.003", "DEF-head",
               "DEF-shoulder.L", "DEF-upper_arm.L", "DEF-forearm.L", "DEF-hand.L",
               "DEF-thigh.L", "DEF-shin.L", "DEF-foot.L", "DEF-toe.L"],
    "mixamo": ["mixamorig:Hips", "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Neck",
               "mixamorig:Head", "mixamorig:LeftShoulder", "mixamorig:LeftArm",
               "mixamorig:LeftForeArm", "mixamorig:LeftHand", "mixamorig:LeftUpLeg",
               "mixamorig:LeftLeg", "mixamorig:LeftFoot", "mixamorig:LeftToeBase"],
}


def _mirror(name):
    """把左侧骨名换成右侧，用于凑出全身骨列表。"""
    for left, right in (("Left", "Right"), (".L", ".R"), ("左", "右"),
                        ("_L_", "_R_"), (" L ", " R "), (".l", ".r")):
        if left in name:
            return name.replace(left, right)
    return name


def test_auto_covers_every_naming_family():
    """auto 逐张表打分选表，所以每个家族的身体骨都该零手工全中、且不触发闸门。"""
    for family, left_names in sorted(NAMING_FAMILIES.items()):
        names = left_names + [_mirror(n) for n in left_names if _mirror(n) != n]
        result = core.build_bone_remap(names, GAME_BODY_BONES)
        missing = [name for name in names if name not in result["bones"]]
        assert not missing, f"{family} 未映射: {missing}"
        assert core.critical_coverage_error(
            names, result["bones"], GAME_BODY_BONES) is None, family


def test_critical_coverage_gate():
    target = list(core.CRITICAL_TARGET_BONES) + ["Spine2"]
    full = {name: name for name in core.CRITICAL_TARGET_BONES}
    assert core.critical_coverage_error(list(full), full, target) is None
    # 手/腿全丢(今天实测的真实事故:整只手钉在 Spine1)必须拦下并点名
    broken = {name: ("Spine1" if "Hand" in name or "Foot" in name else name)
              for name in core.CRITICAL_TARGET_BONES}
    message = core.critical_coverage_error(list(broken), broken, target)
    assert message and "LeftHand" in message and "RightFoot" in message
    # 骨很少的骨架不该误报(与目标骨架取交集)
    assert core.critical_coverage_error(["Hips"], {"Hips": "Hips"}, ["Hips"]) is None


def test_source_bone_classification():
    target = {"Hips", "LeftArm"}
    result = core.classify_source_bones(
        ["Hips", "LeftArm", "Skirt_A", "mystery_ctrl"], target
    )
    assert result == {
        "body": ["Hips", "LeftArm"],
        "accessory": ["Skirt_A", "mystery_ctrl"],
    }
    overridden = core.classify_source_bones(
        ["Hips", "mystery_ctrl"], target, remap={"mystery_ctrl": "Hips"}
    )
    assert overridden == {"body": ["Hips", "mystery_ctrl"], "accessory": []}


def test_accessory_physics_remap():
    result = core.build_accessory_physics_remap(
        [
            {"name": "Skirt_1", "position": [0.0, 0.0, 0.02]},
            {"name": "Bow_L", "position": [0.1, 0.0, 0.0]},
            {"name": "Bow_R", "position": [0.1, 0.0, 0.02]},
            {"name": "Far_Ribbon", "position": [1.0, 0.0, 0.0]},
        ],
        [
            {"name": "LeftSkirt1_S", "position": [0.0, 0.0, 0.0]},
            {"name": "CenterRibbon_S", "position": [0.1, 0.0, 0.01]},
        ],
        ["Skirt_1", "Bow_L", "Bow_R", "Far_Ribbon"],
        parent_by_name={"Bow_L": "Spine", "Bow_R": "Spine", "Far_Ribbon": "Spine"},
        body_remap={"Spine": "Spine"},
        group_by_name={"Bow_L": "bow", "Bow_R": "bow"},
    )
    assert result["bones"] == {}
    assert result["rigidParent"]["Skirt_1"] == "Hips"
    assert result["rigidParent"]["Bow_L"] == "Spine"
    assert result["rigidParent"]["Bow_R"] == "Spine"
    assert result["strategies"]["Bow_L"] == "source_parent"
    assert result["rigidParent"]["Far_Ribbon"] == "Spine"


def test_accessory_bust_name_rule_beats_source_parent():
    result = core.build_accessory_physics_remap(
        [{"name": "胸上2", "position": [0.0, 0.0, 0.0]}],
        [
            {"name": "Bust1_S", "position": [0.0, 0.0, 0.0]},
            {"name": "Bust2_S", "position": [1.0, 0.0, 0.0]},
        ],
        ["胸上2"],
        parent_by_name={"胸上2": "Spine"},
        body_remap={"Spine": "Spine"},
    )
    assert result["bones"] == {"胸上2": "Bust1_S"}
    assert result["strategies"]["胸上2"] == "name_bust"


def test_source_hanging_chain_is_not_centroid_remapped():
    result = core.build_accessory_physics_remap(
        [
            {"name": "Streamer_L_A0", "position": [0.0, 0.0, 0.0]},
            {"name": "Streamer_L_A1", "position": [0.0, 0.0, 0.1]},
            {"name": "SStreamer_L_Aend", "position": [0.0, 0.0, 0.2]},
        ],
        [{"name": "LeftBackRibbon2_S", "position": [0.0, 0.0, 0.0]}],
        ["Streamer_L_A0", "Streamer_L_A1", "SStreamer_L_Aend"],
    )
    assert result["newBones"] == [
        "Streamer_L_A0", "Streamer_L_A1", "SStreamer_L_Aend",
    ]
    assert result["bones"] == {}


def test_lace_rides_skirt_not_nearest_leg():
    # Lace_R sits at the skirt hem, geometrically closest to a leg swing bone but it
    # must ride the skirt (else it flails off the thigh). It should map to the skirt
    # bone, never become an independent new source chain nor pick the closer leg bone.
    result = core.build_accessory_physics_remap(
        [
            {"name": "Lace_R_A0", "position": [0.0, 0.0, 0.30]},
            {"name": "Lace_R_Aend", "position": [0.0, 0.0, 0.32]},
        ],
        [
            {"name": "RightLeg_S", "position": [0.0, 0.0, 0.31]},      # closer leg bone
            {"name": "RightBackSkirt3_S", "position": [0.3, 0.0, 0.30]},  # skirt, >max_distance away
        ],
        ["Lace_R_A0", "Lace_R_Aend"],
        parent_by_name={"Lace_R_A0": "RightLeg", "Lace_R_Aend": "Lace_R_A0"},
        body_remap={"RightLeg": "RightLeg"},
    )
    # skirt bone is past max_distance and a leg bone is closer, yet lace must still ride the
    # skirt — never fall back to a rigid leg parent, never become an independent chain.
    assert "Lace_R_A0" not in result["newBones"]
    assert "Lace_R_A0" not in result["rigidParent"]
    assert result["bones"]["Lace_R_A0"] == "RightBackSkirt3_S"
    assert result["bones"]["Lace_R_Aend"] == "RightBackSkirt3_S"


def test_physics_override_precedence():
    # Author override beats the built-in semantic rule and the position fallback.
    src = [
        {"name": "Streamer_L_A0", "position": [0.0, 0.0, 0.0]},   # semantic: integrate
        {"name": "Petal_R", "position": [0.0, 0.0, 0.05]},        # no rule → position
    ]
    tgt = [{"name": "LeftBackSkirt2_S", "position": [0.0, 0.0, 0.0]}]
    acc = ["Streamer_L_A0", "Petal_R"]

    # Prefix override "Streamer" forces the source chain to ride a specific bone instead
    # of integrating; "Petal" pinned to an explicit target.
    result = core.build_accessory_physics_remap(
        src, tgt, acc,
        overrides={"Streamer": "follow:LeftBackSkirt2_S", "Petal_R": "rigid"},
        parent_by_name={"Petal_R": "Spine"}, body_remap={"Spine": "Spine"},
    )
    assert result["bones"]["Streamer_L_A0"] == "LeftBackSkirt2_S"
    assert result["strategies"]["Streamer_L_A0"] == "override_follow"
    assert "Streamer_L_A0" not in result["newBones"]  # override beat semantic integrate
    assert result["rigidParent"]["Petal_R"] == "Spine"

    # Without the override the same streamer integrates (semantic default).
    default = core.build_accessory_physics_remap(src, tgt, acc)
    assert "Streamer_L_A0" in default["newBones"]


def test_follow_nearest_override_uses_nearest_swing_bone():
    result = core.build_accessory_physics_remap(
        [{"name": "Petal_A", "position": [0.10, 0.0, 0.0]}],
        [
            {"name": "Spine2", "position": [0.10, 0.0, 0.0]},
            {"name": "Ribbon_S", "position": [0.12, 0.0, 0.0]},
            {"name": "OtherSwing_S", "position": [0.25, 0.0, 0.0]},
        ],
        ["Petal_A"],
        overrides={"Petal_A": "follow_nearest"},
    )
    assert result["bones"] == {"Petal_A": "Ribbon_S"}
    assert result["strategies"]["Petal_A"] == "override_nearest"


def test_source_extra_bone_sidecar():
    result = core.build_source_extra_bones(
        [
            {"name": "Bow_A", "localPosition": [1, 0, 0], "length": 0.1},
            {"name": "Bow_B", "localPosition": [0, 1, 0], "length": 0.2},
        ],
        ["Bow_A", "Bow_B"],
        parent_by_name={"Bow_A": "Spine", "Bow_B": "Bow_A"},
        body_remap={"Spine": "Spine"},
    )
    assert [item["name"] for item in result["newBones"]] == ["Bow_A", "Bow_B"]
    assert result["newBones"][0]["parentName"] == "Spine"
    assert result["newBones"][1]["parentName"] == "Bow_A"
    assert result["extraSwingBones"][0]["parentName"] == "Bow_B"


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
    test_bundle_new_bone_index_and_weight_contract()
    test_bundle_root_bone_authoritative()
    test_source_rig_detection()
    test_bone_remap_presets()
    test_bone_remap_resolution_rules()
    test_source_bone_classification()
    test_accessory_physics_remap()
    test_source_hanging_chain_is_not_centroid_remapped()
    test_lace_rides_skirt_not_nearest_leg()
    test_physics_override_precedence()
    test_source_extra_bone_sidecar()
    test_merge_material_groups()
    print("bundle source contract OK")


# ── 一键打包的接线契约 ────────────────────────────────────────────────────
# 算子硬编码的 CLI flag 必须仍被 patch 脚本接受，且打包脚本必须仍把 patch 脚本
# vendor 进 addon。三者任一漂移，一键打包就静默断裂。纯文本级检查——不 import
# operators（它 import bpy，pytest 环境没有）。

def _flags(text):
    return set(re.findall(r'"(--[a-z-]+)"', text))


def test_operator_flags_are_accepted_by_patch_script():
    ops = (ROOT / "gakumas_mi" / "operators.py").read_text(encoding="utf-8")
    patch = (ROOT / "tools" / "patch_unity_bundle.py").read_text(encoding="utf-8")
    # 算子在 _run_bundle_patch 里传的三个 flag
    passed = {"--template", "--mod-root", "--output"}
    assert passed <= _flags(ops), "operators.py 不再传这些 flag，改了要同步"
    accepted = _flags(patch)
    missing = passed - accepted
    assert not missing, f"patch_unity_bundle.py 不再接受: {missing}"


def test_packaging_vendors_patch_script():
    pkg = (ROOT / "tools" / "package_blender_addon.py").read_text(encoding="utf-8")
    assert "patch_unity_bundle.py" in pkg, "打包脚本不再 vendor patch 脚本，一键打包在装好的插件里会找不到它"
