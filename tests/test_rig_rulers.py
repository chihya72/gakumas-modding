"""批次 1 的两把尺子：逐骨静止对齐（位置 + **朝向**）与跨关节权重带。

朝向是作者唯一自查不到的东西 —— 绕骨自身轴的滚转差在静止截图里完全正常，转身之后手臂整个
炸开、手指变面条（实机三次坐实，肩差 172°）。所以这里的判据里必须有"172° 报红"这一条。

跨关节带是唯一能**预判**"肩膀会不会崩"的数字：原版肩 13.3%，作者那副 rip 只有 4.9%。
"""
import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_core", ROOT / "gakumas_mi" / "core.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


# 一副对齐好的胳膊：肩 → 大臂 → 小臂 → 手，都在 Unity 空间（y 向上、x 向侧）。
GAME = {
    "LeftShoulder": (0.05, 1.40, 0.0),
    "LeftArm": (0.15, 1.40, 0.0),
    "LeftForeArm": (0.40, 1.40, 0.0),
    "LeftHand": (0.62, 1.40, 0.0),
}
CHILDREN = {"LeftShoulder": ["LeftArm"], "LeftArm": ["LeftForeArm"],
            "LeftForeArm": ["LeftHand"]}
LENGTHS = {"LeftShoulder": 0.10, "LeftArm": 0.25, "LeftForeArm": 0.22, "LeftHand": 0.08}


def test_self_consistent_rig_is_all_green():
    """源就是目标自己时必须 0.0mm / 0.0° 全绿 —— 尺子在正常样本上不许误报（INV-8）。"""
    rows = core.rest_alignment(dict(GAME), GAME, CHILDREN, LENGTHS)
    assert [row["grade"] for row in rows] == ["green"] * 4
    assert max(row["mm"] for row in rows) < 1e-9
    assert max(row["deg"] or 0.0 for row in rows) < 1e-9


def test_shoulder_off_by_172_degrees_is_red():
    """已知坏样本：源的大臂从肩上朝身后长（Claymore rip 实测肩 172.5°）。

    肩**本身的位置**完全对上 —— 只量位置的尺子看不见它，这正是作者自查不到的那一种。
    """
    source = dict(GAME)
    source["LeftArm"] = (0.05 - 0.099, 1.40, -0.014)      # 从肩点朝身后偏 172°
    rows = {row["bone"]: row for row in
            core.rest_alignment(source, GAME, CHILDREN, LENGTHS)}
    assert rows["LeftShoulder"]["grade"] == "red"
    assert abs(rows["LeftShoulder"]["deg"] - 172.0) < 1.0
    assert rows["LeftShoulder"]["mm"] < 1e-9     # 肩自己一点没偏
    assert rows["LeftShoulder"]["child"] == "LeftArm"


def test_roll_about_the_bone_axis_is_not_flagged():
    """绕骨轴的 roll 不算朝向差 —— 2026-08-17 拿原版自己的身体标定过。

    插件重建参考骨架时 roll 就没保留（`_create_armature` 只按 head→tail + 默认 roll 建骨）：
    104 根里 69 根整体转角正好 180°、骨轴向差 0.00°。按整体转角判，**原版自己全红**。
    这个判据只看位移方向，所以对 roll 免疫。
    """
    rows = core.rest_alignment(dict(GAME), GAME, CHILDREN, LENGTHS)
    assert {row["grade"] for row in rows} == {"green"}


def test_only_humanoid_children_count():
    """脊椎下面挂一堆下垂的衣物骨会把方向拽反（实测报 154°）—— children 只给人形子骨。"""
    source = dict(GAME)
    source["LeftSkirt1"] = (0.05, 1.00, 0.0)     # 从肩往下垂的装饰骨，不该参与判定
    target = dict(GAME)
    target["LeftSkirt1"] = (0.05, 1.00, 0.0)
    clean = core.rest_alignment(source, target, CHILDREN, LENGTHS)
    assert {row["grade"] for row in clean} == {"green"}
    polluted = core.rest_alignment(
        source, target, dict(CHILDREN, LeftShoulder=["LeftArm", "LeftSkirt1"]), LENGTHS)
    assert {row["grade"] for row in polluted} == {"green"}   # 位置都对，只是多量一个方向


