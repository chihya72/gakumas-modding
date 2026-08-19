"""Build an asset-level reference inventory from the existing AssetStudio dumps.

This is deliberately not a live Animator/face reference generator. The checked-in
unpack data contains mesh and skeleton evidence, so this tool records that evidence
and leaves live-only fields marked as ``not_observed`` until the BepInEx probe runs.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


RESOURCE_RE = re.compile(
    r"^mdl_chr_(?P<character>[a-z0-9]+)-(?P<variant>.+)_(?P<part>body|hair)$",
    re.IGNORECASE,
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _shape_names(mesh: dict[str, Any]) -> list[str]:
    raw = mesh.get("m_Shapes")
    if not isinstance(raw, dict):
        return []
    channels = raw.get("channels")
    if not isinstance(channels, list):
        return []
    names: list[str] = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        name = channel.get("name", channel.get("m_Name"))
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return sorted(names)


def _node_names(skeleton: dict[str, Any]) -> tuple[list[str], list[str], str | None]:
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list):
        return [], [], None
    all_names: list[str] = []
    weighted: list[str] = []
    root_path_id = skeleton.get("rootBonePathId")
    root_name: str | None = None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        name = node.get("name")
        if not isinstance(name, str) or not name:
            continue
        all_names.append(name)
        if node.get("weightedIndex") is not None:
            weighted.append(name)
        if root_path_id is not None and node.get("pathId") == root_path_id:
            root_name = name
    return sorted(set(all_names)), sorted(set(weighted)), root_name


def _mesh_stats(mesh_path: Path) -> dict[str, Any]:
    mesh = _read_json(mesh_path)
    submeshes = mesh.get("m_SubMeshes")
    return {
        "meshPath": mesh_path.name,
        "meshName": mesh.get("m_Name"),
        "vertexCount": mesh.get("m_VertexCount"),
        "subMeshCount": len(submeshes) if isinstance(submeshes, list) else None,
        "blendShapes": _shape_names(mesh),
    }


def _renderer_record(
    data_root: Path,
    directory: Path,
    skeleton_path: Path,
    mesh_path: Path | None,
    renderer_name: str,
    include_mesh_stats: bool,
) -> dict[str, Any]:
    skeleton = _read_json(skeleton_path)
    all_names, weighted_names, root_name = _node_names(skeleton)
    record: dict[str, Any] = {
        "renderer": renderer_name,
        "skeletonPath": skeleton_path.relative_to(data_root).as_posix(),
        "unityVersion": skeleton.get("unityVersion"),
        "schemaVersion": skeleton.get("schemaVersion"),
        "nodeCount": skeleton.get("nodeCount", len(all_names)),
        "weightedBoneCount": skeleton.get("weightedBoneCount", len(weighted_names)),
        "rootBone": root_name,
        "boneNames": all_names,
        "weightedBoneNames": weighted_names,
    }
    if mesh_path is not None and mesh_path.is_file():
        if include_mesh_stats:
            record["mesh"] = _mesh_stats(mesh_path)
        else:
            record["mesh"] = {
                "meshPath": mesh_path.relative_to(data_root).as_posix(),
                "stats": "not_collected",
            }
    else:
        record["mesh"] = None
    return record


def _resource_record(
    data_root: Path,
    directory: Path,
    part: str,
    include_mesh_stats: bool,
) -> dict[str, Any] | None:
    match = RESOURCE_RE.match(directory.name)
    if not match or match.group("part").lower() != part:
        return None
    primary_name = "Geo_Body" if part == "body" else "Geo_Hair"
    primary_skeleton = directory / f"{primary_name}.skeleton.json"
    primary_mesh = directory / f"{primary_name}.json"
    if not primary_skeleton.is_file():
        return None
    renderers = [
        _renderer_record(
            data_root,
            directory,
            primary_skeleton,
            primary_mesh,
            primary_name,
            include_mesh_stats,
        )
    ]
    if part == "hair":
        prop_skeleton = directory / "Geo_HairProp.skeleton.json"
        prop_mesh = directory / "Geo_HairProp.json"
        if prop_skeleton.is_file():
            renderers.append(
                _renderer_record(
                    data_root,
                    directory,
                    prop_skeleton,
                    prop_mesh,
                    "Geo_HairProp",
                    include_mesh_stats,
                )
            )
    return {
        "source": directory.name,
        "characterId": match.group("character").lower(),
        "variant": match.group("variant"),
        "part": part,
        "directory": directory.relative_to(data_root).as_posix(),
        "renderers": renderers,
    }


def _intersection(values: Iterable[set[str]]) -> list[str]:
    sets = list(values)
    if not sets:
        return []
    result = set.intersection(*sets)
    return sorted(result)


def build_inventory(data_root: Path, include_mesh_stats: bool = False) -> dict[str, Any]:
    data_root = data_root.resolve()
    source_dirs = {
        "body": data_root / "assetstudio-body-json",
        "hair": data_root / "assetstudio-hair-json",
    }
    resources: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for part, root in source_dirs.items():
        if not root.is_dir():
            skipped.append({"part": part, "reason": "directory_missing", "path": root.name})
            continue
        for directory in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
            record = _resource_record(data_root, directory, part, include_mesh_stats)
            if record is None:
                skipped.append({"part": part, "reason": "primary_skeleton_missing", "path": directory.name})
                continue
            resources.append(record)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        grouped[resource["characterId"]].append(resource)
    characters: list[dict[str, Any]] = []
    for character_id in sorted(grouped):
        character_resources = sorted(grouped[character_id], key=lambda item: item["source"])
        weighted_sets: list[set[str]] = []
        all_sets: list[set[str]] = []
        for resource in character_resources:
            for renderer in resource["renderers"]:
                weighted_sets.append(set(renderer["weightedBoneNames"]))
                all_sets.append(set(renderer["boneNames"]))
        characters.append({
            "characterId": character_id,
            "resourceCount": len(character_resources),
            "bodyResourceCount": sum(item["part"] == "body" for item in character_resources),
            "hairResourceCount": sum(item["part"] == "hair" for item in character_resources),
            "weightedBoneUnion": sorted(set().union(*weighted_sets) if weighted_sets else set()),
            "weightedBoneIntersection": _intersection(weighted_sets),
            "boneUnion": sorted(set().union(*all_sets) if all_sets else set()),
            "resources": [item["source"] for item in character_resources],
        })

    unity_versions = sorted({
        renderer["unityVersion"]
        for resource in resources
        for renderer in resource["renderers"]
        if renderer.get("unityVersion")
    })
    return {
        "schemaVersion": 1,
        "referenceKind": "asset_inventory",
        "status": {
            "animator": "not_observed",
            "face": "not_observed",
            "pose": "not_observed",
            "assetEvidence": "observed",
        },
        "source": {
            "kind": "AssetStudio JSON dump",
            "root": data_root.name,
            "unityVersions": unity_versions,
        },
        "characters": characters,
        "resources": resources,
        "skipped": skipped,
        "counts": {
            "characters": len(characters),
            "resources": len(resources),
            "bodyResources": sum(item["part"] == "body" for item in resources),
            "hairResources": sum(item["part"] == "hair" for item in resources),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True, help="mod-workspace/libraries directory")
    parser.add_argument("--output", type=Path, required=True, help="output JSON path")
    parser.add_argument(
        "--include-mesh-stats",
        action="store_true",
        help="read mesh JSON files and include vertex/submesh/blendshape statistics (slower)",
    )
    args = parser.parse_args()
    inventory = build_inventory(args.data_root, include_mesh_stats=args.include_mesh_stats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(inventory["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
