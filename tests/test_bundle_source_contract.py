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


def test_scsp_preset_survives_the_trailing_one_suffix():
    """SCSP 导出的骨名是「变体名 + _1」，预设规则必须照样命中。

    dress-2219 实测：只查原名时 `LeftArm1_rot_1`、`LeftToe_1` 这类全部落空，
    18 根带权重的身体骨（3514 权重）被误判成装饰骨，脚趾还会撞承重关节闸门。
    """
    target = {"LeftArm", "LeftForeArm", "LeftShoulder", "LeftHand",
              "LeftToeBase", "RightToeBase", "LeftFoot"}
    source = ["LeftArm1_rot_1", "LeftArm2_rot_1", "LeftForeArm_rot_1", "LeftElbow_1",
              "LeftShoulder_rot_1", "LeftClavicle_1", "LeftRing_1",
              "LeftToe_1", "RightToe_1", "LeftFoot_1"]
    report = core.build_bone_remap(source, target, preset_name="scsp")
    assert report["bones"] == {
        "LeftArm1_rot_1": "LeftArm", "LeftArm2_rot_1": "LeftArm",
        "LeftForeArm_rot_1": "LeftForeArm", "LeftElbow_1": "LeftForeArm",
        "LeftShoulder_rot_1": "LeftShoulder", "LeftClavicle_1": "LeftShoulder",
        "LeftRing_1": "LeftHand",
        "LeftToe_1": "LeftToeBase", "RightToe_1": "RightToeBase",
        "LeftFoot_1": "LeftFoot",
    }
    # 不带后缀的写法不能因此回归
    assert core.build_bone_remap(["LeftToe"], target, preset_name="scsp")["bones"] == {
        "LeftToe": "LeftToeBase"}


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


