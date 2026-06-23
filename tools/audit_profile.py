#!/usr/bin/env python3
"""Audit a GakumasMI game Profile and emit a machine-readable data contract.

This intentionally uses only the Python standard library so the same audit can
run from the repository, Blender's bundled Python, or a release validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Check:
    id: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status, "message": self.message}


class Auditor:
    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir.resolve()
        self.repo_root = self.profile_dir.parent.parent
        self.checks: list[Check] = []

    def check(self, check_id: str, condition: bool, ok: str, fail: str) -> None:
        self.checks.append(Check(check_id, "pass" if condition else "fail", ok if condition else fail))

    def warn(self, check_id: str, message: str) -> None:
        self.checks.append(Check(check_id, "warning", message))

    def resolve(self, value: str | Path, base: Path | None = None) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        candidates = [
            (base or self.profile_dir) / path,
            self.profile_dir / path,
            self.repo_root / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return candidates[0].resolve()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def parse_descriptor(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    result: dict[str, Any] = {"raw": text}
    for key, quoted, plain in re.findall(r'(\w+)=(?:"([^"]*)"|([^\s]+))', text):
        value = quoted or plain
        result[key] = int(value) if value.isdigit() else value
    return result


def find_capture_resource(capture: Path, draw: int, binding: str, resource_hash: str) -> list[Path]:
    prefix = f"{draw:06d}-{binding}={resource_hash.lower()}-"
    return sorted(path for path in capture.glob(prefix + "*") if path.suffix.lower() in {".buf", ".dds", ".jpg", ".png"})


def parse_index_dump_header(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        normalized = key.replace(" ", "")
        result[normalized] = int(value) if value.isdigit() else value
    return result


def audit(profile_dir: Path) -> dict[str, Any]:
    auditor = Auditor(profile_dir)
    required = ["profile.json", "drawcall_map.json", "material_map.json", "texture_map.json"]
    documents: dict[str, Any] = {}
    for name in required:
        path = auditor.profile_dir / name
        auditor.check(f"document.{name}", path.is_file(), f"Found {name}", f"Missing {name}")
        if path.is_file():
            documents[name] = load_json(path)

    if "profile.json" not in documents:
        raise ValueError("profile.json is required")
    profile = documents["profile.json"]
    drawcalls = documents.get("drawcall_map.json", {})
    materials = documents.get("material_map.json", {})
    textures = documents.get("texture_map.json", {})
    component = next((item for item in profile.get("components", []) if item.get("id") == "body"), None)
    auditor.check("profile.body", component is not None, "Body component is defined", "Body component is missing")
    if component is None:
        raise ValueError("Body component is required")

    skinning = profile.get("skinning", {})
    inverse = skinning.get("inverseSkin", {})
    mesh_path = auditor.resolve(inverse.get("meshJson", skinning.get("sourceMeshJson", "")))
    skeleton_path = auditor.resolve(inverse.get("skeletonJson", skinning.get("skeletonJson", "")))
    operator_path = auditor.resolve(inverse.get("inverseOperator", ""))
    for check_id, path in (("source.mesh", mesh_path), ("source.skeleton", skeleton_path), ("inverse.operator", operator_path)):
        auditor.check(check_id, path.is_file(), f"Found {path}", f"Missing {path}")

    mesh = load_json(mesh_path) if mesh_path.is_file() else {}
    skeleton = load_json(skeleton_path) if skeleton_path.is_file() else {}
    vertex_count = int(mesh.get("m_VertexCount", 0))
    bind_count = len(mesh.get("m_BindPose", []))
    indices = [int(value) for value in mesh.get("m_Indices", [])]
    source_arrays = {
        "positions": (len(mesh.get("m_Vertices", [])), vertex_count * 3),
        "normals": (len(mesh.get("m_Normals", [])), vertex_count * 3),
        "tangents": (len(mesh.get("m_Tangents", [])), vertex_count * 4),
        "colors": (len(mesh.get("m_Colors", [])), vertex_count * 4),
        "uv0": (len(mesh.get("m_UV0", [])), vertex_count * 2),
        "uv1": (len(mesh.get("m_UV1", [])), vertex_count * 2),
        "skin": (len(mesh.get("m_Skin", [])), vertex_count),
    }
    auditor.check("mesh.vertexCount", vertex_count == int(component.get("vertices", -1)), f"Vertex count is {vertex_count}", f"Mesh/Profile vertex mismatch: {vertex_count} != {component.get('vertices')}")
    auditor.check("mesh.indexCount", len(indices) == int(component.get("indices", -1)), f"Index count is {len(indices)}", f"Mesh/Profile index mismatch: {len(indices)} != {component.get('indices')}")
    auditor.check("mesh.indexBounds", bool(indices) and min(indices) >= 0 and max(indices) < vertex_count, f"Indices address [0, {max(indices) if indices else -1}]", "Index buffer addresses a vertex outside the mesh")
    for name, (actual, expected) in source_arrays.items():
        auditor.check(f"mesh.array.{name}", actual == expected, f"{name}: {actual} scalar/records", f"{name}: expected {expected}, got {actual}")

    weighted_nodes = [node for node in skeleton.get("nodes", []) if node.get("weightedIndex") is not None]
    weighted_indices = sorted(int(node["weightedIndex"]) for node in weighted_nodes)
    expected_weighted = list(range(bind_count))
    auditor.check("skeleton.bindPoseCount", bind_count == int(skinning.get("weightedBones", -1)), f"Bind poses: {bind_count}", f"Bind pose/Profile mismatch: {bind_count} != {skinning.get('weightedBones')}")
    auditor.check("skeleton.weightedIndices", weighted_indices == expected_weighted, f"Weighted indices are contiguous 0..{bind_count - 1}", "Weighted skeleton indices are missing, duplicated, or out of range")
    auditor.check("skeleton.nodeCount", len(skeleton.get("nodes", [])) == int(skinning.get("hierarchyNodes", -1)), f"Hierarchy nodes: {len(skeleton.get('nodes', []))}", "Skeleton node count differs from Profile")

    active_bones: set[int] = set()
    bad_weights = 0
    max_weight_error = 0.0
    for influence in mesh.get("m_Skin", []):
        bones = influence.get("boneIndex", [])
        weights = influence.get("weight", [])
        if len(bones) != 4 or len(weights) != 4:
            bad_weights += 1
            continue
        total = sum(float(weight) for weight in weights)
        max_weight_error = max(max_weight_error, abs(total - 1.0))
        for bone, weight in zip(bones, weights):
            bone, weight = int(bone), float(weight)
            if weight < 0.0 or bone < 0 or bone >= bind_count:
                bad_weights += 1
            if weight > 0.0:
                active_bones.add(bone)
    auditor.check("skin.fourInfluences", bad_weights == 0, "Every source vertex has four valid influence slots", f"Invalid influence records: {bad_weights}")
    auditor.check("skin.weightSums", max_weight_error <= 1e-4, f"Maximum |sum(weights)-1| is {max_weight_error:.3g}", f"Weight sum error reaches {max_weight_error:.3g}")
    configured_active = int(skinning.get("sourceActiveBones", bind_count))
    auditor.check("skin.activeBones", len(active_bones) == configured_active, f"Active weighted bones: {len(active_bones)}", f"Active bone count {len(active_bones)} != {configured_active}")
    inactive_names = [node["name"] for node in weighted_nodes if int(node["weightedIndex"]) not in active_bones]
    configured_inactive = sorted(skinning.get("sourceInactiveBones", []))
    auditor.check("skin.inactiveBones", sorted(inactive_names) == configured_inactive, f"Source-inactive bones: {inactive_names}", f"Observed inactive bones {inactive_names} != Profile {configured_inactive}")
    skeleton_names = {node.get("name") for node in weighted_nodes}
    configured_unobservable = inverse.get("unobservableBones", [])
    auditor.check("inverse.unobservableBones", bool(configured_unobservable) and all(name in skeleton_names for name in configured_unobservable), f"Numerically unobservable bones are declared: {configured_unobservable}", "Inverse-skin unobservable-bone declaration is empty or references an unknown bone")

    coefficient_count = int(inverse.get("coefficientCount", bind_count * 4))
    expected_operator_bytes = coefficient_count * vertex_count * 4
    actual_operator_bytes = operator_path.stat().st_size if operator_path.is_file() else 0
    auditor.check("inverse.operatorSize", actual_operator_bytes == expected_operator_bytes, f"Inverse operator is {actual_operator_bytes} bytes ({coefficient_count} x {vertex_count} float32)", f"Inverse operator size {actual_operator_bytes} != {expected_operator_bytes}")

    region_config = skinning.get("regionMap", {})
    region_schema_path = auditor.resolve(region_config.get("schema", ""))
    vertex_region_path = auditor.resolve(region_config.get("vertexMap", ""))
    triangle_region_path = auditor.resolve(region_config.get("triangleMap", ""))
    region_schema = load_json(region_schema_path) if region_schema_path.is_file() else {}
    auditor.check("regions.schema", region_schema_path.is_file(), f"Found region schema {region_schema_path}", f"Missing region schema {region_schema_path}")
    auditor.check("regions.count", int(region_schema.get("regionCount", -1)) == int(region_config.get("regionCount", -2)), f"Connected regions: {region_schema.get('regionCount')}", "Region count differs between Profile and region schema")
    auditor.check("regions.vertexMap", vertex_region_path.is_file() and vertex_region_path.stat().st_size == vertex_count * 2, f"Vertex region map: {vertex_count} R16_UINT entries", "Vertex region map is missing or has the wrong size")
    auditor.check("regions.triangleMap", triangle_region_path.is_file() and triangle_region_path.stat().st_size == len(indices) // 3 * 2, f"Triangle region map: {len(indices) // 3} R16_UINT entries", "Triangle region map is missing or has the wrong size")

    layout = profile.get("layout", {})
    capture = Path(profile.get("capture", {}).get("directory", ""))
    auditor.check("capture.geometry.exists", capture.is_dir(), f"Found geometry capture {capture}", f"Missing geometry capture {capture}")
    capture_evidence: list[dict[str, Any]] = []
    body_draws = drawcalls.get("components", {}).get("body", {}).get("draws", [])
    pass_bindings = drawcalls.get("components", {}).get("body", {}).get("passBindings", {})
    pass_by_draw = {int(value["draw"]): name for name, value in pass_bindings.items()}
    auditor.check("draw.passBindings", set(body_draws) == set(pass_by_draw), f"Body pass bindings cover draws {body_draws}", "Body draw list and pass bindings differ")
    bindings = (
        ("ib", component.get("ibHash"), int(component.get("indices", 0)) * 2),
        ("vb0", component.get("vbHashes", {}).get("positionNormalTangent"), vertex_count * int(layout.get("positionNormalTangentStride", 0))),
        ("vb1", component.get("vbHashes", {}).get("colorUv"), vertex_count * int(layout.get("colorUvStride", 0))),
    )
    if capture.is_dir():
        for draw in body_draws:
            for binding, resource_hash, expected_bytes in bindings:
                matches = find_capture_resource(capture, int(draw), binding, str(resource_hash))
                actual = matches[0].stat().st_size if matches else None
                auditor.check(f"capture.draw{draw}.{binding}", bool(matches) and actual == expected_bytes, f"Draw {draw} {binding}: {actual} bytes", f"Draw {draw} {binding}: expected {expected_bytes}, found {actual}")
                capture_evidence.append({"draw": draw, "pass": pass_by_draw.get(int(draw), "unknown"), "binding": binding, "hash": resource_hash, "expectedBytes": expected_bytes, "actualBytes": actual, "file": str(matches[0]) if matches else None})
        for pass_name, binding in pass_bindings.items():
            draw = int(binding["draw"])
            shader_token = f"-vs={binding['vertexShader']}-ps={binding['pixelShader']}"
            ib_matches = find_capture_resource(capture, draw, "ib", str(binding["streams"]["ib"]))
            auditor.check(f"draw.{pass_name}.shaders", bool(ib_matches) and shader_token in ib_matches[0].name, f"{pass_name}: VS {binding['vertexShader']} / PS {binding['pixelShader']}", f"{pass_name}: captured shader pair differs from Profile")
            dump = ib_matches[0].with_suffix(".txt") if ib_matches else None
            header = parse_index_dump_header(dump) if dump and dump.is_file() else {}
            arguments = binding.get("arguments", {})
            arguments_match = header.get("firstindex") == arguments.get("firstIndex") and header.get("indexcount") == arguments.get("indexCount") and header.get("topology") == layout.get("topology")
            auditor.check(f"draw.{pass_name}.arguments", arguments_match, f"{pass_name}: DrawIndexed({arguments.get('indexCount')}, {arguments.get('firstIndex')}, {arguments.get('baseVertex')})", f"{pass_name}: captured DrawIndexed arguments differ from Profile")

    stable_captures = [Path(value) for value in profile.get("capture", {}).get("stableSignatureCaptures", [])]
    stable_evidence: list[dict[str, Any]] = []
    for session in stable_captures:
        session_ok = session.is_dir()
        found_passes = []
        if session_ok:
            for pass_name, binding in pass_bindings.items():
                matches = find_capture_resource(session, int(binding["draw"]), "ib", str(binding["streams"]["ib"]))
                shader_token = f"-vs={binding['vertexShader']}-ps={binding['pixelShader']}"
                if matches and shader_token in matches[0].name:
                    found_passes.append(pass_name)
        session_ok = session_ok and len(found_passes) == len(pass_bindings)
        auditor.check(f"stability.{session.name}", session_ok, f"Stable Body signature in {session.name}: {', '.join(found_passes)}", f"Body pass signature missing or changed in {session}")
        stable_evidence.append({"capture": str(session), "passes": found_passes, "conforms": session_ok})

    texture_capture = Path(materials.get("capture", ""))
    if not texture_capture.is_absolute():
        texture_capture = capture.parent / str(materials.get("capture", ""))
    auditor.check("capture.material.exists", texture_capture.is_dir(), f"Found material capture {texture_capture}", f"Missing material capture {texture_capture}")
    texture_evidence: list[dict[str, Any]] = []
    body_material = materials.get("components", {}).get("body", {})
    material_draw = int(body_material.get("draw", 0))
    if texture_capture.is_dir():
        for slot, entry in body_material.get("slots", {}).items():
            matches = find_capture_resource(texture_capture, material_draw, f"ps-{slot}", str(entry.get("hash", "")))
            descriptor_path = matches[0].with_suffix(".dsc") if matches else None
            descriptor = parse_descriptor(descriptor_path) if descriptor_path and descriptor_path.is_file() else {}
            size = entry.get("size", [])
            conforms = bool(matches) and descriptor.get("width") == size[0] and descriptor.get("height") == size[1] and descriptor.get("format") == entry.get("format")
            auditor.check(f"material.body.{slot}", conforms, f"{slot} {entry.get('hash')}: {size[0]}x{size[1]} {entry.get('format')}", f"{slot} capture descriptor does not match Profile")
            texture_evidence.append({"slot": slot, "hash": entry.get("hash"), "semantic": entry.get("semantic"), "confidence": entry.get("confidence"), "descriptor": descriptor, "file": str(matches[0]) if matches else None})

    pending = []
    if any(item.get("confidence") not in {"verified"} for item in body_material.get("slots", {}).values()):
        pending.append("Resolve Body t1 packed-mask channel semantics and verify Body t4 by controlled channel replacements.")
    pending.extend([
        "Record exact main/outline/shadow draw arguments and resource bindings in the Profile instead of relying on draw numbers alone.",
        "Capture and compare a second clean scene entry to prove Body IB/VB/shader hashes are stable across sessions.",
        "Classify native Body geometry regions (hands, neck, skin, clothing) for Blender-side retention and weight-transfer masks.",
    ])

    failures = sum(check.status == "fail" for check in auditor.checks)
    warnings = sum(check.status == "warning" for check in auditor.checks)
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "profileId": profile.get("id"),
        "result": "pass" if failures == 0 else "fail",
        "summary": {"checks": len(auditor.checks), "passed": len(auditor.checks) - failures - warnings, "warnings": warnings, "failed": failures},
        "contract": {
            "component": "body",
            "geometry": {"vertexCount": vertex_count, "indexCount": len(indices), "maxIndex": max(indices) if indices else None, "topology": layout.get("topology"), "indexFormat": layout.get("indexFormat"), "streams": {"vb0": {"hash": component.get("vbHashes", {}).get("positionNormalTangent"), "stride": layout.get("positionNormalTangentStride"), "semantics": ["POSITION.float3", "NORMAL.float3", "TANGENT.float4"]}, "vb1": {"hash": component.get("vbHashes", {}).get("colorUv"), "stride": layout.get("colorUvStride"), "semantics": ["COLOR.unorm8x4", "TEXCOORD0.half2", "TEXCOORD1.half2"]}, "ib": {"hash": component.get("ibHash"), "format": layout.get("indexFormat")}}},
            "skinning": {"mode": skinning.get("drawInput"), "bindPoseCount": bind_count, "hierarchyNodeCount": len(skeleton.get("nodes", [])), "sourceActiveBoneCount": len(active_bones), "sourceInactiveBones": inactive_names, "numericallyUnobservableBones": configured_unobservable, "influencesPerVertex": 4, "inverseOperator": {"path": str(operator_path), "sha256": sha256(operator_path) if operator_path.is_file() else None, "layout": f"{coefficient_count} coefficient-major rows x {vertex_count} source vertices x float32"}, "regionMap": {"schema": str(region_schema_path), "regionCount": region_schema.get("regionCount"), "reviewRequired": region_schema.get("reviewRequired")}},
            "passes": {"bodyDraws": body_draws, "bindings": pass_bindings, "evidence": capture_evidence, "stableSignatureSessions": stable_evidence},
            "materials": {"body": texture_evidence},
        },
        "checks": [check.as_dict() for check in auditor.checks],
        "pendingGameResearch": pending,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    contract = report["contract"]
    lines = [
        "# HSKI Body 游戏数据契约审计",
        "",
        f"Profile：`{report['profileId']}`  ",
        f"结果：**{report['result'].upper()}**（{summary['passed']} 通过 / {summary['warnings']} 警告 / {summary['failed']} 失败）",
        "",
        "## 已冻结的输入契约",
        "",
        f"- Geometry：{contract['geometry']['vertexCount']} vertices / {contract['geometry']['indexCount']} indices / `{contract['geometry']['indexFormat']}`；",
        f"- VB0：`{contract['geometry']['streams']['vb0']['hash']}`，stride {contract['geometry']['streams']['vb0']['stride']}；",
        f"- VB1：`{contract['geometry']['streams']['vb1']['hash']}`，stride {contract['geometry']['streams']['vb1']['stride']}；",
        f"- IB：`{contract['geometry']['streams']['ib']['hash']}`；",
        f"- Skeleton：{contract['skinning']['bindPoseCount']} bind poses / {contract['skinning']['hierarchyNodeCount']} hierarchy nodes；",
        f"- Inverse operator：`{contract['skinning']['inverseOperator']['sha256']}`。",
        "",
        "## 自动检查",
        "",
        "| 状态 | 检查 | 结果 |",
        "| --- | --- | --- |",
    ]
    for item in report["checks"]:
        lines.append(f"| {item['status']} | `{item['id']}` | {item['message']} |")
    lines.extend(["", "## 尚需游戏内研究", ""])
    lines.extend(f"- {item}" for item in report["pendingGameResearch"])
    lines.extend(["", "此文件由 `tools/audit_profile.py` 生成，不应手工维护。", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = audit(args.profile_dir)
    output = args.output or args.profile_dir / "audit-report.json"
    markdown = args.markdown or args.profile_dir / "data-contract.md"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Wrote {output}")
    print(f"Wrote {markdown}")
    if args.strict and report["result"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
