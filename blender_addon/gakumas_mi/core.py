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


def component_by_id(profile, component_id):
    for component in profile["components"]:
        if component["id"] == component_id:
            return component
    raise ValueError(f"Unknown Profile component: {component_id}")


def _capture_file(capture_dir, binding, resource_hash):
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
    vb0_path = _capture_file(capture, "vb0", vb0_hash)
    ib_path = _capture_file(capture, "ib", component["ibHash"])
    vertices, normals, tangents = _read_vb0(
        vb0_path, profile["layout"]["positionNormalTangentStride"]
    )
    colors = uv0 = uv1 = None
    vb1_path = None
    if vb1_hash:
        vb1_path = _capture_file(capture, "vb1", vb1_hash)
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


def _pack_surface_buffers(vertices, normals, uv0, uv1, colors, faces, mappings,
                          expected_indices):
    count = len(vertices)
    if not all(len(values) == count for values in (normals, uv0, uv1, colors, mappings)):
        raise ValueError("Surface-mapped vertex arrays have different lengths")
    if count > 65535:
        raise ValueError("R16_UINT surface mesh cannot exceed 65535 vertices")
    if any(len(face) != 3 for face in faces):
        raise ValueError("Surface mesh must be triangulated before export")
    flat_indices = [int(index) for face in faces for index in face]
    if len(flat_indices) > expected_indices:
        raise ValueError(
            f"Surface mesh has {len(flat_indices)} indices; draw capacity is {expected_indices}"
        )
    if any(index < 0 or index >= count for index in flat_indices):
        raise ValueError("Surface mesh index is outside the exported vertex range")

    vb0 = bytearray()
    vb1 = bytearray()
    mapping_buffer = bytearray()
    for vertex, normal, tex0, tex1, color, mapping in zip(
        vertices, normals, uv0, uv1, colors, mappings
    ):
        indices = mapping["indices"]
        barycentric = mapping["barycentric"]
        if len(indices) != 3 or len(barycentric) != 3:
            raise ValueError("Each surface mapping requires three indices and weights")
        # Preserve the game's exact IA signature. POSITION/NORMAL/TANGENT carry
        # the surface-drive record, then the custom VS replaces them with the
        # animated position/normal read from t120. Float32 represents every
        # valid source vertex index exactly (the source is far below 2^24).
        vb0.extend(struct.pack(
            "<3f3f4f",
            float(indices[0]), float(indices[1]), float(indices[2]),
            float(barycentric[0]), float(barycentric[1]), float(barycentric[2]),
            float(mapping.get("normal_offset", 0.0)), 0.0, 0.0, 0.0,
        ))
        rgba = [max(0, min(255, round(float(channel) * 255.0))) for channel in color]
        vb1.extend(struct.pack("<4B4e", *rgba, float(tex0[0]), 1.0 - float(tex0[1]),
                               float(tex1[0]), 1.0 - float(tex1[1])))
        mapping_buffer.extend(struct.pack(
            "<3I4fI", int(indices[0]), int(indices[1]), int(indices[2]),
            float(barycentric[0]), float(barycentric[1]), float(barycentric[2]),
            float(mapping.get("normal_offset", 0.0)), 0,
        ))
    flat_indices.extend([0] * (expected_indices - len(flat_indices)))
    ib = struct.pack(f"<{len(flat_indices)}H", *flat_indices)
    return bytes(vb0), bytes(vb1), ib, bytes(mapping_buffer)


def write_surface_package(
    profile_dir, output_root, package_id, name, author, component_id,
    vertices, normals, uv0, uv1, colors, faces, mappings,
):
    """Write an arbitrary-topology mesh driven by the game's animated source surface."""
    _validate_package_id(package_id)
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    component = component_by_id(profile, component_id)
    drawcalls = profile_set["drawcalls"]
    expected_indices = int(component["indices"])
    vb0, vb1, ib, mapping_buffer = _pack_surface_buffers(
        vertices, normals, uv0, uv1, colors, faces, mappings, expected_indices
    )

    package_dir = Path(output_root) / package_id
    buffer_dir = package_dir / "Buffers"
    shader_dir = package_dir / "Shaders"
    buffer_dir.mkdir(parents=True, exist_ok=True)
    shader_dir.mkdir(parents=True, exist_ok=True)
    (buffer_dir / "Body.VB0.buf").write_bytes(vb0)
    (buffer_dir / "Body.VB1.buf").write_bytes(vb1)
    (buffer_dir / "Body.IB.R16_UINT.buf").write_bytes(ib)
    (buffer_dir / "Body.SurfaceMap.buf").write_bytes(mapping_buffer)
    shutil.copy2(
        Path(__file__).parent / "shaders" / "SurfaceMappedBody.hlsl",
        shader_dir / "SurfaceMappedBody.hlsl",
    )

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
        "targets": [f"{component_id}.surfaceMappedMesh"],
        "dependencies": [],
        "conflicts": [conflict],
        "runtime": ">=0.1.0",
        "status": "draft",
    }
    _write_json(package_dir / "manifest.json", manifest)
    section = _safe_section(package_id)
    passes = drawcalls["passes"]
    ini = f"""; Generated by GakumasMI Blender Add-on (surface mapped mesh)

[Constants]
global $enable_{section} = 1

[ShaderOverride{section}Main]
hash = {passes['main']['vertexShader']}
checktextureoverride = ib

[TextureOverride{section}{component_id.title()}]
hash = {component['ibHash']}
if $enable_{section}
    Resource{section}AnimatedSource = copy vb0
    vb0 = Resource{section}VB0
    vb1 = Resource{section}VB1
    vb3 = Resource{section}VB0
    ib = Resource{section}IB
    run = CustomShader{section}SurfaceDrive
endif

[CustomShader{section}SurfaceDrive]
vs = Mods\\{package_id}\\Shaders\\SurfaceMappedBody.hlsl
vs-t120 = Resource{section}AnimatedSource
draw = from_caller
handling = skip
post vs-t120 = null

[Resource{section}AnimatedSource]

[Resource{section}VB0]
type = Buffer
stride = 40
filename = Buffers\\Body.VB0.buf

[Resource{section}VB1]
type = Buffer
stride = 12
filename = Buffers\\Body.VB1.buf

[Resource{section}IB]
type = Buffer
format = DXGI_FORMAT_R16_UINT
filename = Buffers\\Body.IB.R16_UINT.buf

"""
    (package_dir / "mod.ini").write_text(ini, encoding="utf-8")
    (package_dir / "README.md").write_text(
        f"# {name}\n\nSurface-mapped Body mesh for Profile `{profile['id']}`.\n"
        "Install this directory under `Mods` without renaming it.\n",
        encoding="utf-8",
    )
    return package_dir


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