def test_new_bones_use_vanilla_swing_presets():
    """新骨的摆动参数必须按「类别 × 链上角色」取自原版基准表，且**字段写全**。

    以前只写六项（damping/stiffness/spring/mass/rootWeight/pendulum），其余交给运行时
    SetDefaultValues。对照 530 套原版 body 的实测那是错的：`pendulumRange` 原版 84.6% 取 1.0
    （它是 pendulum 的作用范围，留 0 等于把重力项乘没了）、`wind` 84.6% 取 1.0、`useLimit`
    93% 是 1。少写这几项时骨看着"参数齐全"，实际既不下垂也不受风——dress-2219 日志全绿
    却一动不动，这是其中一条。
    """
    records = [
        {"name": "Bow_A", "localPosition": [0, 0, 0], "length": 0.1},
        {"name": "Bow_A_Tip", "localPosition": [0, 0, 0], "length": 0.1},
        # 源自带 swing（IP 源同用 ActorAnimation 中间件，能抽出授权值）优先于基准值，
        # 但源里没有的字段仍要由基准表补齐。
        # 源侧的布尔位写成 1（IP 抽出来就是这样），不能原样漏进 sidecar
        {"name": "Ribbon_A", "localPosition": [0, 0, 0], "length": 0.1,
         "swing": {"damping": 0.3, "mass": 0.1, "useWindGlobalForce": 1}},
    ]
    report = core.build_source_extra_bones(
        records, ["Bow_A", "Bow_A_Tip", "Ribbon_A"],
        parent_by_name={"Bow_A_Tip": "Bow_A"}, body_remap={})
    every = report["newBones"] + report["extraSwingBones"]
    for bone in every:
        for field in ("damping", "stiffness", "spring", "pendulum", "pendulumRange",
                      "mass", "wind", "rootWeight", "useWindGlobalForce", "useLimit",
                      "limitY", "limitZ", "colliderType", "colliderRadius"):
            assert field in bone["swing"], (field, bone)
        assert bone["swing"]["pendulumRange"] > 0, bone   # 留 0 = 重力项失效
        assert bone["swing"]["rootWeight"] < 1.0, bone    # 1.0 = 完全刚性跟随根骨
        # 必须是 JSON 原生 bool。写成 1/0 会让运行时的 nlohmann 抛 type_error.302，
        # 而那一抛是**整份 sidecar 作废、骨架 graft 整个跳过**——实测表现是网格根本没换、
        # 只有贴图生效，日志里只有一行 "type must be boolean, but is number"。
        assert isinstance(bone["swing"]["useWindGlobalForce"], bool), bone
        # 限位是按骨轴授权的，作者骨轴和学马不一致（实测原版子骨在 local -X、MMD 源在
        # local -Z），照搬等于锁死真·摆动轴 —— 默认必须关。
        assert bone["swing"]["useLimit"] == 0, bone

    # 碰撞体三项必须显式写出，不能靠运行时缺省 —— 缺省值不进 sidecar 就查不出来用的是什么。
    # `collisionMask` 从 2026-08-18 起按类别取原版众数（48292 根原版骨：skirt 1 /
    # cloth 64 / sleeve 0 / ribbon 256），不再统一写 -1(Everything)：-1 会让窄裙去撞
    # 半径 0.23m 的胯胶囊，表现是贴腿发僵、穿插。这里钉的是「出的值等于基准表」，
    # 不是钉某个具体数字，改预设不该让这条测试变红。
    presets = core.load_swing_presets()
    # 基准表本身也钉一道：这四个数是 48292 根原版骨的逐档众数，改动它等于改实机行为
    assert {name: roles["roles"]["mid"]["collisionMask"] for name, roles in presets.items()} == {
        "skirt": 1, "cloth": 64, "sleeve": 0, "ribbon": 256}
    for bone in every:
        for field in ("colliderRadius", "colliderType", "collisionMask"):
            assert field in bone["swing"], (field, bone)
        expected = presets[bone["swingCategory"]]["roles"][bone["swingRole"]]["collisionMask"]
        assert bone["swing"]["collisionMask"] == expected, bone

    # 源显式给了 useLimit 就照它的来（IP 源同用 ActorAnimation 中间件，轴向一致）
    kept = core.build_source_extra_bones(
        [{"name": "Src_A", "localPosition": [0, 0, 0], "length": 0.1,
          "swing": {"useLimit": 1, "limitY": [-45, 45]}}],
        ["Src_A"], body_remap={})
    assert kept["newBones"][0]["swing"]["useLimit"] == 1

    roles = {bone["name"]: bone["swingRole"] for bone in every}
    assert roles["Bow_A"] == "root" and roles["Bow_A_Tip"] == "mid"
    assert roles["Bow_A_Tip_End"] == "tip"
    # 链根是惰性锚（自身不摆、由子骨摆），中段和链尾才真的摆——原版一致的语义
    anchor = next(b for b in every if b["name"] == "Bow_A")
    swinging = next(b for b in every if b["name"] == "Bow_A_Tip")
    assert anchor["swing"]["mass"] < swinging["swing"]["mass"]

    ribbon = next(b for b in every if b["name"] == "Ribbon_A")
    assert ribbon["swing"]["damping"] == 0.3 and ribbon["swing"]["mass"] == 0.1
    assert ribbon["swing"]["pendulumRange"] == 1.0   # 源没给的仍走基准表


def test_only_skirt_like_parts_get_a_swing_chain():
    """飘带/蝴蝶结不建 ActorSwingChain —— 原版里它们就是裸 ActorSwingDynamicBone。

    530 套原版实测：裙类 94% 挂链、披风类 54%，而飘带绳结类只有 2.6%。链多带一层
    around/radius 的环形碰撞解算，那是裙摆专用的；给蝴蝶结建链是照着裙摆抄错了对象。
    """
    def chain_of(names, parents):
        records = [{"name": n, "localPosition": [0, 0, 0], "length": 0.1} for n in names]
        return core.build_source_extra_bones(
            records, names, parent_by_name=parents, body_remap={"Hips": "Hips"},
        )["swingChains"]

    bow = chain_of(["Spine_Bow_L", "Spine_Bow_L2"],
                   {"Spine_Bow_L": "Hips", "Spine_Bow_L2": "Spine_Bow_L"})
    assert bow == []

    skirt = chain_of(["FrontSkirt_A", "FrontSkirt_B"],
                     {"FrontSkirt_A": "Hips", "FrontSkirt_B": "FrontSkirt_A"})
    assert len(skirt) == 1
    assert skirt[0]["host"] == "Hips" and skirt[0]["rootBones"] == ["FrontSkirt_A"]
    # 链长含合成链尾：A -> B -> B_End
    assert skirt[0]["chainLength"] == 3


