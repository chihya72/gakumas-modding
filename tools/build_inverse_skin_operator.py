#!/usr/bin/env python3
"""Build and validate the fixed linear operator used by the future GPU probe.

The operator maps one posed source-position VB directly to 152 effective 4x3
skinning matrices.  It depends only on the source profile's bind vertices and
weights, so it is generated once offline and reused for every animation frame.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np


def read_positions(path: Path, vertex_count: int, stride: int = 40) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) != vertex_count * stride:
        raise ValueError(f"Unexpected VB size: {len(raw)}")
    result = np.empty((vertex_count, 3), dtype=np.float32)
    for vertex in range(vertex_count):
        result[vertex] = struct.unpack_from("<3f", raw, vertex * stride)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--posed-vb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ridge", type=float, default=1e-8)
    args = parser.parse_args()

    mesh = json.loads(args.mesh_json.read_text(encoding="utf-8"))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    positions = np.asarray(mesh["m_Vertices"], dtype=np.float64).reshape(-1, 3)
    source_h = np.column_stack((positions, np.ones(vertex_count)))
    design = np.zeros((vertex_count, bone_count * 4), dtype=np.float64)
    active = np.zeros(bone_count, dtype=bool)
    for vertex, influence in enumerate(mesh["m_Skin"]):
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            bone, weight = int(bone), float(weight)
            if weight <= 0.0:
                continue
            active[bone] = True
            design[vertex, bone * 4 : bone * 4 + 4] += weight * source_h[vertex]

    active_bones = np.flatnonzero(active)
    active_columns = np.concatenate(
        [np.arange(bone * 4, bone * 4 + 4) for bone in active_bones]
    )
    a = design[:, active_columns]
    gram = a.T @ a
    scale = float(np.trace(gram) / gram.shape[0])
    regularizer = args.ridge * max(scale, 1.0)
    # P=(A^T A + lambda I)^-1 A^T.  One GPU thread later evaluates one row
    # of P against all posed source vertices and emits a float3 coefficient.
    operator_active = np.linalg.solve(
        gram + np.eye(gram.shape[0]) * regularizer, a.T
    )
    operator = np.zeros((bone_count * 4, vertex_count), dtype=np.float32)
    operator[active_columns] = operator_active.astype(np.float32)

    posed = read_positions(args.posed_vb, vertex_count)
    coefficients = operator @ posed
    reconstructed = design.astype(np.float32) @ coefficients
    errors = np.linalg.norm(reconstructed - posed, axis=1)

    # Quantization is measured but not selected automatically. fp16 may be
    # attractive later, but weak/ill-conditioned bones can amplify its error.
    operator_fp16 = operator.astype(np.float16)
    coefficients_fp16 = operator_fp16.astype(np.float32) @ posed
    reconstructed_fp16 = design.astype(np.float32) @ coefficients_fp16
    errors_fp16 = np.linalg.norm(reconstructed_fp16 - posed, axis=1)

    args.output.mkdir(parents=True, exist_ok=True)
    operator.tofile(args.output / "inverse_operator_f32.buf")
    operator_fp16.tofile(args.output / "inverse_operator_f16.buf")
    coefficients.reshape(bone_count, 4, 3).astype(np.float32).tofile(
        args.output / "recovered_matrices_f32.buf"
    )
    report = {
        "schemaVersion": 1,
        "vertexCount": vertex_count,
        "boneCount": bone_count,
        "coefficientCount": bone_count * 4,
        "activeBoneCount": int(active_bones.size),
        "activeBones": active_bones.tolist(),
        "ridge": args.ridge,
        "regularizer": regularizer,
        "operatorLayout": "coefficient-major; coefficientCount rows x vertexCount; scalar weights",
        "matrixLayout": "bone-major; 4 source homogeneous rows x 3 output coordinates",
        "operatorF32Bytes": int(operator.nbytes),
        "operatorF16Bytes": int(operator_fp16.nbytes),
        "f32RmsPositionError": float(np.sqrt(np.mean(errors**2))),
        "f32P95PositionError": float(np.percentile(errors, 95)),
        "f32MaxPositionError": float(np.max(errors)),
        "f16RmsPositionError": float(np.sqrt(np.mean(errors_fp16**2))),
        "f16P95PositionError": float(np.percentile(errors_fp16, 95)),
        "f16MaxPositionError": float(np.max(errors_fp16)),
    }
    (args.output / "operator.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
