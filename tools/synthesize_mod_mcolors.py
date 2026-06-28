"""Synthesize per-vertex Gakumas COLOR/m_Colors for an exported mod package.

The training data is the original profile:
- original Geo_Body mesh positions/normals/colors
- original runtime VB1 UVs
- original baseColor/COL texture

The target data is the exported inverse-skin mod package:
- Body.BindSkin.R32_UINT.buf positions/normals
- Body.VB1.buf UVs, whose first four bytes are replaced with synthesized COLOR
- Body.BaseColor.dds as the mod COL/baseColor texture
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import struct
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image


BIND_STRIDE = struct.calcsize("<3f3f4f4I4I4f")
VB1_STRIDE = 12


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _group(values, width):
    return [values[i : i + width] for i in range(0, len(values), width)]


def _rgba8(values):
    if max(values) <= 1.0:
        return tuple(max(0, min(255, round(float(v) * 255.0))) for v in values)
    return tuple(max(0, min(255, round(float(v)))) for v in values)


def _resolve_profile_file(profile_dir: Path, relative_or_capture: str, capture_dir: Path) -> Path:
    candidates = [
        profile_dir / relative_or_capture,
        capture_dir / relative_or_capture,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(relative_or_capture)


def _load_dds_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.uint8)


def _sample_texture(image: np.ndarray, uv_gpu: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    uv = uv_gpu.copy()
    uv[:, 0] = uv[:, 0] % 1.0
    uv[:, 1] = uv[:, 1] % 1.0
    x = np.clip((uv[:, 0] * width).astype(np.int32), 0, width - 1)
    y = np.clip((uv[:, 1] * height).astype(np.int32), 0, height - 1)
    return image[y, x, :3].astype(np.float32) / 255.0


def _load_original(profile_dir: Path):
    profile = _load_json(profile_dir / "profile.json")
    texture_map = _load_json(profile_dir / "texture_map.json")
    capture_dir = Path(profile["capture"]["directory"])
    component = profile["components"][0]

    mesh = _load_json(profile_dir / "Reference" / "Geo_Body.json")
    positions = np.asarray(_group(mesh["m_Vertices"], 3), dtype=np.float32)
    normals = np.asarray(_group(mesh["m_Normals"], 3), dtype=np.float32)
    colors = np.asarray([_rgba8(c) for c in _group(mesh["m_Colors"], 4)], dtype=np.uint8)

    vb1_path = _resolve_profile_file(
        profile_dir, component["resourceFiles"]["vb1"], capture_dir
    )
    vb1 = vb1_path.read_bytes()
    if len(vb1) // VB1_STRIDE != len(positions):
        raise ValueError("Original VB1 vertex count does not match Geo_Body")
    uv = np.empty((len(positions), 2), dtype=np.float32)
    for i in range(len(positions)):
        uv[i] = struct.unpack_from("<2e", vb1, i * VB1_STRIDE + 4)

    texture_entry = texture_map["textures"]["body.baseColor"]["file"]
    texture_path = _resolve_profile_file(profile_dir, texture_entry, capture_dir)
    texture = _load_dds_rgba(texture_path)
    return positions, normals, uv, colors, texture, texture_path


def _load_mod(mod_dir: Path):
    buffers = mod_dir / "Buffers"
    bind_path = buffers / "Body.BindSkin.R32_UINT.buf"
    vb1_path = buffers / "Body.VB1.buf"
    texture_path = mod_dir / "Textures" / "Body.BaseColor.dds"

    bind = bind_path.read_bytes()
    vb1 = bytearray(vb1_path.read_bytes())
    if len(bind) % BIND_STRIDE:
        raise ValueError(f"{bind_path} size is not divisible by {BIND_STRIDE}")
    if len(vb1) % VB1_STRIDE:
        raise ValueError(f"{vb1_path} size is not divisible by {VB1_STRIDE}")
    count = len(vb1) // VB1_STRIDE
    if len(bind) // BIND_STRIDE != count:
        raise ValueError("Mod BindSkin and VB1 vertex counts differ")

    positions = np.empty((count, 3), dtype=np.float32)
    normals = np.empty((count, 3), dtype=np.float32)
    uv = np.empty((count, 2), dtype=np.float32)
    for i in range(count):
        offset = i * BIND_STRIDE
        positions[i] = struct.unpack_from("<3f", bind, offset)
        normals[i] = struct.unpack_from("<3f", bind, offset + 12)
        uv[i] = struct.unpack_from("<2e", vb1, i * VB1_STRIDE + 4)
    texture = _load_dds_rgba(texture_path)
    return positions, normals, uv, vb1, vb1_path, texture, texture_path


def _normalize_vectors(values: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(length, 1e-8)


def _feature(positions, normals, uv, rgb, bounds_min, bounds_size):
    pos = (positions - bounds_min) / np.maximum(bounds_size, 1e-6)
    normals = _normalize_vectors(normals)
    luma = (
        rgb[:, 0:1] * 0.2126
        + rgb[:, 1:2] * 0.7152
        + rgb[:, 2:3] * 0.0722
    )
    return np.concatenate(
        [
            pos * 0.80,
            normals * 0.25,
            uv * 2.00,
            rgb * 1.20,
            luma * 0.80,
        ],
        axis=1,
    ).astype(np.float32)


def _predict_colors(train_feature, train_colors, query_feature, k=13, chunk=256):
    unique_colors = [tuple(int(v) for v in color) for color in train_colors]
    result = np.empty((len(query_feature), 4), dtype=np.uint8)
    confidence = np.empty(len(query_feature), dtype=np.float32)
    for start in range(0, len(query_feature), chunk):
        q = query_feature[start : start + chunk]
        diff = q[:, None, :] - train_feature[None, :, :]
        dist = np.einsum("qnf,qnf->qn", diff, diff, optimize=True)
        nearest = np.argpartition(dist, min(k, dist.shape[1] - 1), axis=1)[:, :k]
        for row, indices in enumerate(nearest):
            votes = {}
            total = 0.0
            for index in indices:
                weight = 1.0 / max(float(dist[row, index]), 1e-8)
                color = unique_colors[int(index)]
                votes[color] = votes.get(color, 0.0) + weight
                total += weight
            color, score = max(votes.items(), key=lambda item: item[1])
            result[start + row] = color
            confidence[start + row] = score / max(total, 1e-8)
    return result, confidence


def _legacy_low_saturation_cloth_mask(rgb01: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb01 * 255.0 + 0.5, 0, 255).astype(np.int16)
    spread = rgb.max(axis=1) - rgb.min(axis=1)
    return (
        (rgb[:, 0] >= 70)
        & (rgb[:, 0] <= 225)
        & (rgb[:, 1] >= 70)
        & (rgb[:, 1] <= 230)
        & (rgb[:, 2] >= 80)
        & (rgb[:, 2] <= 235)
        & (spread <= 65)
        & (rgb[:, 2] >= rgb[:, 0] - 20)
    )


def _neutralize_preserving_width(colors: np.ndarray, mask: np.ndarray) -> int:
    widths = colors[:, 2] & 0x0F
    changed = int(mask.sum())
    colors[mask, 0] = 0
    colors[mask, 1] = 0
    colors[mask, 2] = 240 + widths[mask]
    colors[mask, 3] = 0
    return changed


def synthesize(profile_dir: Path, mod_dir: Path, dry_run=False, legacy_rgb_safe_filter=False):
    src_pos, src_norm, src_uv, src_colors, src_tex, src_tex_path = _load_original(profile_dir)
    mod_pos, mod_norm, mod_uv, vb1, vb1_path, mod_tex, mod_tex_path = _load_mod(mod_dir)

    bounds_min = np.minimum(src_pos.min(axis=0), mod_pos.min(axis=0))
    bounds_max = np.maximum(src_pos.max(axis=0), mod_pos.max(axis=0))
    bounds_size = bounds_max - bounds_min

    src_rgb = _sample_texture(src_tex, src_uv)
    mod_rgb = _sample_texture(mod_tex, mod_uv)
    src_feature = _feature(src_pos, src_norm, src_uv, src_rgb, bounds_min, bounds_size)
    mod_feature = _feature(mod_pos, mod_norm, mod_uv, mod_rgb, bounds_min, bounds_size)
    predicted, confidence = _predict_colors(src_feature, src_colors, mod_feature)
    legacy_filtered = 0
    if legacy_rgb_safe_filter:
        legacy_filtered = _neutralize_preserving_width(
            predicted, _legacy_low_saturation_cloth_mask(mod_rgb)
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = mod_dir / f"Body.VertexColors.synth-{stamp}.json"
    csv_path = mod_dir / f"Body.VertexColors.synth-{stamp}.csv"
    backup_path = vb1_path.with_suffix(vb1_path.suffix + f".bak-before-synth-mcolors-{stamp}")

    for i, color in enumerate(predicted):
        vb1[i * VB1_STRIDE : i * VB1_STRIDE + 4] = bytes(int(v) for v in color)

    top = Counter(tuple(int(v) for v in color) for color in predicted).most_common(32)
    report = {
        "profileDir": str(profile_dir),
        "modDir": str(mod_dir),
        "sourceTexture": str(src_tex_path),
        "modTexture": str(mod_tex_path),
        "vertexCount": int(len(predicted)),
        "method": "kNN over original Geo_Body position/normal/runtime UV/baseColor RGB -> original m_Colors RGBA",
        "featureWeights": {
            "position": 0.80,
            "normal": 0.25,
            "uv": 2.00,
            "baseColorRgb": 1.20,
            "baseColorLuma": 0.80,
        },
        "confidence": {
            "min": float(confidence.min()),
            "mean": float(confidence.mean()),
            "p05": float(np.quantile(confidence, 0.05)),
        },
        "legacyRgbSafeColorFilter": {
            "enabled": bool(legacy_rgb_safe_filter),
            "neutralizedVertices": int(legacy_filtered),
            "rule": "low-saturation cloth-like baseColor -> (0,0,240+predicted_width,0)",
        },
        "topColors": [
            {"rgba": list(color), "count": int(count), "width": int(color[2] & 15)}
            for color, count in top
        ],
        "output": {
            "vb1": str(vb1_path),
            "backup": str(backup_path),
            "json": str(report_path),
            "csv": str(csv_path),
            "dryRun": bool(dry_run),
        },
    }

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["vertex", "r", "g", "b", "a", "width", "confidence", "u", "v"])
        for i, color in enumerate(predicted):
            writer.writerow([
                i, int(color[0]), int(color[1]), int(color[2]), int(color[3]),
                int(color[2] & 15), f"{float(confidence[i]):.6f}",
                f"{float(mod_uv[i,0]):.8f}", f"{float(mod_uv[i,1]):.8f}",
            ])
    if not dry_run:
        shutil.copy2(vb1_path, backup_path)
        vb1_path.write_bytes(vb1)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--mod-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--legacy-rgb-safe-filter", action="store_true")
    args = parser.parse_args()
    report = synthesize(
        args.profile_dir,
        args.mod_dir,
        dry_run=args.dry_run,
        legacy_rgb_safe_filter=args.legacy_rgb_safe_filter,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