def test_author_swing_category_overrides_the_name_guess():
    """作者在表单里点的部件类型压过按骨名猜，且**对整条链生效**。

    骨名猜不准是常态（MMD 源常是片假名/中文，且源作者会把腰饰绑在胸骨）。点名一根就得
    管整条链，否则同一条链会混用两档参数、上下节硬度对不上。
    """
    names = ["帯_01", "帯_02"]
    records = [{"name": n, "localPosition": [0, 0, 0], "length": 0.1} for n in names]
    parents = {"帯_01": "下半身", "帯_02": "帯_01"}

    def build(categories):
        return core.build_source_extra_bones(
            records, names, parent_by_name=parents,
            body_remap={"下半身": "Hips"}, categories=categories)

    # 认不出来 → 落最保守的 ribbon：自由悬垂、不建链
    auto = build(None)
    assert {b["swingCategory"] for b in auto["newBones"]} == {"ribbon"}
    assert auto["swingChains"] == []

    # 点链上**任意一根**都要对整条链生效——包括中段。以前只沿父链往上找，点中段时链根
    # 找不到、仍按名字猜成 ribbon，于是该建的链没建（实测 categories=['ribbon','skirt']
    # 而 swingChains=[]），和 UI 上写的「选中链上任意一根即对整条链生效」对不上。
    for picked in ("帯_01", "帯_02"):
        forced = build({picked: "skirt"})
        every = forced["newBones"] + forced["extraSwingBones"]
        assert {b["swingCategory"] for b in every} == {"skirt"}, picked
        assert [c["host"] for c in forced["swingChains"]] == ["Hips"], picked
    # 同链多处点名冲突时取最靠近链根的那次，保证一条链只有一个类别
    mixed = build({"帯_01": "cloth", "帯_02": "skirt"})
    assert {b["swingCategory"] for b in mixed["newBones"]} == {"cloth"}

    forced = build({"帯_01": "skirt"})
    every = forced["newBones"] + forced["extraSwingBones"]
    # 换档必须真的换出不同参数，否则这个开关是个摆设
    assert (next(b for b in every if b["name"] == "帯_02")["swing"]["limitZ"]
            != next(b for b in auto["newBones"] if b["name"] == "帯_02")["swing"]["limitZ"])


