"""Blender-independent Profile, buffer, validation and package helpers."""

from __future__ import annotations

import json
import re
import shutil
import struct
import textwrap
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


def write_rgba8_dds(path, width, height, rgba_bytes, srgb=True):
    """Write an uncompressed R8G8B8A8 DDS with a DX10 header (top-down, 1 mip).

    Used to turn a PNG into a 3Dmigoto-loadable texture without an external BC7
    encoder. inspect_dds() requires a DX10 header, so we always emit one.
    """
    if len(rgba_bytes) != width * height * 4:
        raise ValueError("RGBA 数据长度与 width*height*4 不一致")
    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000  # caps|height|width|pitch|pixelformat
    header = struct.pack(
        "<7I", 124, flags, height, width, width * 4, 0, 1
    ) + b"\x00" * 44  # dwReserved1[11]
    header += struct.pack("<2I", 32, 0x4) + b"DX10" + struct.pack("<5I", 0, 0, 0, 0, 0)  # pixelformat
    header += struct.pack("<5I", 0x1000, 0, 0, 0, 0)  # caps + caps2/3/4 + reserved2
    dxgi_format = 29 if srgb else 28  # R8G8B8A8_UNORM_SRGB / R8G8B8A8_UNORM
    dxt10 = struct.pack("<5I", dxgi_format, 3, 0, 1, 0)  # format, dim=Texture2D, misc, arraySize, misc2
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"DDS " + header + dxt10 + bytes(rgba_bytes))


# 中性材质常量:盖掉游戏原版 t1/t4 对新贴图的光照/阴影干扰。
# t1 PackedMask: R=阴影阈值(亮) G=光滑度0(哑光) B=金属度0 A=AO255(不压暗)
NEUTRAL_PACKED_MASK = (255, 0, 0, 255)
# t4 ShadeColor: RGB 为暗色版 baseColor；A 按原生 sdw 近似二值材质遮罩。
# 中性 t4.A=0，避免把原版 shade mask 带到自定义 atlas 上。
NEUTRAL_SHADE_COLOR = (128, 128, 128, 0)
# hair 与 body 共用 t1 算法；A 门控镜面/间接/HHL。当前不替换 t6 HHL，自定义 UV 下
# A=0 可屏蔽旧高光。该 hmsz 实测值是安全中性预设，不代表所有原版 hair 都是常量图。
HAIR_NEUTRAL_PACKED_MASK = (67, 32, 0, 0)


def write_solid_rgba8_dds(path, rgba, size=4, srgb=False):
    """Write a tiny solid-color RGBA8 DDS (for neutral t1/t4 material textures)."""
    r, g, b, a = (
        max(0, min(255, int(_safe_float(channel, 0.0))))
        for channel in rgba
    )
    write_rgba8_dds(path, size, size, bytes([r, g, b, a]) * (size * size), srgb=srgb)


def _dds_formats_compatible(expected, actual):
    return expected == actual or {expected, actual} in (
        {"BC7_UNORM", "R8G8B8A8_UNORM"},
        {"BC7_UNORM_SRGB", "R8G8B8A8_UNORM_SRGB"},
    )


def load_material_presets():
    """读取分材质 t1/t4 预设库(随插件分发)。"""
    return load_json(Path(__file__).parent / "material_presets.json")["presets"]


def _srgb_to_linear(c):
    import numpy as np
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    import numpy as np
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _rgb_to_hsv(rgb):
    import numpy as np
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.max(rgb, axis=-1)
    mn = np.min(rgb, axis=-1)
    df = mx - mn
    h = np.zeros_like(mx)
    nz = df > 1e-9
    rm, gm, bm = (mx == r) & nz, (mx == g) & nz, (mx == b) & nz
    h[rm] = ((g - b)[rm] / df[rm]) % 6
    h[gm] = ((b - r)[gm] / df[gm]) + 2
    h[bm] = ((r - g)[bm] / df[bm]) + 4
    h = (h / 6.0) % 1.0
    s = np.where(mx > 1e-9, df / np.maximum(mx, 1e-9), 0.0)
    return h, s, mx


def _hsv_to_rgb(h, s, v):
    import numpy as np
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = (i.astype(int)) % 6
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def shade_color_from_base(base_rgb8, darken, hue_shift_deg, sat_scale):
    """由 baseColor(sRGB 8-bit RGB)派生 shadeColor RGB(sRGB 8-bit)。

    压暗在线性光下进行(与游戏采样后的着色一致),色相/饱和在 HSV 上微调。
    """
    import numpy as np
    base01 = base_rgb8.astype(np.float32) / 255.0
    lin = _srgb_to_linear(base01) * float(darken)
    h, s, v = _rgb_to_hsv(lin)
    h = (h + hue_shift_deg / 360.0) % 1.0
    s = np.clip(s * sat_scale, 0.0, 1.0)
    out = _linear_to_srgb(_hsv_to_rgb(h, s, v))
    return np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)


def shade_color_linear_mul(base_rgb8, mul_rgb):
    """由 baseColor 按线性光逐通道乘数派生 shadeColor(hair 冷阴影实测语义)。"""
    import numpy as np
    lin = _srgb_to_linear(base_rgb8.astype(np.float32) / 255.0)
    lin = lin * np.asarray(mul_rgb, dtype=np.float32)
    out = _linear_to_srgb(lin)
    return np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)


def rasterize_material_ids(uv_tris, mat_ids, size, dilate=8):
    """把每个三角形按 UV 栅格化成材质槽 ID 图(top-down,V 翻转)。

    uv_tris: (N,3,2) float UV；mat_ids: (N,) int(材质槽索引)。
    返回 (size,size) int16,未覆盖处为 -1;dilate 步外扩以补 UV 缝隙/外扩填充。
    """
    import numpy as np
    id_map = np.full((size, size), -1, dtype=np.int16)
    px = uv_tris[:, :, 0] * size
    py = (1.0 - uv_tris[:, :, 1]) * size  # V 翻转 → top-down
    for tri in range(uv_tris.shape[0]):
        x0, x1, x2 = px[tri]
        y0, y1, y2 = py[tri]
        minx, maxx = int(np.floor(min(x0, x1, x2))), int(np.ceil(max(x0, x1, x2)))
        miny, maxy = int(np.floor(min(y0, y1, y2))), int(np.ceil(max(y0, y1, y2)))
        minx, miny = max(minx, 0), max(miny, 0)
        maxx, maxy = min(maxx, size), min(maxy, size)
        if maxx <= minx or maxy <= miny:
            continue
        ys, xs = np.mgrid[miny:maxy, minx:maxx]
        xs = xs + 0.5
        ys = ys + 0.5
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-9:
            continue
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / denom
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / denom
        c = 1.0 - a - b
        inside = (a >= 0) & (b >= 0) & (c >= 0)
        block = id_map[miny:maxy, minx:maxx]
        block[inside] = mat_ids[tri]
    # 外扩填充:用最近的已覆盖材质补缝隙,避免 mip/采样在岛边漏到中性
    for _ in range(dilate):
        empty = id_map < 0
        if not empty.any():
            break
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shifted = np.roll(id_map, (dy, dx), axis=(0, 1))
            take = empty & (shifted >= 0)
            id_map[take] = shifted[take]
            empty = id_map < 0
    return id_map


def rasterize_vertex_scalar(uv_tris, scalar_tris, size, dilate=8):
    """把每顶点标量(如 AO)按 UV 栅格化并重心插值成 (size,size) float 图。

    uv_tris: (N,3,2) UV；scalar_tris: (N,3) 每个三角顶点的标量。
    未覆盖处为 NaN，dilate 步用最近值外扩补缝。
    """
    import numpy as np
    out = np.full((size, size), np.nan, dtype=np.float32)
    px = uv_tris[:, :, 0] * size
    py = (1.0 - uv_tris[:, :, 1]) * size
    for tri in range(uv_tris.shape[0]):
        x0, x1, x2 = px[tri]
        y0, y1, y2 = py[tri]
        minx, maxx = int(np.floor(min(x0, x1, x2))), int(np.ceil(max(x0, x1, x2)))
        miny, maxy = int(np.floor(min(y0, y1, y2))), int(np.ceil(max(y0, y1, y2)))
        minx, miny = max(minx, 0), max(miny, 0)
        maxx, maxy = min(maxx, size), min(maxy, size)
        if maxx <= minx or maxy <= miny:
            continue
        ys, xs = np.mgrid[miny:maxy, minx:maxx]
        xs = xs + 0.5
        ys = ys + 0.5
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-9:
            continue
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / denom
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / denom
        c = 1.0 - a - b
        inside = (a >= 0) & (b >= 0) & (c >= 0)
        s0, s1, s2 = scalar_tris[tri]
        vals = a * s0 + b * s1 + c * s2
        block = out[miny:maxy, minx:maxx]
        block[inside] = vals[inside]
    for _ in range(dilate):
        empty = np.isnan(out)
        if not empty.any():
            break
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shifted = np.roll(out, (dy, dx), axis=(0, 1))
            take = empty & ~np.isnan(shifted)
            out[take] = shifted[take]
            empty = np.isnan(out)
    return out


