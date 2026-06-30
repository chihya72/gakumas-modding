"""智能蒙皮转权：法线闸门置信最近 + 零依赖 Laplacian inpaint。

纯 numpy，不依赖 bpy / scipy（Blender 只内置 numpy），因此既能在 CI 跑，也能在
Blender 运行时调用。用来替代朴素「最近表面插值」(POLYINTERP_NEAREST) 的两个硬伤：

  1. 欧氏最近会跨薄缝串权重（大腿内侧、腋下、裙子贴腿、手指之间）。
  2. 空间上贴很近但语义相反的前后两层面，会互相污染。

流程：
  - 每个目标顶点找最近的 source 顶点。
  - 只有「距离 <= max_distance 且 法线一致度 >= normal_cos_threshold」才算**置信**，
    直接抄 source 权重；其余顶点留空（unknown）。
  - 未置信顶点用目标网格图上的迭代 Laplacian 平滑做 **inpaint**（Dirichlet 边界 =
    置信顶点），让权重**沿表面流动**而不是跨欧氏缝隙跳过去。
  - 钳负、保留前 max_influences 个、归一化到和为 1。

source_weights 用稠密 (S, B) 矩阵表示（B = 骨骼通道数）。调用方负责骨骼名 <-> 列号
的映射，本模块只跟数字打交道，方便测试与复用。
"""

from __future__ import annotations

import numpy as np


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    """把每行单位化；零向量保持为零。"""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return vectors / norms