def test_hair_and_hairprop_share_one_package():
    """发型+发饰必须导成一个包两个 renderer，格式对齐实机验证过的
    IP/06-ab-route-handoff/ab-mods/qa-madoka-ttmr-hair-0002-2b/mod.json。"""
    skeleton = {"nodes": [{"name": "Root", "parent": -1, "weightedIndex": None},
                          {"name": "Hips", "parent": 0, "weightedIndex": 0}]}
    source_mesh = {"m_BindPose": [{"id": "hips"}], "m_Name": "Test"}
    def data():
        return {
            "vertices": [(0, 0, 0)] * 3, "normals": [(0, 0, 1)] * 3,
            "tangents": [(1, 0, 0, 1)] * 3, "uv0": [(0, 0)] * 3,
            "colors": [(0, 0, 1, 0)] * 3, "faces": [(0, 1, 2)],
            "materials": [0, 0, 0], "skin": [[(0, 1.0)]] * 3, "source_rig_report": {},
        }
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        mesh_path, skeleton_path = root / "mesh.json", root / "skeleton.json"
        mesh_path.write_text(json.dumps(source_mesh), encoding="utf-8")
        skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
        bundle_dir = root / "hairpkg" / "bundle-src"
        bundle_dir.mkdir(parents=True)
        for name in ("hair_slot0_t0.png", "hairprop_slot0_t0.png"):
            (bundle_dir / name).write_bytes(b"png")
        output = core.write_bundle_source(
            root, "hairpkg", "mdl_chr_ttmr-hair-0002_hair", "hair", "Hair", "Author",
            data(), mesh_path, skeleton_path,
            [{"materialSlot": 0, "property": "_BaseMap", "filename": "hair_slot0_t0.png"},
             {"materialSlot": 0, "property": "_BaseMap", "filename": "hairprop_slot0_t0.png",
              "rendererName": "Geo_HairProp"}],
            extra_components=[{"component_id": "hairprop", "data": data(),
                               "mesh_json": mesh_path, "skeleton_json": skeleton_path}],
        )
        manifest = json.loads((output / "mod.json").read_text(encoding="utf-8"))
        replacement = manifest["replacements"][0]
        assert replacement["part"] == "hair"
        rules = replacement["renderers"]
        assert [rule["targetRenderer"] for rule in rules] == ["Geo_Hair", "Geo_HairProp"]
        # 主 renderer 继承顶层 source/skeleton，副 renderer 自带
        assert "source" not in rules[0] and "skeleton" not in rules[0]
        prop_source = "mdl_chr_ttmr-hair-0002_hair__Geo_HairProp"
        assert rules[1]["source"] == prop_source
        assert rules[1]["skeleton"] == f"Assets/Mods/hairpkg/{prop_source}_bones.json.txt"
        # 两份 geojson / 两份 sidecar 都在，且盖同一个 buildId
        assert (output / "mdl_chr_ttmr-hair-0002_hair.geojson.txt").is_file()
        assert (output / f"{prop_source}.geojson.txt").is_file()
        prop_sidecar = json.loads((output / f"{prop_source}_bones.json.txt").read_text(encoding="utf-8"))
        assert prop_sidecar["buildId"] == manifest["buildId"]
        assert prop_sidecar["runtimeProtocol"] == core.AB_RUNTIME_PROTOCOL
        # 贴图按 renderer 分流
        by_renderer = {item["rendererName"] for item in replacement["textures"]}
        assert by_renderer == {"Geo_Hair", "Geo_HairProp"}


def test_hairprop_only_package_is_hair_part():
    """单独导发饰时 part 也必须是 hair —— 写成 body 会被运行时当身体 mod，装了没反应。"""
    skeleton = {"nodes": [{"name": "Root", "parent": -1, "weightedIndex": None},
                          {"name": "Hips", "parent": 0, "weightedIndex": 0}]}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        mesh_path, skeleton_path = root / "mesh.json", root / "skeleton.json"
        mesh_path.write_text(json.dumps({"m_BindPose": [{"id": "hips"}], "m_Name": "T"}), encoding="utf-8")
        skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
        bundle_dir = root / "proppkg" / "bundle-src"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "hairprop_slot0_t0.png").write_bytes(b"png")
        output = core.write_bundle_source(
            root, "proppkg", "mdl_chr_ttmr-hair-0002_hair", "hairprop", "P", "A",
            {"vertices": [(0, 0, 0)] * 3, "normals": [(0, 0, 1)] * 3,
             "tangents": [(1, 0, 0, 1)] * 3, "uv0": [(0, 0)] * 3,
             "colors": [(0, 0, 1, 0)] * 3, "faces": [(0, 1, 2)],
             "materials": [0, 0, 0], "skin": [[(0, 1.0)]] * 3, "source_rig_report": {}},
            mesh_path, skeleton_path,
            [{"materialSlot": 0, "property": "_BaseMap", "filename": "hairprop_slot0_t0.png"}],
        )
        manifest = json.loads((output / "mod.json").read_text(encoding="utf-8"))
        assert manifest["replacements"][0]["part"] == "hair"


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
    test_new_bones_carry_root_weight_and_pendulum()
    test_hair_and_hairprop_share_one_package()
    test_hairprop_only_package_is_hair_part()
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


