from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


PHYSICS_FIELDS = ("swingCategory", "swingRole", "swing")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index(items: list[dict], label: str) -> dict[str, dict]:
    result = {item["name"]: item for item in items}
    if len(result) != len(items):
        raise RuntimeError(f"{label} contains duplicate bone names")
    return result


def _copy_physics(base: dict[str, object], candidate: dict[str, object], label: str) -> None:
    for field in PHYSICS_FIELDS:
        if field in base:
            candidate[field] = copy.deepcopy(base[field])
        elif field in candidate:
            del candidate[field]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lock E's swing metadata and chain declarations to D while preserving E transforms."
    )
    parser.add_argument("base", type=Path, help="D sidecar")
    parser.add_argument("candidate", type=Path, help="E sidecar to update")
    args = parser.parse_args()

    base = _load(args.base)
    candidate = _load(args.candidate)
    base_new = base["sourceRigRemap"]["newBones"]
    candidate_new = candidate["sourceRigRemap"]["newBones"]

    base_bones = _index(base["bones"], "base bones")
    candidate_bones = _index(candidate["bones"], "candidate bones")
    base_extra = _index(base["extraSwingBones"], "base extraSwingBones")
    candidate_extra = _index(candidate["extraSwingBones"], "candidate extraSwingBones")
    base_new_bones = _index(base_new["newBones"], "base remap newBones")
    candidate_new_bones = _index(candidate_new["newBones"], "candidate remap newBones")
    base_new_extra = _index(base_new["extraSwingBones"], "base remap extraSwingBones")
    candidate_new_extra = _index(candidate_new["extraSwingBones"], "candidate remap extraSwingBones")

    cloth_bone_names = {
        item["name"] for item in base_new["newBones"] if item.get("swingCategory") == "cloth"
    }
    cloth_extra_names = {
        item["name"] for item in base["extraSwingBones"] if item.get("swingCategory") == "cloth"
    }
    if not cloth_bone_names or not cloth_extra_names:
        raise RuntimeError("D sidecar does not contain the expected cloth metadata")

    for name in sorted(cloth_bone_names):
        _copy_physics(base_bones[name], candidate_bones[name], f"bone:{name}")
        _copy_physics(base_new_bones[name], candidate_new_bones[name], f"remap-new:{name}")
    for name in sorted(cloth_extra_names):
        _copy_physics(base_extra[name], candidate_extra[name], f"extra:{name}")
        _copy_physics(base_new_extra[name], candidate_new_extra[name], f"remap-extra:{name}")

    candidate["swingChains"] = copy.deepcopy(base["swingChains"])
    candidate_new["swingChains"] = copy.deepcopy(base_new["swingChains"])

    args.candidate.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "candidate": str(args.candidate),
                "lockedClothBones": len(cloth_bone_names),
                "lockedClothExtraBones": len(cloth_extra_names),
                "lockedSwingChains": len(base["swingChains"]),
                "buildId": candidate.get("buildId"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
