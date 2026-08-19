"""实机日志尺子自己的自检：坏日志必须报、好日志不许误报。

这把尺子的整个价值在于"进游戏一次，回来只跑它"。所以它自己错一次，代价是一次白跑的实机。
样本行都是**真实日志里出现过的形状**（2026-08-18 用 D:/Games/gakumas 那份校准）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_log", ROOT / "tools" / "read_runtime_log.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)

BOOT = "[BOOT] GakumasMod: [ModAsset] gakumas-mod-runtime dev loaded. logLevel=info\n"

GOOD = BOOT + """\
[INFO] GakumasMod: [ModAsset] Applied lossless IP skeleton graft: droppedInfluences=0 fallbackVertices=0
[INFO] GakumasMod: [ModAsset] ActorSwing registration coverage: swingDynamicBones=178 initialTransforms=178 modBonesRegistered=42/42 missing=(none)
[WARN] GakumasMod: [ModAsset][EXPERIMENT] Swing motion probe watching 23 of 178 swing bones on this actor
[WARN] GakumasMod: [ModAsset][EXPERIMENT] Swing motion over 300 frames: 17/23 bones moved, best=Bone_SkirtA02_R 94.42deg - simulated
[INFO] GakumasMod: [ModAsset] native ActorSwing chain layers: object=Pelvis stats=3layers/24bones
[WARN] GakumasMod: [ModAsset] Grew missing socket nodes from replaced asset: mdl count=9 nodes=[LeftHand1_E]
"""

BAD = """\
[INFO] GakumasMod: [ModAsset] Applied lossless IP skeleton graft: droppedInfluences=12 fallbackVertices=3
[WARN] GakumasMod: [ModAsset][EXPERIMENT] Swing motion over 300 frames: 0/23 bones moved, best=x 0.00deg - NOT SIMULATED (parameters are irrelevant until this moves)
[ERROR] GakumasMod: [ModAsset] Pelvis 上拒绝挂 ActorAnimationQuartzDriverSkirtBone：缺 2 项必需引用
[WARN] GakumasMod: [ModAsset] ActorAnimationQuartzDriverSkirtSetting.referenceBone 指向的骨 LeftUpLeg 找不到，驱动器会按空引用跑
"""

# 探针早期是单骨版，抽到不挂链的袖子就报 0° —— 那不是"解算没跑"，不许当失败。
LEGACY = GOOD + (
    "[WARN] GakumasMod: [ModAsset][EXPERIMENT] Swing motion over 300 frames: "
    "bone=Bone_SleeveSA01_L peakLocalRotation=0.00deg - NOT SIMULATED (parameters are irrelevant)\n"
)


def write(tmp_path, text, name="log.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_good_log_passes(tmp_path):
    assert reader.main([str(write(tmp_path, GOOD))]) == 0


def test_bad_log_fails_and_says_which(tmp_path, capsys):
    assert reader.main([str(write(tmp_path, BAD))]) == 1
    output = capsys.readouterr().out
    for key in ("droppedInfluences", "fallbackVertices", "swingNotSimulated", "driverRefused"):
        assert key in output.split("不合格：")[-1] or key in output


def test_legacy_single_bone_probe_is_not_a_failure(tmp_path):
    """老日志里两种探针形状同时存在，宽泛匹配 NOT SIMULATED 会把好包判红。"""
    assert reader.main([str(write(tmp_path, LEGACY))]) == 0


def test_only_the_last_session_is_judged(tmp_path, capsys):
    """日志跨会话追加。上一次跑（旧 DLL）的报错不能算到这次头上 —— 默认只判最后一个 BOOT 之后。

    2026-08-18 实机撞到过：修掉那两条 ERROR 重跑，脚本仍报 2 条，实际是 566 行里第 68/69 行的历史。
    """
    old_session = BOOT + "[ERROR] GakumasMod: [ModAsset] Method not found: UnityEngine::X.Y\n"
    path = write(tmp_path, old_session + GOOD)
    assert reader.main([str(path)]) == 0                    # 只看新会话 → 通过
    assert "最后一次启动" in capsys.readouterr().out
    assert reader.main([str(path), "--all"]) == 1           # 整个文件 → 旧报错仍要现形


def test_numbers_are_read_not_guessed(tmp_path):
    counts, numbers, _samples, _boot = reader.scan(write(tmp_path, GOOD))
    assert numbers["swingDynamicBones"] == [178]
    assert numbers["swingMoved"] == [17]
    assert numbers["socketGrown"] == [9]
    assert numbers["droppedInfluences"] == [0] and numbers["fallbackVertices"] == [0]
    assert counts["nativeChainLayers"] == 1


def test_since_skips_everything_before_the_marker(tmp_path):
    text = "[INFO] old run droppedInfluences=99\nMARKER\n" + GOOD
    counts, numbers, _samples, _boot = reader.scan(write(tmp_path, text), since="MARKER")
    assert numbers["droppedInfluences"] == [0]          # 老那一行不该混进来
    assert counts["graft"] == 1


def test_an_error_line_alone_fails_the_run(tmp_path, capsys):
    """判据表里写了"期望 0"的项，就必须真的挡住退出码。

    2026-08-18 实机第一跑撞到过：`error` 命中 2 行，脚本照样打印"全部判据通过" ——
    判定规则里手抄的键名清单漏了它。现在三类规则必须恰好覆盖 CHECKS（覆盖不全会断言失败），
    这条用例守的是"漏掉一项会怎样"。
    """
    text = GOOD + "[ERROR] GakumasMod: [ModAsset] Method not found: UnityEngine::X.Y\n"
    assert reader.main([str(write(tmp_path, text))]) == 1
    assert "error" in capsys.readouterr().out.split("不合格：")[-1]


def test_every_judged_item_participates_in_the_verdict(tmp_path):
    """规则表与 CHECKS 必须一一对应 —— 加了新判据却忘了接进退出码，这里直接炸。"""
    counts, numbers, _samples, _boot = reader.scan(write(tmp_path, GOOD))
    assert reader.main([str(write(tmp_path, GOOD))]) == 0     # 断言在 main 里，跑到即验证
    assert set(numbers) | set(counts)                          # 样本确实解析出了东西


def test_missing_graft_is_reported_as_no_mod_applied(tmp_path):
    """没有 graft 行 = 这份日志里根本没应用过 mod，不能读成"检查通过"。"""
    thin = "[INFO] GakumasMod: [ModAsset] native ActorSwing chain layers: object=Pelvis\n"
    assert reader.main([str(write(tmp_path, thin))]) == 1
