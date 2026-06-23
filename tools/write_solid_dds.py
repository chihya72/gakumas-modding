#!/usr/bin/env python3
"""Write a tiny uncompressed RGBA8 DDS for controlled material probes."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("rgba", nargs=4, type=int)
    parser.add_argument("--size", type=int, default=4)
    args = parser.parse_args()
    if args.size < 1 or any(value < 0 or value > 255 for value in args.rgba):
        raise ValueError("Size must be positive and RGBA channels must be 0..255")
    width = height = args.size
    pixel_format = struct.pack(
        "<8I", 32, 0x41, 0, 32, 0x000000FF, 0x0000FF00,
        0x00FF0000, 0xFF000000,
    )
    header = struct.pack(
        "<7I11I", 124, 0x100F, height, width, width * 4, 0, 0,
        *([0] * 11),
    ) + pixel_format + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(b"DDS " + header + bytes(args.rgba) * (width * height))
    print(f"Wrote {args.output} ({width}x{height}, RGBA={args.rgba})")


if __name__ == "__main__":
    main()