def test_leaf_bones_report_unmeasurable_not_zero():
    """末节骨没有人形子骨 —— 报"量不了"，别显示成 0°（那是"已对齐"的意思）。"""
    row = {item["bone"]: item for item in
           core.rest_alignment(dict(GAME), GAME, CHILDREN, LENGTHS)}["LeftHand"]
    assert row["deg"] is None and row["grade"] == "green"
    assert core.format_degrees(row["deg"]) == "量不了"
    assert core.format_degrees(172.0) == "172.0°"


def test_position_is_judged_against_bone_length_and_never_red():
    """8mm 在手指骨节上要报，在大腿上不用；但位置最高只判黄 —— 会炸的是朝向，不是位置。

    lossless 蒙皮把静止位置差当重定向吸收（"免的是位置"），所以位置差是"该对齐"不是"会炸"。
    """
    finger = core.rest_alignment({"LeftHandIndex1": (0.008, 0, 0)},
                                 {"LeftHandIndex1": (0.0, 0, 0)},
                                 {}, {"LeftHandIndex1": 0.022})
    thigh = core.rest_alignment({"LeftUpLeg": (0.008, 0, 0)}, {"LeftUpLeg": (0.0, 0, 0)},
                                {}, {"LeftUpLeg": 0.30})
    huge = core.rest_alignment({"Hips": (0.20, 0, 0)}, {"Hips": (0.0, 0, 0)},
                               {}, {"Hips": 0.10})
    assert finger[0]["grade"] == "yellow"
    assert thigh[0]["grade"] == "green"
    assert huge[0]["grade"] == "yellow"       # 20cm 也只是黄


PARENTS = {
    "Hips": None, "Spine": "Hips", "Spine1": "Spine",
    "LeftShoulder": "Spine1", "LeftArm": "LeftShoulder",
    "LeftForeArm": "LeftArm", "LeftHand": "LeftForeArm",
    "LeftHandIndex1": "LeftHand",
}


def test_cross_joint_band_counts_only_vertices_that_span_the_joint():
    sides = core.joint_band_sides(PARENTS)
    # 远侧包含整条子树：手指也算"肩关节的远侧"
    assert sides["肩"]["LeftHandIndex1"] == 2
    assert sides["肩"]["LeftShoulder"] == 1
    assert sides["肩"].get("Hips") is None        # 近端骨的子树之外，两侧都不算

    vertices = [
        {"LeftShoulder": 0.6, "LeftArm": 0.4},    # 跨肩
        {"LeftShoulder": 1.0},                    # 只在近侧
        {"LeftArm": 1.0},                         # 只在远侧
        {"LeftShoulder": 0.999, "LeftArm": 0.001},  # 权重低于阈值 → 不算跨
        {"Hips": 1.0},                            # 与肩无关，不进分母
    ]
    band = core.cross_joint_bands(vertices, sides)["肩"]
    assert (band["cross"], band["total"]) == (1, 4)
    assert abs(band["share"] - 0.25) < 1e-9


def test_shoulder_band_far_below_vanilla_is_red():
    """作者那副 rip 的真值：跨肩带 4.9% vs 原版 13.3% → 报红（原版的四成以下）。"""
    mod = {"肩": {"cross": 49, "total": 1000, "share": 0.049},
           "肘": {"cross": 35, "total": 1000, "share": 0.035}}
    rows = {row["joint"]: row for row in core.cross_joint_band_findings(mod)}
    assert rows["肩"]["grade"] == "red"
    assert abs(rows["肩"]["vanilla"] - 0.133) < 1e-9
    # 肘 3.5% vs 原版 3.9%：低于原版但没到四成以下 —— 值得看，不是崩
    assert rows["肘"]["grade"] == "yellow"


def test_vanilla_reference_bands_beat_the_table():
    """场景里有带权重参考体时用它现算的基线，而不是写死的真值表。"""
    mod = {"肩": {"cross": 100, "total": 1000, "share": 0.10}}
    vanilla = {"肩": {"cross": 110, "total": 1000, "share": 0.11}}
    row = core.cross_joint_band_findings(mod, vanilla)[0]
    assert abs(row["vanilla"] - 0.11) < 1e-9
    assert row["grade"] == "yellow"       # 按真值表 13.3% 也是黄，但基线得是参考体那个数


