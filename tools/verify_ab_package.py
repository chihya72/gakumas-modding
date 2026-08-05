"""Offline verifier for an AB bundle source directory.

Stdlib only.  It checks the export contract that can be checked without Unity:
manifest/sidecar handshake, t4 size, m_Colors shape/channel loss, weighted
critical joints, declared new-bone ownership, and optional log/artifact hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


CRITICAL_BONES = (
    "Hips", "Spine",
    "LeftArm", "LeftForeArm", "LeftHand",
    "RightArm", "RightForeArm", "RightHand",
    "LeftUpLeg", "LeftLeg", "LeftFoot",
    "RightUpLeg", "RightLeg", "RightFoot",
)


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_src(root: Path) -> Path:
    root = root.resolve()
    candidate = root / "bundle-src"
    if (candidate / "mod.json").is_file():
        return candidate
    if (root / "mod.json").is_file():
        return root
    raise FileNotFoundError(f"找不到 bundle-src/mod.json: {root}")


def _record(report, level: str, message: str):
    report[level].append(message)


def _asset_path(bundle_src: Path, asset: str) -> Path:
    return bundle_src / Path(str(asset)).name


def _new_bone_records(sidecar: dict):
    records = []
    for field in ("newBones", "extraSwingBones"):
        values = sidecar.get(field) or []
        if isinstance(values, list):
            records.extend(item for item in values if isinstance(item, dict))
    source_report = sidecar.get("sourceRigRemap") or {}
    nested = source_report.get("newBones") if isinstance(source_report, dict) else None
    if isinstance(nested, dict):
        for field in ("newBones", "extraSwingBones"):
            values = nested.get(field) or []
            if isinstance(values, list):
                records.extend(item for item in values if isinstance(item, dict))
    return records


def _check_colors(report, geo: dict):
    vertex_count = int(geo.get("m_VertexCount") or 0)
    colors = list(geo.get("m_Colors") or [])
    check = {
        "vertexCount": vertex_count,
        "valueCount": len(colors),
        "expectedValueCount": vertex_count * 4,
        "zeroByChannel": {name: 0 for name in "RGBA"},
        "allZeroVertices": 0,
    }
    if len(colors) != vertex_count * 4:
        _record(report, "errors", "m_Colors 数量与 m_VertexCount 不匹配")
        report["colors"] = check
        return
    for offset in range(0, len(colors), 4):
        values = colors[offset:offset + 4]
        for index, value in enumerate(values):
            if float(value) == 0.0:
                check["zeroByChannel"]["RGBA"[index]] += 1
        if not any(float(value) for value in values):
            check["allZeroVertices"] += 1
    check["zeroChannelValues"] = sum(check["zeroByChannel"].values())
    report["colors"] = check


def _check_weights(report, geo: dict, sidecar: dict, is_body: bool):
    bone_names = [item.get("name") for item in sidecar.get("bones", [])
                  if isinstance(item, dict) and item.get("name")]
    active = [0.0] * len(bone_names)
    invalid = 0
    for influence in geo.get("m_Skin", []) or []:
        indices = influence.get("boneIndex", []) if isinstance(influence, dict) else []
        weights = influence.get("weight", []) if isinstance(influence, dict) else []
        for index, weight in zip(indices, weights):
            index = int(index)
            if index < 0 or index >= len(active):
                invalid += 1
                continue
            if float(weight) > 0.0:
                active[index] += float(weight)
    missing = [name for name in CRITICAL_BONES if name in bone_names
               and active[bone_names.index(name)] <= 0.0]
    absent = [name for name in CRITICAL_BONES if name not in bone_names]
    check = {
        "boneCount": len(bone_names),
        "activeBoneCount": sum(value > 0.0 for value in active),
        "invalidInfluenceCount": invalid,
        "criticalMissingWeight": missing,
        "criticalAbsent": absent,
    }
    if invalid:
        _record(report, "errors", f"boneWeights 有 {invalid} 个越界索引")
    if is_body and (missing or absent):
        _record(report, "errors", "身体承重骨缺失或零权重: " + ", ".join(missing + absent))
    report["weights"] = check


def _check_ownership(report, sidecar: dict):
    bone_names = {item.get("name") for item in sidecar.get("bones", [])
                  if isinstance(item, dict) and item.get("name")}
    source_report = sidecar.get("sourceRigRemap") or {}
    mapped = source_report.get("bones", {}) if isinstance(source_report, dict) else {}
    mapped_targets = set(mapped.values()) if isinstance(mapped, dict) else set()
    source_names = set(mapped) | set(source_report.get("accessoryBones", []) or [])
    declared_records = _new_bone_records(sidecar)
    declared = {item.get("name") for item in declared_records if item.get("name")}
    # The sidecar contains the full target template skeleton, not only bones that
    # received source weights.  Therefore an unreferenced target helper (e.g. *_H,
    # *_S, Spine2) is legal.  Leakage means a source name survived into that array
    # without being mapped to a target or declared as a runtime-created new bone.
    source_leaks = sorted((bone_names & source_names) - mapped_targets - declared)
    bad_parents = []
    known = bone_names | declared | mapped_targets | set(CRITICAL_BONES) | {"Hips"}
    for item in declared_records:
        name = item.get("name")
        parent = item.get("parentName")
        if not name or not parent or parent not in known:
            bad_parents.append({"name": name, "parentName": parent})
        if "swing" not in item:
            _record(report, "warnings", f"新骨 {name} 未声明 swing 参数")
    check = {
        "sourceBoneLeaks": source_leaks,
        "declaredNewBones": sorted(declared),
        "invalidNewBoneParents": bad_parents,
    }
    if source_leaks:
        _record(report, "errors", "sidecar 存在未归属源骨名: " + ", ".join(source_leaks))
    if bad_parents:
        _record(report, "errors", "新骨存在无效父级")
    report["boneOwnership"] = check


def _side_of(name: str):
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    if normalized.startswith("left_") or normalized.startswith("left"):
        return "left"
    if normalized.startswith("right_") or normalized.startswith("right"):
        return "right"
    tokens = normalized.split("_")
    if "l" in tokens:
        return "left"
    if "r" in tokens:
        return "right"
    return "unclassified"


def _check_swing(report, sidecar: dict):
    bones = [item for item in sidecar.get("bones", []) if isinstance(item, dict)]
    required = {"damping", "stiffness", "spring", "mass", "useWindGlobalForce"}
    counts = {"left": 0, "right": 0, "unclassified": 0}
    invalid_parents = []
    missing_parameters = []
    for item in bones:
        swing = item.get("swing")
        if not isinstance(swing, dict):
            continue
        name = item.get("name") or "<unnamed>"
        counts[_side_of(name)] += 1
        parent = item.get("parentIndex")
        if not isinstance(parent, int) or parent < -1 or parent >= len(bones):
            invalid_parents.append({"name": name, "parentIndex": parent})
        missing = sorted(required - set(swing))
        if missing:
            missing_parameters.append({"name": name, "missing": missing})
    check = {
        "total": sum(counts.values()),
        **counts,
        "invalidParentCount": len(invalid_parents),
        "missingParameterCount": len(missing_parameters),
    }
    if invalid_parents:
        _record(report, "errors", "摇物骨存在无效 parentIndex")
    if missing_parameters:
        _record(report, "warnings", "摇物骨缺少物理参数: " + ", ".join(item["name"] for item in missing_parameters))
    if counts["left"] and counts["left"] != counts["right"]:
        _record(report, "warnings", f"摇物骨左右数量不对称: Left={counts['left']} Right={counts['right']}")
    report["swing"] = check


def verify_package(root, log_paths=(), hash_paths=()):
    bundle_src = _bundle_src(Path(root))
    manifest_path = bundle_src / "mod.json"
    manifest = _read_json(manifest_path)
    report = {
        "ok": False,
        "bundleSource": str(bundle_src),
        "errors": [],
        "warnings": [],
        "files": {},
    }
    for path in sorted(bundle_src.iterdir()):
        if path.is_file():
            report["files"][path.name] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}

    replacements = manifest.get("replacements") or []
    replacement = replacements[0] if replacements else {}
    sidecar_path = _asset_path(bundle_src, replacement.get("skeleton", ""))
    geo_paths = sorted(bundle_src.glob("*.geojson.txt"))
    if not sidecar_path.is_file():
        _record(report, "errors", f"找不到骨骼 sidecar: {sidecar_path.name}")
        sidecar = {}
    else:
        sidecar = _read_json(sidecar_path)
    if not geo_paths:
        _record(report, "errors", "找不到 *.geojson.txt")

    manifest_protocol = manifest.get("runtimeProtocol")
    sidecar_protocol = sidecar.get("runtimeProtocol")
    manifest_build = manifest.get("buildId")
    sidecar_build = sidecar.get("buildId")
    report["handshake"] = {
        "manifestRuntimeProtocol": manifest_protocol,
        "sidecarRuntimeProtocol": sidecar_protocol,
        "manifestBuildId": manifest_build,
        "sidecarBuildId": sidecar_build,
    }
    if manifest_protocol != 1 or sidecar_protocol != 1:
        _record(report, "errors", "runtimeProtocol 缺失或不是 1")
    if not manifest_build or manifest_build != sidecar_build:
        _record(report, "errors", "manifest 与 sidecar 的 buildId 缺失或不一致")

    renderer_ids = {
        str(item.get("rendererId", "")).lower()
        for item in replacement.get("renderers", []) or []
    }
    is_body = (
        str(replacement.get("part", "body")).lower() == "body"
        and not renderer_ids.difference({"", "body"})
    )
    t4_files = []
    for item in replacement.get("textures", []) or []:
        prop = str(item.get("property", "")).lower()
        if "t4" in prop or "shade" in prop or "sdw" in prop:
            path = _asset_path(bundle_src, item.get("asset", ""))
            if path.is_file():
                t4_files.append({"name": path.name, "bytes": path.stat().st_size})
            else:
                _record(report, "errors", f"t4 贴图不存在: {path.name}")
    report["t4"] = {"files": t4_files, "mbLevel": any(item["bytes"] >= 1_000_000 for item in t4_files)}
    if is_body and not t4_files:
        _record(report, "errors", "身体替换没有 t4/ShadeMap 贴图")
    elif t4_files and not report["t4"]["mbLevel"]:
        _record(report, "warnings", "t4/ShadeMap 小于 1 MB，需确认不是纯黑/空图")

    if sidecar:
        _check_ownership(report, sidecar)
        _check_swing(report, sidecar)
    for geo_path in geo_paths:
        geo = _read_json(geo_path)
        _check_colors(report, geo)
        if sidecar:
            _check_weights(report, geo, sidecar, is_body)
        break

    for path in log_paths:
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        found = bool(sidecar_build and sidecar_build in text)
        report.setdefault("logs", []).append({"path": str(path), "exists": path.is_file(), "buildIdFound": found})
        if not found:
            _record(report, "errors", f"日志未找到 buildId={sidecar_build}: {path}")
    report["artifacts"] = [{"path": str(path), "exists": Path(path).is_file(),
                            "sha256": _sha256(Path(path)) if Path(path).is_file() else None}
                           for path in hash_paths]
    report["ok"] = not report["errors"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="核对 AB bundle 源/发布包的离线契约")
    parser.add_argument("root", type=Path, help="包目录或 bundle-src 目录")
    parser.add_argument("--log", action="append", default=[], type=Path, help="可重复；检查日志是否含 buildId")
    parser.add_argument("--hash", action="append", default=[], type=Path, dest="hash_paths", help="可重复；输出 ZIP/DLL/bundle SHA-256")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)
    try:
        report = verify_package(args.root, args.log, args.hash_paths)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"核包失败: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"AB package: {'PASS' if report['ok'] else 'FAIL'}")
        for message in report["errors"]:
            print(f"ERROR: {message}")
        for message in report["warnings"]:
            print(f"WARN: {message}")
        if report.get("handshake"):
            print("buildId:", report["handshake"].get("sidecarBuildId"))
        if report.get("swing"):
            swing = report["swing"]
            print("swing:", "total={total} left={left} right={right} unclassified={unclassified}".format(**swing))
        print("files:", len(report["files"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
