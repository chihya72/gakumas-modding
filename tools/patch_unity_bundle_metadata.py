"""Patch fixed-width textual metadata in a Unity bundle without reserializing assets."""

from __future__ import annotations

import argparse
from pathlib import Path


def patch_metadata(source: Path, destination: Path, old: str, new: str, expected: int) -> int:
    if len(old) != len(new):
        raise ValueError("old and new metadata values must have the same byte length")

    payload = source.read_bytes()
    old_bytes = old.encode("ascii")
    new_bytes = new.encode("ascii")
    count = payload.count(old_bytes)
    if count != expected:
        raise ValueError(f"expected {expected} occurrences of {old!r}, found {count}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload.replace(old_bytes, new_bytes))
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--expected", type=int, default=2)
    args = parser.parse_args()

    count = patch_metadata(
        args.source,
        args.destination,
        args.old,
        args.new,
        args.expected,
    )
    print(f"patched {count} metadata occurrence(s): {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