def test_collapsed_reference_child_is_not_measured():
    """参考向量塌了就别量朝向 —— MMD 的 腰/下半身 都映射到 Hips，赢的那根离 Spine 源骨
    只有 3.5mm（游戏侧 75.1mm），量出来 35° 是假阳性，模型没毛病。实机 blend 上坐实过。
    """
    game = {"Hips": (0.0, 0.90, 0.0), "Spine": (0.0, 0.9751, 0.0)}
    children, lengths = {"Hips": ["Spine"]}, {"Hips": 0.075}
    # 源的 Hips 落在 Spine 源骨下方 3.5mm，方向随便偏一点 —— 3.5mm 的向量没有方向可言
    source = {"Hips": (0.002, 0.9751 - 0.0029, 0.0), "Spine": (0.0, 0.9751, 0.0)}
    row = core.rest_alignment(source, game, children, lengths)[0]
    assert row["deg"] is None and row["child"] is None   # 量不了，不是 0°
    assert row["grade"] != "red"
    # 同样的角度、参考向量不退化 → 照样报红，别把闸门放漏了
    healthy = dict(source)
    healthy["Hips"] = (0.043, 0.9751 - 0.0617, 0.0)      # 离 Spine 75mm，偏 35°
    row = core.rest_alignment(healthy, game, children, lengths)[0]
    assert row["deg"] is not None and row["deg"] >= core.ORIENTATION_FAIL_DEG


MIRROR_GAME = {
    "LeftShoulder": (-0.05, 1.40, 0.0), "RightShoulder": (0.05, 1.40, 0.0),
    "LeftArm": (-0.15, 1.40, 0.0), "RightArm": (0.15, 1.40, 0.0),
    "LeftHand": (-0.62, 1.40, 0.0), "RightHand": (0.62, 1.40, 0.0),
    "LeftUpLeg": (-0.09, 0.85, 0.0), "RightUpLeg": (0.09, 0.85, 0.0),
    "LeftFoot": (-0.08, 0.11, 0.0), "RightFoot": (0.08, 0.11, 0.0),
}


def test_unmirrored_source_is_caught():
    """MMD 的 .L 在 +X、游戏的 Left 在 −X。整副没镜像 = 五对全反，而位置差照样很小
    （身体左右对称），所以只有符号这一把尺子看得见它。
    """
    source = {name: (-x, y, z) for name, (x, y, z) in MIRROR_GAME.items()}
    assert core.mirrored_side_pairs(source, MIRROR_GAME) == list(core.MIRROR_CHECK_PAIRS)
    message = core.mirrored_side_error(source, MIRROR_GAME)
    assert message and "镜像" in message and "骨骼映射表" in message


def test_aligned_and_partial_and_degenerate_sides():
    assert core.mirrored_side_pairs(dict(MIRROR_GAME), MIRROR_GAME) == []
    assert core.mirrored_side_error(dict(MIRROR_GAME), MIRROR_GAME) is None
    # 只有一对反 = 那两根的映射写反了，不是整副镜像；也要报出来
    partial = dict(MIRROR_GAME)
    partial["LeftHand"], partial["RightHand"] = MIRROR_GAME["RightHand"], MIRROR_GAME["LeftHand"]
    assert core.mirrored_side_pairs(partial, MIRROR_GAME) == [("LeftHand", "RightHand")]
    # 左右挤在一起（局部骨架 / 没摆开的骨）不判：那是噪声不是左右
    squashed = dict(MIRROR_GAME)
    squashed["LeftFoot"] = squashed["RightFoot"] = (0.0, 0.11, 0.0)
    assert ("LeftFoot", "RightFoot") not in core.mirrored_side_pairs(squashed, MIRROR_GAME)


HAND = {
    "LeftHand": (0.62, 1.40, 0.0),
    "LeftHandIndex1": (0.70, 1.40, 0.02), "LeftHandMiddle1": (0.706, 1.40, 0.0),
    "LeftHandRing1": (0.70, 1.40, -0.02), "LeftHandPinky1": (0.69, 1.40, -0.04),
    "LeftHandThumb1": (0.647, 1.387, 0.023),
}
HAND_CHILDREN = {"LeftHand": ["LeftHandIndex1", "LeftHandMiddle1", "LeftHandRing1",
                              "LeftHandPinky1", "LeftHandThumb1"]}


