from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


TRANSFORM_FIELDS = ("localPosition", "localRotation", "localScale", "bindPose")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index(items: list[dict], label: str) -> dict[str, dict]:
    result = {item["name"]: item for item in items}
    if len(result) != len(items):
        raise RuntimeError(f"{label} contains duplicate bone names")
    return result


def _copy_fields(source: dict, target: dict, fields: tuple[str, ...], label: str) -> None:
    for field in fields:
        if field not in source:
            raise RuntimeError(f"{label} has no {field}")
        target[field] = copy.deepcopy(source[field])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build E as D plus only the 22 chain-root transforms from a candidate sidecar."
    )
    parser.add_argument("base", type=Path, help="D final sidecar")
    parser.add_argument("candidate", type=Path, help="candidate sidecar containing root transforms")
    args = parser.parse_args()

    base = _load(args.base)
    candidate = _load(args.candidate)
    result = copy.deepcopy(base)
    result["buildId"] = candidate.get("buildId", base.get("buildId"))

    roots = {root for chain in base["swingChains"] for root in chain["rootBones"]}
    base_bones = _index(base["bones"], "base bones")
    candidate_bones = _index(candidate["bones"], "candidate bones")
    result_bones = _index(result["bones"], "result bones")

    base_new = base["sourceRigRemap"]["newBones"]
    candidate_new = candidate["sourceRigRemap"]["newBones"]
    result_new = result["sourceRigRemap"]["newBones"]
    base_new_bones = _index(base_new["newBones"], "base remap newBones")
    candidate_new_bones = _index(candidate_new["newBones"], "candidate remap newBones")
    result_new_bones = _index(result_new["newBones"], "result remap newBones")

    for name in sorted(roots):
        _copy_fields(candidate_bones[name], result_bones[name], TRANSFORM_FIELDS[:3], f"bone:{name}")
        _copy_fields(
            candidate_new_bones[name],
            result_new_bones[name],
            TRANSFORM_FIELDS,
            f"remap-new:{name}",
        )

    args.candidate.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "candidate": str(args.candidate),
                "baseBuildId": base.get("buildId"),
                "candidateBuildId": result.get("buildId"),
                "rootCount": len(roots),
                "preservedBoneCount": len(result["bones"]) - len(roots),
                "preservedExtraSwingBones": len(result["extraSwingBones"]),
                "preservedSwingChains": len(result["swingChains"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
