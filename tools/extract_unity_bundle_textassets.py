"""Extract selected Unity TextAsset payloads without changing their bytes."""

from __future__ import annotations

import argparse
from pathlib import Path

import UnityPy


def extract(bundle: Path, output_dir: Path, names: list[str]) -> int:
    env = UnityPy.load(str(bundle))
    wanted = set(names)
    found: set[str] = set()
    output_dir.mkdir(parents=True, exist_ok=True)
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        asset = obj.read()
        name = str(getattr(asset, "m_Name", ""))
        if name not in wanted:
            continue
        payload = bytes(asset.m_Script)
        (output_dir / name).write_bytes(payload)
        found.add(name)
    missing = wanted - found
    if missing:
        raise ValueError(f"missing TextAsset(s): {', '.join(sorted(missing))}")
    return len(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    count = extract(args.bundle, args.output_dir, args.names)
    print(f"extracted {count} TextAsset(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