def test_one_outlier_child_does_not_redden_the_parent():
    """手有五个人形子骨。MMD 的拇指根比游戏往外 15mm —— 四个子骨 0.3~3.3°、拇指 20°。
    那 20° 是**拇指自己的位置**差（已有位置行在报），不是手的朝向差，不许把手判红。
    """
    source = dict(HAND)
    source["LeftHandThumb1"] = (0.66, 1.395, 0.026)      # 拇指根往外挪，方向偏 ~20°
    row = {r["bone"]: r for r in
           core.rest_alignment(source, HAND, HAND_CHILDREN, {"LeftHand": 0.08})}["LeftHand"]
    assert row["deg"] < core.ORIENTATION_FAIL_DEG
    assert row["grade"] != "red"


def test_whole_hand_rotated_is_still_red():
    """反过来：手真的转了，五个子骨会一起偏，中位数照样报红——别为了放过拇指把闸门放漏。"""
    def spun(point):                                      # 绕手腕在 xz 平面转 40°
        dx, dz = point[0] - 0.62, point[2]
        angle = math.radians(40.0)
        return (0.62 + dx * math.cos(angle) - dz * math.sin(angle), point[1],
                dx * math.sin(angle) + dz * math.cos(angle))
    source = {name: (point if name == "LeftHand" else spun(point))
              for name, point in HAND.items()}
    row = {r["bone"]: r for r in
           core.rest_alignment(source, HAND, HAND_CHILDREN, {"LeftHand": 0.08})}["LeftHand"]
    assert row["grade"] == "red" and abs(row["deg"] - 40.0) < 3.0


def test_two_children_still_take_the_worst():
    """子骨只有 1~2 个时没有"多数"可言，保持取最差——肩差 172° 那条实测坏样本就是单子骨。"""
    two = {"LeftHand": ["LeftHandThumb1", "LeftHandMiddle1"]}
    source = dict(HAND)
    source["LeftHandThumb1"] = (0.66, 1.395, 0.026)
    row = {r["bone"]: r for r in
           core.rest_alignment(source, HAND, two, {"LeftHand": 0.08})}["LeftHand"]
    assert row["deg"] > core.ORIENTATION_FAIL_DEG and row["child"] == "LeftHandThumb1"


def test_inverted_mesh_is_caught():
    """镜像后没翻回来 = 全部面朝里。实测这个模型 signed volume = -0.41 m³，
    烧掉两轮进游戏才发现，而离线一次散度定理积分就够。"""
    assert core.inverted_mesh_error(-0.4118) is not None
    assert "Alt+N" in core.inverted_mesh_error(-0.4118)
    assert core.inverted_mesh_error(0.4118) is None
    assert core.inverted_mesh_error(0.0) is None          # 平面/开放面片不冤枉
    assert core.inverted_mesh_error(None) is None


def test_orphaned_subtree_merge_is_caught():
    """并进游戏衣物骨、子骨却留在 mod 骨架里 → 整支子树被外来物理拽走。

    实测坏样本：`スカート_1_2` 并进 `LeftFrontSideSkirt1_S`，第 2 列从 `スカート_2_2`
    往下整支重挂到那根原版骨上，三分之一的裙面飞出去，而所有现有闸门全绿。
    """
    mapping = {"スカート_1_2": "LeftFrontSideSkirt1_S", "スカート_0_2": "LeftFrontSkirt1_S"}
    parents = {"スカート_2_2": "スカート_1_2", "スカート_3_2": "スカート_2_2"}
    orphans = core.orphaned_subtree_merges(mapping, ["スカート_2_2", "スカート_3_2"], parents)
    assert orphans == [("スカート_1_2", "スカート_2_2")]
    assert core.orphaned_subtree_error(orphans) is not None
    # 整条链一起并过去 = 没有孤儿，不该报
    assert core.orphaned_subtree_merges(mapping, [], parents) == []
    assert core.orphaned_subtree_error([]) is None


