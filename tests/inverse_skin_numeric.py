"""P0 回归：逆解蒙皮的数值正确性。

恢复链：design(bind 位置×权重) → posed = design @ 矩阵系数 → recovered = operator @ posed
→ rebuilt = design @ recovered。锁定两件事：
  1. 恢复算法本身（合成小网格 + pinv 算子）—— 纯 numpy，CI 可跑；
  2. 真实默认档算子的重建/骨矩阵 RMS 不回退 —— 依赖本地档产物
     (profiles/atbm-cstm-0140/{Reference/Geo_Body.json, Buffers/InverseOperator...})，
     数据缺失时自动 SKIP（CI 即走此分支）。

旧 HSKI 实机基准见 research/inverse-skin-matrix-recovery.md；当前 ATBM 默认档是
离线重建样本，位置重建仍稳定，但欠定骨更多。阈值锁定各自实测量级，只拦明显回退。
"""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "atbm-cstm-0140"


def _rotation(axis, angle):
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    c, s, q = np.cos(angle), np.sin(angle), 1.0 - np.cos(angle)
    return np.asarray([
        [c + x*x*q, x*y*q - z*s, x*z*q + y*s],
        [y*x*q + z*s, c + y*y*q, y*z*q - x*s],
        [z*x*q - y*s, z*y*q + x*s, c + z*z*q],
    ], dtype=np.float32)


def _build_design(positions, skin, bone_count):
    n = len(positions)
    source_h = np.column_stack((positions, np.ones(n, np.float32)))
    design = np.zeros((n, bone_count * 4), np.float32)
    active = np.zeros(bone_count, bool)
    for vertex, influence in enumerate(skin):
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            bone, weight = int(bone), float(weight)
            if weight > 0:
                active[bone] = True
                design[vertex, bone*4:bone*4+4] += weight * source_h[vertex]
    return design, active


def _recovery_rms(design, operator, active, samples, seed):
    """返回 (重建位置 RMS 最大值, 每活动骨的矩阵 RMS 数组)。

    矩阵 RMS 用「逐骨」返回而非聚合 mean：真实算子里有少数不可观测/欠定骨
    (如 RightFrontRibbon1_S)，它们的矩阵恢复误差很大但不影响重建位置(误差落在
    不影响观测顶点的零空间)。用 P95 等分位数即可稳健排除这些已知离群点。
    """
    rng = np.random.default_rng(seed)
    bone_count = design.shape[1] // 4
    recon_rms, per_bone = [], []
    for _ in range(samples):
        coeff = np.zeros((bone_count, 4, 3), np.float32)
        for bone in np.flatnonzero(active):
            coeff[bone, :3] = _rotation(rng.normal(size=3), rng.uniform(-0.6, 0.6))
            coeff[bone, 3] = rng.uniform(-0.08, 0.08, size=3)
        c = coeff.reshape(bone_count * 4, 3)
        posed = design @ c
        recovered = operator @ posed
        rebuilt = design @ recovered
        recon_rms.append(float(np.sqrt(np.mean((rebuilt - posed) ** 2))))
        delta = (recovered - c).reshape(bone_count, 4, 3)
        per_bone.append(np.sqrt(np.mean(delta * delta, axis=(1, 2)))[active])
    return max(recon_rms), np.concatenate(per_bone)


def test_synthetic_recovery_exact():
    """合成网格 + pinv 算子：恢复应近乎精确（CI 可跑，无需游戏数据）。"""
    rng = np.random.default_rng(1)
    n, bones = 300, 10
    positions = (rng.normal(size=(n, 3)) * 0.3).astype(np.float32)
    skin = []
    for _ in range(n):
        k = int(rng.integers(2, 4))
        chosen = rng.choice(bones, size=k, replace=False)
        weights = rng.random(k)
        weights /= weights.sum()
        skin.append({"boneIndex": chosen.tolist(), "weight": weights.tolist()})
    design, active = _build_design(positions, skin, bones)
    assert np.linalg.matrix_rank(design) == bones * 4, "合成 design 非满秩，恢复不可逆"
    operator = np.linalg.pinv(design).astype(np.float32)
    recon, per_bone = _recovery_rms(design, operator, active, samples=8, seed=42)
    matrix_p95 = float(np.percentile(per_bone, 95))
    # 合成网格满秩可逆 → 恢复近乎精确(float32 量级)
    assert recon < 1e-3, ("合成重建 RMS 异常", recon)
    assert matrix_p95 < 1e-3, ("合成骨矩阵 RMS 异常", matrix_p95)
    print(f"synthetic_recovery_exact OK  recon={recon:.2e} boneP95={matrix_p95:.2e}")


def test_real_operator_thresholds():
    """真实默认档(atbm-cstm-0140)算子：重建/骨矩阵 RMS 不得回退（本地数据；缺失则 SKIP）。"""
    mesh_path = PROFILE / "Reference" / "Geo_Body.json"
    op_path = PROFILE / "Buffers" / "InverseOperator.R32_FLOAT.buf"
    if not (mesh_path.is_file() and op_path.is_file()):
        print("real_operator_thresholds SKIP（本地数据缺失：Geo_Body.json + InverseOperator buf）")
        return
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    positions = np.asarray(mesh["m_Vertices"], np.float32).reshape(-1, 3)
    design, active = _build_design(positions, mesh["m_Skin"], bone_count)
    operator = np.fromfile(op_path, np.float32).reshape(bone_count * 4, vertex_count)
    recon, per_bone = _recovery_rms(design, operator, active, samples=4, seed=0x534B494E)
    matrix_p50 = float(np.percentile(per_bone, 50))
    matrix_p95 = float(np.percentile(per_bone, 95))
    bad_bones = int((per_bone > 1e-3).sum() / 4)  # 4 samples → 折算成「骨条数」
    # ATBM 离线重建档实测：重建 RMS 2.3e-5、骨 P95 2.7e-3、约 30 根欠定骨。
    # 阈值留少量浮点余量；算子损坏时会升到 1e-1 量级。
    assert recon < 1e-4, ("重建 RMS 回退", recon)
    assert matrix_p95 < 5e-3, ("骨矩阵 P95 回退", matrix_p95)
    assert bad_bones <= 40, ("欠定骨数量异常增多", bad_bones)
    print(f"real_operator_thresholds OK  recon={recon:.2e} boneP50={matrix_p50:.2e} "
          f"boneP95={matrix_p95:.2e} badBones≈{bad_bones} (activeBones={int(active.sum())})")


if __name__ == "__main__":
    test_synthetic_recovery_exact()
    test_real_operator_thresholds()
    print("ALL inverse_skin_numeric OK")
