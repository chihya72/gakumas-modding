#!/usr/bin/env python3
"""CPU emulation of the two experimental D3D11 compute shaders."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np


def read_vb(path: Path, count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    if len(raw) != count * 40:
        raise ValueError("Unexpected posed VB size")
    p = np.empty((count, 3), np.float32)
    n = np.empty((count, 3), np.float32)
    t = np.empty((count, 4), np.float32)
    for i in range(count):
        p[i] = struct.unpack_from("<3f", raw, i * 40)
        n[i] = struct.unpack_from("<3f", raw, i * 40 + 12)
        t[i] = struct.unpack_from("<4f", raw, i * 40 + 24)
    return p, n, t


def normalize(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-20)


def shader_reduce(operator: np.ndarray, posed: np.ndarray) -> np.ndarray:
    coefficient_count, vertex_count = operator.shape
    thread_count = 256
    iterations = (vertex_count + thread_count - 1) // thread_count
    padded = iterations * thread_count
    result = np.empty((coefficient_count, 3), np.float32)
    for axis in range(3):
        products = np.zeros((coefficient_count, padded), np.float32)
        products[:, :vertex_count] = operator * posed[:, axis][None, :]
        # Each shader lane sums vertex lane, lane+256, ... in increasing order.
        partial = np.zeros((coefficient_count, thread_count), np.float32)
        lane_values = products.reshape(coefficient_count, iterations, thread_count)
        for iteration in range(iterations):
            partial += lane_values[:, iteration, :]
        width = 128
        while width:
            partial[:, :width] += partial[:, width : width * 2]
            width //= 2
        result[:, axis] = partial[:, 0]
    return result


def angular_error(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    dots = np.sum(normalize(a) * normalize(b), axis=1)
    return np.degrees(np.arccos(np.clip(dots, -1.0, 1.0)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--posed-vb", type=Path, required=True)
    parser.add_argument("--operator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    mesh = json.loads(args.mesh_json.read_text(encoding="utf-8"))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    operator = np.fromfile(args.operator, dtype=np.float32).reshape(bone_count * 4, vertex_count)
    posed_p, posed_n, posed_t = read_vb(args.posed_vb, vertex_count)
    coefficients = shader_reduce(operator, posed_p)
    matrices = coefficients.reshape(bone_count, 4, 3)

    bind_p = np.asarray(mesh["m_Vertices"], np.float32).reshape(-1, 3)
    bind_n = np.asarray(mesh["m_Normals"], np.float32).reshape(-1, 3)
    bind_t = np.asarray(mesh["m_Tangents"], np.float32).reshape(-1, 4)
    out_p = np.zeros_like(bind_p)
    out_n = np.zeros_like(bind_n)
    out_t = np.zeros((vertex_count, 3), np.float32)
    for influence in range(4):
        bones = np.asarray([row["boneIndex"][influence] for row in mesh["m_Skin"]], np.int32)
        weights = np.asarray([row["weight"][influence] for row in mesh["m_Skin"]], np.float32)
        selected = matrices[bones]
        out_p += weights[:, None] * (
            bind_p[:, 0:1] * selected[:, 0]
            + bind_p[:, 1:2] * selected[:, 1]
            + bind_p[:, 2:3] * selected[:, 2]
            + selected[:, 3]
        )
        out_n += weights[:, None] * (
            bind_n[:, 0:1] * selected[:, 0]
            + bind_n[:, 1:2] * selected[:, 1]
            + bind_n[:, 2:3] * selected[:, 2]
        )
        out_t += weights[:, None] * (
            bind_t[:, 0:1] * selected[:, 0]
            + bind_t[:, 1:2] * selected[:, 1]
            + bind_t[:, 2:3] * selected[:, 2]
        )
    out_n, out_t = normalize(out_n), normalize(out_t)
    position_error = np.linalg.norm(out_p - posed_p, axis=1)
    normal_error = angular_error(out_n, posed_n)
    tangent_error = angular_error(out_t, posed_t[:, :3])
    report = {
        "emulation": "RecoverMatricesCS 256-lane sequential accumulation + tree reduction; SkinSourceCS float32",
        "positionRms": float(np.sqrt(np.mean(position_error**2))),
        "positionP95": float(np.percentile(position_error, 95)),
        "positionMax": float(np.max(position_error)),
        "normalAngleMeanDegrees": float(np.mean(normal_error)),
        "normalAngleP95Degrees": float(np.percentile(normal_error, 95)),
        "normalAngleMaxDegrees": float(np.max(normal_error)),
        "tangentAngleMeanDegrees": float(np.mean(tangent_error)),
        "tangentAngleP95Degrees": float(np.percentile(tangent_error, 95)),
        "tangentAngleMaxDegrees": float(np.max(tangent_error)),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    coefficients.astype(np.float32).tofile(args.output / "shader_recovered_matrices.buf")
    (args.output / "compute-emulation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