def bake_material_maps(id_map, base_rgb8, class_per_slot, presets,
                       form_map=None, form_strength=0.0, smoothness_max=1.0,
                       toon_override=None, toon_per_slot=None, neutral_key="neutral"):
    """按材质ID图烘焙 t1(packedMask)/t4(shadeColor)的 RGBA8 数组。

    id_map: (H,W) int 材质槽索引(-1=未覆盖→中性);base_rgb8: (H,W,3 或 4) uint8;
    class_per_slot: {slot_index: 预设键};presets: load_material_presets()。
    form_map: 可选 (H,W) 0..1 几何 AO/曲率图(NaN=无),用于给 toon/AO 通道
    叠加随形体的空间渐变,避免 flat toon 在圆柱体上出硬光影分界。
    form_strength: 渐变强度(0=关闭)。
    neutral_key: 未覆盖区(-1)使用的预设键;hair 传 "hair"，以 A=0 屏蔽未替换 t6 HHL。
    返回 (t1_rgba8, t4_rgba8),均为 (H,W,4) uint8。
    """
    import numpy as np
    h, w = id_map.shape
    base = base_rgb8[..., :3]
    t1 = np.empty((h, w, 4), dtype=np.uint8)
    t4 = np.empty((h, w, 4), dtype=np.uint8)
    use_form = form_map is not None and form_strength > 0.0
    if use_form:
        form = np.where(np.isnan(form_map), 0.5, form_map)  # 无几何处取中性 0.5

    def _fill(mask, toon, smooth, metal, ao):
        if toon_override is not None:
            toon = toon_override  # 调试/统一:强制 toon 阈值,验证 t1 是否生效
        if use_form:
            delta = (form[mask] - 0.5) * form_strength
            t1[mask, 0] = np.clip((toon + delta) * 255.0 + 0.5, 0, 255).astype(np.uint8)
            # 凹陷(form 低)再补一点 AO 暗,凸起不动
            t1[mask, 3] = np.clip((ao - np.minimum(delta, 0.0)) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        else:
            t1[mask, 0] = round(toon * 255)
            t1[mask, 3] = round(ao * 255)
        t1[mask, 1] = round(min(smooth, smoothness_max) * 255)
        t1[mask, 2] = round(metal * 255)

    def _shade_rgb(m4, base_pixels):
        # hair 实测阴影 = base_lin × 逐通道冷阴影乘数,与 body 的单一 darken 不同
        if m4.get("linearMul"):
            return shade_color_linear_mul(base_pixels, m4["linearMul"])
        return shade_color_from_base(
            base_pixels, m4["darken"], m4["hueShiftDeg"], m4["satScale"])

    neutral = presets.get(neutral_key) or presets["neutral"]
    n1, n4 = neutral["t1"], neutral["t4"]
    _fill(np.ones((h, w), bool), n1["toonShadowThreshold"], n1["smoothness"],
          n1["metallic"], n1["ao"])
    t4[..., :3] = _shade_rgb(n4, base)
    t4[..., 3] = round(n4["alpha"] * 255)
    for slot, key in class_per_slot.items():
        preset = presets.get(key)
        if preset is None:
            continue
        mask = id_map == slot
        if not mask.any():
            continue
        m1, m4 = preset["t1"], preset["t4"]
        toon = m1["toonShadowThreshold"]
        if toon_per_slot and toon_per_slot.get(slot) is not None:
            toon = toon_per_slot[slot]  # 该材质的逐材质 toon 微调,覆盖预设
        _fill(mask, toon, m1["smoothness"], m1["metallic"], m1["ao"])
        if m4.get("fixedColor"):  # 兼容旧预设：允许固定阴影色，不从底色派生
            t4[mask, 0], t4[mask, 1], t4[mask, 2] = m4["fixedColor"]
        else:
            t4[mask, :3] = _shade_rgb(m4, base[mask])
        # t4.A 不暴露给作者手调；它是材质类型预设的二值结果。
        t4[mask, 3] = round(m4["alpha"] * 255)
    return t1, t4


def packed_mask_channel_label(channel):
    return ("R", "G", "B", "A")[int(channel)]


def apply_packed_mask_channel_overrides(t1_rgba8, id_map, channel_maps, *, global_if_complete=True,
                                        material_signal_threshold=0.01):
    """Merge external single-channel maps into a baked t1/PackedMask.

    channel_maps: {0..3: (H,W) uint8}. R/G/B/A correspond to toon threshold,
    smoothness, metallic and AO. If all four channels are present, they are
    treated as an authored full t1 and applied globally. If only some channels
    are present, each channel is applied per material only where that material's
    UV area contains visible signal, so blank atlas regions do not overwrite
    baked presets.

    Returns a summary dict with mode and applied material slots.
    """
    import numpy as np

    if not channel_maps:
        return {"mode": "none", "applied": {}}
    t1 = np.asarray(t1_rgba8)
    if t1.ndim != 3 or t1.shape[2] != 4:
        raise ValueError("t1_rgba8 must be an HxWx4 array")
    h, w = t1.shape[:2]
    for channel, channel_map in channel_maps.items():
        if channel not in (0, 1, 2, 3):
            raise ValueError(f"Unsupported t1 channel: {channel}")
        if channel_map.shape != (h, w):
            raise ValueError(
                f"t1.{packed_mask_channel_label(channel)} 尺寸不匹配: "
                f"{channel_map.shape[1]}x{channel_map.shape[0]} != {w}x{h}"
            )

    applied = {}
    complete = set(channel_maps) == {0, 1, 2, 3}
    if global_if_complete and complete:
        for channel, channel_map in channel_maps.items():
            t1[..., channel] = channel_map
            applied[packed_mask_channel_label(channel)] = ["global"]
        return {"mode": "complete", "applied": applied}

    if id_map is None:
        for channel, channel_map in channel_maps.items():
            t1[..., channel] = channel_map
            applied[packed_mask_channel_label(channel)] = ["global"]
        return {"mode": "partial-global", "applied": applied}

    ids = sorted(int(slot) for slot in np.unique(id_map) if int(slot) >= 0)
    for channel, channel_map in channel_maps.items():
        channel_applied = []
        for slot in ids:
            mask = id_map == slot
            if not mask.any():
                continue
            values = channel_map[mask]
            # Blank atlas regions are usually flat black or flat white. Real
            # authored masks have variation or mid-range values; use that as
            # the signal to keep missing-material regions on the baked preset.
            varied = int(values.max()) - int(values.min()) > 1
            mid_fraction = ((values > 0) & (values < 255)).mean()
            if not varied and mid_fraction < material_signal_threshold:
                continue
            t1[mask, channel] = values
            channel_applied.append(slot)
        applied[packed_mask_channel_label(channel)] = channel_applied
    return {"mode": "partial-material", "applied": applied}


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
            "textureBindingCount": sum(
                1
                for (resource_draw, binding), entry in resources.items()
                if resource_draw == draw and binding.startswith("ps-t")
                and (entry.get("texture") or entry.get("dsc"))
            ),
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


def _select_main_candidate(candidates, requested_draw=None, expected_vertex_count=None,
                           expected_vertex_counts=None):
    if not candidates:
        raise ValueError("抓帧中没有找到可作为 Body 的 IB/VB0/VB1 候选")
    if requested_draw is not None:
        for candidate in candidates:
            if candidate["draw"] == int(requested_draw):
                return candidate
        raise ValueError(f"指定 Draw {int(requested_draw):06d} 没有可用 Body 候选")
    complete = [
        item for item in candidates
        if item.get("vb1ByteWidth") and item["vertices"] >= 1000
    ]
    # Tiny repeated helper meshes can outscore the real body by pass count alone.
    # Body draws have both streams; if such candidates exist, choose only among them.
    pool = complete or candidates
    expected_counts = {
        int(value)
        for value in (expected_vertex_counts or [])
        if value
    }
    if expected_vertex_count:
        expected_counts.add(int(expected_vertex_count))
    if expected_counts:
        expected_pool = [
            item for item in pool
            if int(item.get("vertices") or 0) in expected_counts
        ]
        if expected_pool:
            pool = expected_pool
    best = pool[0]
    group = [
        item for item in pool
        if item.get("ibHash") == best.get("ibHash")
        and item["indices"] == best["indices"]
        and item["vertices"] == best["vertices"]
    ]
    if len(group) >= 3:
        visible = [item for item in group if int(item.get("textureBindingCount") or 0) > 0]
        if visible:
            return sorted(
                visible,
                key=lambda item: (int(item.get("textureBindingCount") or 0), int(item["draw"])),
            )[-1]
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


def _texture_semantic(slot, bindings=None):
    return {
        "ps-t0": "baseColor",
        "ps-t1": "packedMask",
        "ps-t4": "shadeColor",
        "ps-t5": "ramp",
        "ps-t7": "rampAdd",
    }.get(slot, slot.replace("ps-", ""))


def _same_body_streams(candidate, selected):
    return (
        candidate.get("ibHash") == selected.get("ibHash")
        and candidate["vertices"] == selected["vertices"]
        and candidate.get("vbHashes", {}).get("positionNormalTangent")
        == selected.get("vbHashes", {}).get("positionNormalTangent")
        and candidate.get("vbHashes", {}).get("colorUv")
        == selected.get("vbHashes", {}).get("colorUv")
    )


def _section_texture_slots(resources, draw, component_id, key_prefix):
    slots = []
    textures = {}
    draw_bindings = {
        binding for (resource_draw, binding), entry in resources.items()
        if resource_draw == draw and binding.startswith("ps-t")
    }
    for (resource_draw, binding), entry in sorted(resources.items()):
        if resource_draw != draw or not binding.startswith("ps-t"):
            continue
        semantic = _texture_semantic(binding, draw_bindings)
        texture_key = f"{key_prefix}.{semantic}"
        texture_file = entry.get("texture")
        textures[texture_key] = {
            "slot": binding,
            "semantic": semantic,
            "hash": entry.get("hash") or f"draw:{draw:06d}:{binding}",
            "pixelShader": entry.get("ps"),
            "file": texture_file.name if texture_file else None,
            "descriptor": entry.get("descriptor", {}),
            "component": component_id,
        }
        slots.append({
            "key": texture_key,
            "slot": binding,
            "semantic": semantic,
            "hash": textures[texture_key]["hash"],
        })
    return textures, slots


def extract_profile_from_frame_dump(capture_dir, output_dir, component_id="body",
                                    main_draw=None, expected_vertex_count=None,
                                    expected_vertex_counts=None, body_resource=None):
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
    selected = _select_main_candidate(
        candidates,
        main_draw if main_draw else None,
        expected_vertex_count=expected_vertex_count,
        expected_vertex_counts=expected_vertex_counts,
    )
    same_group = [
        item for item in candidates
        if item.get("ibHash") == selected.get("ibHash")
        and item["indices"] == selected["indices"]
        and item["vertices"] == selected["vertices"]
    ]
    ordered_draws = sorted(item["draw"] for item in same_group)
    section_group = [
        item for item in candidates
        if _same_body_streams(item, selected)
    ]

    # 同一 body IB 的各段 StartIndexLocation:主体段 + 尾部小段(原版配件)。
    # 生成器据此 match_first_index + drawindexed 主体、skip 尾部,避免叠图/漏出。
    body_ib = selected.get("ibHash")
    main_first_index = int((selected.get("drawCall") or {}).get("startIndex") or 0)
    section_starts = {
        int(rec.get("startIndex") or 0)
        for rec in draw_records.values()
        if rec.get("ibHash") == body_ib
    }
    tail_first_indices = sorted(s for s in section_starts if s != main_first_index)
    section_items = {}
    for item in section_group:
        start = int((item.get("drawCall") or {}).get("startIndex") or 0)
        section_items.setdefault(start, []).append(item)
    material_sections = []
    for section_index, (first_index, items) in enumerate(sorted(section_items.items())):
        representative = sorted(
            items,
            key=lambda value: (
                abs(int(value["draw"]) - int(selected["draw"])),
                int(value["draw"]) > int(selected["draw"]),
                int(value["draw"]),
            ),
        )[0]
        role = "main" if int(first_index) == main_first_index else "secondary"
        section_id = f"{component_id}.section{section_index}"
        material_sections.append({
            "id": section_id,
            "role": role,
            "firstIndex": int(first_index),
            "indexCount": int(representative["indices"]),
            "draws": sorted(int(item["draw"]) for item in items),
            "representativeDraw": int(representative["draw"]),
            "vertexShader": representative.get("vs"),
            "pixelShader": representative.get("ps"),
            "textureKeyPrefix": component_id if role == "main" else section_id,
            "pixelShaders": sorted({item.get("ps") for item in items if item.get("ps")}),
        })

    layout = selected["layout"]
    vb0_hash = selected["vbHashes"].get("positionNormalTangent")
    vb1_hash = selected["vbHashes"].get("colorUv")
    component = {
        "id": component_id,
        "kind": "body",
        "source": "frame-analysis-runtime",
        "confidence": (
            "manual-draw-selected" if main_draw
            else "body-resource-vertex-selected" if expected_vertex_count
            else "auto-selected"
        ),
        "ibHash": selected.get("ibHash") or f"draw:{selected['draw']:06d}:ib",
        "vbHashes": {
            "positionNormalTangent": vb0_hash or f"draw:{selected['draw']:06d}:vb0",
            "colorUv": vb1_hash or f"draw:{selected['draw']:06d}:vb1",
        },
        "resourceFiles": selected["resourceFiles"],
        "vertices": selected["vertices"],
        "indices": selected["indices"],
        "mainFirstIndex": main_first_index,
        "tailFirstIndices": tail_first_indices,
        "materialSections": material_sections,
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
            "bodyResource": body_resource or "unknown",
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
            "firstIndex": int((item.get("drawCall") or {}).get("startIndex") or 0),
            "indexCount": item["indices"],
            "vertexCount": item["vertices"],
            "streams": {
                "ib": item.get("ibHash") or f"draw:{item['draw']:06d}:ib",
                "vb0": item["vbHashes"].get("positionNormalTangent") or f"draw:{item['draw']:06d}:vb0",
                "vb1": item["vbHashes"].get("colorUv") or f"draw:{item['draw']:06d}:vb1",
            },
            "streamFiles": item["resourceFiles"],
        }
    section_bindings = {}
    for section in material_sections:
        bindings = {}
        for item in sorted(
            section_items.get(int(section["firstIndex"]), []),
            key=lambda value: value["draw"],
        ):
            bindings[f"draw_{item['draw']:06d}"] = {
                "role": section["role"],
                "draw": item["draw"],
                "vertexShader": item.get("vs"),
                "pixelShader": item.get("ps"),
                "firstIndex": int((item.get("drawCall") or {}).get("startIndex") or 0),
                "indexCount": item["indices"],
                "vertexCount": item["vertices"],
                "streams": {
                    "ib": item.get("ibHash") or f"draw:{item['draw']:06d}:ib",
                    "vb0": item["vbHashes"].get("positionNormalTangent") or f"draw:{item['draw']:06d}:vb0",
                    "vb1": item["vbHashes"].get("colorUv") or f"draw:{item['draw']:06d}:vb1",
                },
                "streamFiles": item["resourceFiles"],
            }
        section_bindings[section["id"]] = {
            "role": section["role"],
            "firstIndex": section["firstIndex"],
            "indexCount": section["indexCount"],
            "representativeDraw": section["representativeDraw"],
            "passBindings": bindings,
        }
    drawcall_map = {
        "schemaVersion": 1,
        "capture": str(capture),
        "generatedFrom": capture.name,
        "components": {
            component_id: {
                "mainDraw": selected["draw"],
                "passBindings": passes,
                "sectionBindings": section_bindings,
            }
        },
    }

    textures = {}
    material_slots = []
    material_section_slots = []
    for section in material_sections:
        section_textures, slots = _section_texture_slots(
            resources,
            int(section["representativeDraw"]),
            component_id,
            section["textureKeyPrefix"],
        )
        for key, value in section_textures.items():
            value["pixelShader"] = value.get("pixelShader") or section.get("pixelShader")
            textures[key] = value
        section_entry = dict(section)
        section_entry["textureSlots"] = slots
        material_section_slots.append(section_entry)
        if section["role"] == "main":
            material_slots = slots
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
                "materialSections": material_section_slots,
                "note": "t0/t1/t4 语义按 Gakumas Body 模板命名；未识别槽位保留原 slot。",
            }
        },
    }
    report = {
        "ok": True,
        "captureDir": str(capture),
        "outputDir": str(output),
        "selected": selected,
        "expectedVertexCount": int(expected_vertex_count) if expected_vertex_count else None,
        "expectedVertexCounts": sorted({
            int(value)
            for value in (expected_vertex_counts or [])
            if value
        }),
        "bodyResourceHint": body_resource or None,
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


# 组件 → 资源库网格 JSON 名。库目录结构不变（每个 bundle 一个文件夹），
# 只是文件夹里的网格/骨架 JSON 按组件命名（Geo_Body.json / Geo_HairProp.json ...）。
_COMPONENT_MESH_NAMES = {
    "body": "Geo_Body",
    "hair": "Geo_Hair",
    "hairprop": "Geo_HairProp",
    "face": "Geo_Face",
}


def component_mesh_name(component_id):
    return _COMPONENT_MESH_NAMES.get(str(component_id or "body"), "Geo_Body")


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


def build_bone_name_hierarchy_template(json_dir):
    """Scan library skeleton sidecars → {boneNameHash: {"name", "parentHash"}}.

    Real Unity skeletons (from bodies that exported one) carry bone names + parent
    links keyed by a stable boneNameHash that is shared across characters for the
    common humanoid bones. Merging all available skeletons lets us give mesh-only
    bodies real bone names and a connected hierarchy for the bones they share.
    """
    template = {}
    root = Path(json_dir)
    if not root.is_dir():
        return template
    for body_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        # 库文件名按组件而异（Geo_Body/Geo_HairProp/...），骨架 sidecar 统一 *.skeleton.json
        skel_candidates = sorted(body_dir.glob("*.skeleton.json"))
        if not skel_candidates:
            continue
        skel_path = skel_candidates[0]
        try:
            nodes = load_json(skel_path).get("nodes", [])
        except Exception:
            continue
        for node in nodes:
            bone_hash = node.get("boneNameHash")
            if bone_hash is None or int(bone_hash) in template:
                continue
            # Nearest ancestor that is itself a hashed bone becomes the parent hash.
            parent_hash = None
            pidx = node.get("parent", -1)
            guard = 0
            while isinstance(pidx, int) and 0 <= pidx < len(nodes) and guard < 512:
                ph = nodes[pidx].get("boneNameHash")
                if ph is not None:
                    parent_hash = int(ph)
                    break
                pidx = nodes[pidx].get("parent", -1)
                guard += 1
            template[int(bone_hash)] = {
                "name": node.get("name") or f"bone_{int(bone_hash)}",
                "parentHash": parent_hash,
            }
    return template


def _synthesize_skeleton_from_mesh(mesh_json_path, template=None):
    """Build a skeleton sidecar from a Mesh JSON alone (no Unity SkinnedMeshRenderer).

    Bind transforms come from m_BindPose; bone identity from m_BoneNameHashes. If a
    hierarchy template is given (see build_bone_name_hierarchy_template), shared bones
    get their real name + parent so they form a connected standard skeleton; bones not
    in the template (costume-specific cloth bones) fall back to "bone_<hash>" under root.
    """
    mesh = load_json(Path(mesh_json_path))
    bind = mesh.get("m_BindPose") or []
    hashes = mesh.get("m_BoneNameHashes") or []
    bone_count = len(bind)
    template = template or {}

    # Our bone hash -> node list index (bones start at 1; root is node 0).
    hash_to_index = {}
    for i in range(bone_count):
        if i < len(hashes):
            hash_to_index[int(hashes[i])] = i + 1

    nodes = [{
        "name": "Root", "parent": -1, "weightedIndex": None,
        "localPosition": [0.0, 0.0, 0.0],
        "localRotation": [0.0, 0.0, 0.0, 1.0],
        "localScale": [1.0, 1.0, 1.0],
    }]
    named = 0
    for i in range(bone_count):
        bone_hash = int(hashes[i]) if i < len(hashes) else i
        info = template.get(bone_hash)
        name = info["name"] if info else f"bone_{bone_hash}"
        if info:
            named += 1
        # Climb template ancestors until one is also one of our bones → real parent.
        parent_index = 0
        ancestor = info.get("parentHash") if info else None
        guard = 0
        while ancestor is not None and guard < 512:
            if ancestor in hash_to_index:
                parent_index = hash_to_index[ancestor]
                break
            ancestor_info = template.get(ancestor)
            ancestor = ancestor_info.get("parentHash") if ancestor_info else None
            guard += 1
        nodes.append({
            "name": name,
            "parent": parent_index,
            "weightedIndex": i,
            "boneNameHash": bone_hash,
            "bindPose": bind[i],
        })
    return {
        "schemaVersion": 1,
        "synthetic": "mesh m_BindPose + m_BoneNameHashes; names/hierarchy from library skeletons by hash",
        "weightedBoneCount": bone_count,
        "namedBoneCount": named,
        "nodeCount": bone_count + 1,
        "nodes": nodes,
    }


def inverse_skin_config(profile, component_id):
    """Return per-component inverse-skin data, falling back to legacy single-component data."""
    component = component_by_id(profile, component_id)
    return component.get("inverseSkin") or (profile.get("skinning", {}) or {}).get("inverseSkin")


def resolve_profile_reference(profile_dir, component_id="body"):
    """Return a completed profile's own Reference Mesh/Skeleton, or None.

    After completion the profile is self-contained (Reference/ holds the real or
    synthesized skeleton). Import should prefer this over re-resolving the library.
    """
    profile_dir = Path(profile_dir)
    profile_path = profile_dir / "profile.json"
    if not profile_path.is_file():
        return None
    profile = load_json(profile_path)
    config = inverse_skin_config(profile, component_id) or {}
    mesh_rel, skel_rel = config.get("meshJson"), config.get("skeletonJson")
    if not mesh_rel or not skel_rel:
        return None
    mesh_path, skel_path = profile_dir / mesh_rel, profile_dir / skel_rel
    if not (mesh_path.is_file() and skel_path.is_file()):
        return None
    result = {
        "meshJson": str(mesh_path.resolve()),
        "skeletonJson": str(skel_path.resolve()),
        "body": profile.get("target", {}).get("bodyResource", ""),
        "match": "profile-reference",
    }
    try:
        result.update(_mesh_summary(mesh_path))
        result["body"] = result["body"] or profile.get("target", {}).get("bodyResource", "")
    except Exception:
        pass
    return result


def scan_body_json_library(json_dir, name_filter=None, mesh_name="Geo_Body"):
    """Scan an AssetStudio mesh JSON library. Includes mesh-only entries.

    mesh_name: which mesh JSON to look for in each bundle folder
    (Geo_Body / Geo_HairProp / ...); see component_mesh_name().

    name_filter: optional case-insensitive substring (e.g. a character code like
    "hmsz"); only folders whose name contains it are loaded. This both narrows
    matching to one character and avoids parsing the whole 500+ library every call.

    Entries without a valid skeleton sidecar are still returned (skeletonJson=None,
    hasSkeleton=False); completion synthesizes a skeleton from the mesh for them.
    """
    root = Path(json_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Body JSON 资源库目录不存在：{root}")

    filter_lower = name_filter.lower() if name_filter else None
    entries = []
    for body_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if filter_lower and filter_lower not in body_dir.name.lower():
            continue
        mesh_json = body_dir / f"{mesh_name}.json"
        if not mesh_json.is_file():
            continue
        try:
            summary = _mesh_summary(mesh_json)
        except Exception:
            continue
        skeleton_json = body_dir / f"{mesh_name}.skeleton.json"
        has_skeleton = _valid_skeleton_sidecar(skeleton_json)
        entries.append({
            "body": body_dir.name,
            "meshJson": str(mesh_json.resolve()),
            "skeletonJson": str(skeleton_json.resolve()) if has_skeleton else None,
            "hasSkeleton": has_skeleton,
            **summary,
        })
    return entries


def resolve_exact_body_json_entry(json_dir, body_resource, mesh_name="Geo_Body"):
    """Return one exact body entry from the JSON library, or None.

    This is used before frame-profile extraction: if the author already knows
    the exact body resource, its vertex count is a stronger signal than generic
    draw-size scoring.
    """
    body_resource = (body_resource or "").strip()
    if not body_resource or body_resource == "unknown":
        return None
    entries = scan_body_json_library(json_dir, name_filter=body_resource, mesh_name=mesh_name)
    exact = [entry for entry in entries if entry["body"] == body_resource]
    if len(exact) == 1:
        return dict(exact[0])
    return None


def body_json_vertex_hints(json_dir, body_resource, mesh_name="Geo_Body"):
    """Return candidate vertex counts from the body library for a user hint.

    A full body name should resolve to one exact mesh. A short actor code such as
    "shro" intentionally resolves to all matching bodies so frame extraction can
    choose the matching runtime draw before the later AssetStudio completion step.
    """
    body_resource = (body_resource or "").strip()
    if not body_resource or body_resource == "unknown":
        return {
            "bodyResource": body_resource,
            "entries": [],
            "vertexCounts": [],
            "exact": None,
        }
    entries = scan_body_json_library(json_dir, name_filter=body_resource, mesh_name=mesh_name)
    exact = [entry for entry in entries if entry["body"] == body_resource]
    pool = exact if len(exact) == 1 else entries
    return {
        "bodyResource": body_resource,
        "entries": [dict(entry) for entry in pool],
        "vertexCounts": sorted({int(entry["vertexCount"]) for entry in pool}),
        "exact": dict(exact[0]) if len(exact) == 1 else None,
    }


def _capture_vertex_counts(capture_dir):
    """Vertex counts of every drawable candidate in a FrameAnalysis dir."""
    capture = Path(capture_dir)
    if not capture.is_dir():
        return set()
    candidates = _build_frame_candidates(_scan_frame_resources(capture), _parse_frame_log(capture))
    return {int(item["vertices"]) for item in candidates if item.get("vertices")}


def _disambiguate_hair_by_hairprop(profile, pool):
    """Pick the hair candidate whose bundle's Geo_HairProp is drawn in the same
    capture. A shared base hair (same verts/indices) is bound to different
    skeletons per bundle → different inverse operator, so the paired hairprop
    (the crown/accessory the user captured) is the discriminant. Returns one
    entry, or None if it can't be uniquely resolved."""
    capture_dir = (profile.get("capture") or {}).get("directory") or ""
    if not capture_dir:
        return None
    present = _capture_vertex_counts(capture_dir)
    if not present:
        return None
    hits = []
    for entry in pool:
        prop_json = Path(entry["meshJson"]).with_name(f"{component_mesh_name('hairprop')}.json")
        if not prop_json.is_file():
            continue
        try:
            if int(_mesh_summary(prop_json)["vertexCount"]) in present:
                hits.append(entry)
        except Exception:
            continue
    return hits[0] if len({e["body"] for e in hits}) == 1 else None


def resolve_body_json_resource(profile_dir, json_dir, component_id="body"):
    """Resolve a profile component's Mesh/Skeleton JSON from its resource library."""
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    component = component_by_id(profile, component_id)

    # body_resource 既可填完整 body 名，也可只填角色代号(如 "hmsz")。它同时用作
    # 扫描过滤器：只加载名称含它的文件夹 —— 既消歧又避免每次解析整个 500+ 资源库。
    body_resource = (profile.get("target", {}) or {}).get("bodyResource") or ""
    if body_resource == "unknown":
        body_resource = ""
    name_filter = body_resource or None

    mesh_name = component_mesh_name(component_id)
    component_label = "发饰" if component_id == "hairprop" else "发型" if component_id == "hair" else "Body"
    entries = scan_body_json_library(json_dir, name_filter=name_filter, mesh_name=mesh_name)
    if not entries:
        if name_filter:
            raise ValueError(
                f"资源库里没有名称含「{name_filter}」且带 {mesh_name}.json 的条目，"
                "请检查角色代号或资源库目录。"
            )
        raise ValueError(f"{mesh_name} JSON 资源库没有可用样本：{json_dir}")

    # 顶点数 = 身体网格的可靠标识(整个 VB);索引数只作软偏好——游戏内主体 Draw 常
    # 不含次网格(牙齿/舌头等),其索引数会比 mesh 的 m_Indices 略少,所以不能要求相等。
    vertex_count = int(component.get("vertices") or 0)
    index_count = int(component.get("indices") or 0)

    # 完整 body 名精确命中优先。
    if body_resource:
        exact = [entry for entry in entries if entry["body"] == body_resource]
        if len(exact) == 1:
            if vertex_count and int(exact[0].get("vertexCount") or 0) != vertex_count:
                raise ValueError(
                    f"指定{component_label}资源 {body_resource} 是 {exact[0].get('vertexCount')} 顶点，"
                    f"但抓帧主{component_label}是 {vertex_count} 顶点。"
                    "请确认抓帧目标与网格 JSON 资源库对应，或清空「目标资源」后按顶点数自动匹配。"
                )
            result = dict(exact[0])
            result["match"] = "bodyResource"
            return result

    vmatches = [entry for entry in entries if entry["vertexCount"] == vertex_count]
    if not vmatches:
        scope = f"(已按「{name_filter}」过滤)" if name_filter else ""
        raise ValueError(
            f"资源库{scope}里没有 {vertex_count} 顶点的{component_label}。"
            "请确认抓帧目标与资源库是否对应。"
        )

    imatches = [entry for entry in vmatches if entry["indexCount"] == index_count]
    pool = imatches if imatches else vmatches
    label = ("char+" if name_filter else "") + ("vertex+index" if imatches else "vertex")

    if len(pool) == 1:
        result = dict(pool[0])
        result["match"] = label
        return result
    # 多个候选:bind pose 一致即等价(同款同体型),任取其一;否则需要更精确的名字。
    if len({entry.get("bindPoseSig") for entry in pool}) == 1:
        result = dict(pool[0])
        result["match"] = label + "(equivalent)"
        return result
    # 发型基础网格常被多套发型共用(同顶点/同索引),仅蒙皮骨架不同→逆算子不同。
    # 用抓帧里一起画出来的发饰(Geo_HairProp)顶点数选中正确的 bundle。
    if component_id == "hair":
        picked = _disambiguate_hair_by_hairprop(profile, pool)
        if picked is not None:
            result = dict(picked)
            result["match"] = label + "(hairprop)"
            return result
    names = ", ".join(entry["body"] for entry in pool[:12])
    suffix = " ..." if len(pool) > 12 else ""
    raise ValueError(
        f"{vertex_count} 顶点仍匹配到多个候选:\n{names}{suffix}\n"
        "请在「目标资源」填更精确的名字（角色代号不够时填完整资源名）。"
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
    for suffix in ("_body", "_hair", "_face"):
        if core_name.endswith(suffix):
            core_name = core_name[: -len(suffix)]
            break
    actor, _, costume = core_name.partition("-")
    return actor, costume


def complete_inverse_skin_profile(profile_dir, library_dir, component_id="body",
                                  ridge=1e-8, unobservable_weight_threshold=0.1,
                                  body_resource=None):
    """Upgrade a runtime-only frame profile into a complete inverse-skin profile.

    Matches the body Mesh/Skeleton JSON from the library (by recorded/overridden
    bodyResource, else by vertex count), copies them into the profile, builds the
    inverse operator and writes component.inverseSkin (legacy single-component profiles also
    mirror it to skinning.inverseSkin). Afterwards the profile carries
    (1) injection info, (2) structural data and (3) the operator.

    body_resource: optional exact library body name to disambiguate when several
    same-topology costumes (same vertex count, different idol) match.
    """
    profile_dir = Path(profile_dir)
    profile_path = profile_dir / "profile.json"
    profile = load_json(profile_path)
    component_by_id(profile, component_id)  # validate component exists

    # Caller-supplied override wins; written before resolve so exact-name match is used.
    if body_resource:
        profile.setdefault("target", {})["bodyResource"] = body_resource
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    resolved = resolve_body_json_resource(profile_dir, library_dir, component_id)

    # (2) Structural data: copy matched Mesh + Skeleton into the profile.
    reference_dir = profile_dir / "Reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    mesh_name = component_mesh_name(component_id)
    mesh_dst = reference_dir / f"{mesh_name}.json"
    skeleton_dst = reference_dir / f"{mesh_name}.skeleton.json"
    shutil.copy2(Path(resolved["meshJson"]), mesh_dst)
    skeleton_src = resolved.get("skeletonJson")
    if skeleton_src and Path(skeleton_src).is_file():
        shutil.copy2(Path(skeleton_src), skeleton_dst)
        bone_naming = "skeleton"
    else:
        # mesh-only：合成骨架；用资源库里有骨架的 body 按 hash 补真名+层级。
        template = build_bone_name_hierarchy_template(library_dir)
        synthetic = _synthesize_skeleton_from_mesh(mesh_dst, template=template)
        skeleton_dst.write_text(
            json.dumps(synthetic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        named = synthetic.get("namedBoneCount", 0)
        total = synthetic.get("weightedBoneCount", 0)
        bone_naming = f"boneNameHash(命名 {named}/{total})"

    # (3) Inverse operator from the bind mesh.
    operator_rel = f"Buffers/{component_id.title()}.InverseOperator.R32_FLOAT.buf"
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
    config = {
        "sourceVertexCount": operator_meta["vertexCount"],
        "weightedBoneCount": weighted_bone_count,
        "coefficientCount": operator_meta["coefficientCount"],
        "posedVertexStride": stride,
        "inverseOperator": operator_rel,
        "meshJson": f"Reference/{mesh_name}.json",
        "skeletonJson": f"Reference/{mesh_name}.skeleton.json",
        "boneNaming": bone_naming,
        "unobservableBones": unobservable,
    }
    component = component_by_id(profile, component_id)
    component["inverseSkin"] = config
    # Preserve compatibility with existing consumers of single-component profiles.
    if len(profile.get("components", [])) == 1:
        skinning["inverseSkin"] = config
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


def merge_profile_component(profile_dir, component_profile_dir, component_id):
    """Merge one completed component profile into a multi-component item profile."""
    profile_dir, source_dir = Path(profile_dir), Path(component_profile_dir)
    profile_path, source_path = profile_dir / "profile.json", source_dir / "profile.json"
    profile, source = load_json(profile_path), load_json(source_path)
    component = component_by_id(source, component_id)
    config = inverse_skin_config(source, component_id)
    if not config:
        raise ValueError(f"Component {component_id} has no inverse-skin data")

    legacy = (profile.get("skinning", {}) or {}).pop("inverseSkin", None)
    if legacy and len(profile.get("components", [])) == 1:
        profile["components"][0].setdefault("inverseSkin", legacy)

    component = json.loads(json.dumps(component))
    component["inverseSkin"] = json.loads(json.dumps(config))
    for key in ("meshJson", "skeletonJson", "inverseOperator"):
        src = source_dir / config[key]
        suffix = src.name.split(".", 1)[-1]
        folder = "Buffers" if key == "inverseOperator" else "Reference"
        name = f"{component_id.title()}.{suffix}" if key == "inverseOperator" else src.name
        dst = profile_dir / folder / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        component["inverseSkin"][key] = f"{folder}/{name}"

    profile["components"] = [c for c in profile.get("components", []) if c.get("id") != component_id]
    profile["components"].append(component)
    profile.setdefault("skinning", {})["status"] = "per-component inverse-skin operators"
    profile["status"] = "complete-inverse-skin"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for filename, field in (
        ("drawcall_map.json", "components"),
        ("texture_map.json", "textures"),
        ("material_map.json", "materials"),
    ):
        target_file, source_file = profile_dir / filename, source_dir / filename
        if not source_file.is_file():
            continue
        target = load_json(target_file) if target_file.is_file() else {"schemaVersion": 1, field: {}}
        target.setdefault(field, {}).update(load_json(source_file).get(field, {}))
        target_file.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return component


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


def _shader_check_overrides(section, component_id, drawcalls, extra_components=()):
    """为 body IB 关联的全部 VS 生成 ShaderOverride...checktextureoverride = ib。

    Buffer/IB 的 TextureOverride 只在挂了 checktextureoverride 的 ShaderOverride 上才会
    稳定执行 draw-time 替换。只覆盖部分 VS 会让另一些 pass 漏画原版 → 叠图。故收齐
    passBindings 里全部唯一 VS,每个都生成。
    """
    component_ids = [component_id, *extra_components]
    bindings = {}
    for current_id in component_ids:
        draw_component = drawcalls.get("components", {}).get(current_id, {})
        bindings.update(draw_component.get("passBindings", {}) or {})
        for section_data in (draw_component.get("sectionBindings", {}) or {}).values():
            for key, value in (section_data.get("passBindings", {}) or {}).items():
                bindings[f"{current_id}_section_{key}"] = value
    if not bindings:
        return ""
    seen = []
    for item in sorted(bindings.values(), key=lambda v: int(v.get("draw") or 0)):
        vs = item.get("vertexShader")
        if vs and vs not in seen:
            seen.append(vs)
    if not seen:
        return ""
    blocks = []
    for index, shader in enumerate(seen):
        blocks.append(
            f"[ShaderOverride{section}{component_id.title()}VS{index}]\n"
            f"hash = {shader}\n"
            "allow_duplicate_hash = true\n"
            "checktextureoverride = ib\n"
        )
    return "\n".join(blocks)


def _secondary_material_sections(component, drawcalls, component_id):
    draw_component = drawcalls.get("components", {}).get(component_id, {}) or {}
    by_id = {
        str(section.get("id")): dict(section)
        for section in component.get("materialSections", []) or []
        if section.get("id") and section.get("role") != "main"
    }
    for section_id, section_data in (draw_component.get("sectionBindings", {}) or {}).items():
        if section_data.get("role") == "main":
            continue
        entry = by_id.setdefault(str(section_id), {"id": str(section_id), "role": section_data.get("role", "secondary")})
        for key in ("firstIndex", "indexCount", "representativeDraw"):
            if key in section_data and key not in entry:
                entry[key] = section_data[key]
        if "passBindings" in section_data:
            entry["passBindings"] = section_data["passBindings"]
    return sorted(
        by_id.values(),
        key=lambda item: (
            int(item.get("firstIndex") or 0),
            str(item.get("id") or ""),
        ),
    )


def _select_native_co_section(component, drawcalls, component_id):
    sections = _secondary_material_sections(component, drawcalls, component_id)
    if not sections:
        raise ValueError(
            "当前 Profile 没有 secondary materialSections；无法使用原生 co 材质。"
            "请用包含 m_bdyco/第二材质段的 FrameAnalysis 重新生成配置档，"
            "或把该材质槽改回「不透明」走主 body 路径。"
        )
    return sections[0]


def _section_texture_slot(profile_set, section_id, semantic, fallback, pixel_shader=None):
    entry = _profile_material_texture_entry(profile_set, f"{section_id}.{semantic}")
    return _material_texture_slot(entry, fallback, pixel_shader=pixel_shader)


def _material_texture_slot(entry, fallback, pixel_shader=None):
    entry = entry or {}
    if pixel_shader:
        variants = entry.get("slotVariants") or {}
        slot = variants.get(str(pixel_shader).lower()) or variants.get(str(pixel_shader))
        if slot:
            return slot
    return entry.get("slot") or fallback


def _profile_material_texture_entry(profile_set, texture_key):
    """Return the runtime binding for a material texture key.

    Older extracted profiles mislabeled the t2 environment cubemap as
    shadeColor and left the real _ShadeMap/sdw texture under *.t4. For export,
    shadeColor must bind to ps-t4, so transparently migrate those profiles.
    """
    textures = profile_set.get("textures", {}).get("textures", {}) or {}
    entry = textures.get(texture_key)
    prefix, _, semantic = texture_key.rpartition(".")
    if semantic == "shadeColor":
        t4_entry = textures.get(f"{prefix}.t4")
        if t4_entry and t4_entry.get("slot") == "ps-t4":
            migrated = dict(t4_entry)
            migrated["semantic"] = "shadeColor"
            migrated["_migratedFrom"] = f"{prefix}.t4"
            return migrated
        if entry and entry.get("slot") != "ps-t4" and not entry.get("slotVariants"):
            migrated = dict(entry)
            migrated["slot"] = "ps-t4"
            migrated["_migratedFrom"] = texture_key
            return migrated
    return entry


# --- Runtime texture-slot layout auto-detect (replaces per-PS slot variants) ---
# The game repacks base/mask/shade into different ps-tN slots per lighting shader.
# Instead of enumerating pixel-shader hashes, detect the layout at draw time from a
# global body landmark texture (hash 0ff26bed) that the engine always binds:
#   landmark at ps-t2 -> layout A (base t0, mask t1, shade t4)
#   landmark at ps-t3 -> layout B (base t1, mask t2, shade t5)  <- only B moves base/mask
#   neither           -> layout C/unknown (base t0, mask t1, no custom shade) -- safe
# This needs no per-costume or per-scene shader hash and degrades gracefully.
GMI_BODY_LAYOUT_LANDMARK = "0ff26bed"


def _landmark_layout_sections(section, match_priority, reset_variable=None):
    """DetectLayout command list + the landmark probe TextureOverride (once per mod)."""
    reset_line = f"${reset_variable} = 0\n" if reset_variable else ""
    return (
        f"[CommandList{section}DetectLayout]\n"
        f"$gmi_{section}_layout = 0\n"
        f"$gmi_{section}_probe = 0\n"
        f"checktextureoverride = ps-t2\n"
        f"if $gmi_{section}_probe == 1\n"
        f"    $gmi_{section}_layout = 2\n"
        f"endif\n"
        f"$gmi_{section}_probe = 0\n"
        f"checktextureoverride = ps-t3\n"
        f"if $gmi_{section}_probe == 1\n"
        f"    $gmi_{section}_layout = 1\n"
        f"endif\n\n"
        f"[TextureOverride{section}BodyLayoutLandmark]\n"
        f"; fires when the global body landmark {GMI_BODY_LAYOUT_LANDMARK} is bound;\n"
        f"; DetectLayout reads its slot (ps-t2=A / ps-t3=B). match_priority disambiguates\n"
        f"; the shared hash when several body mods are installed.\n"
        f"hash = {GMI_BODY_LAYOUT_LANDMARK}\n"
        f"match_priority = {match_priority}\n"
        f"{reset_line}"
        f"$gmi_{section}_probe = 1\n"
    )


def _hairprop_selector(profile):
    """Return the hairprop draw signature used to select a shared hair base.

    A hair IB is commonly shared by several hairstyles.  The optional hairprop
    component is the discriminant when it has its own IB and main section.  The
    runtime matcher uses hash + firstIndex; indexCount is retained in the
    manifest for audit and future matcher upgrades.
    """
    if not isinstance(profile, dict):
        return None
    prop = component_by_id(profile, "hairprop")
    if not prop or not prop.get("ibHash"):
        return None
    first_index = prop.get("mainFirstIndex")
    if first_index is None:
        return None
    return {
        "component": "hairprop",
        "ibHash": str(prop["ibHash"]),
        "firstIndex": int(first_index),
        "indexCount": int(prop.get("indices") or 0),
    }


def _runtime_guard(section, body, selector_variable=None):
    """Wrap an override body in the package enable flag and optional selector."""
    body = textwrap.indent(body.strip("\n"), "    ")
    if selector_variable:
        body = (
            f"    if ${selector_variable} == 1\n"
            f"{textwrap.indent(body, '    ')}\n"
            "    endif"
        )
    return f"if $enable_{section}\n{body}\nendif"


def _landmark_binding_block(section, resources, indent="    "):
    """Per-section slot binding driven by $gmi_<section>_layout (see above)."""
    base = resources.get("baseColor")
    mask = resources.get("packedMask")
    shade = resources.get("shadeColor")
    out = [f"{indent}run = CommandList{section}DetectLayout"]
    # layout 0 = C / unknown: base+mask at t0/t1, no custom shade (safe fallback)
    out.append(f"{indent}if $gmi_{section}_layout == 0")
    if base:
        out.append(f"{indent}    ps-t0 = Resource{base}")
    if mask:
        out.append(f"{indent}    ps-t1 = Resource{mask}")
    out.append(f"{indent}endif")
    # layout 2 = A: t0/t1/t4
    out.append(f"{indent}if $gmi_{section}_layout == 2")
    if base:
        out.append(f"{indent}    ps-t0 = Resource{base}")
    if mask:
        out.append(f"{indent}    ps-t1 = Resource{mask}")
    if shade:
        out.append(f"{indent}    ps-t4 = Resource{shade}")
    out.append(f"{indent}endif")
    # layout 1 = B: t1/t2/t5
    out.append(f"{indent}if $gmi_{section}_layout == 1")
    if base:
        out.append(f"{indent}    ps-t1 = Resource{base}")
    if mask:
        out.append(f"{indent}    ps-t2 = Resource{mask}")
    if shade:
        out.append(f"{indent}    ps-t5 = Resource{shade}")
    out.append(f"{indent}endif")
    return "\n".join(out)


def _landmark_match_priority(ib_hash):
    """Stable per-costume priority from the IB hash so independently generated mods
    rarely collide on the shared landmark hash (0..65535)."""
    try:
        return int(str(ib_hash)[:8], 16) % 65536
    except (ValueError, TypeError):
        return 0


def _sanitize_package_id(value):
    """把用户填的模组标识规整成文件名/ini 安全的 token。

    自动小写、空格/下划线转连字符、去掉其它非法字符。纯单词(如 ppmmpp)即可，
    不强制带分隔符。
    """
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9.-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip(".-")
    if not text:
        raise ValueError("模组标识为空或全是非法字符，请用英文/数字命名（如 ppmmpp 或 test.hmsz）")
    return text


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_index_package(
    profile_dir, output_root, package_id, name, author, component_id, faces,
    vertex_count=None,
):
    package_id = _sanitize_package_id(package_id)
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
    # IB-only 触发：只按本服装唯一的 IB hash 匹配，不注册共享的 ShaderOverride，
    # 这样多个 body mod 共存也不会重复(IB hash 各不相同),且自动覆盖所有 pass。
    ini = f"""; Generated by GakumasMI Blender Add-on

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
    package_id = _sanitize_package_id(package_id)
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    entry = _profile_material_texture_entry(profile_set, texture_key)
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


def inverse_skin_bone_map(profile_dir, skeleton_json=None, component_id="body"):
    """Return weighted bone name -> matrix index for an inverse-skin Profile."""
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    config = inverse_skin_config(profile, component_id)
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


_FP16_MAX = 65504.0


def _safe_unorm8(value):
    v = float(value)
    if v != v:  # NaN
        return 0
    if v <= 0.0:
        return 0
    if v >= 1.0:
        return 255
    return max(0, min(255, round(v * 255.0)))


def _safe_float(value, default=0.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if v != v or v == float("inf") or v == float("-inf"):
        return float(default)
    return v


def _safe_half(value):
    """Clamp a float into the fp16-representable range so struct 'e' packing never
    overflows. Game VB1 UVs are fp16; out-of-range or non-finite values (corrupt /
    extra UV channels) are clamped instead of crashing the export."""
    v = _safe_float(value, 0.0)
    if v > _FP16_MAX:
        return _FP16_MAX
    if v < -_FP16_MAX:
        return -_FP16_MAX
    return v


def _validate_export_uv(value, label):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} 不是有效浮点数")
    if v != v or v == float("inf") or v == float("-inf"):
        raise ValueError(f"{label} 不是有效浮点数")
    if abs(v) > 8.0:
        raise ValueError(f"{label} 超出合理范围：{v}")
    return v


def _pack_inverse_skin_buffers(vertices, normals, tangents, uv0, uv1, colors,
                               faces, skin, expected_indices, materials=None):
    count = len(vertices)
    arrays = (normals, tangents, uv0, uv1, colors, skin)
    if not all(len(values) == count for values in arrays):
        raise ValueError("Inverse-skin vertex arrays have different lengths")
    if any(len(face) != 3 for face in faces):
        raise ValueError("Inverse-skin mesh must be triangulated")
    for face in faces:
        for index in face:
            if index < 0 or index >= count:
                raise ValueError("网格索引超出了导出顶点范围")
    # 按材质分组面,使每个材质的索引在 IB 中连续,从而导出为各自独立的 drawindexed。
    # 皮肤/衣服等不同材质不再在同一 draw 内共享屏幕 2x2 求导块,消除 atlas mip 在
    # 屏幕相邻处的跨材质渗色(裙角橙斑),与原版"分 draw"渲染结构一致。
    if materials and len(materials) == count:
        face_material = [int(materials[face[0]]) for face in faces]
    else:
        face_material = [0] * len(faces)
    order = sorted(range(len(faces)), key=lambda fi: face_material[fi])
    flat_indices = []
    draw_ranges = []  # [{"start": int, "count": int, "material": int}, ...]
    current_material = None
    range_start = 0
    for fi in order:
        material = face_material[fi]
        if material != current_material:
            if current_material is not None:
                draw_ranges.append({
                    "start": range_start,
                    "count": len(flat_indices) - range_start,
                    "material": current_material,
                })
            current_material = material
            range_start = len(flat_indices)
        flat_indices.extend(int(index) for index in faces[fi])
    if current_material is not None:
        draw_ranges.append({
            "start": range_start,
            "count": len(flat_indices) - range_start,
            "material": current_material,
        })

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
        rgba = [_safe_unorm8(channel) for channel in color]
        u0 = _validate_export_uv(tex0[0], "UV0.u")
        v0 = _validate_export_uv(tex0[1], "UV0.v")
        u1 = _validate_export_uv(tex1[0], "UV1.u")
        v1 = _validate_export_uv(tex1[1], "UV1.v")
        vb1.extend(struct.pack(
            "<4B4e", *rgba,
            _safe_half(u0), _safe_half(1.0 - v0),
            _safe_half(u1), _safe_half(1.0 - v1),
        ))
    if len(flat_indices) < expected_indices:
        flat_indices.extend([0] * (expected_indices - len(flat_indices)))
    max_index = max(flat_indices, default=0)
    if max_index > 0xFFFFFFFF:
        raise ValueError("网格索引超过 R32_UINT 上限")
    index_format = "R32_UINT" if max_index > 0xFFFF else "R16_UINT"
    pack_code = "I" if index_format == "R32_UINT" else "H"
    ib = struct.pack(f"<{len(flat_indices)}{pack_code}", *flat_indices)
    return bytes(bind), bytes(vb1), ib, draw_ranges, index_format


_COVER_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_COVER_MAX_BYTES = 2 * 1024 * 1024


def _prepare_cover(package_dir, cover_image):
    """校验预览图并复制进包，返回包内文件名。要求：存在、png/jpg/webp、≤2MB。"""
    value = str(cover_image or "").strip()
    if not value:
        raise ValueError("必须提供 mod 预览图（cover）：导出前在面板选择预览图。")
    src = Path(value)
    if not src.is_file():
        raise ValueError(f"预览图文件不存在：{src}")
    ext = src.suffix.lower()
    if ext not in _COVER_EXTS:
        raise ValueError(f"预览图格式不支持：{ext or '无扩展名'}（请用 png/jpg/webp）")
    size = src.stat().st_size
    if size > _COVER_MAX_BYTES:
        raise ValueError(
            f"预览图过大：{size / 1024 / 1024:.1f}MB，上限 2MB（建议 512–1024px、≤1MB）"
        )
    head = src.read_bytes()[:12]
    is_png = head.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpg = head.startswith(b"\xff\xd8\xff")
    is_webp = head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if not (is_png or is_jpg or is_webp):
        raise ValueError("预览图不是有效的 png/jpg/webp 文件")
    dest_name = "cover" + ext
    shutil.copyfile(src, Path(package_dir) / dest_name)
    return dest_name


def write_inverse_skin_package(
    profile_dir, output_root, package_id, name, author, component_id,
    vertices, normals, tangents, uv0, uv1, colors, faces, skin, corrections,
    material_textures=None, materials=None, alpha_modes=None, opacity_texture=None,
    native_co_textures=None, cover_image=None,
):
    """Write an arbitrary-topology, bone-weighted 3Dmigoto package."""
    package_id = _sanitize_package_id(package_id)
    profile_set = load_profile_set(profile_dir)
    profile = profile_set["profile"]
    component = component_by_id(profile, component_id)
    drawcalls = profile_set["drawcalls"]
    config = inverse_skin_config(profile, component_id)
    if not config:
        raise ValueError("Profile has no inverse-skin runtime data")
    expected_indices = int(component["indices"])
    bind, vb1, ib, draw_ranges, index_format = _pack_inverse_skin_buffers(
        vertices, normals, tangents, uv0, uv1, colors, faces, skin, expected_indices, materials
    )
    vertex_count = len(vertices)
    source_vertex_count = int(config["sourceVertexCount"])
    coefficient_count = int(config["coefficientCount"])
    material_textures = material_textures or {}
    opacity_texture = str(opacity_texture or "").strip()
    native_co_textures = dict(native_co_textures or {})
    if opacity_texture and not native_co_textures.get("baseColor"):
        native_co_textures["baseColor"] = opacity_texture
    # 只剩原生 co 一条透明路径：把第二材质段交给游戏原生 m_bdyco draw 上下文绘制。
    # 旧的镂空(ALPHA_CLIP)/半透明(ALPHA_BLEND)自建 pass 已整体移除。
    alpha_modes = {
        int(slot): "NATIVE_CO"
        for slot, mode in (alpha_modes or {}).items()
        if str(mode).upper() in {"NATIVE_CO", "NATIVE_SECTION", "CO"}
    }

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
    ib_buffer_name = f"Body.IB.{index_format}.buf"
    (buffer_dir / ib_buffer_name).write_bytes(ib)
    operator_source = (profile_set["root"] / config["inverseOperator"]).resolve()
    if not operator_source.is_file():
        raise FileNotFoundError(f"Inverse operator not found: {operator_source}")
    shutil.copy2(operator_source, buffer_dir / "InverseOperator.R32_FLOAT.buf")
    shader_root = Path(__file__).parent / "shaders"
    # RecoverMatricesCS 的 SOURCE_VERTEX_COUNT / COEFFICIENT_COUNT 必须按本配置档替换，
    # 否则会沿用 hski 的 17615/608，导致非 hski body 读错逆算子→恢复矩阵爆炸。
    recover_shader = (shader_root / "RecoverMatricesCS.hlsl").read_text(encoding="utf-8")
    recover_shader = recover_shader.replace(
        "#define SOURCE_VERTEX_COUNT 17615", f"#define SOURCE_VERTEX_COUNT {source_vertex_count}"
    ).replace(
        "#define COEFFICIENT_COUNT 608", f"#define COEFFICIENT_COUNT {coefficient_count}"
    )
    if f"SOURCE_VERTEX_COUNT {source_vertex_count}" not in recover_shader \
            or f"COEFFICIENT_COUNT {coefficient_count}" not in recover_shader:
        raise ValueError("RecoverMatricesCS 顶点数/系数替换失败，请检查着色器模板")
    (shader_dir / "RecoverMatricesCS.hlsl").write_text(recover_shader, encoding="utf-8")
    skin_shader = (shader_root / "SkinCustomCS.hlsl").read_text(encoding="utf-8")
    skin_shader = skin_shader.replace(
        "#define TARGET_VERTEX_COUNT 1", f"#define TARGET_VERTEX_COUNT {vertex_count}"
    )
    (shader_dir / "SkinCustomCS.hlsl").write_text(skin_shader, encoding="utf-8")
    native_co_ranges = []
    for item in draw_ranges:
        if alpha_modes.get(int(item["material"]), "OPAQUE") == "NATIVE_CO":
            native_co_ranges.append({
                "start": int(item["start"]),
                "count": int(item["count"]),
                "material": int(item["material"]),
                "mode": "NATIVE_CO",
            })
    if native_co_ranges and not native_co_textures.get("baseColor"):
        raise ValueError("原生 co 材质需要单独的透明材质 t0 / m_bdyco；不会回退基础色 t0")
    section = _safe_section(package_id)
    material_bindings = []
    material_resources = []
    material_manifest = {}
    material_resource_names = {}
    native_co_section = None
    native_section_id = None
    if native_co_ranges:
        native_co_section = _select_native_co_section(component, drawcalls, component_id)
        native_section_id = str(native_co_section.get("id") or f"{component_id}.section1")
    if material_textures:
        texture_dir.mkdir(parents=True, exist_ok=True)
    for texture_key, source_file in material_textures.items():
        entry = _profile_material_texture_entry(profile_set, texture_key)
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
        if entry.get("format") and not _dds_formats_compatible(entry["format"], description["format"]):
            raise ValueError(
                f"{texture_key} must be {entry['format']}, got {description['format']}"
            )
        texture_component, semantic = texture_key.split(".", 1)
        if texture_component != component_id:
            raise ValueError(f"Texture {texture_key} does not belong to {component_id}")
        resource_name = f"{section}{semantic.title()}"
        material_resource_names[semantic] = resource_name
        filename = f"{component_id.title()}.{semantic[0].upper() + semantic[1:]}.dds"
        shutil.copy2(source, texture_dir / filename)
        material_resources.append(
            f"[Resource{resource_name}]\nfilename = Textures\\{filename}\n"
        )
        material_manifest[texture_key] = {
            "slot": entry["slot"], "hash": entry["hash"], "file": f"Textures/{filename}"
        }
    opacity_manifest = None
    native_co_resource_names = {}

    def add_native_co_resource(semantic, source_file=None, neutral_rgba=None, srgb=False):
        if semantic in native_co_resource_names:
            return native_co_resource_names[semantic]
        texture_dir.mkdir(parents=True, exist_ok=True)
        resource_name = f"{section}NativeCo{semantic.title()}"
        if source_file:
            source = Path(source_file)
            if not source.is_file() or source.suffix.lower() != ".dds":
                raise ValueError(f"Native co {semantic} texture must be an existing DDS: {source}")
            entry = _profile_material_texture_entry(profile_set, f"{native_section_id}.{semantic}") or {}
            description = inspect_dds(source)
            expected_size = entry.get("size")
            if expected_size and [description["width"], description["height"]] != expected_size:
                raise ValueError(
                    f"{native_section_id}.{semantic} must be {expected_size[0]}x{expected_size[1]}, got "
                    f"{description['width']}x{description['height']}"
                )
            if entry.get("format") and not _dds_formats_compatible(entry["format"], description["format"]):
                raise ValueError(
                    f"{native_section_id}.{semantic} must be {entry['format']}, got {description['format']}"
                )
            filename = f"{component_id.title()}.NativeCo.{semantic[0].upper() + semantic[1:]}.dds"
            shutil.copy2(source, texture_dir / filename)
            material_manifest[f"{native_section_id}.{semantic}"] = {
                "slot": entry.get("slot"),
                "hash": entry.get("hash"),
                "file": f"Textures/{filename}",
            }
        else:
            filename = f"{component_id.title()}.NativeCo.{semantic[0].upper() + semantic[1:]}.Neutral.dds"
            write_solid_rgba8_dds(texture_dir / filename, neutral_rgba, srgb=srgb)
            material_manifest[f"{native_section_id}.{semantic}"] = {
                "slot": None,
                "hash": None,
                "file": f"Textures/{filename}",
                "generated": "neutral",
            }
        native_co_resource_names[semantic] = resource_name
        material_resources.append(
            f"[Resource{resource_name}]\nfilename = Textures\\{filename}\n"
        )
        return resource_name

    def ensure_material_resource(semantic, neutral_rgba, srgb=False):
        resource_name = material_resource_names.get(semantic)
        if resource_name:
            return resource_name
        texture_dir.mkdir(parents=True, exist_ok=True)
        resource_name = f"{section}{semantic.title()}"
        filename = f"{component_id.title()}.{semantic[0].upper() + semantic[1:]}.Neutral.dds"
        write_solid_rgba8_dds(texture_dir / filename, neutral_rgba, srgb=srgb)
        material_resource_names[semantic] = resource_name
        material_resources.append(
            f"[Resource{resource_name}]\nfilename = Textures\\{filename}\n"
        )
        material_manifest[f"{component_id}.{semantic}"] = {
            "slot": None,
            "hash": None,
            "file": f"Textures/{filename}",
            "generated": "neutral",
        }
        return resource_name

    dispatch_matrices = coefficient_count
    dispatch_vertices = (vertex_count + 63) // 64
    hairprop_selector = _hairprop_selector(profile) if component_id == "hair" else None
    selector_variable = f"gmi_{section}_hairprop_match" if hairprop_selector else None
    extra_shader_components = ("hairprop",) if hairprop_selector else ()
    shader_check_blocks = [
        _shader_check_overrides(
            section, component_id, drawcalls, extra_components=extra_shader_components
        )
    ]
    if not shader_check_blocks[0]:
        raise ValueError("Profile drawcall_map 没有可用于 checktextureoverride 的 VS pass")
    landmark_priority = _landmark_match_priority(component['ibHash'])
    # 注意:landmark 不再重置 hairprop_match(reset_variable=None)。landmark 是 body draw,
    # 夹在皇冠和发型 draw 之间清零会让发型主 pass 漏替换。改由 [Present] 每帧末重置。
    landmark_sections = _landmark_layout_sections(
        section, landmark_priority, reset_variable=None
    )
    # 共享发型选择器:配套发饰的主 draw 出现即置 latch=1,发型只在戴该发饰时替换;
    # 每帧末由 [Present] 清零。合并成完整包时,这个 HairpropSelector 块会被 merge 删掉、
    # 把置位语句注入发饰自己的同 hash TextureOverride——本 3DMigoto 分支的 TextureOverride
    # 不认 allow_duplicate_hash,同 hash 两个 override 会互相覆盖。单独导出发型时此块照常生效。
    selector_block = ""
    if hairprop_selector:
        selector_block = f"""
[Present]
${selector_variable} = 0

[TextureOverride{section}HairpropSelector]
hash = {hairprop_selector['ibHash']}
match_first_index = {hairprop_selector['firstIndex']}
${selector_variable} = 1
"""
    material_bindings = _landmark_binding_block(section, material_resource_names)
    # 主体段可能不在 IB 偏移 0(随服装而变),原版 draw 用其 StartIndex 采我们从 0 起的
    # 自定义 IB 会越界 → 跳过原 draw、用 drawindexed 从 0 画满整网格。
    main_first_index = int(component.get("mainFirstIndex") or 0)
    body_index_count = int(component.get("indices") or 0)
    body_title = component_id.title()
    # 每材质一段 drawindexed:切断跨材质屏幕求导,消除 atlas mip 渗色(裙角橙斑)。
    # 原生 co 材质段从主 body draw 移出,交给 NativeCo override 在游戏原生第二材质段绘制。
    opaque_ranges = [
        item for item in draw_ranges
        if int(item["material"]) not in alpha_modes
    ]
    if opaque_ranges:
        drawindexed_lines = "\n".join(
            f"    drawindexed = {int(item['count'])}, {int(item['start'])}, 0"
            for item in opaque_ranges
        )
    else:
        drawindexed_lines = "    ; no opaque material ranges"
    packed_mask_resource = None
    shade_color_resource = None
    native_co_first_indices = set()
    native_co_override = ""
    if native_co_ranges:
        native_co_first_indices.add(int(native_co_section.get("firstIndex") or 0))
        opacity_resource = add_native_co_resource("baseColor", native_co_textures.get("baseColor"), srgb=True)
        opacity_manifest = material_manifest.get(f"{native_section_id}.baseColor")
        packed_mask_resource = add_native_co_resource(
            "packedMask",
            native_co_textures.get("packedMask"),
            neutral_rgba=NEUTRAL_PACKED_MASK,
            srgb=False,
        )
        shade_color_resource = add_native_co_resource(
            "shadeColor",
            native_co_textures.get("shadeColor"),
            neutral_rgba=NEUTRAL_SHADE_COLOR,
            srgb=False,
        )
        native_first_index = int(native_co_section.get("firstIndex") or 0)
        native_draws = native_co_section.get("draws") or []
        native_resources = {
            "baseColor": opacity_resource,
            "packedMask": packed_mask_resource,
            "shadeColor": shade_color_resource,
        }
        native_bindings = _landmark_binding_block(section, native_resources)
        native_drawindexed_lines = "\n".join(
            f"    drawindexed = {int(item['count'])}, {int(item['start'])}, 0"
            for item in native_co_ranges
        )
        native_body = f"""
    Resource{section}PosedVB = copy vb0
    run = CustomShader{section}RecoverMatrices
    run = CustomShader{section}SkinCustom
    Resource{section}SkinnedVBIA = copy Resource{section}SkinnedVB
    vb0 = Resource{section}SkinnedVBIA
    vb1 = Resource{section}VB1
    vb3 = Resource{section}SkinnedVBIA
    ib = Resource{section}IB
{native_bindings}
{native_drawindexed_lines}
    handling = skip
"""
        native_co_override = f"""
[TextureOverride{section}{body_title}NativeCo]
hash = {component['ibHash']}
match_first_index = {native_first_index}
{_runtime_guard(section, native_body, selector_variable)}
; native co section: {native_section_id}; source draws: {native_draws}
"""
    tail_skips = ""
    for tail_index, first_index in enumerate(component.get("tailFirstIndices") or []):
        if int(first_index) in native_co_first_indices:
            continue
        tail_skips += (
            f"\n[TextureOverride{section}{body_title}Tail{tail_index}]\n"
            f"hash = {component['ibHash']}\n"
            f"match_first_index = {first_index}\n"
            f"{_runtime_guard(section, 'handling = skip', selector_variable)}\n"
        )
    # Buffer TextureOverride 需要由相关 ShaderOverride 显式 checktextureoverride。
    # 只登记 IB hash 会显示 resource matched，但不会稳定执行 draw-time 替换。
    shader_checks = "\n".join(block for block in shader_check_blocks if block)
    ini = f"""; Generated by GakumasMI Blender Add-on (inverse-skin weighted mesh)

[Constants]
global $enable_{section} = 1
global $gmi_{section}_layout = 0
global $gmi_{section}_probe = 0
{f"global ${selector_variable} = 0" if selector_variable else ""}

{landmark_sections}
{shader_checks}
{selector_block}

[TextureOverride{section}{component_id.title()}]
hash = {component['ibHash']}
match_first_index = {main_first_index}
{_runtime_guard(section, f'''Resource{section}PosedVB = copy vb0
run = CustomShader{section}RecoverMatrices
run = CustomShader{section}SkinCustom
Resource{section}SkinnedVBIA = copy Resource{section}SkinnedVB
vb0 = Resource{section}SkinnedVBIA
vb1 = Resource{section}VB1
vb3 = Resource{section}SkinnedVBIA
ib = Resource{section}IB
{material_bindings}
{drawindexed_lines}
handling = skip''', selector_variable)}
{tail_skips}
{native_co_override}

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
format = DXGI_FORMAT_{index_format}
filename = Buffers\\{ib_buffer_name}

{chr(10).join(material_resources)}
"""
    (package_dir / "mod.ini").write_text(ini, encoding="utf-8")
    target = profile["target"]
    cover_name = _prepare_cover(package_dir, cover_image)
    # 目标改成被替换的游戏内模型资源名（如 mdl_chr_hski-cstm-0000_body），
    # 让用户直接看到本 mod 替换了游戏里的哪个 body/hair/face。缺资源名时回退到旧语义。
    if component_id == "hair":
        replaced_resource = target.get("hairResource") or target.get("bodyResource")
    elif component_id == "hairprop":
        replaced_resource = target.get("hairResource") or target.get("bodyResource")
    else:
        resource_field = {"body": "bodyResource", "face": "faceResource"}.get(component_id)
        replaced_resource = target.get(resource_field) if resource_field else None
    replaced_resource = replaced_resource or f"{component_id}.weightedMesh"
    runtime_selector = dict(hairprop_selector) if hairprop_selector else None
    manifest = {
        "schemaVersion": 2,
        "id": package_id,
        "name": name,
        "version": "0.1.0",
        "author": author,
        "type": "inverse-skin-mesh-replacement",
        "profile": profile["id"],
        "targets": [replaced_resource],
        "cover": cover_name,
        "components": [component_id],
        "conflicts": [
            f"{target['actorId']}.{target['costumeId']}.hair.bundle"
            if runtime_selector and component_id == "hair"
            else f"{target['actorId']}.{target['costumeId']}.{component_id}.mesh"
        ],
        "runtime": "3dmigoto-compute",
        "vertexCount": vertex_count,
        "indexCount": len(faces) * 3,
        "indexFormat": index_format,
        "status": "draft",
        "materials": material_manifest,
        "opacityTexture": opacity_manifest,
        "alphaModes": {str(slot): mode for slot, mode in sorted(alpha_modes.items())},
        "nativeCoRanges": native_co_ranges,
        "nativeCoSection": native_co_section,
        "transparencyStrategy": "native-co-section-only",
    }
    if runtime_selector:
        manifest["runtimeSelector"] = runtime_selector
    _write_json(package_dir / "manifest.json", manifest)
    (package_dir / "README.md").write_text(
        f"# {name}\n\nInverse-skin weighted Body mesh for Profile `{profile['id']}`.\n",
        encoding="utf-8",
    )
    return package_dir


def merge_inverse_skin_packages(
    hair_package, hairprop_package, output_root, package_id, name, author,
):
    """Merge the two author meshes into one complete hair package.

    The profile remains multi-component internally, but the published package
    owns both draw overrides.  Prop filenames are prefixed to avoid the two
    component exports clobbering each other's Body/Shader resources.
    """
    hair_package = Path(hair_package)
    hairprop_package = Path(hairprop_package)
    if not hair_package.is_dir() or not hairprop_package.is_dir():
        raise FileNotFoundError("完整发型包需要 hair 和 hairprop 两个已导出的组件包")
    hair_manifest = json.loads((hair_package / "manifest.json").read_text(encoding="utf-8"))
    prop_manifest = json.loads((hairprop_package / "manifest.json").read_text(encoding="utf-8"))
    selector = hair_manifest.get("runtimeSelector")
    if not selector or selector.get("component") != "hairprop":
        raise ValueError("hair 组件包缺少 hairprop runtimeSelector，拒绝生成会误替换的完整包")

    package_dir = Path(output_root) / _sanitize_package_id(package_id)
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.copytree(hair_package, package_dir)

    for source in hairprop_package.rglob("*"):
        if not source.is_file() or source.name in {"manifest.json", "mod.ini", "README.md", "export-report.json", "cover.png"}:
            continue
        rel = source.relative_to(hairprop_package)
        if rel.parts[0] in {"Buffers", "Shaders"}:
            rel = rel.with_name(f"Hairprop.{rel.name}")
        destination = package_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    prop_blocks = re.split(
        r"(?=^\[)",
        (hairprop_package / "mod.ini").read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    # 发饰的 [ShaderOverride] 丢弃(与发型同 shader-hash,发型包已顺带 check 发饰资源);
    # 但 [Constants] 里的 global 声明必须保留——发饰段的 $enable_/$..._layout/$..._probe
    # 被别的 block 引用,整块删掉会导致运行时"未声明标识符"。把它们并进发型 [Constants]。
    prop_globals = [
        line
        for block in prop_blocks if block.startswith("[Constants]")
        for line in block.splitlines() if line.strip().startswith("global $")
    ]
    prop_blocks = [
        block for block in prop_blocks
        if block and not block.startswith("[Constants]") and not block.startswith("[ShaderOverride")
    ]
    prop_ini = "\n".join(prop_blocks)
    prop_ini = re.sub(r"Buffers\\([^\r\n]+)", r"Buffers\\Hairprop.\1", prop_ini)
    prop_ini = re.sub(r"Shaders\\([^\r\n]+)", r"Shaders\\Hairprop.\1", prop_ini)
    hair_ini = (package_dir / "mod.ini").read_text(encoding="utf-8")
    if prop_globals:
        hair_ini = hair_ini.replace(
            "[Constants]\n", "[Constants]\n" + "\n".join(prop_globals) + "\n", 1
        )
    # 发型选择:删掉发型 ini 里独立的 HairpropSelector 块(它和发饰 override 挂同一 hash,
    # 本分支不支持 allow_duplicate_hash,并存会互相覆盖),把 match=1 注入发饰自己的同 hash
    # 主 override。发型只在该发饰主 draw 出现时替换;清零仍由发型 ini 的 [Present] 负责。
    sel_var = re.search(r"\$(gmi_\w+_hairprop_match)\b", hair_ini)
    if sel_var:
        hair_ini = re.sub(
            r"\n\[TextureOverride\w*HairpropSelector\][^\[]*", "\n", hair_ini
        )
        anchor = (
            f"hash = {selector['ibHash']}\n"
            f"match_first_index = {int(selector['firstIndex'])}\n"
        )
        injected, n = re.subn(
            re.escape(anchor),
            anchor + f"${sel_var.group(1)} = 1\n",
            prop_ini,
            count=1,
        )
        if n != 1:
            raise ValueError("合并失败:发饰包里找不到可注入发型选择标志的主 override")
        prop_ini = injected
    (package_dir / "mod.ini").write_text(hair_ini.rstrip() + "\n\n" + prop_ini.lstrip(), encoding="utf-8")

    manifest = dict(hair_manifest)
    manifest.update({
        "id": _sanitize_package_id(package_id),
        "name": name,
        "author": author,
        "components": ["hair", "hairprop"],
        "materials": {**hair_manifest.get("materials", {}), **prop_manifest.get("materials", {})},
        "componentStats": {
            "hair": {
                "vertexCount": hair_manifest.get("vertexCount", 0),
                "indexCount": hair_manifest.get("indexCount", 0),
            },
            "hairprop": {
                "vertexCount": prop_manifest.get("vertexCount", 0),
                "indexCount": prop_manifest.get("indexCount", 0),
            },
        },
        "runtimeSelector": selector,
        "conflicts": [f"{selector.get('actorId', '')}.{selector.get('costumeId', '')}.hair.bundle"]
        if selector.get("actorId") and selector.get("costumeId")
        else hair_manifest.get("conflicts", []),
    })
    _write_json(package_dir / "manifest.json", manifest)
    def _read_report(package):
        report = package / "export-report.json"
        return json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None

    _write_json(package_dir / "export-report.json", {
        "merge": {
            "components": ["hair", "hairprop"],
            "selector": selector,
            "sourcePackages": [hair_manifest.get("id"), prop_manifest.get("id")],
        },
        "hair": _read_report(hair_package),
        "hairprop": _read_report(hairprop_package),
    })
    (package_dir / "README.md").write_text(
        f"# {name}\n\n这是一个完整发型包，包含 `Geo_Hair` 与 `Geo_HairProp`，两部分必须一起启用。\n"
        f"发型只在 hairprop selector `{selector['ibHash']}@{selector['firstIndex']}` 命中时替换。\n",
        encoding="utf-8",
    )
    return package_dir
