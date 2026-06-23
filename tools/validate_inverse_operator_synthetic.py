#!/usr/bin/env python3
"""Test whether the inverse operator recovers matrices, not merely vertices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    c, s, q = np.cos(angle), np.sin(angle), 1.0 - np.cos(angle)
    return np.asarray([
        [c + x*x*q, x*y*q - z*s, x*z*q + y*s],
        [y*x*q + z*s, c + y*y*q, y*z*q - x*s],
        [z*x*q - y*s, z*y*q + x*s, c + z*z*q],
    ], dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--skeleton-json", type=Path, required=True)
    parser.add_argument("--operator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args()

    mesh = json.loads(args.mesh_json.read_text(encoding="utf-8"))
    skeleton = json.loads(args.skeleton_json.read_text(encoding="utf-8"))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    positions = np.asarray(mesh["m_Vertices"], np.float32).reshape(-1, 3)
    source_h = np.column_stack((positions, np.ones(vertex_count, np.float32)))
    design = np.zeros((vertex_count, bone_count * 4), np.float32)
    active = np.zeros(bone_count, bool)
    for vertex, influence in enumerate(mesh["m_Skin"]):
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            bone, weight = int(bone), float(weight)
            if weight > 0:
                active[bone] = True
                design[vertex, bone*4:bone*4+4] += weight * source_h[vertex]
    operator = np.fromfile(args.operator, np.float32).reshape(bone_count * 4, vertex_count)
    names = [f"bone_{i}" for i in range(bone_count)]
    for node in skeleton["nodes"]:
        index = node.get("weightedIndex")
        if index is not None:
            names[index] = node["name"]

    rng = np.random.default_rng(0x534B494E)
    bone_errors = np.zeros((args.samples, bone_count), np.float32)
    reconstruction_errors = []
    for sample in range(args.samples):
        matrices = np.zeros((bone_count, 4, 3), np.float32)
        for bone in np.flatnonzero(active):
            axis = rng.normal(size=3)
            angle = rng.uniform(-0.6, 0.6)
            matrices[bone, :3] = rotation(axis, angle)
            matrices[bone, 3] = rng.uniform(-0.08, 0.08, size=3)
        coefficients = matrices.reshape(bone_count * 4, 3)
        posed = design @ coefficients
        recovered = operator @ posed
        rebuilt = design @ recovered
        reconstruction_errors.append(float(np.sqrt(np.mean((rebuilt - posed) ** 2))))
        delta = (recovered - coefficients).reshape(bone_count, 4, 3)
        bone_errors[sample] = np.sqrt(np.mean(delta * delta, axis=(1, 2)))

    active_indices = np.flatnonzero(active)
    per_bone_p95 = np.percentile(bone_errors, 95, axis=0)
    ranked = sorted(active_indices, key=lambda bone: per_bone_p95[bone], reverse=True)
    report = {
        "samples": args.samples,
        "activeBoneCount": int(active.sum()),
        "syntheticSourceReconstructionRmsMean": float(np.mean(reconstruction_errors)),
        "syntheticSourceReconstructionRmsMax": float(np.max(reconstruction_errors)),
        "activeBoneMatrixRmsP50": float(np.percentile(bone_errors[:, active], 50)),
        "activeBoneMatrixRmsP95": float(np.percentile(bone_errors[:, active], 95)),
        "activeBoneMatrixRmsP99": float(np.percentile(bone_errors[:, active], 99)),
        "worstBones": [
            {
                "index": int(bone),
                "name": names[bone],
                "matrixRmsP95": float(per_bone_p95[bone]),
                "matrixRmsMax": float(np.max(bone_errors[:, bone])),
            }
            for bone in ranked[:12]
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