def test_bundle_patch_subprocess_is_bounded_and_utf8():
    """外部 Python 不能无限挂住 Blender，输出编码也不能跟着系统代码页漂移。"""
    ops = (ROOT / "gakumas_mi" / "operators.py").read_text(encoding="utf-8")
    assert '[python_exe, "-X", "utf8", str(script)' in ops
    assert 'encoding="utf-8"' in ops
    assert 'errors="replace"' in ops
    assert 'timeout=_BUNDLE_PATCH_TIMEOUT_SECONDS' in ops
    assert 'except subprocess.TimeoutExpired' in ops


def test_bundle_textures_only_cover_used_groups():
    """贴图按【用到的段】出，不按目标资源的段数出。

    cstm-0119 全系列原版 body 是 3 段。按 range(target_n) 出的话，没做 co 部件的
    工程会被空着的段 1 拽去要「原生 co 基础色 t0」，导出直接报“材质槽 1 缺少 t0”。
    """
    ops = (ROOT / "gakumas_mi" / "operators.py").read_text(encoding="utf-8")
    assert "for group in used_groups" in ops
    assert "for group in range(target_n)" not in ops, "贴图又按目标段数出了，空段会硬要 co 贴图"


def test_forked_chain_is_not_built():
    """分叉的链不建：`UpdateChainInfo` 只沿**第一个**子节点建层。

    一根骨带两个子分支时，我们却按"最深那支"报了个链长，等于静默建了条只覆盖一半的链。
    不建是安全降级——那些骨照样进 `swingDynamicBones` 逐骨模拟（原版飘带就是这么摆的），
    只是没有链那层环形碰撞。
    """
    def chains(names, parents):
        records = [{"name": n, "localPosition": [0, 0, 0], "length": 0.1} for n in names]
        return core.build_source_extra_bones(
            records, names, parent_by_name=parents,
            body_remap={"Hips": "Hips"})["swingChains"]

    forked = chains(["SkirtRoot", "SkirtLeft", "SkirtRight"],
                    {"SkirtRoot": "Hips", "SkirtLeft": "SkirtRoot", "SkirtRight": "SkirtRoot"})
    assert forked == []
    linear = chains(["SkirtA", "SkirtB"], {"SkirtA": "Hips", "SkirtB": "SkirtA"})
    assert [c["rootBones"] for c in linear] == [["SkirtA"]]


def test_swing_category_rules_match_the_scanner():
    """插件的分类规则必须和产出基准表的扫描器一致 —— **词表和顺序都要**。

    词表分叉：Gown/Shirt/Inner 曾在扫描器算 cloth、在插件落 ribbon。
    顺序分叉：`BeltChain`(belt→cloth / chain→ribbon)、`CapeRibbon`、`CollarBow` 这类两边
    词表都命中的名字，先判哪个就归哪类；插件曾把 cloth 排在 ribbon 前面，这几个名字两边
    分类相反。**上一版测试把规则转成 dict，正好丢掉了顺序，所以没拦住。**
    """
    source = (ROOT / "tools" / "scan_vanilla_swing_bones.py").read_text(encoding="utf-8")
    start = source.index("CATEGORY_RULES = (")
    end = source.index(chr(10) + ")", start) + 2
    scanner = eval(source[start:end].split("=", 1)[1].strip())
    plugin = list(core._SWING_CATEGORY_RULES)

    # skin 是身体软组织，插件不提供这一档；其余类别的**相对顺序**必须一致
    scanner_order = [name for name, _ in scanner if name != "skin"]
    assert [name for name, _ in plugin] == scanner_order

    for (name, tokens), (plugin_name, plugin_tokens) in zip(
            [item for item in scanner if item[0] != "skin"], plugin):
        assert name == plugin_name
        missing = sorted(set(tokens) - set(plugin_tokens))
        assert not missing, (name, missing)

    # 两边词表都命中的名字，分类结果必须一样
    def scanner_category(part):
        lower = part.lower()
        for name, tokens in scanner:
            if any(token in lower for token in tokens):
                return name
        return "ribbon"

    for part in ("BeltChain", "CapeRibbon", "CollarBow", "ClothTie", "InnerLace",
                 "Gown", "Shirt", "Inner", "Acce", "Neckless"):
        assert core.swing_category(part) == scanner_category(part), part


