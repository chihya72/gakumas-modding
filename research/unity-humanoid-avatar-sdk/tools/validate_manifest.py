"""Validate the runtime manifest without requiring Unity or BepInEx."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
CHARACTER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def _relative(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{field} must be a non-empty relative path")
        return
    parts = value.split("/")
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        errors.append(f"{field} must use a relative Unity path: {value}")
    if any(part in {"", ".", ".."} for part in parts):
        errors.append(f"{field} must be normalized: {value}")


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    for field in ("id", "name", "version", "author"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            errors.append(f"{field} is required")
    if isinstance(manifest.get("id"), str) and not ID_RE.fullmatch(manifest["id"]):
        errors.append("id must match ^[a-z0-9][a-z0-9._-]{1,63}$")
    for field in ("bundle", "asset", "descriptor"):
        _relative(manifest.get(field), field, errors)

    targets = manifest.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append("targets must contain at least one character")
        targets = []
    seen: set[str] = set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            errors.append(f"targets[{index}] must be an object")
            continue
        character_id = target.get("characterId")
        if not isinstance(character_id, str) or not CHARACTER_RE.fullmatch(character_id):
            errors.append(f"targets[{index}].characterId is invalid")
        elif character_id in seen:
            errors.append(f"duplicate target characterId: {character_id}")
        else:
            seen.add(character_id)
    if "enabled" in manifest and not isinstance(manifest["enabled"], bool):
        errors.append("enabled must be boolean")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        errors = validate_manifest(_read(args.manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
