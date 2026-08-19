"""P1b：肢体权重按原版剖面分给 `*_H`。

合成骨架，不依赖原版 bundle。真数据的端到端结果记在 research/ab-v2-plan.md：
chisaki-swimsuit 上 `*_H` 承重 0.00% → 17.85%（原版中位 11.28%、范围 6.02–21.00%），
权重和无异常，4329 个顶点因超过 4 骨被截断。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gmi_redistribute",
                                              ROOT / "tools" / "redistribute_helper_weights.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class FakeVanilla:
    """只需要 position()：左臂从原点沿 +x 伸长 1.0。"""

    POSITIONS = {
        "LeftArm": [0.0, 0.0, 0.0],
        "LeftForeArm": [1.0, 0.0, 0.0],
        "LeftHand": [2.0, 0.0, 0.0],
    }

    def position(self, bone):
        return self.POSITIONS.get(bone)


BONES = ["LeftArm", "LeftArm_H", "LeftArm_Roll_H", "LeftForeArm", "LeftForeArm_H",
         "LeftForeArm_Roll_H", "LeftHand_H", "Hips"]


def _skin(pairs):
    return [{"boneIndex": [i for i, _ in pairs] + [0] * (4 - len(pairs)),
             "weight": [w for _, w in pairs] + [0.0] * (4 - len(pairs))}]


def test_shoulder_end_goes_almost_entirely_to_the_corrective_bone():
    """臂根那一档原版剖面是 humanoid 0.00 / Arm_H 0.99 / Arm_Roll_H 0.01。"""
    verts = [0.05, 0.0, 0.0]                     # t=0.05 → 第 0 档
    plan, stats = plan_redistribution_wrapper(verts, _skin([(0, 1.0)]))
    assert plan[0]["LeftArm_H"] > 0.9
    assert plan[0].get("LeftArm", 0.0) < 0.01
    assert stats["movedMass"] > 0.9


def test_elbow_end_keeps_most_of_it_on_the_humanoid_bone():
    """靠肘那一档回到 humanoid 0.77 —— 剖面不是一刀切，两端行为相反。"""
    verts = [0.95, 0.0, 0.0]                     # t=0.95 → 第 9 档
    plan, _ = plan_redistribution_wrapper(verts, _skin([(0, 1.0)]))
    assert plan[0]["LeftArm"] > 0.7
    assert plan[0]["LeftArm_Roll_H"] < 0.3


def test_weights_stay_normalised_and_capped_at_four_bones():
    verts = [0.55, 0.0, 0.0]
    skin = _skin([(0, 0.6), (3, 0.4)])
    plan, _ = plan_redistribution_wrapper(verts, skin)
    truncated = mod.apply_plan(BONES, skin, plan)
    assert len(skin[0]["boneIndex"]) == 4
    assert abs(sum(skin[0]["weight"]) - 1.0) < 1e-6
    assert truncated >= 0


def test_untouched_bone_is_left_alone():
    """不属于任何肢体家族的骨（Hips）原样保留，不该被剖面碰。"""
    verts = [0.5, 0.0, 0.0]
    plan, _ = plan_redistribution_wrapper(verts, _skin([(7, 1.0)]))
    assert plan == {} or plan.get(0, {}).get("Hips") == 1.0


def plan_redistribution_wrapper(verts, skin):
    return mod.plan_redistribution(BONES, verts, skin, FakeVanilla())