def test_unknown_swing_category_is_rejected():
    """手写覆盖文件里拼错的类别必须报错，不能静默降级。

    以前 `{"SkirtA": "skrit"}` 会原样留在 sidecar 里：参数悄悄回退到 ribbon，还因为非法
    类别查不到 useChain 而不建链 —— 两处静默降级，作者只会觉得"设了没用"。
    """
    records = [{"name": "SkirtA", "localPosition": [0, 0, 0], "length": 0.1}]
    try:
        core.build_source_extra_bones(
            records, ["SkirtA"], parent_by_name={"SkirtA": "Hips"},
            body_remap={"Hips": "Hips"}, categories={"SkirtA": "skrit"})
    except ValueError as error:
        assert "skrit" in str(error) and "skirt" in str(error)
    else:
        raise AssertionError("拼错的类别没有被拒绝")

    # 正确的类别照常工作
    report = core.build_source_extra_bones(
        records, ["SkirtA"], parent_by_name={"SkirtA": "Hips"},
        body_remap={"Hips": "Hips"}, categories={"SkirtA": "skirt"})
    assert report["newBones"][0]["swingCategory"] == "skirt"


def test_mmd_twist_bones_land_on_the_corrective_rig():
    """源模型自带的捩骨要落到 `*_Roll_H`，不是折叠进 humanoid 骨。

    折叠进 `LeftArm` 的后果是 16 根 `*_H` 一份权重都拿不到（4 个已出货成品实测 0.00%，
    原版中位 11.28%），扭转分配整个丢掉 —— 姿势驱动器就装在这些骨上。
    这不是权重重分配，只是换个落点，作者的权重数值一个都没动。
    """
    target = {
        "LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm",
        "LeftArm_Roll_H", "LeftForeArm_Roll_H", "RightArm_Roll_H", "RightForeArm_Roll_H",
    }
    report = core.build_bone_remap(
        ["左腕", "左ひじ", "左手首", "左腕捩", "左腕捩2", "左手捩", "右腕捩", "右手捩3"],
        target, preset_name="mmd-standard",
    )
    assert report["bones"]["左腕捩"] == "LeftArm_Roll_H"
    assert report["bones"]["左腕捩2"] == "LeftArm_Roll_H"
    assert report["bones"]["左手捩"] == "LeftForeArm_Roll_H"
    assert report["bones"]["右腕捩"] == "RightArm_Roll_H"
    assert report["bones"]["右手捩3"] == "RightForeArm_Roll_H"
    # humanoid 骨本身不受影响
    assert report["bones"]["左腕"] == "LeftArm"


def test_twist_bones_fall_back_when_the_target_has_no_corrective_rig():
    """目标骨架没有 `*_Roll_H` 时退回 humanoid 骨——绝不能整根掉进 unmapped 把权重丢掉。"""
    target = {"LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm"}
    report = core.build_bone_remap(
        ["左腕", "左腕捩", "左手捩", "右腕捩"], target, preset_name="mmd-standard",
    )
    assert report["bones"]["左腕捩"] == "LeftArm"
    assert report["bones"]["左手捩"] == "LeftForeArm"
    assert report["bones"]["右腕捩"] == "RightArm"
    assert not [name for name in report["unmapped"] if "捩" in name]


