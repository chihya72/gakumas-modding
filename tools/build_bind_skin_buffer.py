#!/usr/bin/env python3
"""Pack the source profile's bind attributes and four influences for HLSL."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    mesh = json.loads(args.mesh_json.read_text(encoding="utf-8"))
    count = int(mesh["m_VertexCount"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        for vertex in range(count):
            p, t = vertex * 3, vertex * 4
            skin = mesh["m_Skin"][vertex]
            stream.write(struct.pack(
                "<3f3f4f4I4f",
                *mesh["m_Vertices"][p:p+3],
                *mesh["m_Normals"][p:p+3],
                *mesh["m_Tangents"][t:t+4],
                *(int(value) for value in skin["boneIndex"]),
                *(float(value) for value in skin["weight"]),
            ))
    expected = count * 72
    actual = args.output.stat().st_size
    if actual != expected:
        raise RuntimeError(f"Packed {actual} bytes, expected {expected}")
    print(json.dumps({"vertexCount": count, "stride": 72, "byteLength": actual, "output": str(args.output.resolve())}, indent=2))


if __name__ == "__main__":
    main()