def test_mixed_family_directive_row_is_caught():
    """结构组装得下互不相干的两件衣服：实测一行 177 根 = 大半条裙子 + 全部经文。

    判据是**横跨几个骨族**，不是行有多大 —— 整条裙子 192 根同族骨下一个指令完全正常，
    按大小拦就会误伤它。族名去掉尾部编号段和左右后缀；互为前缀的族并成一组。
    """
    assert core.bone_family("スカート_0_0") == "スカート"
    assert core.bone_family("经文3_3_1") == "经文"
    assert core.bone_family("3袖子_0_1") == "3袖子"          # 前导数字不是编号段
    assert core.bone_family("蝴蝶结带.L") == "蝴蝶结带"        # 左右后缀不是另一件衣服
    assert core.bone_family("左腕") == core.bone_family("右腕") == "腕"
    # `蝴蝶结` 与 `蝴蝶结带` 互为前缀 = 同一件饰品；`裙带` 与 `裙飘带` 只是共享 `裙`，不是
    assert core.family_groups(["蝴蝶结", "蝴蝶结带"]) == ["蝴蝶结"]
    assert sorted(core.family_groups(["裙带", "裙飘带"])) == ["裙带", "裙飘带"]

    skirt = ["スカート_%d_%d" % (r, c) for r in range(12) for c in range(16)]
    rows = [
        ("经文3_3_1 等", "integrate", ["经文3_%d_1" % i for i in range(12)] + skirt[:165]),
        ("经文1_7_1 等", "integrate",
         ["经文1_%d_1" % i for i in range(11)] + ["裙带_0_1"] + skirt[:25]),
        ("スカート_0_0 等", "native_driver", skirt),          # 192 根同族，必须放行
        ("裙飘带1_6_2 等", "follow_nearest",
         ["裙飘带1_%d_%d" % (a, b) for a in range(7) for b in range(3)]),
        ("混族但没下指令", "auto", ["スカート_0_0", "经文1_0_1"] * 8),
        # 实测误报：一个蝴蝶结 5 根骨被判成横跨 5 族，硬拦住一个完全正常的饰品
        ("蝴蝶结 等", "integrate",
         ["蝴蝶结", "蝴蝶结.R", "蝴蝶结.L", "蝴蝶结带.L", "蝴蝶结带.R"]),
    ]
    mixed = core.mixed_family_directive_rows(rows)
    assert [name for name, _f in mixed] == ["经文3_3_1 等", "经文1_7_1 等"]
    assert core.mixed_family_directive_error(mixed) is not None
    assert core.mixed_family_directive_error([]) is None
    # 骨太少的行一律不拦：成员在面板里一眼看得完，硬拦的代价大于收益
    tiny = [("小混族", "integrate", ["スカート_0_0", "经文1_0_1", "裙带_0_1"])]
    assert core.mixed_family_directive_rows(tiny) == []


def test_chain_blend_ruler_flags_hard_edged_weights():
    """跨节权重过渡带：MMD 裙 1.2% vs 原版 79.4%，差 66 倍，而现有尺子一个都看不见。"""
    node_of = {"A0": ("A", 0), "A1": ("A", 1), "A2": ("A", 2)}
    hard = [{"A0": 1.0}] * 60 + [{"A1": 1.0}] * 60      # 每个顶点只沾一节
    soft = [{"A0": 0.6, "A1": 0.4}] * 60 + [{"A1": 0.5, "A2": 0.5}] * 60
    assert core.chain_blend_ratio(hard, node_of)["A"][1] == 0.0
    assert core.chain_blend_ratio(soft, node_of)["A"][1] == 1.0
    findings = core.chain_blend_findings(core.chain_blend_ratio(hard, node_of),
                                         core.chain_blend_ratio(soft, node_of))
    assert findings and findings[0]["chain"] == "A"
    assert core.chain_blend_note(findings) is not None
    # 过渡带够厚就不报；顶点太少的链也不报（噪声）
    assert core.chain_blend_findings(core.chain_blend_ratio(soft, node_of)) == []
    assert core.chain_blend_findings(core.chain_blend_ratio(hard[:10], node_of)) == []