def test_weighted_reference_keeps_unity_uv_orientation(tmp_path):
    """Mesh JSON 的 UV 原样进 Blender：Unity 与 Blender 的原点都在左下，翻 v 就是错的。

    导出端不翻回去（`operators._inverse_skin_export_data` 原样写 Blender 的 UV 层），
    所以这里翻一次 = 出包的贴图上下颠倒着采（chs-sucu 实测：整身贴图错乱）。
    """
    mesh = tmp_path / "mesh.json"
    skeleton = tmp_path / "skeleton.json"
    mesh.write_text(json.dumps({
        "m_VertexCount": 1,
        "m_Vertices": [0.0, 0.0, 0.0],
        "m_Normals": [0.0, 1.0, 0.0],
        "m_Tangents": [1.0, 0.0, 0.0, 1.0],
        "m_Colors": [1.0, 1.0, 1.0, 1.0],
        "m_UV0": [0.25, 0.75],
        "m_UV1": [0.125, 0.875],
        "m_Indices": [],
        "m_Skin": [{"weight": [1.0, 0, 0, 0], "boneIndex": [0, 0, 0, 0]}],
        "m_BindPose": [{}],
    }), encoding="utf-8")
    skeleton.write_text(json.dumps({"weightedBoneCount": 1, "nodes": []}), encoding="utf-8")

    data = core.read_weighted_reference(mesh, skeleton)
    assert data["uv0"] == [(0.25, 0.75)]
    assert data["uv1"] == [(0.125, 0.875)]


def test_new_bone_names_must_not_collide_with_the_target_rig():
    """契约 §4.1：自建骨不许和目标骨架重名（坏样本会报 / 正常样本不误报）。"""
    target = ["Hips", "RightFrontSkirt1_S", "LeftUpLeg"]
    message = core.new_bone_name_collision_error(["RightFrontSkirt1_S", "MyRibbon1"], target)
    assert message and "RightFrontSkirt1_S" in message
    assert core.new_bone_name_collision_error(["chssucu_RightFrontSkirt1_S"], target) is None
    assert core.new_bone_name_collision_error([], target) is None


def test_chain_tip_follows_the_geometry_not_the_bone_axis():
    """链尾按主导顶点质心放；没有几何时才退回骨长沿局部 -Z。

    链尾定义"这一节朝哪儿"。硬写 `[0,0,-骨长]` 用的是 Blender 骨的默认轴，而源骨的局部轴
    是任意的 —— chs-sucu 实测：三片前裙板的链尾世界方向是正侧向，画面上裙片整体偏一边。
    """
    args = (
        [{"name": "Panel_A", "localPosition": [1, 0, 0], "length": 0.055}],
        ["Panel_A"],
    )
    kwargs = {"parent_by_name": {"Panel_A": "Hips"}, "body_remap": {"Hips": "Hips"}}

    geometry = core.build_source_extra_bones(
        *args, tip_offset_by_name={"Panel_A": [0.01, -0.10, 0.0]}, **kwargs)
    assert geometry["extraSwingBones"][0]["localPosition"] == [0.01, -0.10, 0.0]

    fallback = core.build_source_extra_bones(*args, **kwargs)
    assert fallback["extraSwingBones"][0]["localPosition"] == [0.0, 0.0, -0.055]


def test_anchor_only_roots_flags_chains_whose_geometry_sits_on_the_root():
    """表单常驻黄标的判据：几何全在链根、子骨是空的 → 装了摇物也不会动。"""
    parents = {"Lace_A0": "Hips", "Lace_Aend": "Lace_A0",
               "Bow_A0": "Hips", "Bow_A1": "Bow_A0"}
    members = ["Lace_A0", "Lace_Aend", "Bow_A0", "Bow_A1"]
    dominant = {"Lace_A0": 97, "Lace_Aend": 0, "Bow_A0": 12, "Bow_A1": 40}
    # Lace：97 个主导顶点全在链根，子骨 0 → 要标；Bow：子骨扛着几何 → 不标
    assert core.anchor_only_roots(members, parents, dominant) == ["Lace_A0"]
    # 链根自己没有几何（纯锚点）也不该标
    assert core.anchor_only_roots(
        members, parents, {"Lace_A0": 0, "Lace_Aend": 30}) == []