def chunked_nearest(target_pos: np.ndarray, source_pos: np.ndarray,
                    chunk: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """对每个 target 点找最近的 source 点，返回 (索引, 距离)。

    分块 brute-force，避免一次性 N*S 距离矩阵爆内存；纯 numpy，无需 KDTree/scipy。
    对 ~2e4 量级的身体/服装网格足够快。
    """
    n = len(target_pos)
    idx = np.empty(n, dtype=np.int64)
    dist = np.empty(n, dtype=np.float64)
    src = source_pos.astype(np.float64)
    src_sq = np.einsum("ij,ij->i", src, src)  # |s|^2 预算一次
    for start in range(0, n, chunk):
        block = target_pos[start:start + chunk].astype(np.float64)
        # |t|^2 - 2 t·s + |s|^2  （省去开方排序，最后再开方）
        cross = block @ src.T
        d2 = (np.einsum("ij,ij->i", block, block)[:, None] - 2.0 * cross + src_sq[None, :])
        near = np.argmin(d2, axis=1)
        idx[start:start + chunk] = near
        dist[start:start + chunk] = np.sqrt(np.maximum(d2[np.arange(len(block)), near], 0.0))
    return idx, dist


def nearest_compatible(target_pos: np.ndarray, target_nrm: np.ndarray,
                       source_pos: np.ndarray, source_nrm: np.ndarray,
                       normal_cos_threshold: float,
                       chunk: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """在「法线一致 (dot >= 阈值)」的 source 顶点里，给每个 target 找最近的。

    关键：不是「先取最近再判法线」，而是「在合法集合里取最近」——否则当欧氏最近恰好
    是法线相反的另一层面时，会误判为无匹配。返回 (索引, 距离)；无任何合法 source 的
    目标顶点距离为 +inf、索引为 -1。
    """
    n = len(target_pos)
    idx = np.full(n, -1, dtype=np.int64)
    dist = np.full(n, np.inf, dtype=np.float64)
    src = source_pos.astype(np.float64)
    src_nrm = source_nrm.astype(np.float64)
    src_sq = np.einsum("ij,ij->i", src, src)
    for start in range(0, n, chunk):
        block = target_pos[start:start + chunk].astype(np.float64)
        bnrm = target_nrm[start:start + chunk].astype(np.float64)
        d2 = (np.einsum("ij,ij->i", block, block)[:, None]
              - 2.0 * (block @ src.T) + src_sq[None, :])
        dot = bnrm @ src_nrm.T  # (block, S) 法线一致度
        d2 = np.where(dot >= normal_cos_threshold, d2, np.inf)
        near = np.argmin(d2, axis=1)
        best = d2[np.arange(len(block)), near]
        ok = np.isfinite(best)
        rows = np.arange(start, start + len(block))
        idx[rows[ok]] = near[ok]
        dist[rows[ok]] = np.sqrt(np.maximum(best[ok], 0.0))
    return idx, dist


def build_edges(num_verts: int, faces: np.ndarray) -> np.ndarray:
    """从三角面构建无向边（双向），返回 (E, 2) int64，供 Laplacian 平滑用。"""
    faces = np.asarray(faces, dtype=np.int64)
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0)
    e = np.concatenate([e, e[:, ::-1]], axis=0)  # 双向
    e = np.unique(np.sort(e, axis=1), axis=0)     # 去重（无向）
    return np.concatenate([e, e[:, ::-1]], axis=0)  # 再展开成双向有向，方便累加


def laplacian_inpaint(weights: np.ndarray, known_mask: np.ndarray,
                      edges: np.ndarray, iterations: int = 256,
                      tol: float = 1e-5) -> np.ndarray:
    """对 known_mask=False 的行做图上 Laplacian inpaint（Jacobi 迭代）。

    已知行固定为 Dirichlet 边界，未知行反复取邻居均值，收敛到调和解——等价于在表面
    上最光滑地把权重「补」进空洞，且不会跨缝（因为只沿网格边传播）。
    """
    n, b = weights.shape
    src = edges[:, 0]
    dst = edges[:, 1]
    deg = np.zeros(n, dtype=np.float64)
    np.add.at(deg, src, 1.0)
    deg[deg == 0.0] = 1.0  # 孤立点：避免除零，下一步它会保持自身值

    w = weights.astype(np.float64).copy()
    unknown = ~known_mask
    if not unknown.any():
        return w
    for _ in range(iterations):
        acc = np.zeros((n, b), dtype=np.float64)
        np.add.at(acc, src, w[dst])
        avg = acc / deg[:, None]
        new_unknown = avg[unknown]
        delta = np.abs(new_unknown - w[unknown]).max() if unknown.any() else 0.0
        w[unknown] = new_unknown
        if delta < tol:
            break
    return w


def _top_k_normalize(weights: np.ndarray, max_influences: int = 4) -> np.ndarray:
    """钳负 → 每行保留权重最大的 max_influences 个 → 归一化到和为 1。"""
    w = np.clip(weights, 0.0, None)
    if w.shape[1] > max_influences:
        # 把每行除最大 K 个以外的列清零
        keep = np.argsort(-w, axis=1)[:, :max_influences]
        mask = np.zeros_like(w, dtype=bool)
        np.put_along_axis(mask, keep, True, axis=1)
        w = np.where(mask, w, 0.0)
    sums = w.sum(axis=1, keepdims=True)
    sums[sums == 0.0] = 1.0
    return w / sums


def smart_weight_transfer(
    target_pos: np.ndarray,
    target_nrm: np.ndarray,
    faces: np.ndarray,
    source_pos: np.ndarray,
    source_nrm: np.ndarray,
    source_weights: np.ndarray,
    *,
    max_distance: float,
    normal_cos_threshold: float = 0.0,
    inpaint_iterations: int = 256,
    max_influences: int = 4,
) -> dict:
    """把 source 权重智能转到 target 网格。

    返回 dict:
      weights        (N, B)  最终权重（已 top-k + 归一）
      confident_mask (N,)    哪些顶点是直接置信传递的
      distance       (N,)    到最近 source 顶点的距离
      stats          指标汇总
    """
    target_pos = np.asarray(target_pos, dtype=np.float64)
    source_pos = np.asarray(source_pos, dtype=np.float64)
    tnrm = _normalize_rows(np.asarray(target_nrm, dtype=np.float64))
    snrm = _normalize_rows(np.asarray(source_nrm, dtype=np.float64))
    source_weights = np.asarray(source_weights, dtype=np.float64)
    n = len(target_pos)
    b = source_weights.shape[1]

    # 几何最近（兜底用）与「法线一致里最近」（置信用）。
    geo_idx, geo_dist = chunked_nearest(target_pos, source_pos)
    cidx, cdist = nearest_compatible(target_pos, tnrm, source_pos, snrm, normal_cos_threshold)
    confident = cdist <= max_distance

    weights = np.zeros((n, b), dtype=np.float64)
    weights[confident] = source_weights[cidx[confident]]
    dist = np.where(confident, cdist, geo_dist)

    if not confident.any():
        # 没有任何置信点：退化为朴素最近（带警告统计），避免整体为零。
        weights = source_weights[geo_idx]
    else:
        edges = build_edges(n, faces)
        weights = laplacian_inpaint(weights, confident, edges, iterations=inpaint_iterations)
        # inpaint 后仍全零的孤立顶点（图上与置信区不连通）→ 兜底用最近 source。
        still_zero = weights.sum(axis=1) <= 1e-9
        if still_zero.any():
            weights[still_zero] = source_weights[geo_idx[still_zero]]

    weights = _top_k_normalize(weights, max_influences=max_influences)

    zero_after = int((weights.sum(axis=1) <= 1e-9).sum())
    ordered = np.sort(dist)
    p95 = float(ordered[min(n - 1, int(n * 0.95))]) if n else 0.0
    stats = {
        "vertices": n,
        "confidentVertices": int(confident.sum()),
        "inpaintedVertices": int((~confident).sum()),
        "zeroWeightVertices": zero_after,
        "maxDistance": float(dist.max()) if n else 0.0,
        "meanDistance": float(dist.mean()) if n else 0.0,
        "p95Distance": p95,
        # 法线闸门「改写匹配」的顶点数：置信匹配与纯几何最近不同 → 闸门拦下了错误的近邻。
        "normalRedirected": int((confident & (geo_idx != cidx)).sum()),
        # 几何上够近、却没有任何法线一致 source、只能 inpaint/兜底的顶点数。
        "normalStranded": int(((geo_dist <= max_distance) & (~confident)).sum()),
    }
    return {
        "weights": weights,
        "confident_mask": confident,
        "distance": dist,
        "stats": stats,
    }
