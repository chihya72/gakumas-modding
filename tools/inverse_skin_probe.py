#!/usr/bin/env python3
"""Recover one frame of effective skinning matrices from a captured posed VB.

This is an offline feasibility probe.  It solves

    posed_vertex = sum(weight * affine_bone_matrix * bind_vertex)

for every weighted bone, then reports how accurately those matrices reproduce
the captured game vertices.  No game files are modified.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np


def read_vb0(path: Path, vertex_count: int, stride: int = 40) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    expected = vertex_count * stride
    if len(raw) != expected:
        raise ValueError(f"{path}: {len(raw)} bytes, expected {expected}")
    positions = np.empty((vertex_count, 3), dtype=np.float64)
    normals = np.empty((vertex_count, 3), dtype=np.float64)
    tangents = np.empty((vertex_count, 4), dtype=np.float64)
    for vertex in range(vertex_count):
        positions[vertex] = struct.unpack_from("<3f", raw, vertex * stride)
        normals[vertex] = struct.unpack_from("<3f", raw, vertex * stride + 12)
        tangents[vertex] = struct.unpack_from("<4f", raw, vertex * stride + 24)
    return positions, normals, tangents


def normalize_rows(values: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(lengths, 1e-20)


def angular_error_degrees(expected: np.ndarray, actual: np.ndarray) -> np.ndarray:
    dots = np.sum(normalize_rows(expected) * normalize_rows(actual), axis=1)
    return np.degrees(np.arccos(np.clip(dots, -1.0, 1.0)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--posed-vb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ridge", type=float, default=1e-8)
    parser.add_argument(
        "--holdout", type=float, default=0.0,
        help="fraction of vertices excluded from fitting and used only for validation",
    )
    args = parser.parse_args()

    mesh = json.loads(args.mesh_json.read_text(encoding="utf-8"))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    bind_positions = np.asarray(mesh["m_Vertices"], dtype=np.float64).reshape(-1, 3)
    if bind_positions.shape[0] != vertex_count:
        raise ValueError("m_Vertices count does not match m_VertexCount")
    skin = mesh["m_Skin"]
    if len(skin) != vertex_count:
        raise ValueError("m_Skin count does not match m_VertexCount")
    posed_positions, posed_normals, posed_tangents = read_vb0(args.posed_vb, vertex_count)

    # Four affine coefficients per bone and output coordinate. The source
    # coordinate system does not need to match the posed VB: the recovered
    # affine matrices absorb the fixed mesh-to-draw-space conversion.
    columns = bone_count * 4
    design = np.zeros((vertex_count, columns), dtype=np.float64)
    source_h = np.concatenate(
        (bind_positions, np.ones((vertex_count, 1), dtype=np.float64)), axis=1
    )
    influence_count = np.zeros(bone_count, dtype=np.int64)
    weight_sum = np.zeros(bone_count, dtype=np.float64)
    for vertex, influence in enumerate(skin):
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            bone = int(bone)
            weight = float(weight)
            if weight <= 0.0:
                continue
            design[vertex, bone * 4 : bone * 4 + 4] += weight * source_h[vertex]
            influence_count[bone] += 1
            weight_sum[bone] += weight

    active_bones = np.flatnonzero(weight_sum > 0.0)
    active_columns = np.concatenate(
        [np.arange(bone * 4, bone * 4 + 4) for bone in active_bones]
    )
    active_design = design[:, active_columns]

    # Ridge-regularized normal equations are sufficient for this diagnostic;
    # the reconstruction residual, not the individual matrix decomposition,
    # is the decisive result.
    if not 0.0 <= args.holdout < 1.0:
        raise ValueError("--holdout must be in [0, 1)")
    rng = np.random.default_rng(0x474D49)
    fit_mask = np.ones(vertex_count, dtype=bool)
    if args.holdout > 0.0:
        fit_mask = rng.random(vertex_count) >= args.holdout
    fit_design = active_design[fit_mask]
    fit_positions = posed_positions[fit_mask]
    gram = fit_design.T @ fit_design
    scale = float(np.trace(gram) / max(1, gram.shape[0]))
    regularizer = args.ridge * max(scale, 1.0)
    rhs = fit_design.T @ fit_positions
    coefficients = np.linalg.solve(
        gram + np.eye(gram.shape[0], dtype=np.float64) * regularizer, rhs
    )
    reconstructed = active_design @ coefficients
    errors = np.linalg.norm(reconstructed - posed_positions, axis=1)
    held_out_errors = errors[~fit_mask]

    full_coefficients = np.zeros((columns, 3), dtype=np.float64)
    full_coefficients[active_columns] = coefficients
    matrices = full_coefficients.reshape(bone_count, 4, 3)

    source_normals = np.asarray(mesh["m_Normals"], dtype=np.float64).reshape(-1, 3)
    source_tangents = np.asarray(mesh["m_Tangents"], dtype=np.float64).reshape(-1, 4)
    reconstructed_normals = np.zeros_like(source_normals)
    reconstructed_tangents = np.zeros((vertex_count, 3), dtype=np.float64)
    for vertex, influence in enumerate(skin):
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            bone = int(bone)
            weight = float(weight)
            if weight <= 0.0:
                continue
            linear = matrices[bone, :3, :]
            reconstructed_normals[vertex] += weight * (source_normals[vertex] @ linear)
            reconstructed_tangents[vertex] += weight * (source_tangents[vertex, :3] @ linear)
    reconstructed_normals = normalize_rows(reconstructed_normals)
    reconstructed_tangents = normalize_rows(reconstructed_tangents)
    normal_angles = angular_error_degrees(reconstructed_normals, posed_normals)
    tangent_angles = angular_error_degrees(reconstructed_tangents, posed_tangents[:, :3])

    singular_values = np.linalg.svd(matrices[active_bones, :3, :], compute_uv=False)
    gram_eigenvalues = np.linalg.eigvalsh(gram)
    positive_eigenvalues = gram_eigenvalues[gram_eigenvalues > gram_eigenvalues.max() * 1e-12]

    report = {
        "meshJson": str(args.mesh_json.resolve()),
        "posedVB": str(args.posed_vb.resolve()),
        "vertexCount": vertex_count,
        "boneCount": bone_count,
        "activeBoneCount": int(active_bones.size),
        "ridge": args.ridge,
        "fitVertexCount": int(np.count_nonzero(fit_mask)),
        "heldOutVertexCount": int(np.count_nonzero(~fit_mask)),
        "regularizer": regularizer,
        "rmsPositionError": float(np.sqrt(np.mean(errors**2))),
        "meanPositionError": float(np.mean(errors)),
        "p50PositionError": float(np.percentile(errors, 50)),
        "p95PositionError": float(np.percentile(errors, 95)),
        "p99PositionError": float(np.percentile(errors, 99)),
        "maxPositionError": float(np.max(errors)),
        "normalAngleMeanDegrees": float(np.mean(normal_angles)),
        "normalAngleP95Degrees": float(np.percentile(normal_angles, 95)),
        "normalAngleMaxDegrees": float(np.max(normal_angles)),
        "tangentAngleMeanDegrees": float(np.mean(tangent_angles)),
        "tangentAngleP95Degrees": float(np.percentile(tangent_angles, 95)),
        "tangentAngleMaxDegrees": float(np.max(tangent_angles)),
        "designNumericalRank": int(positive_eigenvalues.size),
        "designColumnCount": int(active_design.shape[1]),
        "designConditionEstimate": (
            float(np.sqrt(positive_eigenvalues.max() / positive_eigenvalues.min()))
            if positive_eigenvalues.size else None
        ),
        "matrixSingularValueP01": np.percentile(singular_values, 1, axis=0).tolist(),
        "matrixSingularValueP50": np.percentile(singular_values, 50, axis=0).tolist(),
        "matrixSingularValueP99": np.percentile(singular_values, 99, axis=0).tolist(),
        "heldOutRmsPositionError": (
            float(np.sqrt(np.mean(held_out_errors**2))) if held_out_errors.size else None
        ),
        "heldOutP95PositionError": (
            float(np.percentile(held_out_errors, 95)) if held_out_errors.size else None
        ),
        "heldOutMaxPositionError": (
            float(np.max(held_out_errors)) if held_out_errors.size else None
        ),
        "posedBoundsMin": posed_positions.min(axis=0).tolist(),
        "posedBoundsMax": posed_positions.max(axis=0).tolist(),
        "weakBones": [
            {
                "index": int(bone),
                "influencedVertices": int(influence_count[bone]),
                "weightSum": float(weight_sum[bone]),
            }
            for bone in active_bones
            if influence_count[bone] < 4 or weight_sum[bone] < 0.01
        ],
    }

    args.output.mkdir(parents=True, exist_ok=True)
    np.save(args.output / "effective_skin_matrices.npy", matrices.astype(np.float32))
    np.save(args.output / "reconstructed_positions.npy", reconstructed.astype(np.float32))
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
