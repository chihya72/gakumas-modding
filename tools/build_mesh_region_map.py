#!/usr/bin/env python3
"""Split an extracted Unity mesh into deterministic connected regions.

The region map is Profile evidence, not an automatic deletion decision.  It
lets Blender show the original hands/neck/clothing islands as reviewable units
instead of hiding geometry behind hard-coded coordinate thresholds.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--skeleton-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--vertex-map", type=Path, required=True)
    parser.add_argument("--triangle-map", type=Path, required=True)
    args = parser.parse_args()

    mesh = load_json(args.mesh_json)
    skeleton = load_json(args.skeleton_json)
    vertex_count = int(mesh["m_VertexCount"])
    indices = [int(value) for value in mesh["m_Indices"]]
    positions = mesh["m_Vertices"]
    skin = mesh["m_Skin"]
    if len(indices) % 3:
        raise ValueError("Only triangle-list meshes are supported")

    parent = list(range(vertex_count))
    size = [1] * vertex_count

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left == right:
            return
        if size[left] < size[right]:
            left, right = right, left
        parent[right] = left
        size[left] += size[right]

    for offset in range(0, len(indices), 3):
        a, b, c = indices[offset : offset + 3]
        union(a, b)
        union(a, c)

    raw_regions: dict[int, dict[str, Any]] = {}
    triangle_roots: list[int] = []
    for offset in range(0, len(indices), 3):
        triangle = indices[offset : offset + 3]
        root = find(triangle[0])
        triangle_roots.append(root)
        region = raw_regions.setdefault(root, {"triangles": 0, "vertices": set()})
        region["triangles"] += 1
        region["vertices"].update(triangle)

    # Largest regions first, then minimum source vertex for a stable tie-break.
    ordered = sorted(
        raw_regions.items(),
        key=lambda item: (-item[1]["triangles"], min(item[1]["vertices"])),
    )
    id_by_root = {root: region_id for region_id, (root, _) in enumerate(ordered)}
    names = {
        int(node["weightedIndex"]): node["name"]
        for node in skeleton["nodes"]
        if node.get("weightedIndex") is not None
    }

    regions = []
    for region_id, (_, raw) in enumerate(ordered):
        vertices = sorted(raw["vertices"])
        bounds_min = [min(float(positions[v * 3 + axis]) for v in vertices) for axis in range(3)]
        bounds_max = [max(float(positions[v * 3 + axis]) for v in vertices) for axis in range(3)]
        bone_weights: dict[str, float] = {}
        for vertex in vertices:
            influence = skin[vertex]
            for bone, weight in zip(influence["boneIndex"], influence["weight"]):
                weight = float(weight)
                if weight > 0.0:
                    name = names[int(bone)]
                    bone_weights[name] = bone_weights.get(name, 0.0) + weight
        dominant = sorted(bone_weights.items(), key=lambda item: item[1], reverse=True)[:8]
        total = max(float(len(vertices)), 1.0)
        hand_score = sum(weight for name, weight in bone_weights.items() if "Hand" in name) / total
        neck_score = sum(weight for name, weight in bone_weights.items() if name in {"Neck", "Head"}) / total
        centered = bounds_min[0] >= -0.075 and bounds_max[0] <= 0.075
        suggestions = []
        if hand_score >= 0.20 and max(abs(bounds_min[0]), abs(bounds_max[0])) >= 0.45:
            suggestions.append("native-hand-candidate")
        if neck_score >= 0.04 and centered and bounds_max[1] >= 1.19:
            suggestions.append("native-neck-candidate")
        regions.append({
            "id": region_id,
            "triangleCount": raw["triangles"],
            "vertexCount": len(vertices),
            "minVertex": vertices[0],
            "bounds": {"min": bounds_min, "max": bounds_max},
            "dominantBones": [{"name": name, "accumulatedWeight": weight} for name, weight in dominant],
            "scores": {"hand": hand_score, "neckOrHead": neck_score},
            "suggestions": suggestions,
        })

    vertex_regions = [0xFFFF] * vertex_count
    for root, raw in raw_regions.items():
        region_id = id_by_root[root]
        for vertex in raw["vertices"]:
            if vertex_regions[vertex] != 0xFFFF and vertex_regions[vertex] != region_id:
                raise ValueError("A vertex belongs to multiple connected regions")
            vertex_regions[vertex] = region_id
    triangle_regions = [id_by_root[root] for root in triangle_roots]

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.vertex_map.parent.mkdir(parents=True, exist_ok=True)
    args.triangle_map.parent.mkdir(parents=True, exist_ok=True)
    args.vertex_map.write_bytes(struct.pack(f"<{len(vertex_regions)}H", *vertex_regions))
    args.triangle_map.write_bytes(struct.pack(f"<{len(triangle_regions)}H", *triangle_regions))
    report = {
        "schemaVersion": 1,
        "sourceMesh": str(args.mesh_json),
        "vertexCount": vertex_count,
        "triangleCount": len(indices) // 3,
        "regionCount": len(regions),
        "vertexMap": str(args.vertex_map),
        "triangleMap": str(args.triangle_map),
        "mapFormat": "little-endian R16_UINT region id",
        "reviewRequired": True,
        "regions": regions,
    }
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidates = [region for region in regions if region["suggestions"]]
    print(json.dumps({"regions": len(regions), "candidates": len(candidates), "candidateIds": [region["id"] for region in candidates]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
