#!/usr/bin/env python3
"""Build one-channel-at-a-time DDS probes from captured game textures."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def write_variant(source: Path, output_png: Path, channel: int, value: int) -> None:
    image = Image.open(source).convert("RGBA")
    channels = list(image.split())
    channels[channel] = Image.new("L", image.size, value)
    Image.merge("RGBA", channels).save(output_png)


def convert(texconv: Path, source: Path, output_dir: Path, srgb: bool) -> None:
    command = [str(texconv), "-y", "-f", "BC7_UNORM_SRGB" if srgb else "BC7_UNORM",
               "-o", str(output_dir), str(source)]
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mask", type=Path, required=True, help="Captured Packed Mask DDS")
    parser.add_argument("--shade", type=Path, required=True, help="Captured Shade Color DDS")
    parser.add_argument("--texconv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gakumas-material-probes-") as temporary:
        temporary_dir = Path(temporary)
        sources = {}
        for source, stem in ((args.mask, "MaskSource"), (args.shade, "ShadeSource")):
            subprocess.run(
                [str(args.texconv), "-y", "-ft", "png", "-o", str(temporary_dir), str(source)],
                check=True,
            )
            converted = temporary_dir / f"{source.stem}.png"
            sources[stem] = converted

        for index, name in enumerate("RGBA"):
            for value in (0, 255):
                stem = f"Mask{name}{value}"
                png = temporary_dir / f"{stem}.png"
                write_variant(sources["MaskSource"], png, index, value)
                convert(args.texconv, png, args.output, srgb=False)

        for value in (0, 255):
            stem = f"ShadeA{value}"
            png = temporary_dir / f"{stem}.png"
            write_variant(sources["ShadeSource"], png, 3, value)
            convert(args.texconv, png, args.output, srgb=True)

    print(f"Wrote channel probes to {args.output}")


if __name__ == "__main__":
    main()
