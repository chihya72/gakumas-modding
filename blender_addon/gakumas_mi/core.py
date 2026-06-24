"""Blender-independent Profile, buffer, validation and package helpers."""

from __future__ import annotations

import json
import re
import shutil
import struct
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def inspect_dds(path):
    """Return the dimensions and DXGI format of a standard DX10 DDS."""
    data = Path(path).read_bytes()[:148]
    if len(data) < 128 or data[:4] != b"DDS ":
        raise ValueError(f"Not a DDS file: {path}")
    height, width = struct.unpack_from("<2I", data, 12)
    fourcc = data[84:88]
    if fourcc != b"DX10" or len(data) < 132:
        raise ValueError(f"DDS must use a DX10 header: {path}")
    dxgi_format = struct.unpack_from("<I", data, 128)[0]
    formats = {98: "BC7_UNORM", 99: "BC7_UNORM_SRGB"}
    return {"width": width, "height": height, "format": formats.get(dxgi_format, f"DXGI_{dxgi_format}")}


def load_profile_set(profile_dir):
    root = Path(profile_dir)
    required = ("profile.json", "drawcall_map.json", "texture_map.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"Profile is missing: {', '.join(missing)}")
    return {
        "root": root,
        "profile": load_json(root / "profile.json"),
        "drawcalls": load_json(root / "drawcall_map.json"),
        "textures": load_json(root / "texture_map.json"),
    }


def _capture_timestamp_from_name(name):
    match = re.search(r"FrameAnalysis-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})", name)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    return f"{year}-{month}-{day}T{hour}:{minute}:{second}+08:00"


def _resource_key_pattern(binding, resource_hash):
    return re.compile(rf"(?:^|[-_]){re.escape(binding)}={re.escape(resource_hash)}(?:[-_.]|$)", re.I)


def _resource_files(capture_dir, binding, resource_hash, suffix=None):
    capture = Path(capture_dir)
    if not resource_hash:
        return []
    pattern = _resource_key_pattern(binding, resource_hash)
    files = []
    for path in capture.rglob("*"):
        if not path.is_file():
            continue
        if suffix and path.suffix.lower() != suffix.lower():
            continue
        if pattern.search(path.name):
            files.append(path)
    return sorted(files)


def _resource_files_by_draw(capture_dir, draw, binding, suffix=None):
    capture = Path(capture_dir)
    files = []
    for path in capture.glob(f"{int(draw):06d}-{binding}*"):
        if not path.is_file():
            continue
        if suffix and path.suffix.lower() != suffix.lower():
            continue
        files.append(path)
    return sorted(files)


def _capture_resource_entry(capture_dir, binding, resource_hash, suffix=None, fallback_draws=None):
    matches = _resource_files(capture_dir, binding, resource_hash, suffix)
    fallback_matches = []
    if not matches:
        for draw in fallback_draws or []:
            fallback_matches.extend(_resource_files_by_draw(capture_dir, draw, binding, suffix))
        fallback_matches = sorted(set(fallback_matches))
    all_matches = matches or fallback_matches
    return {
        "binding": binding,
        "hash": resource_hash,
        "files": [path.name for path in all_matches[:16]],
        "matchCount": len(all_matches),
        "matchMode": "hash" if matches else ("drawNumberFallback" if fallback_matches else "none"),
        "missing": len(all_matches) == 0,
    }


def inspect_frame_dump_for_profile(profile_dir, capture_dir):
    """Inspect whether a 3DMigoto FrameAnalysis directory contains a Profile's resources."""
    profile_set = load_profile_set(profile_dir)
    root = profile_set["root"]
    profile = profile_set["profile"]
    texture_map = profile_set["textures"]
    drawcalls = profile_set["drawcalls"]
    capture = Path(capture_dir)
    if not capture.is_dir():
        raise FileNotFoundError(f"FrameAnalysis 目录不存在：{capture}")

    files = [path for path in capture.rglob("*") if path.is_file()]
    report = {
        "profile": profile.get("id"),
        "captureDir": str(capture),
        "timestamp": _capture_timestamp_from_name(capture.name),
        "fileCount": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "components": {},
        "textures": {},
        "missing": [],
    }

    for component in profile.get("components", []):
        component_id = component.get("id", "unknown")
        draw_component = drawcalls.get("components", {}).get(component_id, {})
        fallback_draws_by_binding = {}
        for pass_data in draw_component.get("passBindings", {}).values():
            draw = pass_data.get("draw")
            streams = pass_data.get("streams", {})
            if draw is None:
                continue
            for binding in ("ib", "vb0", "vb1", "vb2", "vb3"):
                if binding in streams:
                    fallback_draws_by_binding.setdefault(binding, []).append(draw)
        entries = {}
        bindings = [
            ("ib", component.get("ibHash"), ".buf"),
            ("vb0", component.get("vbHashes", {}).get("positionNormalTangent"), ".buf"),
            ("vb1", component.get("vbHashes", {}).get("colorUv"), ".buf"),
        ]
        for binding, resource_hash, suffix in bindings:
            if not resource_hash:
                continue
            entry = _capture_resource_entry(
                capture, binding, resource_hash, suffix,
                fallback_draws=fallback_draws_by_binding.get(binding),
            )
            entries[binding] = entry
            if entry["missing"]:
                report["missing"].append(f"{component_id}.{binding}={resource_hash}")
        report["components"][component_id] = entries

    for texture_key, texture in texture_map.get("textures", {}).items():
        slot = texture.get("slot")
        resource_hash = texture.get("hash")
        if not slot or not resource_hash:
            continue
        entry = _capture_resource_entry(capture, slot, resource_hash)
        entry["pixelShader"] = texture.get("pixelShader")
        report["textures"][texture_key] = entry
        if entry["missing"]:
            report["missing"].append(f"{texture_key}.{slot}={resource_hash}")

    report["ok"] = not report["missing"]
    report["reportFile"] = str(root / "profile-capture-update-report.json")
    return report


def update_profile_capture_from_frame_dump(profile_dir, capture_dir):
    """Update profile.json capture metadata after validating a FrameAnalysis directory."""
    profile_set = load_profile_set(profile_dir)
    root = profile_set["root"]
    profile = profile_set["profile"]
    capture = Path(capture_dir)
    report = inspect_frame_dump_for_profile(root, capture)

    capture_block = profile.setdefault("capture", {})
    capture_block["directory"] = str(capture)
    if report.get("timestamp"):
        capture_block["timestamp"] = report["timestamp"]
    capture_block["files"] = report["fileCount"]
    capture_block["bytes"] = report["bytes"]
    stable = capture_block.setdefault("stableSignatureCaptures", [])
    capture_text = str(capture)
    if capture_text not in stable:
        stable.append(capture_text)

    _write_json(root / "profile.json", profile)
    _write_json(root / "profile-capture-update-report.json", report)
    return report


_FRAME_RESOURCE_RE = re.compile(
    r"^(?P<draw>\d{6})-"
    r"(?P<binding>ib|vb\d+|(?:vs|ps)-t\d+)"
    r"(?:=(?P<hash>[0-9a-fA-F]+))?"
    r"(?:-vs=(?P<vs>[0-9a-fA-F]+))?"
    r"(?:-ps=(?P<ps>[0-9a-fA-F]+))?"
    r"\.(?P<ext>buf|dsc|dds|png|jpg|jpeg)$",
    re.I,
)


def _parse_descriptor(path):
    data = {}
    if not path or not Path(path).is_file():
        return data
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        for key, raw_value in re.findall(r"([A-Za-z_]+)=((?:\"[^\"]*\")|\S+)", line):
            value = raw_value.strip('"')
            if value.lstrip("-").isdigit():
                value = int(value)
            data[key] = value
    return data


def _scan_frame_resources(capture_dir):
    resources = {}
    capture = Path(capture_dir)
    for path in capture.rglob("*"):
        if not path.is_file():
            continue
        match = _FRAME_RESOURCE_RE.match(path.name)
        if not match:
            continue
        info = match.groupdict()
        draw = int(info["draw"])
        binding = info["binding"].lower()
        entry = resources.setdefault((draw, binding), {
            "draw": draw,
            "binding": binding,
            "hash": None,
            "vs": None,
            "ps": None,
            "buf": None,
            "dsc": None,
            "texture": None,
            "byteWidth": None,
        })
        if info.get("hash"):
            entry["hash"] = info["hash"].lower()
        if info.get("vs"):
            entry["vs"] = info["vs"].lower()
        if info.get("ps"):
            entry["ps"] = info["ps"].lower()
        ext = info["ext"].lower()
        if ext == "buf":
            entry["buf"] = path
        elif ext == "dsc":
            entry["dsc"] = path
        else:
            entry["texture"] = path
    for entry in resources.values():
        desc = _parse_descriptor(entry.get("dsc"))
        byte_width = desc.get("byte_width")
        if byte_width is None and entry.get("buf") and entry["buf"].is_file():
            byte_width = entry["buf"].stat().st_size
        entry["descriptor"] = desc
        entry["byteWidth"] = byte_width
    return resources


def _parse_frame_log(capture_dir):
    log = Path(capture_dir) / "log.txt"
    if not log.is_file():
        return {}
    current = {"vs": None, "ps": None, "ibHash": None}
    draws = {}
    line_re = re.compile(r"^(?P<draw>\d{6})\s+(?P<body>.*)$")
    draw_re = re.compile(
        r"DrawIndexed(?:Instanced)?\(IndexCountPerInstance:(?P<indices>\d+),\s*"
        r"InstanceCount:(?P<instances>\d+),\s*StartIndexLocation:(?P<start>-?\d+),\s*"
        r"BaseVertexLocation:(?P<base>-?\d+),\s*StartInstanceLocation:(?P<start_instance>-?\d+)\)"
    )
    for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = line_re.match(line)
        if not match:
            continue
        draw = int(match.group("draw"))
        body = match.group("body")
        if "VSSetShader" in body:
            shader = re.search(r"hash=([0-9a-fA-F]+)", body)
            if shader:
                current["vs"] = shader.group(1).lower()
        elif "PSSetShader" in body:
            shader = re.search(r"hash=([0-9a-fA-F]+)", body)
            if shader:
                current["ps"] = shader.group(1).lower()
        elif "IASetIndexBuffer" in body:
            ib_hash = re.search(r"hash=([0-9a-fA-F]+)", body)
            if ib_hash:
                current["ibHash"] = ib_hash.group(1).lower()
        elif "DrawIndexed" in body:
            draw_match = draw_re.search(body)
            if draw_match:
                draws[draw] = {
                    "draw": draw,
                    "vs": current["vs"],
                    "ps": current["ps"],
                    "ibHash": current["ibHash"],
                    "indexCount": int(draw_match.group("indices")),
                    "instanceCount": int(draw_match.group("instances")),
                    "startIndex": int(draw_match.group("start")),
                    "baseVertex": int(draw_match.group("base")),
                    "startInstance": int(draw_match.group("start_instance")),
                }
    return draws


def _infer_vertex_stream_layout(vb0_bytes, vb1_bytes):
    primary = (40, 12)
    if vb0_bytes and vb1_bytes and vb0_bytes % primary[0] == 0:
        vertices = vb0_bytes // primary[0]
        if vertices > 0 and vb1_bytes == vertices * primary[1]:
            return {
                "positionNormalTangentStride": primary[0],
                "colorUvStride": primary[1],
                "vertices": vertices,
                "confidence": "known-gakumas-body-layout",
            }
    for vb0_stride in (40, 48, 44, 36, 32):
        if not vb0_bytes or vb0_bytes % vb0_stride:
            continue
        vertices = vb0_bytes // vb0_stride
        for vb1_stride in (12, 16, 20, 24, 28, 32):
            if vb1_bytes == vertices * vb1_stride:
                return {
                    "positionNormalTangentStride": vb0_stride,
                    "colorUvStride": vb1_stride,
                    "vertices": vertices,
                    "confidence": "inferred-by-matching-byte-width",
                }
    if vb0_bytes and vb0_bytes % 40 == 0:
        return {
            "positionNormalTangentStride": 40,
            "colorUvStride": 12,
            "vertices": vb0_bytes // 40,
            "confidence": "partial-vb0-only-assumption",
        }
    return None


def _component_resource_files(resources, draw):
    files = {}
    for binding in ("ib", "vb0", "vb1"):
        entry = resources.get((draw, binding))
        if entry and entry.get("buf"):
            files[binding] = entry["buf"].name
    return files


def _build_frame_candidates(resources, draw_records):
    candidates = []
    for draw, record in draw_records.items():
        ib = resources.get((draw, "ib"))
        vb0 = resources.get((draw, "vb0"))
        vb1 = resources.get((draw, "vb1"))
        if not (ib and vb0):
            continue
        layout = _infer_vertex_stream_layout(vb0.get("byteWidth"), (vb1 or {}).get("byteWidth"))
        if not layout:
            continue
        ib_indices = int((ib.get("byteWidth") or 0) // 2)
        draw_indices = int(record.get("indexCount") or ib_indices)
        score = 0.0
        reasons = []
        if ib and vb0 and vb1:
            score += 50
            reasons.append("ib/vb0/vb1 同 draw 齐全")
        if layout["positionNormalTangentStride"] == 40 and layout["colorUvStride"] == 12:
            score += 30
            reasons.append("符合 Gakumas Body 常见 40+12 双 VB 布局")
        score += min(draw_indices / 1000.0, 120)
        score += min(layout["vertices"] / 1000.0, 80)
        if record.get("instanceCount") == 1:
            score += 5
        candidates.append({
            "draw": draw,
            "score": round(score, 3),
            "reasons": reasons,
            "vs": record.get("vs") or (vb0 or {}).get("vs"),
            "ps": record.get("ps") or (vb0 or {}).get("ps"),
            "ibHash": (ib or {}).get("hash") or record.get("ibHash"),
            "vbHashes": {
                "positionNormalTangent": (vb0 or {}).get("hash"),
                "colorUv": (vb1 or {}).get("hash"),
            },
            "resourceFiles": _component_resource_files(resources, draw),
            "vertices": int(layout["vertices"]),
            "indices": draw_indices,
            "ibByteWidth": ib.get("byteWidth"),
            "vb0ByteWidth": vb0.get("byteWidth"),
            "vb1ByteWidth": (vb1 or {}).get("byteWidth"),
            "layout": layout,
            "drawCall": record,
        })
    repeat_counts = {}
    for candidate in candidates:
        key = (candidate.get("ibHash"), candidate["indices"], candidate["vertices"])
        repeat_counts[key] = repeat_counts.get(key, 0) + 1
    for candidate in candidates:
        key = (candidate.get("ibHash"), candidate["indices"], candidate["vertices"])
        repeats = repeat_counts.get(key, 1)
        candidate["score"] = round(candidate["score"] + repeats * 8, 3)
        if repeats > 1:
            candidate["reasons"].append(f"同一资源组在 {repeats} 个 pass 中重复出现")
    return sorted(candidates, key=lambda item: (item["score"], item["indices"], item["draw"]), reverse=True)


def _select_main_candidate(candidates, requested_draw=None):
    if not candidates:
        raise ValueError("抓帧中没有找到可作为 Body 的 IB/VB0/VB1 候选")
    if requested_draw is not None:
        for candidate in candidates:
            if candidate["draw"] == int(requested_draw):
                return candidate
        raise ValueError(f"指定 Draw {int(requested_draw):06d} 没有可用 Body 候选")
    best = candidates[0]
    group = [
        item for item in candidates
        if item.get("ibHash") == best.get("ibHash")
        and item["indices"] == best["indices"]
        and item["vertices"] == best["vertices"]
    ]
    if len(group) >= 3:
        return sorted(group, key=lambda item: item["draw"])[len(group) // 2]
    return best


def _role_for_group(draw, main_draw, ordered_draws):
    if draw == main_draw:
        return "main"
    if draw < main_draw:
        return "shadow_or_depth"
    if ordered_draws and draw == ordered_draws[-1]:
        return "outline_or_aux"
    return "aux"


def _texture_semantic(slot):
    return {
        "ps-t0": "baseColor",
        "ps-t1": "packedMask",
        "ps-t4": "shadeColor",
    }.get(slot, slot.replace("ps-", ""))


def extract_profile_from_frame_dump(capture_dir, output_dir, component_id="body", main_draw=None):
    """Generate a runtime-only Profile from a 3DMigoto FrameAnalysis directory.

    Frame dumps expose runtime GPU resources, draw calls and texture bindings. They do not
    contain full Unity skeleton names, bind poses or authoring weights, so this profile is
    suitable for object/material discovery and GPU replacement binding, not as an AssetStudio
    skeleton substitute.
    """
    capture = Path(capture_dir)
    if not capture.is_dir():
        raise FileNotFoundError(f"FrameAnalysis 目录不存在：{capture}")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    resources = _scan_frame_resources(capture)
    draw_records = _parse_frame_log(capture)
    if not draw_records:
        # Resource file names still carry draw numbers; synthesize minimal draw records.
        for (draw, binding), entry in resources.items():
            if binding == "ib":
                draw_records.setdefault(draw, {
                    "draw": draw,
                    "vs": entry.get("vs"),
                    "ps": entry.get("ps"),
                    "ibHash": entry.get("hash"),
                    "indexCount": int((entry.get("byteWidth") or 0) // 2),
                    "instanceCount": 1,
                    "startIndex": 0,
                    "baseVertex": 0,
                    "startInstance": 0,
                })
    candidates = _build_frame_candidates(resources, draw_records)
    selected = _select_main_candidate(candidates, main_draw if main_draw else None)
    same_group = [
        item for item in candidates
        if item.get("ibHash") == selected.get("ibHash")
        and item["indices"] == selected["indices"]
        and item["vertices"] == selected["vertices"]
    ]
    ordered_draws = sorted(item["draw"] for item in same_group)

    layout = selected["layout"]
    vb0_hash = selected["vbHashes"].get("positionNormalTangent")
    vb1_hash = selected["vbHashes"].get("colorUv")
    component = {
        "id": component_id,
        "kind": "body",
        "source": "frame-analysis-runtime",
        "confidence": "auto-selected" if not main_draw else "manual-draw-selected",
        "ibHash": selected.get("ibHash") or f"draw:{selected['draw']:06d}:ib",
        "vbHashes": {
            "positionNormalTangent": vb0_hash or f"draw:{selected['draw']:06d}:vb0",
            "colorUv": vb1_hash or f"draw:{selected['draw']:06d}:vb1",
        },
        "resourceFiles": selected["resourceFiles"],
        "vertices": selected["vertices"],
        "indices": selected["indices"],
        "draws": ordered_draws,
        "mainDraw": selected["draw"],
        "hashNotes": {
            "positionNormalTangent": "filename" if vb0_hash else "missing-in-frame-filename; resourceFiles fallback required",
            "colorUv": "filename" if vb1_hash else "missing-in-frame-filename; resourceFiles fallback required",
        },
    }
    profile_id = f"frame-{capture.name}-{component_id}-{component['ibHash']}".replace(":", "-")
    profile = {
        "schemaVersion": 1,
        "id": profile_id,
        "status": "runtime-only-frame-extracted",
        "target": {
            "actorId": "unknown",
            "costumeId": "unknown",
            "bodyResource": "unknown",
            "note": "从 FrameAnalysis 推断；骨骼名/BindPose/权重由 Body JSON资源库自动匹配补全。",
        },
        "capture": {
            "directory": str(capture),
            "timestamp": _capture_timestamp_from_name(capture.name),
            "files": len([path for path in capture.rglob("*") if path.is_file()]),
            "bytes": sum(path.stat().st_size for path in capture.rglob("*") if path.is_file()),
            "stableSignatureCaptures": [str(capture)],
        },
        "layout": {
            "topology": "trianglelist",
            "indexFormat": "R16_UINT",
            "positionNormalTangentStride": layout["positionNormalTangentStride"],
            "colorUvStride": layout["colorUvStride"],
            "inference": layout["confidence"],
        },
        "skinning": {
            "drawInput": "CPU-skinned or runtime-skinned final vertex buffer",
            "status": "runtime-only; frame dump does not include complete skeleton names, weights or bind poses",
            "inverseSkin": {
                "meshJson": None,
                "skeletonJson": None,
                "note": "稍后可由插件导入 AssetStudio JSON 作为权重源补全。",
            },
        },
        "components": [component],
    }

    passes = {}
    for item in sorted(same_group, key=lambda value: value["draw"]):
        role = _role_for_group(item["draw"], selected["draw"], ordered_draws)
        passes[f"draw_{item['draw']:06d}"] = {
            "role": role,
            "draw": item["draw"],
            "vertexShader": item.get("vs"),
            "pixelShader": item.get("ps"),
            "indexCount": item["indices"],
            "vertexCount": item["vertices"],
            "streams": {
                "ib": item.get("ibHash") or f"draw:{item['draw']:06d}:ib",
                "vb0": item["vbHashes"].get("positionNormalTangent") or f"draw:{item['draw']:06d}:vb0",
                "vb1": item["vbHashes"].get("colorUv") or f"draw:{item['draw']:06d}:vb1",
            },
            "streamFiles": item["resourceFiles"],
        }
    drawcall_map = {
        "schemaVersion": 1,
        "capture": str(capture),
        "generatedFrom": capture.name,
        "components": {
            component_id: {
                "mainDraw": selected["draw"],
                "passBindings": passes,
            }
        },
    }

    textures = {}
    material_slots = []
    for (draw, binding), entry in sorted(resources.items()):
        if draw != selected["draw"] or not binding.startswith("ps-t"):
            continue
        semantic = _texture_semantic(binding)
        texture_key = f"{component_id}.{semantic}"
        texture_file = entry.get("texture")
        textures[texture_key] = {
            "slot": binding,
            "semantic": semantic,
            "hash": entry.get("hash") or f"draw:{draw:06d}:{binding}",
            "pixelShader": entry.get("ps") or selected.get("ps"),
            "file": texture_file.name if texture_file else None,
            "descriptor": entry.get("descriptor", {}),
        }
        material_slots.append({
            "key": texture_key,
            "slot": binding,
            "semantic": semantic,
            "hash": textures[texture_key]["hash"],
        })
    texture_map = {
        "schemaVersion": 1,
        "capture": str(capture),
        "textures": textures,
    }
    material_map = {
        "schemaVersion": 1,
        "materials": {
            component_id: {
                "source": "frame-analysis-runtime",
                "mainDraw": selected["draw"],
                "pixelShader": selected.get("ps"),
                "textureSlots": material_slots,
                "note": "t0/t1/t4 语义按 Gakumas Body 模板命名；未识别槽位保留原 slot。",
            }
        },
    }
    report = {
        "ok": True,
        "captureDir": str(capture),
        "outputDir": str(output),
        "selected": selected,
        "candidateCount": len(candidates),
        "candidates": candidates[:32],
        "warnings": [
            "这是 runtime-only profile：帧数据不能单独还原完整 Unity 骨架名、权重和 BindPose。",
            "若 VB 文件名没有 hash，已写入 resourceFiles 作为读取兜底。",
        ],
    }

    _write_json(output / "profile.json", profile)
    _write_json(output / "drawcall_map.json", drawcall_map)
    _write_json(output / "texture_map.json", texture_map)
    _write_json(output / "material_map.json", material_map)
    _write_json(output / "extraction-report.json", report)
    return report


def component_by_id(profile, component_id):
    for component in profile["components"]:
        if component["id"] == component_id:
            return component
    raise ValueError(f"Unknown Profile component: {component_id}")


def _valid_skeleton_sidecar(path):
    if not Path(path).is_file():
        return False
    try:
        skeleton = load_json(Path(path))
    except Exception:
        return False
    if int(skeleton.get("weightedBoneCount") or 0) <= 0:
        return False
    if int(skeleton.get("nodeCount") or 0) <= 0:
        return False
    return any(node.get("weightedIndex") is not None for node in skeleton.get("nodes", []))


def _mesh_summary(path):
    import hashlib

    mesh = load_json(Path(path))
    bindpose = mesh.get("m_BindPose") or []
    # Bind-pose signature lets us tell whether two same-topology bodies are the
    # same rig (shared base body, only costume/texture differs) or genuinely different.
    bindpose_sig = hashlib.md5(json.dumps(bindpose, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {
        "vertexCount": int(mesh.get("m_VertexCount") or 0),
        "indexCount": len(mesh.get("m_Indices") or []),
        "bindPoseCount": len(bindpose),
        "bindPoseSig": bindpose_sig,
        "name": mesh.get("m_Name") or mesh.get("Name") or "Geo_Body",
    }


def _synthesize_skeleton_from_mesh(mesh_json_path):
    """Build a skeleton sidecar from a Mesh JSON alone (no Unity SkinnedMeshRenderer).

    Bone identity comes from m_BoneNameHashes (names become "bone_<hash>") and bind
    transforms from m_BindPose (same {M00..} format the real sidecar uses). Hierarchy
    is flat — the inverse-skin pipeline deforms by recovered matrices, not the armature
    pose, so bones placed at their bind positions under one root are sufficient.
    """
    mesh = load_json(Path(mesh_json_path))
    bind = mesh.get("m_BindPose") or []
    hashes = mesh.get("m_BoneNameHashes") or []
    bone_count = len(bind)
    nodes = [{
        "name": "Root", "parent": -1, "weightedIndex": None,
        "localPosition": [0.0, 0.0, 0.0],
        "localRotation": [0.0, 0.0, 0.0, 1.0],
        "localScale": [1.0, 1.0, 1.0],
    }]
    for i in range(bone_count):
        bone_hash = int(hashes[i]) if i < len(hashes) else i
        nodes.append({
            "name": f"bone_{bone_hash}",
            "parent": 0,
            "weightedIndex": i,
            "boneNameHash": bone_hash,
            "bindPose": bind[i],
        })
    return {
        "schemaVersion": 1,
        "synthetic": "derived from mesh m_BoneNameHashes + m_BindPose (no Unity skeleton)",
        "weightedBoneCount": bone_count,
        "nodeCount": bone_count + 1,
        "nodes": nodes,
    }


def resolve_profile_reference(profile_dir):
    """Return a completed profile's own Reference Mesh/Skeleton, or None.

    After completion the profile is self-contained (Reference/ holds the real or
    synthesized skeleton). Import should prefer this over re-resolving the library.
    """
    profile_dir = Path(profile_dir)
    profile_path = profile_dir / "profile.json"
    if not profile_path.is_file():
        return None
    profile = load_json(profile_path)
    config = (profile.get("skinning", {}) or {}).get("inverseSkin") or {}
    mesh_rel, skel_rel = config.get("meshJson"), config.get("skeletonJson")
    if not mesh_rel or not skel_rel:
        return None
    mesh_path, skel_path = profile_dir / mesh_rel, profile_dir / skel_rel
    if not (mesh_path.is_file() and skel_path.is_file()):
        return None
    return {
        "meshJson": str(mesh_path.resolve()),
        "skeletonJson": str(skel_path.resolve()),
        "body": profile.get("target", {}).get("bodyResource", ""),
        "match": "profile-reference",
    }


def scan_body_json_library(json_dir):
    """Scan an AssetStudio body JSON library. Includes mesh-only entries.

    Entries without a valid skeleton sidecar are still returned (skeletonJson=None,
    hasSkeleton=False); completion synthesizes a skeleton from the mesh for them.
    """
    root = Path(json_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Body JSON 资源库目录不存在：{root}")

    entries = []
    for body_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        mesh_json = body_dir / "Geo_Body.json"
        if not mesh_json.is_file():
            continue
        try:
            summary = _mesh_summary(mesh_json)
        except Exception:
            continue
        skeleton_json = body_dir / "Geo_Body.skeleton.json"
        has_skeleton = _valid_skeleton_sidecar(skeleton_json)
        entries.append({
            "body": body_dir.name,
            "meshJson": str(mesh_json.resolve()),
            "skeletonJson": str(skeleton_json.resolve()) if has_skeleton else None,
            "hasSkeleton": has_skeleton,
            **summary,
        })
    return entries


def resolve_body_json_resource(profile_dir, json_dir, component_id="body"):
    """Resolve profile body Mesh/Skeleton JSON from a shared body JSON library."""
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    component = component_by_id(profile, component_id)
    body_resource = profile.get("target", {}).get("bodyResource")
    entries = scan_body_json_library(json_dir)
    if not entries:
        raise ValueError(f"Body JSON 资源库没有严格可用样本：{json_dir}")

    if body_resource and body_resource != "unknown":
        exact = [entry for entry in entries if entry["body"] == body_resource]
        if exact:
            result = dict(exact[0])
            result["match"] = "bodyResource"
            return result
        raise ValueError(
            f"当前模型 {body_resource} 不在 Body JSON资源库的 {len(entries)} 个严格可用样本中。"
            "请换用已支持的 body，或先把该 body 导出为严格可用的 Geo_Body.json + Geo_Body.skeleton.json。"
        )

    vertex_count = int(component.get("vertices") or 0)
    index_count = int(component.get("indices") or 0)
    matches = [
        entry for entry in entries
        if entry["vertexCount"] == vertex_count and entry["indexCount"] == index_count
    ]
    if len(matches) == 1:
        result = dict(matches[0])
        result["match"] = "vertex+index"
        return result
    if len(matches) > 1:
        # 同拓扑且 bind pose 一致 = 同一套身体（仅服装/贴图不同），逆算子完全相同，任取其一。
        if len({entry.get("bindPoseSig") for entry in matches}) == 1:
            result = dict(matches[0])
            result["match"] = "vertex+index(equivalent)"
            return result
        names = ", ".join(entry["body"] for entry in matches[:8])
        suffix = " ..." if len(matches) > 8 else ""
        raise ValueError(
            f"按顶点/索引匹配到多个不等价候选：{names}{suffix}。"
            "请在配置档 target.bodyResource 指定具体 Body 后重试。"
        )
    raise ValueError(
        f"配置档未记录 bodyResource，资源库中也没有 "
        f"{vertex_count} 顶点 / {index_count} 索引的唯一候选"
    )


def build_inverse_operator(mesh_json_path, output_buf, ridge=1e-8):
    """Build the fixed inverse-skin operator P from a body Mesh JSON.

    P maps one posed source-position VB (40-byte stride) to boneCount*4 effective
    skinning-matrix rows. It depends only on bind positions + four-influence
    weights, so it is built once per costume and reused every animation frame.
    Writes a coefficient-major R32_FLOAT buffer to output_buf; returns metadata.
    """
    import numpy as np  # Blender ships numpy; import lazily so other paths don't require it.

    mesh = load_json(Path(mesh_json_path))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    positions = np.asarray(mesh["m_Vertices"], dtype=np.float64).reshape(-1, 3)
    if positions.shape[0] != vertex_count:
        raise ValueError("Mesh m_Vertices 与 m_VertexCount 不一致")

    # design[v, b*4:b*4+4] = sum of weight * [x y z 1] for each influence on vertex v.
    source_h = np.column_stack((positions, np.ones(vertex_count)))
    design = np.zeros((vertex_count, bone_count * 4), dtype=np.float64)
    active = np.zeros(bone_count, dtype=bool)
    bone_weight_total = np.zeros(bone_count, dtype=np.float64)
    for vertex, influence in enumerate(mesh["m_Skin"]):
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            bone, weight = int(bone), float(weight)
            if weight <= 0.0:
                continue
            active[bone] = True
            bone_weight_total[bone] += weight
            design[vertex, bone * 4 : bone * 4 + 4] += weight * source_h[vertex]

    active_bones = np.flatnonzero(active)
    if active_bones.size == 0:
        raise ValueError("Mesh 没有任何加权骨骼，无法构建逆算子")
    # Solve only the active columns; ill-conditioning is regularized by a ridge term.
    active_columns = np.concatenate([np.arange(b * 4, b * 4 + 4) for b in active_bones])
    a = design[:, active_columns]
    gram = a.T @ a
    scale = float(np.trace(gram) / gram.shape[0])
    regularizer = ridge * max(scale, 1.0)
    operator_active = np.linalg.solve(gram + np.eye(gram.shape[0]) * regularizer, a.T)
    operator = np.zeros((bone_count * 4, vertex_count), dtype=np.float32)
    operator[active_columns] = operator_active.astype(np.float32)

    output_buf = Path(output_buf)
    output_buf.parent.mkdir(parents=True, exist_ok=True)
    operator.tofile(str(output_buf))
    return {
        "vertexCount": vertex_count,
        "boneCount": bone_count,
        "coefficientCount": bone_count * 4,
        "activeBoneCount": int(active_bones.size),
        "regularizer": regularizer,
        "boneWeightTotal": bone_weight_total.tolist(),
        "operatorBytes": int(operator.nbytes),
    }


def _parse_body_target(body_name):
    """mdl_chr_hski-cstm-0000_body -> (actorId, costumeId)."""
    core_name = body_name
    if core_name.startswith("mdl_chr_"):
        core_name = core_name[len("mdl_chr_"):]
    if core_name.endswith("_body"):
        core_name = core_name[: -len("_body")]
    actor, _, costume = core_name.partition("-")
    return actor, costume


def complete_inverse_skin_profile(profile_dir, library_dir, component_id="body",
                                  ridge=1e-8, unobservable_weight_threshold=0.1):
    """Upgrade a runtime-only frame profile into a complete inverse-skin profile.

    Matches the body Mesh/Skeleton JSON from the library (by recorded bodyResource
    or by vertex+index count), copies them into the profile, builds the inverse
    operator and writes skinning.inverseSkin. Afterwards the profile carries
    (1) injection info, (2) structural data and (3) the operator.
    """
    profile_dir = Path(profile_dir)
    profile_path = profile_dir / "profile.json"
    profile = load_json(profile_path)
    component_by_id(profile, component_id)  # validate component exists

    resolved = resolve_body_json_resource(profile_dir, library_dir, component_id)

    # (2) Structural data: copy matched Mesh + Skeleton into the profile.
    reference_dir = profile_dir / "Reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    mesh_dst = reference_dir / "Geo_Body.json"
    skeleton_dst = reference_dir / "Geo_Body.skeleton.json"
    shutil.copy2(Path(resolved["meshJson"]), mesh_dst)
    skeleton_src = resolved.get("skeletonJson")
    if skeleton_src and Path(skeleton_src).is_file():
        shutil.copy2(Path(skeleton_src), skeleton_dst)
        bone_naming = "skeleton"
    else:
        # mesh-only：从 mesh 的 m_BoneNameHashes + m_BindPose 合成骨架。
        synthetic = _synthesize_skeleton_from_mesh(mesh_dst)
        skeleton_dst.write_text(
            json.dumps(synthetic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        bone_naming = "boneNameHash"

    # (3) Inverse operator from the bind mesh.
    operator_rel = "Buffers/InverseOperator.R32_FLOAT.buf"
    operator_meta = build_inverse_operator(mesh_dst, profile_dir / operator_rel, ridge=ridge)

    # Skeleton weighted-bone count must agree with the mesh bone count.
    skeleton = load_json(skeleton_dst)
    weighted_nodes = [n for n in skeleton.get("nodes", []) if n.get("weightedIndex") is not None]
    weighted_bone_count = int(skeleton.get("weightedBoneCount") or len(weighted_nodes))
    if weighted_bone_count != operator_meta["boneCount"]:
        raise ValueError(
            f"Mesh 骨骼数 {operator_meta['boneCount']} 与骨架加权骨骼数 "
            f"{weighted_bone_count} 不一致，无法构建一致的逆解配置"
        )

    # Flag low-total-weight bones as unobservable (their recovered matrix is noisy).
    index_to_name = {int(n["weightedIndex"]): n.get("name", f"bone{n['weightedIndex']}")
                     for n in weighted_nodes}
    unobservable = sorted(
        index_to_name.get(i, f"bone{i}")
        for i, total in enumerate(operator_meta["boneWeightTotal"])
        if 0.0 < total < unobservable_weight_threshold
    )

    stride = int(profile.get("layout", {}).get("positionNormalTangentStride") or 40)
    actor, costume = _parse_body_target(resolved["body"])
    profile.setdefault("target", {})
    profile["target"].update({"actorId": actor, "costumeId": costume, "bodyResource": resolved["body"]})
    profile["target"].pop("note", None)
    profile["status"] = "complete-inverse-skin"
    skinning = profile.setdefault("skinning", {})
    skinning["status"] = "inverse-skin operator built from matched library Mesh"
    skinning["inverseSkin"] = {
        "sourceVertexCount": operator_meta["vertexCount"],
        "weightedBoneCount": weighted_bone_count,
        "coefficientCount": operator_meta["coefficientCount"],
        "posedVertexStride": stride,
        "inverseOperator": operator_rel,
        "meshJson": "Reference/Geo_Body.json",
        "skeletonJson": "Reference/Geo_Body.skeleton.json",
        "boneNaming": bone_naming,
        "unobservableBones": unobservable,
    }
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "body": resolved["body"],
        "match": resolved.get("match"),
        "boneNaming": bone_naming,
        "vertexCount": operator_meta["vertexCount"],
        "weightedBoneCount": weighted_bone_count,
        "activeBoneCount": operator_meta["activeBoneCount"],
        "unobservableBones": unobservable,
        "operatorBytes": operator_meta["operatorBytes"],
    }


def _capture_file(capture_dir, binding, resource_hash, resource_file=None):
    if resource_file:
        file_path = Path(capture_dir) / resource_file
        if file_path.is_file():
            return file_path
        matches = sorted(Path(capture_dir).rglob(resource_file))
        if matches:
            return matches[0]
    if resource_hash and str(resource_hash).startswith("draw:"):
        parts = str(resource_hash).split(":")
        if len(parts) >= 3:
            matches = _resource_files_by_draw(capture_dir, int(parts[1]), binding, ".buf")
            if matches:
                return matches[0]
    matches = sorted(Path(capture_dir).glob(f"*-{binding}={resource_hash}-*.buf"))
    if not matches:
        raise FileNotFoundError(
            f"No {binding} buffer with hash {resource_hash} in {capture_dir}"
        )
    return matches[0]


def _read_vb0(path, stride):
    data = Path(path).read_bytes()
    if len(data) % stride:
        raise ValueError(f"VB0 byte size is not divisible by stride {stride}")
    vertices, normals, tangents = [], [], []
    for offset in range(0, len(data), stride):
        x, y, z, nx, ny, nz, tx, ty, tz, tw = struct.unpack_from(
            "<3f3f4f", data, offset
        )
        # Unity Y-up/Z-forward to Blender Z-up/-Y-forward.
        vertices.append((x, -z, y))
        normals.append((nx, -nz, ny))
        tangents.append((tx, -tz, ty, tw))
    return vertices, normals, tangents


def _read_vb1(path, stride, expected_vertices):
    data = Path(path).read_bytes()
    if len(data) != stride * expected_vertices:
        raise ValueError("VB1 size does not match the Profile vertex count")
    colors, uv0, uv1 = [], [], []
    for offset in range(0, len(data), stride):
        r, g, b, a = struct.unpack_from("<4B", data, offset)
        u0, v0 = struct.unpack_from("<2e", data, offset + 4)
        u1, v1 = struct.unpack_from("<2e", data, offset + 8)
        colors.append((r / 255.0, g / 255.0, b / 255.0, a / 255.0))
        uv0.append((float(u0), 1.0 - float(v0)))
        uv1.append((float(u1), 1.0 - float(v1)))
    return colors, uv0, uv1


def _read_indices(path):
    data = Path(path).read_bytes()
    if len(data) % 6:
        raise ValueError("R16 triangle-list IB size must be divisible by 6")
    values = struct.unpack(f"<{len(data) // 2}H", data)
    return [tuple(values[i : i + 3]) for i in range(0, len(values), 3)]


def read_reference(profile_dir, component_id="body", capture_dir=None):
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    component = component_by_id(profile, component_id)
    capture = Path(capture_dir or profile["capture"]["directory"])
    vb0_hash = component["vbHashes"]["positionNormalTangent"]
    vb1_hash = component["vbHashes"].get("colorUv")
    resource_files = component.get("resourceFiles", {})
    vb0_path = _capture_file(capture, "vb0", vb0_hash, resource_files.get("vb0"))
    ib_path = _capture_file(capture, "ib", component["ibHash"], resource_files.get("ib"))
    vertices, normals, tangents = _read_vb0(
        vb0_path, profile["layout"]["positionNormalTangentStride"]
    )
    colors = uv0 = uv1 = None
    vb1_path = None
    if vb1_hash:
        vb1_path = _capture_file(capture, "vb1", vb1_hash, resource_files.get("vb1"))
        colors, uv0, uv1 = _read_vb1(
            vb1_path, profile["layout"]["colorUvStride"], len(vertices)
        )
    faces = _read_indices(ib_path)
    return {
        "profile_set": profile_set,
        "component": component,
        "capture_dir": str(capture),
        "vertices": vertices,
        "normals": normals,
        "tangents": tangents,
        "colors": colors,
        "uv0": uv0,
        "uv1": uv1,
        "faces": faces,
        "source_files": {
            "vb0": str(vb0_path),
            "vb1": str(vb1_path) if vb1_path else None,
            "ib": str(ib_path),
        },
    }


def _group(values, width):
    return [tuple(values[i : i + width]) for i in range(0, len(values), width)]


def read_weighted_reference(mesh_json, skeleton_json):
    """Read AssetStudio Mesh JSON plus a GakumasMI skeleton sidecar."""
    mesh = load_json(Path(mesh_json))
    skeleton = load_json(Path(skeleton_json))
    vertex_count = mesh["m_VertexCount"]
    vertices = [(x, -z, y) for x, y, z in _group(mesh["m_Vertices"], 3)]
    normals = [(x, -z, y) for x, y, z in _group(mesh["m_Normals"], 3)]
    tangents = [(x, -z, y, w) for x, y, z, w in _group(mesh["m_Tangents"], 4)]
    colors = _group(mesh["m_Colors"], 4)
    if colors and max(colors[0]) > 1.0:
        colors = [tuple(channel / 255.0 for channel in color) for color in colors]
    uv0 = [(u, 1.0 - v) for u, v in _group(mesh["m_UV0"], 2)]
    uv1 = [(u, 1.0 - v) for u, v in _group(mesh["m_UV1"], 2)]
    indices = mesh["m_Indices"]
    faces = [tuple(indices[i : i + 3]) for i in range(0, len(indices), 3)]
    if len(vertices) != vertex_count or len(mesh["m_Skin"]) != vertex_count:
        raise ValueError("Weighted Mesh arrays do not match m_VertexCount")
    if skeleton["weightedBoneCount"] != len(mesh["m_BindPose"]):
        raise ValueError("Skeleton weighted bone count does not match bind poses")
    return {
        "vertices": vertices,
        "normals": normals,
        "tangents": tangents,
        "colors": colors,
        "uv0": uv0,
        "uv1": uv1,
        "faces": faces,
        "skin": mesh["m_Skin"],
        "shapes": mesh.get("m_Shapes"),
        "skeleton": skeleton,
        "vertex_count": vertex_count,
        "index_count": len(indices),
        "name": mesh.get("m_Name", "WeightedMesh"),
    }


def validate_index_mesh(vertex_count, faces, expected_vertices, expected_indices):
    errors, warnings = [], []
    if vertex_count != expected_vertices:
        errors.append(
            f"原拓扑导出要求顶点数保持 {expected_vertices}，当前为 {vertex_count}"
        )
    if any(len(face) != 3 for face in faces):
        errors.append("所有面都必须先三角化")
    index_count = sum(len(face) for face in faces)
    if index_count > expected_indices:
        errors.append(
            f"索引数 {index_count} 超过原 Draw 容量 {expected_indices}"
        )
    elif index_count < expected_indices:
        warnings.append(
            f"索引数 {index_count} 会用退化三角形补齐到 {expected_indices}"
        )
    max_index = max((max(face) for face in faces if face), default=0)
    if max_index > 65535:
        errors.append("R16_UINT 无法引用超过 65535 的顶点索引")
    return errors, warnings


def _safe_section(value):
    return re.sub(r"[^A-Za-z0-9]", "", value.title()) or "GakumasMI"


def _validate_package_id(value):
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9-]+)+", value):
        raise ValueError("Mod 标识只能使用小写字母、数字、点和连字符")


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_index_package(
    profile_dir, output_root, package_id, name, author, component_id, faces,
    vertex_count=None,
):
    _validate_package_id(package_id)
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    drawcalls = profile_set["drawcalls"]
    component = component_by_id(profile, component_id)
    expected_indices = component.get("indices")
    if not expected_indices:
        raise ValueError(f"Profile component {component_id} has no fixed index count")
    errors, warnings = validate_index_mesh(
        vertex_count if vertex_count is not None else component["vertices"],
        faces, component["vertices"], expected_indices
    )
    if errors:
        raise ValueError("; ".join(errors))
    flat = [index for face in faces for index in face]
    flat.extend([0] * (expected_indices - len(flat)))
    package_dir = Path(output_root) / package_id
    buffer_dir = package_dir / "Buffers"
    buffer_dir.mkdir(parents=True, exist_ok=True)
    buffer_name = f"{component_id.title()}.IB.R16_UINT.buf"
    (buffer_dir / buffer_name).write_bytes(struct.pack(f"<{len(flat)}H", *flat))
    target = profile["target"]
    conflict = f"{target['actorId']}.{target['costumeId']}.{component_id}.mesh"
    manifest = {
        "schemaVersion": 1,
        "id": package_id,
        "name": name,
        "version": "0.1.0",
        "author": author,
        "type": "mesh-replacement",
        "profile": profile["id"],
        "targets": [f"{component_id}.indexBuffer"],
        "dependencies": [],
        "conflicts": [conflict],
        "runtime": ">=0.1.0",
        "status": "draft",
    }
    _write_json(package_dir / "manifest.json", manifest)
    section = _safe_section(package_id)
    passes = drawcalls["passes"]
    ini = f"""; Generated by GakumasMI Blender Add-on

[ShaderOverride{section}Shadow]
hash = {passes['shadowOrDepth']['vertexShader']}
checktextureoverride = ib

[ShaderOverride{section}Main]
hash = {passes['main']['vertexShader']}
checktextureoverride = ib

[ShaderOverride{section}Outline]
hash = {passes['main']['outlineVertexShader']}
checktextureoverride = ib

[TextureOverride{section}{component_id.title()}]
hash = {component['ibHash']}
ib = Resource{section}IB

[Resource{section}IB]
type = Buffer
format = DXGI_FORMAT_R16_UINT
filename = Buffers\\{buffer_name}
"""
    (package_dir / "mod.ini").write_text(ini, encoding="utf-8")
    (package_dir / "README.md").write_text(
        f"# {name}\n\nGenerated for Profile `{profile['id']}`.\n", encoding="utf-8"
    )
    return package_dir, warnings


def write_texture_package(profile_dir, output_root, package_id, name, author, texture_key, source_file):
    _validate_package_id(package_id)
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    entry = profile_set["textures"]["textures"].get(texture_key)
    if not entry:
        raise ValueError(f"Unknown texture key: {texture_key}")
    source = Path(source_file)
    if source.suffix.lower() != ".dds" or not source.is_file():
        raise ValueError("Texture export currently requires an existing DDS file")
    package_dir = Path(output_root) / package_id
    texture_dir = package_dir / "Textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    component, semantic = texture_key.split(".", 1)
    texture_name = f"{component.title()}.{semantic[0].upper() + semantic[1:]}.dds"
    shutil.copy2(source, texture_dir / texture_name)
    target = profile["target"]
    conflict = f"{target['actorId']}.{target['costumeId']}.{texture_key}"
    manifest = {
        "schemaVersion": 1,
        "id": package_id,
        "name": name,
        "version": "0.1.0",
        "author": author,
        "type": "texture-replacement",
        "profile": profile["id"],
        "targets": [texture_key],
        "dependencies": [],
        "conflicts": [conflict],
        "runtime": ">=0.1.0",
        "status": "draft",
    }
    _write_json(package_dir / "manifest.json", manifest)
    section = _safe_section(package_id)
    slot = entry["slot"]
    ini = f"""; Generated by GakumasMI Blender Add-on

[ShaderOverride{section}Texture]
hash = {entry['pixelShader']}
checktextureoverride = {slot}

[TextureOverride{section}{component.title()}{semantic.title()}]
hash = {entry['hash']}
this = Resource{section}Texture

[Resource{section}Texture]
filename = Textures\\{texture_name}
"""
    (package_dir / "mod.ini").write_text(ini, encoding="utf-8")
    (package_dir / "README.md").write_text(
        f"# {name}\n\nGenerated for `{texture_key}` in Profile `{profile['id']}`.\n",
        encoding="utf-8",
    )
    return package_dir


def _to_unity(vector):
    """Blender Z-up/-Y-forward to Unity Y-up/Z-forward."""
    return float(vector[0]), float(vector[2]), float(-vector[1])


def inverse_skin_bone_map(profile_dir, skeleton_json=None):
    """Return weighted bone name -> matrix index for an inverse-skin Profile."""
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    config = profile.get("skinning", {}).get("inverseSkin")
    if not config:
        raise ValueError("Profile has no skinning.inverseSkin configuration")
    source = Path(skeleton_json) if skeleton_json else profile_set["root"] / config["skeletonJson"]
    source = source.resolve()
    skeleton = load_json(source)
    result = {
        node["name"]: int(node["weightedIndex"])
        for node in skeleton["nodes"] if node.get("weightedIndex") is not None
    }
    if len(result) != int(config["weightedBoneCount"]):
        raise ValueError("Inverse-skin skeleton weighted bone count is inconsistent")
    return result


def _pack_inverse_skin_buffers(vertices, normals, tangents, uv0, uv1, colors,
                               faces, skin, expected_indices):
    count = len(vertices)
    arrays = (normals, tangents, uv0, uv1, colors, skin)
    if not all(len(values) == count for values in arrays):
        raise ValueError("Inverse-skin vertex arrays have different lengths")
    if count > 65535:
        raise ValueError("R16_UINT inverse-skin mesh cannot exceed 65535 vertices")
    if any(len(face) != 3 for face in faces):
        raise ValueError("Inverse-skin mesh must be triangulated")
    flat_indices = [int(index) for face in faces for index in face]
    if len(flat_indices) > expected_indices:
        raise ValueError(
            f"Mesh has {len(flat_indices)} indices; draw capacity is {expected_indices}"
        )
    if any(index < 0 or index >= count for index in flat_indices):
        raise ValueError("网格索引超出了导出顶点范围")

    bind = bytearray()
    vb1 = bytearray()
    for position, normal, tangent, tex0, tex1, color, influences in zip(
        vertices, normals, tangents, uv0, uv1, colors, skin
    ):
        if not influences or len(influences) > 4:
            raise ValueError("每个导出顶点必须有 1 到 4 个骨骼权重")
        bones = [int(item[0]) for item in influences]
        corrections = [int(item[1]) for item in influences]
        weights = [float(item[2]) for item in influences]
        if any(bone < 0 for bone in bones) or any(weight < 0.0 for weight in weights):
            raise ValueError("骨骼索引和权重不能为负数")
        total = sum(weights)
        if total <= 1e-8:
            raise ValueError("导出顶点的骨骼权重总和为 0")
        weights = [weight / total for weight in weights]
        bones.extend([0] * (4 - len(bones)))
        corrections.extend([0] * (4 - len(corrections)))
        weights.extend([0.0] * (4 - len(weights)))
        bind.extend(struct.pack(
            "<3f3f4f4I4I4f", *position, *normal, *tangent,
            *bones, *corrections, *weights
        ))
        rgba = [max(0, min(255, round(float(channel) * 255.0))) for channel in color]
        vb1.extend(struct.pack(
            "<4B4e", *rgba, float(tex0[0]), 1.0 - float(tex0[1]),
            float(tex1[0]), 1.0 - float(tex1[1])
        ))
    flat_indices.extend([0] * (expected_indices - len(flat_indices)))
    ib = struct.pack(f"<{len(flat_indices)}H", *flat_indices)
    return bytes(bind), bytes(vb1), ib


def write_inverse_skin_package(
    profile_dir, output_root, package_id, name, author, component_id,
    vertices, normals, tangents, uv0, uv1, colors, faces, skin, corrections,
    material_textures=None,
):
    """Write an arbitrary-topology, bone-weighted 3Dmigoto package."""
    _validate_package_id(package_id)
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    component = component_by_id(profile, component_id)
    drawcalls = profile_set["drawcalls"]
    config = profile.get("skinning", {}).get("inverseSkin")
    if not config:
        raise ValueError("Profile has no inverse-skin runtime data")
    expected_indices = int(component["indices"])
    bind, vb1, ib = _pack_inverse_skin_buffers(
        vertices, normals, tangents, uv0, uv1, colors, faces, skin, expected_indices
    )
    vertex_count = len(vertices)
    source_vertex_count = int(config["sourceVertexCount"])
    coefficient_count = int(config["coefficientCount"])
    material_textures = material_textures or {}

    package_dir = Path(output_root) / package_id
    buffer_dir = package_dir / "Buffers"
    shader_dir = package_dir / "Shaders"
    buffer_dir.mkdir(parents=True, exist_ok=True)
    shader_dir.mkdir(parents=True, exist_ok=True)
    texture_dir = package_dir / "Textures"
    (buffer_dir / "Body.BindSkin.R32_UINT.buf").write_bytes(bind)
    flat_corrections = [float(value) for matrix in corrections for row in matrix for value in row]
    (buffer_dir / "Body.BoneCorrections.R32_FLOAT.buf").write_bytes(
        struct.pack(f"<{len(flat_corrections)}f", *flat_corrections)
    )
    (buffer_dir / "Body.VB1.buf").write_bytes(vb1)
    (buffer_dir / "Body.IB.R16_UINT.buf").write_bytes(ib)
    operator_source = (profile_set["root"] / config["inverseOperator"]).resolve()
    if not operator_source.is_file():
        raise FileNotFoundError(f"Inverse operator not found: {operator_source}")
    shutil.copy2(operator_source, buffer_dir / "InverseOperator.R32_FLOAT.buf")
    shader_root = Path(__file__).parent / "shaders"
    shutil.copy2(shader_root / "RecoverMatricesCS.hlsl", shader_dir / "RecoverMatricesCS.hlsl")
    skin_shader = (shader_root / "SkinCustomCS.hlsl").read_text(encoding="utf-8")
    skin_shader = skin_shader.replace(
        "#define TARGET_VERTEX_COUNT 1", f"#define TARGET_VERTEX_COUNT {vertex_count}"
    )
    (shader_dir / "SkinCustomCS.hlsl").write_text(skin_shader, encoding="utf-8")

    section = _safe_section(package_id)
    material_bindings = []
    material_resources = []
    material_manifest = {}
    if material_textures:
        texture_dir.mkdir(parents=True, exist_ok=True)
    for texture_key, source_file in material_textures.items():
        entry = profile_set["textures"]["textures"].get(texture_key)
        if not entry:
            raise ValueError(f"Unknown Profile material texture: {texture_key}")
        source = Path(source_file)
        if not source.is_file() or source.suffix.lower() != ".dds":
            raise ValueError(f"Material texture must be an existing DDS: {source}")
        description = inspect_dds(source)
        expected_size = entry.get("size")
        if expected_size and [description["width"], description["height"]] != expected_size:
            raise ValueError(
                f"{texture_key} must be {expected_size[0]}x{expected_size[1]}, got "
                f"{description['width']}x{description['height']}"
            )
        if entry.get("format") and description["format"] != entry["format"]:
            raise ValueError(
                f"{texture_key} must be {entry['format']}, got {description['format']}"
            )
        texture_component, semantic = texture_key.split(".", 1)
        if texture_component != component_id:
            raise ValueError(f"Texture {texture_key} does not belong to {component_id}")
        resource_name = f"{section}{semantic.title()}"
        filename = f"{component_id.title()}.{semantic[0].upper() + semantic[1:]}.dds"
        shutil.copy2(source, texture_dir / filename)
        material_bindings.append(f"    {entry['slot']} = Resource{resource_name}")
        material_resources.append(
            f"[Resource{resource_name}]\nfilename = Textures\\{filename}\n"
        )
        material_manifest[texture_key] = {
            "slot": entry["slot"], "hash": entry["hash"], "file": f"Textures/{filename}"
        }

    passes = drawcalls["passes"]
    dispatch_matrices = coefficient_count
    dispatch_vertices = (vertex_count + 63) // 64
    ini = f"""; Generated by GakumasMI Blender Add-on (inverse-skin weighted mesh)

[Constants]
global $enable_{section} = 1

[ShaderOverride{section}Shadow]
hash = {passes['shadowOrDepth']['vertexShader']}
checktextureoverride = ib

[ShaderOverride{section}Main]
hash = {passes['main']['vertexShader']}
checktextureoverride = ib

[ShaderOverride{section}Outline]
hash = {passes['main']['outlineVertexShader']}
checktextureoverride = ib

[TextureOverride{section}{component_id.title()}]
hash = {component['ibHash']}
if $enable_{section}
    Resource{section}PosedVB = copy vb0
    run = CustomShader{section}RecoverMatrices
    run = CustomShader{section}SkinCustom
    Resource{section}SkinnedVBIA = copy Resource{section}SkinnedVB
    vb0 = Resource{section}SkinnedVBIA
    vb1 = Resource{section}VB1
    vb3 = Resource{section}SkinnedVBIA
    ib = Resource{section}IB
{chr(10).join(material_bindings)}
endif

[CustomShader{section}RecoverMatrices]
cs = Shaders\\RecoverMatricesCS.hlsl
cs-t0 = Resource{section}PosedVB
cs-t1 = Resource{section}InverseOperator
cs-u0 = Resource{section}RecoveredMatrices
dispatch = {dispatch_matrices}, 1, 1
post cs-t0 = null
post cs-t1 = null
post cs-u0 = null

[CustomShader{section}SkinCustom]
cs = Shaders\\SkinCustomCS.hlsl
cs-t0 = Resource{section}BindVertices
cs-t1 = Resource{section}RecoveredMatrices
cs-t2 = Resource{section}BoneCorrections
cs-u0 = Resource{section}SkinnedVB
dispatch = {dispatch_vertices}, 1, 1
post cs-t0 = null
post cs-t1 = null
post cs-t2 = null
post cs-u0 = null

[Resource{section}PosedVB]
type = Buffer
stride = 4
array = {source_vertex_count * 10}

[Resource{section}InverseOperator]
type = Buffer
format = R32_FLOAT
filename = Buffers\\InverseOperator.R32_FLOAT.buf

[Resource{section}RecoveredMatrices]
type = RWBuffer
format = R32_UINT
array = {coefficient_count * 3}

[Resource{section}BindVertices]
type = Buffer
format = R32_UINT
filename = Buffers\\Body.BindSkin.R32_UINT.buf

[Resource{section}BoneCorrections]
type = Buffer
format = R32_FLOAT
filename = Buffers\\Body.BoneCorrections.R32_FLOAT.buf

[Resource{section}SkinnedVB]
type = RWBuffer
format = R32_UINT
array = {vertex_count * 10}

[Resource{section}SkinnedVBIA]
type = Buffer
stride = 40

[Resource{section}VB1]
type = Buffer
stride = 12
filename = Buffers\\Body.VB1.buf

[Resource{section}IB]
type = Buffer
format = DXGI_FORMAT_R16_UINT
filename = Buffers\\Body.IB.R16_UINT.buf

{chr(10).join(material_resources)}
"""
    (package_dir / "mod.ini").write_text(ini, encoding="utf-8")
    target = profile["target"]
    manifest = {
        "schemaVersion": 1,
        "id": package_id,
        "name": name,
        "version": "0.1.0",
        "author": author,
        "type": "inverse-skin-mesh-replacement",
        "profile": profile["id"],
        "targets": [f"{component_id}.weightedMesh"],
        "conflicts": [f"{target['actorId']}.{target['costumeId']}.{component_id}.mesh"],
        "runtime": "3dmigoto-compute",
        "vertexCount": vertex_count,
        "indexCount": len(faces) * 3,
        "status": "draft",
        "materials": material_manifest,
    }
    _write_json(package_dir / "manifest.json", manifest)
    (package_dir / "README.md").write_text(
        f"# {name}\n\nInverse-skin weighted Body mesh for Profile `{profile['id']}`.\n",
        encoding="utf-8",
    )
    return package_dir
