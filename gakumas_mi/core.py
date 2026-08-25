"""Blender-independent Profile, buffer, validation and package helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import struct
import textwrap
from pathlib import Path

AB_RUNTIME_PROTOCOL = 1
AB_CODE_MARKER = "ab-export-20260727"


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


def read_rgba8_dds(path):
    """Read the top-down RGBA8 DDS emitted by write_rgba8_dds()."""
    raw = Path(path).read_bytes()
    if len(raw) < 148 or raw[:4] != b"DDS ":
        raise ValueError(f"Not a GMI RGBA8 DDS file: {path}")
    height, width = struct.unpack_from("<2I", raw, 12)
    if raw[84:88] != b"DX10":
        raise ValueError(f"DDS must use a DX10 header: {path}")
    dxgi_format, dimension, _misc, array_size, _misc2 = struct.unpack_from(
        "<5I", raw, 128
    )
    if dxgi_format not in (28, 29) or dimension != 3 or array_size != 1:
        raise ValueError(f"DDS is not an uncompressed RGBA8 texture: {path}")
    size = width * height * 4
    pixels = raw[148:]
    if not width or not height or len(pixels) != size:
        raise ValueError(f"DDS RGBA8 数据长度无效：{path}")
    return width, height, pixels


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


# 原版身体 albedo 的皮肤色。实测跨角色是同一个常数：atbm/hmsz/fktn/jsna 共 16 套服装、
# 58,651 个皮肤顶点，4 级量化众数只在 (254,230,218) 与 (254,234,218) 之间摆动，即一个
# 量化桶以内。每角色的肤色差异走 _RampMap（t_chr_<角色>-base-0000_rmp），不在 albedo 上，
# 所以这里不需要按角色查表。
VANILLA_SKIN_TONE = (254, 230, 218)
SKIN_TONE_QUANT = 4


def dominant_tone(rgb8, quant=SKIN_TONE_QUANT):
    """一组 RGB 采样的主色调 = 按 quant 级量化后的众数。

    不能用均值：皮肤区里画进了阴影/AO 细节，均值会被拖到肤色以下约 28 级
    （原版 atbm 皮肤众数 (254,230,218)，同一批采样的均值只有 (226,206,199)）。
    按均值对齐会把整块皮肤压暗并去饱和。
    """
    import numpy as np
    a = np.asarray(rgb8).reshape(-1, 3).astype(np.int64) // quant
    key = (a[:, 0] << 32) | (a[:, 1] << 16) | a[:, 2]
    values, counts = np.unique(key, return_counts=True)
    top = values[counts.argmax()]
    half = quant // 2
    return np.array([((top >> 32) & 0xFFFF) * quant + half,
                     ((top >> 16) & 0xFFFF) * quant + half,
                     (top & 0xFFFF) * quant + half], dtype=np.float32)


def calibrate_skin_tone(base_rgba8, area_mask, sample_rgb,
                        target=VANILLA_SKIN_TONE, iterations=10, tolerance=0.01):
    """把 base 的皮肤区在线性光下整体缩放，使其主色调对齐原版肤色。

    sample_rgb  决定「当前肤色是多少」，必须按网格 UV 采样——目标常数就是这么测的。
                面积统计不行：面积众数会被图集布局和留白带偏，同角色不同服装能差 60 级。
    area_mask   决定「改哪些 texel」，用光栅化后的皮肤区（含 dilate 外扩），这样 UV 缝隙
                和外扩填充跟着一起校准，不会在岛边留下色阶。

    只缩放 RGB，alpha 不动（body t0.A 是不透明、hair t0.A 是发丝覆盖率，都不该被动）。
    返回 (新 base_rgba8, 报告 dict)。
    """
    import numpy as np
    target = np.asarray(target, dtype=np.float32)
    before = dominant_tone(sample_rgb)
    # 量化众数对全黑返回的是桶中心而不是 0，所以不能拿 >0 当判据。近黑的采样说明这块
    # 根本不是皮肤（材质类型标错、或 UV 落在空白区），此时缩放比会炸到几百倍。
    if before.max() < 2 * SKIN_TONE_QUANT:
        return base_rgba8, {"calibrated": False,
                            "reason": f"皮肤采样近黑 {before.round(0).tolist()}，材质类型可能标错"}

    rgb = base_rgba8[..., :3].astype(np.float32) / 255.0
    sample = np.asarray(sample_rgb, dtype=np.float32).reshape(-1, 3) / 255.0
    ratio = _srgb_to_linear(target / 255.0) / np.maximum(_srgb_to_linear(before / 255.0), 1e-6)
    for _ in range(iterations):
        scaled_sample = _linear_to_srgb(np.clip(_srgb_to_linear(sample) * ratio, 0.0, 1.0))
        current = dominant_tone(scaled_sample * 255.0)
        if np.abs(target / np.maximum(current, 1e-5) - 1.0).max() < tolerance:
            break
        ratio = ratio * (_srgb_to_linear(target / 255.0)
                         / np.maximum(_srgb_to_linear(np.maximum(current, 1.0) / 255.0), 1e-6))

    out = base_rgba8.copy()
    scaled = _linear_to_srgb(np.clip(_srgb_to_linear(rgb) * ratio, 0.0, 1.0))
    out[area_mask, :3] = np.clip(scaled[area_mask] * 255.0 + 0.5, 0, 255).astype(np.uint8)
    after = dominant_tone(out[area_mask][:, :3] if area_mask.any() else out[..., :3])
    return out, {
        "calibrated": True,
        "before": before.round(1).tolist(),
        "after": after.round(1).tolist(),
        "target": target.tolist(),
        "texels": int(area_mask.sum()),
    }


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


def outline_nibbles_from_base(br, bg, bb, gain=1.0):
    """把顶点基础色编码成描边色 nibble (R高, R低, G高)，各 0..15。

    曲线实测自 saki body draw227 + 0628outfit：R 随基础 R 明显上升(亮处 ~4/15)，
    G/B 偏低(~1-2/15) —— 暗/中性面得暗灰线，亮/米面偏暖，肤色偏棕。
    """
    def _nib(value):
        return max(0, min(15, int(round(value))))

    br = min(1.0, max(0.0, float(br)))
    bg = min(1.0, max(0.0, float(bg)))
    bb = min(1.0, max(0.0, float(bb)))
    r_high = _nib(gain * 5.0 * br ** 2.7)
    r_low = _nib(gain * 1.50 * bg ** 0.41)
    g_high = _nib(gain * 1.50 * bb ** 0.86)
    # 三条曲线陡度差太大，中暗底色(0.11~0.42)会掉通道：R(指数2.7)先归零，只剩 G/B
    # → (0,1,1) 青边 或 (0,1,0) 绿边。而抓帧实测原版是「所有通道有 ~1/15 底，永远是
    # 暗灰线」(中等亮度 base 0.4-0.6 三通道 nibble 都≈1)。所以只要不是纯黑面，三通道
    # 一起抬到至少 1，回到中性暗灰；亮部曲线不受影响(本来就都 ≥1)。
    if r_high or r_low or g_high:
        r_high, r_low, g_high = max(1, r_high), max(1, r_low), max(1, g_high)
    return r_high, r_low, g_high


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
            "localPosition": [0.0, 0.0, 0.0],
            "localRotation": [0.0, 0.0, 0.0, 1.0],
            "localScale": [1.0, 1.0, 1.0],
        })
    return {
        "schemaVersion": 1,
        "synthetic": "mesh m_BindPose + m_BoneNameHashes; names/hierarchy from library skeletons by hash",
        "weightedBoneCount": bone_count,
        "namedBoneCount": named,
        "nodeCount": bone_count + 1,
        "nodes": nodes,
    }


def _bundle_bone_order(skeleton):
    """Return topological weighted bones and the old mesh-index remap."""
    nodes = skeleton.get("nodes") or []
    weighted = []
    old_to_node = {}
    for node_index, node in enumerate(nodes):
        if node.get("weightedIndex") is None:
            continue
        old_index = int(node["weightedIndex"])
        if old_index in old_to_node:
            raise ValueError(f"骨架 weightedIndex 重复：{old_index}")
        old_to_node[old_index] = node_index
        weighted.append((node_index, node, old_index))
    if not weighted:
        raise ValueError("骨架没有可打包的 weighted bone")

    def parent_weighted_index(node_index):
        parent = int(nodes[node_index].get("parent", -1))
        visited = set()
        while 0 <= parent < len(nodes) and parent not in visited:
            visited.add(parent)
            parent_node = nodes[parent]
            if parent_node.get("weightedIndex") is not None:
                return int(parent_node["weightedIndex"])
            parent = int(parent_node.get("parent", -1))
        return None

    parent_by_old = {
        old_index: parent_weighted_index(node_index)
        for node_index, _node, old_index in weighted
    }
    pending = {node_index for node_index, _node, _old_index in weighted}
    ordered = []
    while pending:
        progressed = False
        for node_index, node, old_index in weighted:
            if node_index not in pending:
                continue
            parent_old = parent_by_old[old_index]
            parent_node = old_to_node.get(parent_old) if parent_old is not None else None
            if parent_node is None or parent_node not in pending:
                ordered.append((node, old_index, parent_old))
                pending.remove(node_index)
                progressed = True
        if not progressed:
            raise ValueError("骨架父子关系存在循环，无法生成 sidecar 顺序")

    old_to_new = {old_index: index for index, (_node, old_index, _parent) in enumerate(ordered)}
    bones = []
    for index, (node, old_index, parent_old) in enumerate(ordered):
        bones.append({
            "index": index,
            "name": node.get("name") or f"bone_{old_index}",
            "parentIndex": old_to_new.get(parent_old, -1),
            "localPosition": node.get("localPosition") or [0.0, 0.0, 0.0],
            "localRotation": node.get("localRotation") or [0.0, 0.0, 0.0, 1.0],
            "localScale": node.get("localScale") or [1.0, 1.0, 1.0],
        })
    return ordered, old_to_new, bones


def _bundle_skin(skin, old_to_new, bind_pose_count):
    result = []
    for vertex_index, influences in enumerate(skin):
        accumulated = {}
        for item in influences:
            if len(item) >= 3:
                old_index, correction_index, weight = item[:3]
                if abs(float(correction_index)) > 1e-6:
                    raise ValueError(
                        f"顶点 {vertex_index} 含逆蒙皮 correction；请先传递配置档权重再导出 bundle 源"
                    )
            elif len(item) == 2:
                old_index, weight = item
            else:
                raise ValueError(f"顶点 {vertex_index} 的权重格式无效")
            old_index = int(old_index)
            if old_index < 0 or old_index >= bind_pose_count or old_index not in old_to_new:
                raise ValueError(f"顶点 {vertex_index} 引用了无效骨骼索引：{old_index}")
            weight = max(0.0, float(weight))
            if weight:
                new_index = old_to_new[old_index]
                accumulated[new_index] = accumulated.get(new_index, 0.0) + weight
        ordered = sorted(accumulated.items(), key=lambda item: item[1], reverse=True)[:4]
        total = sum(weight for _index, weight in ordered)
        if total <= 1e-8:
            raise ValueError(f"顶点 {vertex_index} 没有有效骨骼权重")
        indices = [index for index, _weight in ordered]
        weights = [weight / total for _index, weight in ordered]
        indices.extend([0] * (4 - len(indices)))
        weights.extend([0.0] * (4 - len(weights)))
        result.append({"weight": weights, "boneIndex": indices})
    return result


def _bundle_submeshes(faces, materials, vertex_count, material_slot_count):
    if any(len(face) != 3 for face in faces):
        raise ValueError("bundle 源要求所有面都是三角形")
    per_vertex = len(materials) == vertex_count
    per_face = len(materials) == len(faces)
    if materials and not (per_vertex or per_face):
        raise ValueError("材质索引数量与顶点/面数量不一致")

    groups = {}
    for face_index, face in enumerate(faces):
        if any(int(index) < 0 or int(index) >= vertex_count for index in face):
            raise ValueError(f"面 {face_index} 含越界顶点索引")
        if per_vertex:
            slot = int(materials[face[0]])
            if any(int(materials[index]) != slot for index in face):
                raise ValueError(f"面 {face_index} 的三个顶点跨材质槽")
        elif per_face:
            slot = int(materials[face_index])
        else:
            slot = 0
        if slot < 0:
            raise ValueError(f"面 {face_index} 的材质槽无效：{slot}")
        groups.setdefault(slot, []).append(tuple(int(index) for index in face))

    slot_count = max(1, int(material_slot_count or 0), max(groups, default=0) + 1)
    indices = []
    submeshes = []
    for slot in range(slot_count):
        grouped_faces = groups.get(slot, [])
        start = len(indices)
        indices.extend(index for face in grouped_faces for index in face)
        used = indices[start:]
        first_vertex = min(used) if used else 0
        used_count = max(used) - first_vertex + 1 if used else 0
        # ponytail: Unity oracle consumes firstByte as an R16 offset; keep this
        # compatibility quirk until the build script stops dividing by two.
        submeshes.append({
            "indexCount": len(used),
            "firstVertex": first_vertex,
            "vertexCount": used_count,
            "firstByte": start * 2,
            "baseVertex": 0,
        })
    return indices, submeshes


def _bundle_geojson(data, source_mesh, skeleton, material_slot_count):
    vertex_count = len(data.get("vertices") or [])
    if not vertex_count:
        raise ValueError("没有可导出的顶点")
    normals = data.get("normals") or []
    tangents = data.get("tangents") or []
    uv0 = data.get("uv0") or []
    colors = data.get("colors") or []
    if not (len(normals) == len(tangents) == len(uv0) == len(colors) == vertex_count):
        raise ValueError("网格顶点/法线/切线/UV/COLOR 数量不一致")

    bind_poses = list(source_mesh.get("m_BindPose") or [])
    bind_poses.extend(data.get("bundle_extra_bind_poses") or [])
    ordered, old_to_new, bones = _bundle_bone_order(skeleton)
    if len(bind_poses) != len(ordered):
        raise ValueError(
            f"骨架骨骼数 {len(ordered)} 与 m_BindPose 数量 {len(bind_poses)} 不一致"
        )
    indices, submeshes = _bundle_submeshes(
        data.get("faces") or [], data.get("materials") or [], vertex_count, material_slot_count
    )
    flat = lambda values: [float(axis) for item in values for axis in item]
    color_values = flat(colors)
    if color_values and max(color_values) > 1.0:
        color_values = [value / 255.0 for value in color_values]
    geo = {
        "m_VertexCount": vertex_count,
        "m_Vertices": flat(data["vertices"]),
        "m_Normals": flat(normals),
        "m_Tangents": flat(tangents),
        "m_UV0": flat(uv0),
        "m_Colors": color_values,
        "m_Indices": indices,
        "m_Skin": _bundle_skin(data.get("skin") or [], old_to_new, len(bind_poses)),
        "m_BindPose": [bind_poses[old_index] for _node, old_index, _parent in ordered],
        # Keep the source weighted-index identity available to the template
        # patcher when a Unity-built template omitted m_BoneNameHashes.
        "m_BoneNameHashes": list(source_mesh.get("m_BoneNameHashes") or []),
        "m_SubMeshes": submeshes,
        "m_Name": source_mesh.get("m_Name") or source_mesh.get("Name") or "Geo_Body",
    }
    if len(geo["m_Skin"]) != vertex_count:
        raise ValueError("m_Skin 数量与 m_VertexCount 不一致")
    return geo, bones


def merge_material_groups(co_slots, target_submesh_count, materials, transparent_slots=()):
    """把作者网格的每-面/每-顶点材质槽索引，归并到目标 body 的材质方案。

    目标 body 只有 1 段(bdy)或 2 段(bdy+bdyco)。归并规则：不透明槽 → 组 0(bdy)，
    被标 NATIVE_CO 的槽 → 组 1(bdyco)。这样 madoka 那种 9 材质(已共用一张图集)
    能塌到 1/2 段；未共用图集的 mod 材质数天然就是 1/2，直接通过。

    co_slots: 被标 NATIVE_CO 的槽索引集合。
    返回归并后的 materials(同长度，值 ∈ {0,1})。方案对不上时抛清晰错误。

    ponytail: 只按 opaque/co 归并 + 校验，不做通用 UV atlas 烘焙——那是重活，
    未共用图集的多材质 mod 应由作者自己收拢到 bdy(+bdyco)。
    """
    co_slots = {int(slot) for slot in co_slots}
    # 自建半透明段落在目标段数之后：原版 renderer 没有这些槽，runtime 会按 mod.json 的
    # transparentMaterials 把 sharedMaterials 数组扩容并塞进新建的 Gmi/Transparent 材质。
    # 所以它们不受"目标只有 N 段"这条限制 —— 但每个源材质槽仍然各占一段（各自一张 t0）。
    extra = {int(slot): index for index, slot in enumerate(sorted(
        {int(slot) for slot in transparent_slots} - co_slots))}
    target = max(1, int(target_submesh_count or 1))

    def group_of(slot):
        slot = int(slot)
        if slot in extra:
            return target + extra[slot]
        return 1 if slot in co_slots else 0

    used = {group_of(slot) for slot in materials} if materials else {0}
    transparent_groups = {target + index for index in extra.values()}
    used_native = used - transparent_groups
    if target == 1 and 1 in used_native:
        raise ValueError(
            "目标 body 只有 bdy 一段，但你的网格含 co(NATIVE_CO)材质；"
            "请去掉 co 材质，或选一个带 bdyco 的目标服装")
    if used_native and max(used_native) >= target:
        raise ValueError(
            f"网格材质分组 {sorted(used_native)} 超出目标 body 的 {target} 段；"
            "请把材质合并到 bdy" + ("(和 bdyco)" if target > 1 else ""))
    return [group_of(slot) for slot in materials]


def transparent_group_map(co_slots, target_submesh_count, transparent_slots):
    """{源材质槽: 归并后的段号}，只含自建半透明槽。与 merge_material_groups 同一套算法。"""
    co_slots = {int(slot) for slot in co_slots}
    target = max(1, int(target_submesh_count or 1))
    ordered = sorted({int(slot) for slot in transparent_slots} - co_slots)
    return {slot: target + index for index, slot in enumerate(ordered)}


def _bundle_root_bone(skeleton, bone_names):
    """SMR rootBone 名。优先按 skeleton 的 rootBonePathId 反查（权威，来自真实
    body 的 SkinnedMeshRenderer），回退到 weightedIndex==0 的骨，再回退 "Hips"。
    必须是 prefab 里存在的骨（即 sidecar 的加权骨之一），否则运行时插件的
    originalRootName==modRootName 校验会失败、graft 中止。
    ponytail: 不猜根骨——rootBonePathId 是权威记录，只在它缺失/非加权时才回退。"""
    nodes = skeleton.get("nodes") or []
    candidates = []
    root_pathid = skeleton.get("rootBonePathId")
    if root_pathid is not None:
        candidates += [n.get("name") for n in nodes if n.get("pathId") == root_pathid]
    # weightedIndex==0 只在真实骨架里可信；合成骨架（rootBonePathId 缺失、pathId 全 None）
    # 的 weightedIndex 顺序是任意的（按 m_BoneNameHashes），0 号往往是手指骨之类而非根骨，
    # 会让 modRoot != originalRoot 导致 graft 中止。合成骨架直接落到权威约定根 Hips。
    if not skeleton.get("synthetic"):
        candidates += [n.get("name") for n in nodes if n.get("weightedIndex") == 0]
    candidates.append("Hips")
    for candidate in candidates:
        if candidate and candidate in bone_names:
            return candidate
    # 加权骨里一个都不匹配：返回权威名而非静默 Hips，让不一致显性化。
    return next((candidate for candidate in candidates if candidate), "Hips")


RENDERER_NAMES = {"body": "Geo_Body", "hair": "Geo_Hair", "hairprop": "Geo_HairProp"}


def _bundle_sidecar(component):
    """一个 renderer 的骨架 sidecar（buildId 由调用方最后统一盖上）。"""
    bones, skeleton = component["bones"], component["skeleton"]
    source_report = component["data"].get("source_rig_report", {})
    sidecar = {
        "schemaVersion": 4 if source_report.get("newBones") else 2,
        "runtimeProtocol": AB_RUNTIME_PROTOCOL,
        "gmiCodeMarker": AB_CODE_MARKER,
        "boneCount": len(bones),
        "rootBone": _bundle_root_bone(skeleton, {bone["name"] for bone in bones}),
        "bones": bones,
        "sourceRigRemap": source_report,
    }
    if source_report.get("newBones"):
        if not component["extra_nodes"]:
            sidecar["newBones"] = source_report["newBones"].get("newBones", [])
        sidecar["extraSwingBones"] = source_report["newBones"].get("extraSwingBones", [])
        # 建链数据（宿主骨 + 按链长分好组的链根）。运行时照单建，不做启发式。
        sidecar["swingChains"] = source_report["newBones"].get("swingChains", [])
        # Runtime BuildHybridBoneArray creates new bones from bones[] and reads each entry's
        # swing (parseSwing). New bones live in bones[] without a swing field → the runtime
        # falls back to SetDefaultValues (mass=0/spring=0, inert) → they flail when driven or
        # never swing. Carry the swing params computed for newBones onto the matching bones[]
        # entry so created bones get real spring/damping instead of degenerate defaults.
        swing_by_name = {
            nb["name"]: nb["swing"]
            for nb in source_report["newBones"].get("newBones", [])
            if isinstance(nb, dict) and nb.get("name") and nb.get("swing")
        }
        for bone in bones:
            swing = swing_by_name.get(bone.get("name"))
            if swing and "swing" not in bone:
                bone["swing"] = dict(swing)
    return sidecar


def _bundle_component(bundle_dir, package_id, source, component_id, data,
                      mesh_json, skeleton_json, material_slot_count, primary):
    """写一个 renderer 的 geojson，返回它的 sidecar 和 manifest 里的 renderer 规则。

    发型和发饰是同一个 bundle 里的两个 renderer，共用一个顶层 source；副 renderer 的
    geojson/sidecar 按 `{source}__{targetRenderer}` 命名——这正是模板里第二个 Mesh 的
    命名（`..._hair__Geo_HairProp_mesh`），也是 patch_unity_bundle 查找时认的名字。
    """
    renderer_name = RENDERER_NAMES.get(component_id, "Geo_Body")
    rule_source = source if primary else f"{source}__{renderer_name}"
    skeleton = load_json(Path(skeleton_json))
    extra_nodes = data.get("bundle_extra_skeleton_nodes") or []
    if extra_nodes:
        skeleton = dict(skeleton)
        skeleton["nodes"] = list(skeleton.get("nodes") or []) + extra_nodes
    geo, bones = _bundle_geojson(
        data, load_json(Path(mesh_json)), skeleton, material_slot_count
    )
    geo_name = f"{rule_source}.geojson.txt"
    bones_name = (f"{package_id}_bones.json.txt" if primary
                  else f"{rule_source}_bones.json.txt")
    _write_json(bundle_dir / geo_name, geo)
    asset_root = f"Assets/Mods/{package_id}"
    rule = {"rendererId": component_id, "targetRenderer": renderer_name,
            "modRenderer": renderer_name}
    if not primary:
        rule["source"] = rule_source
        rule["skeleton"] = f"{asset_root}/{bones_name}"
    return {"geo": geo, "bones": bones, "skeleton": skeleton, "extra_nodes": extra_nodes,
            "geo_name": geo_name, "bones_name": bones_name, "renderer_name": renderer_name,
            "rule": rule, "data": data}


def write_bundle_source(
    output_root, package_id, source, component_id, name, author, data,
    mesh_json, skeleton_json, textures, material_slot_count=1, version="0.1.0",
    extra_components=(), transparent_materials=(),
):
    """Write the Unity-independent source files consumed by the Phase 2 build.

    `extra_components` 让一个包带多个 renderer（当前唯一用途：发型 + 发饰同包）。
    每项是 dict：component_id / data / mesh_json / skeleton_json / material_slot_count。
    """
    package_id = _sanitize_package_id(package_id)
    source = str(source or "").strip()
    if not source or Path(source).name != source:
        raise ValueError("bundle source 的 source 必须是单个资源名")
    bundle_dir = Path(output_root) / package_id / "bundle-src"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    components = [_bundle_component(bundle_dir, package_id, source, component_id, data,
                                    mesh_json, skeleton_json, material_slot_count, True)]
    for item in extra_components:
        components.append(_bundle_component(
            bundle_dir, package_id, source, item["component_id"], item["data"],
            item["mesh_json"], item["skeleton_json"],
            item.get("material_slot_count", 1), False))

    geo, bones = components[0]["geo"], components[0]["bones"]
    skeleton, extra_nodes = components[0]["skeleton"], components[0]["extra_nodes"]
    renderer_name = components[0]["renderer_name"]
    asset_root = f"Assets/Mods/{package_id}"
    geo_name = components[0]["geo_name"]
    bones_name = components[0]["bones_name"]
    prefab_name = f"{source}.prefab"
    bundle_name = f"{package_id}.bundle"
    source_report = data.get("source_rig_report", {})
    for component in components:
        component["sidecar"] = _bundle_sidecar(component)
    sidecar = components[0]["sidecar"]
    texture_entries = []
    for item in textures:
        filename = Path(item["filename"]).name
        path = bundle_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"bundle 贴图不存在：{path}")
        texture_entries.append({
            "rendererName": item.get("rendererName", renderer_name),
            "materialSlot": int(item["materialSlot"]),
            "property": item["property"],
            "asset": f"{asset_root}/{filename}",
            "type": "Texture2D",
        })

    build_id_hash = hashlib.sha256()
    build_id_hash.update(package_id.encode("utf-8"))
    build_id_hash.update(str(version).encode("utf-8"))
    values = [value for component in components
              for value in (component["geo"], component["sidecar"])]
    for value in values + [texture_entries]:
        build_id_hash.update(json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))
        build_id_hash.update(b"\0")
    for item in sorted(texture_entries, key=lambda entry: entry["asset"]):
        path = bundle_dir / Path(item["asset"]).name
        build_id_hash.update(path.name.encode("utf-8"))
        build_id_hash.update(hashlib.sha256(path.read_bytes()).digest())
    build_id = build_id_hash.hexdigest()[:16]
    # runtime 是逐 renderer 读 sidecar 的，每份都要盖同一个 buildId
    for component in components:
        component["sidecar"]["buildId"] = build_id
        _write_json(bundle_dir / component["bones_name"], component["sidecar"])

    mod = {
        "schemaVersion": 2,
        "runtimeProtocol": AB_RUNTIME_PROTOCOL,
        "buildId": build_id,
        "id": package_id,
        "name": name or package_id,
        "version": version,
        "author": author or "",
        "priority": 0,
        "enabled": True,
        "replacements": [{
            "source": source,
            # 发饰属于 hair 部位；写成 body 会让 runtime 按身体 mod 处理，装上去毫无反应
            "part": "hair" if component_id in {"hair", "hairprop"} else "body",
            "priority": 0,
            "bundle": bundle_name,
            "asset": f"{asset_root}/{prefab_name}",
            "skeleton": f"{asset_root}/{bones_name}",
            "type": "GameObject",
            "renderers": [component["rule"] for component in components],
            "replaceMaterials": False,
            "textures": texture_entries,
        }],
    }
    # 自建半透明段：runtime 拿它去扩 sharedMaterials 并新建 Gmi/Transparent 材质。
    # 缺 shader 包或缺贴图时 runtime 整体拒绝（不静默回落成不透明）。
    transparent_entries = [{
        "rendererName": item.get("rendererName", renderer_name),
        "materialSlot": int(item["materialSlot"]),
        "asset": f"{asset_root}/{Path(item['filename']).name}",
        "defMap": f"{asset_root}/{Path(item['defMap']).name}" if item.get("defMap") else "",
        "shadeMap": f"{asset_root}/{Path(item['shadeMap']).name}" if item.get("shadeMap") else "",
        "type": "Texture2D",
        "alpha": float(item.get("alpha", 0.5)),
        "toonStrength": float(item.get("toonStrength", 1.0)),
        "shadeDarken": float(item.get("shadeDarken", 0.45)),
        "cull": float(item.get("cull", 0.0)),
        "zwrite": float(item.get("zwrite", 0.0)),
        "renderQueue": int(item.get("renderQueue", 3000)),
        "props": {str(k): float(v) for k, v in (item.get("props") or {}).items()},
    } for item in transparent_materials]
    if transparent_entries:
        mod["replacements"][0]["transparentMaterials"] = transparent_entries
    _write_json(bundle_dir / "mod.json", mod)
    return bundle_dir


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


def summarize_bind_mesh(mesh_json_path):
    """Return bind-mesh counts and per-bone total weight from a Mesh JSON.

    Used to size the profile and to flag bones whose total weight is too low to
    be worth trusting. Until 0.9.0 this also solved for the inverse-skin operator
    P and wrote a ~40 MB R32_FLOAT buffer; that operator only ever fed the
    3DMigoto re-skinning path, which is gone, so the solve and the buffer went
    with it. The counts below are what the profile actually consumes.
    """
    mesh = load_json(Path(mesh_json_path))
    vertex_count = int(mesh["m_VertexCount"])
    bone_count = len(mesh["m_BindPose"])
    if len(mesh["m_Vertices"]) != vertex_count * 3:
        raise ValueError("Mesh m_Vertices 与 m_VertexCount 不一致")

    bone_weight_total = [0.0] * bone_count
    active = 0
    for influence in mesh["m_Skin"]:
        for bone, weight in zip(influence["boneIndex"], influence["weight"]):
            weight = float(weight)
            if weight <= 0.0:
                continue
            if bone_weight_total[int(bone)] == 0.0:
                active += 1
            bone_weight_total[int(bone)] += weight
    if active == 0:
        raise ValueError("Mesh 没有任何加权骨骼")

    return {
        "vertexCount": vertex_count,
        "boneCount": bone_count,
        "coefficientCount": bone_count * 4,
        "activeBoneCount": active,
        "boneWeightTotal": bone_weight_total,
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
                                  unobservable_weight_threshold=0.1,
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

    # (3) Bind-mesh statistics (counts + per-bone weight totals).
    operator_meta = summarize_bind_mesh(mesh_dst)

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
    for key in ("meshJson", "skeletonJson"):
        src = source_dir / config[key]
        dst = profile_dir / "Reference" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        component["inverseSkin"][key] = f"Reference/{src.name}"

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
    # UV 原样进 Blender：Unity 和 Blender 的 UV 原点都在左下，不需要翻 v。以前这里翻了一次，
    # 而导出端**不翻回去**（`operators._inverse_skin_export_data` 原样写 Blender 的 UV 层），
    # 于是任何从 Mesh JSON 导进来再出包的模型，贴图都是上下颠倒着采的 —— 画面上就是"贴图错乱"。
    # 判据（chs-sucu 源模型 + 它自己的 col 图）：Head 的皮肤顶点原样 v 采到 (228,193,179) 肤色，
    # 翻转 v 采到 (122,104,104)。
    uv0 = list(_group(mesh["m_UV0"], 2))
    uv1 = list(_group(mesh["m_UV1"], 2))
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


# --- Runtime texture-slot layout auto-detect (replaces per-PS slot variants) ---
# The game repacks base/mask/shade into different ps-tN slots per lighting shader.
# Instead of enumerating pixel-shader hashes, detect the layout at draw time from a
# global body landmark texture (hash 0ff26bed) that the engine always binds:
#   landmark at ps-t2 -> layout A (base t0, mask t1, shade t4)
#   landmark at ps-t3 -> layout B (base t1, mask t2, shade t5)  <- only B moves base/mask
#   neither           -> layout C/unknown (base t0, mask t1, no custom shade) -- safe
# This needs no per-costume or per-scene shader hash and degrades gracefully.
GMI_BODY_LAYOUT_LANDMARK = "0ff26bed"


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


def load_bone_remap_presets(path=None):
    """Load the small built-in source-rig remap table."""
    source = Path(path) if path else Path(__file__).with_name("bone_remap_presets.json")
    return load_json(source).get("presets", {})


def detect_source_rig(source_bones, target_bones=()):
    """Identify the supported naming convention from bone names."""
    names = {str(name) for name in source_bones if str(name)}
    lowered = {name.lower() for name in names}
    target = {str(name) for name in target_bones}
    if any(name.startswith("mixamorig:") for name in lowered):
        return "mixamo"
    if any(name.startswith(("def-", "org-", "mch-")) for name in lowered):
        return "rigify"
    if any(name in {"センター", "下半身", "上半身", "左腕", "右腕", "左ひじ", "右ひじ"}
           for name in names):
        return "mmd-standard"
    if any(re.sub(r"(?:_1)+$", "", name) in target and name not in target for name in names):
        return "scsp"
    return "custom"


def _fold_side_suffix(name):
    """mmd_tools 把 PMX 的 右腕 导成 腕.R；折回去才查得到日文表。"""
    sided = re.fullmatch(r"(.+)\.([LR])", name)
    if not sided:
        return None
    return ("左" if sided.group(2) == "L" else "右") + sided.group(1)


def _preset_target(name, preset_bones):
    candidate = preset_bones.get(name)
    if candidate is not None:
        return candidate
    folded = _fold_side_suffix(name)
    return preset_bones.get(folded) if folded else None


def _resolve_preset_value(value, target):
    """预设表的值可以是一个骨名，也可以是**按优先级排的候选列表**。

    捩骨要的就是这个：源模型的 `左腕捩` 该落到 `LeftArm_Roll_H`（原版 528/530 套都有，
    而且姿势驱动器就装在它上面），但万一目标骨架没有这根，退回 `LeftArm` 也比整根骨
    掉进 unmapped、权重直接消失要好。返回第一个真正存在于目标骨架里的候选。
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for candidate in value:
            if candidate in target:
                return candidate
        return None
    return value if value in target else None


def _preset_lookup(name, preset_bones):
    """查预设表：原名查不到时，剥掉 `_1` 后缀再查一次。

    SCSP 导出的骨名常是「变体名 + _1」（`LeftArm1_rot_1`、`LeftElbow_1`）。只查原名的话，
    `_1` 后缀会让 `*_rot` / `Elbow` / `Clavicle` 这些预设规则全部落空，带权重的捩骨、
    脚趾被误判成装饰骨——dress-2219 上实测漏了 18 根骨、3514 权重。
    """
    candidate = _preset_target(name, preset_bones)
    if candidate is not None:
        return candidate
    stripped = re.sub(r"(?:_1)+$", "", name)
    return _preset_target(stripped, preset_bones) if stripped != name else None


def _best_preset(source, target, presets, preferred=None):
    """逐张表试算命中数，取最高的那张。

    嗅探（detect_source_rig）只用来打平手：这样以后支持一种新命名规范＝纯加一张表，
    不用再加嗅探分支，也不会因为嗅探探针没命中就让整张表空转。
    """
    def hits(key):
        bones = presets.get(key, {}).get("bones", {})
        # 与 mapped_name 同一套匹配（含 _1 剥离），否则整套骨名都带 _1 的源会让每张表都得 0 分
        return sum(1 for name in source
                   if _resolve_preset_value(_preset_lookup(name, bones), target) is not None)

    ranked = sorted(presets, key=lambda key: (-hits(key), key != preferred, key))
    if ranked and hits(ranked[0]):
        return ranked[0]
    return preferred or "custom"


def classify_source_bones(source_bones, target_bones, remap=None, accessory_prefixes=None):
    """Split source bones into Track A body bones and Track B accessories."""
    target = {str(name) for name in target_bones}
    remap = remap or {}
    prefixes = tuple(str(value).lower() for value in (accessory_prefixes or (
        "skirt", "bow", "streamer", "ribbon", "hair", "cloth", "dress", "tie",
        "accessory", "髪", "スカート", "リボン", "ネクタイ", "飾",
    )))
    body, accessory = [], []
    for name in (str(value) for value in source_bones):
        lower = name.lower()
        if any(token in lower for token in prefixes):
            accessory.append(name)
        elif name in target or name in remap:
            body.append(name)
        else:
            accessory.append(name)
    return {"body": body, "accessory": accessory}


def build_bone_remap(source_bones, target_bones, parent_by_name=None,
                     preset_name="auto", presets=None):
    """Build deterministic Track A mappings and diagnose Track B bones.

    Direct names, ``_1`` cleanup, and the selected preset are safe weight-label
    translations. Parent fallback is reported separately for accessory grafting;
    it is deliberately not added to ``bones``.
    """
    source = list(dict.fromkeys(str(name) for name in source_bones if str(name)))
    target = {str(name) for name in target_bones if str(name)}
    presets = presets or load_bone_remap_presets()
    rig = detect_source_rig(source, target)
    selected = (_best_preset(source, target, presets, rig)
                if preset_name in (None, "", "auto") else str(preset_name))
    preset = presets.get(selected, {})
    preset_bones = preset.get("bones", {})
    mappings, methods = {}, {}

    def mapped_name(name):
        if name in target:
            return name, "direct"
        stripped = re.sub(r"(?:_1)+$", "", name)
        if stripped in target:
            return stripped, "strip_suffix"
        candidate = _resolve_preset_value(_preset_lookup(name, preset_bones), target)
        if candidate:
            return candidate, "preset"
        return None, None

    for name in source:
        candidate, method = mapped_name(name)
        if candidate:
            mappings[name] = candidate
            methods[name] = method

    parents = parent_by_name or {}
    parent_fallback = {}
    for name in source:
        if name in mappings:
            continue
        parent = parents.get(name)
        visited = set()
        while parent and parent not in visited:
            visited.add(parent)
            candidate = mappings.get(parent)
            if candidate is None:
                candidate, _ = mapped_name(parent)
            if candidate:
                parent_fallback[name] = candidate
                break
            parent = parents.get(parent)

    classes = classify_source_bones(
        source, target, mappings, preset.get("accessoryPrefixes")
    )
    return {
        "sourceRig": rig,
        "preset": selected if selected in presets else None,
        "bones": mappings,
        "methods": methods,
        "parentFallback": parent_fallback,
        "unmapped": [name for name in source if name not in mappings],
        "bodyBones": classes["body"],
        "accessoryBones": classes["accessory"],
    }


# 任何全身网格都必须有权重的承重关节。少一个 = 源骨名没映射上，静止看着正常、
# 进游戏那块跟着别的骨乱跑（实测过：整只手 100% 钉在 Spine1）。
CRITICAL_TARGET_BONES = (
    # Spine2 故意不在闸门里:游戏有三节脊椎,Auto Rig Pro 等源只有两节,
    # 拦它等于误伤所有两节脊椎的源。Spine1 有就够定位躯干映射没跑偏。
    "Hips", "Spine", "Spine1", "Neck", "Head",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
    "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
)


def missing_critical_bones(source_names, remap, target_bones):
    """承重关节里没拿到任何权重的那些（与目标骨架取交集，局部骨架不会误报）。"""
    target = set(target_bones)
    hit = {remap.get(name) for name in source_names}
    return [name for name in CRITICAL_TARGET_BONES
            if name in target and name not in hit]


def critical_coverage_error(source_names, remap, target_bones):
    """承重关节零权重 → 返回报错文案，正常返回 None。

    不猜源骨语义，只查游戏侧的胳膊腿有没有拿到权重，所以对任何命名规范都适用；
    与目标骨架取交集，骨很少的测试/局部骨架不会误报。位置匹配永远能返回一个骨名，
    不拦就是静默出废品——这是唯一便宜且可靠的拦法。
    """
    missing = missing_critical_bones(source_names, remap, target_bones)
    if not missing:
        return None
    # 两条出路必须都给：**骨存在但没认出来**去表单指定；**骨压根不存在**（MMD/Biped 没有
    # 锁骨、Head 直接挂 Spine2）在表单里永远找不到，那种只能从相邻骨劈权重。
    # 只写前一条的话，作者按提示去找一个不存在的东西，卡死。
    return ("以下承重关节没有拿到任何权重：" + "、".join(missing)
            + f"（共 {len(missing)} 个）。这样导出进游戏，那块几何会跟着别的骨乱跑"
              "（实测：整只手 100% 钉在 Spine1）。两种情形两条出路：\n"
              "  · 源模型**有**这根骨、只是名字没认出来 → 导出面板「骨骼映射表」里指定；\n"
              "  · 源模型**根本没有**这根骨（MMD/Biped 常见）→ 点「从相邻骨劈权重」，"
              "按原版身体的权重分布从旁边那圈骨里劈出来。")


def redistribute_family_weight(author, vanilla, missing):
    """一个顶点上：按原版的比例，从相邻骨劈出 `missing` 那根骨的权重。

    `author`  {目标骨: 权重} 这个顶点现有的权重（按目标骨合并过）
    `vanilla` {目标骨: 权重} 原版身体在最近那一点的权重
    `missing` 缺的那根骨

    返回 {目标骨: 新权重}，只含这一族；空 dict = 这个顶点不该动。规矩：

    · **只在作者和原版都认的骨之间重分**。作者有权重、原版在这点上没有的骨不进族，
      原样不动 —— 那是作者自己的画法（§7.3 档 2：两种画法各自自洽）。
    · **总量守恒**：这一族的权重总和不变，不做全身重绘，也不会把顶点的总权重改掉。
    · 原版只决定"分给缺骨多少"；剩下的按**作者自己的比例**分回捐赠骨（要求 2：保留源权重）。
    """
    donors = {name: max(0.0, float(weight)) for name, weight in author.items()
              if name != missing and float(vanilla.get(name) or 0.0) > 0.0}
    share = max(0.0, float(vanilla.get(missing) or 0.0))
    family_total = sum(donors.values()) + max(0.0, float(author.get(missing) or 0.0))
    if share <= 0.0 or family_total <= 0.0:
        return {}
    vanilla_family = share + sum(float(vanilla[name]) for name in donors)
    ratio = share / vanilla_family
    result = {missing: family_total * ratio}
    donor_total = sum(donors.values())
    for name, weight in donors.items():
        result[name] = (family_total * (1.0 - ratio) * weight / donor_total
                        if donor_total > 0.0 else 0.0)
    return result


def collapsed_chains(remap, parent_of, mass_by_name=None):
    """节数不同 → 一串**父子相连**的源骨塌进同一根目标骨（§7.3 档 3）。

    返回 [{target, sources, mass}]，按权重降序。手指 4 节 vs 游戏 3 节、脊椎 2 节 vs 3 节都长这样。
    **塌是安全的，塌错是"有值但错"——闸门永远抓不到**（每根骨都有目标、权重也归一），
    所以只能标出来给人看。左右两根骨并到一根不算这一类（它们不是父子），那是普通合并。
    """
    grouped = {}
    for name, target in (remap or {}).items():
        if target:
            grouped.setdefault(target, []).append(str(name))
    mass = mass_by_name or {}
    rows = []
    for target, names in grouped.items():
        if len(names) < 2:
            continue
        pool = set(names)
        # 只留"父也在同一组里"的那些：那才是把一条链压短了
        chained = [name for name in names if (parent_of or {}).get(name) in pool]
        if not chained:
            continue
        rows.append({
            "target": target,
            "sources": sorted(names),
            "mass": sum(float(mass.get(name) or 0.0) for name in names),
        })
    rows.sort(key=lambda row: (-row["mass"], row["target"]))
    return rows


def weight_state_summary(mass_by_name, remap, new_bones=(), unmapped=()):
    """{五档: 权重占比} —— 让"尽可能保留源权重"可量化，而不是凭画面猜（§8.2）。

    `mass_by_name` {源骨: 权重占比}（百分比或任意单位，原样加总）。判档只看数据本身：
    独占一根目标骨 = `direct`，几根源骨挤一根目标骨 = `merge`，新建辅助骨 = `helper`，
    连目标都没有 = `undecided`。
    """
    helpers, unresolved = set(new_bones), set(unmapped)
    users = {}
    for name in mass_by_name:
        target = remap.get(name)
        if target and name not in helpers and name not in unresolved:
            users[target] = users.get(target, 0) + 1
    summary = {}
    for name, mass in mass_by_name.items():
        if name in unresolved or not remap.get(name):
            state = "undecided"
        elif name in helpers:
            state = "helper"
        else:
            state = "direct" if users.get(remap[name], 0) <= 1 else "merge"
        summary[state] = summary.get(state, 0.0) + float(mass)
    return summary


def weight_sum_errors(sums, tolerance=1e-3):
    """逐顶点权重和不为 1（或为 0）的那些：[(顶点号, 权重和)]，最偏的排前面。

    全零 = 那个顶点在游戏里塌到原点；不归一 = 顶点整体缩向骨骼（Unity 不给你补）。
    """
    bad = [(index, float(value)) for index, value in enumerate(sums)
           if abs(float(value) - 1.0) > tolerance]
    bad.sort(key=lambda item: -abs(item[1] - 1.0))
    return bad


# ------------------------------------------------------------------ 尺子（P2 / P4）
# 作者唯一自查不到的东西是**骨的静止朝向**：肩差 172° 的包在静止截图里完全正常，转身之后
# 手臂整个转到身后、手指拉成面条（实机三次坐实），而且它不在头/手/脚/根骨这几个容易抽查的
# 位置上，它在肩和手指。所以逐骨把位置和朝向两个数都报出来。
#
# **朝向的定义是「本骨 → 人形子骨」的位移方向**，两边同一个定义，在 Unity 空间里比。
# 这是事实文档 §6.2 那六个坑换来的定义，别改成别的：
#   · 不能用 Blender 骨的 head→tail —— Biped 的 tail 约定给反向（Spine1 报 172.9°）；
#   · 不能把全部子骨平均 —— 脊椎下挂的衣物骨会把方向拽反（报 154°），只取人形子骨；
#   · 不能量骨自身坐标系的整体转角（含绕骨轴的 roll）—— 2026-08-17 拿**原版自己的身体**标定：
#     插件重建参考骨架时 roll 就没保留（`_create_armature` 只按 head→tail + 默认 roll 建骨），
#     104 根里 69 根整体转角正好 180°、而骨轴向差 0.00°。按整体转角判，原版自己全红。
#     lossless 路径下 `M_game × B_source` 本身就是重定向，roll 不要求逐根对齐。
#
# 阈值有实测背书：烘对了的包 39 根人形骨残差全 0.0°；坏样本 52°~172°，而"腿/躯干看着正常"
# 那一档是 7°。
ORIENTATION_WARN_DEG, ORIENTATION_FAIL_DEG = 5.0, 15.0
# 位置按**骨节长度的比例**判：手指骨节 20~25mm、四肢 150~300mm，同一个绝对毫米数两头都判错。
# 位置**最高只判黄**：lossless 蒙皮把静止位置差当重定向吸收（"免的是位置"），对齐更好但差了
# 不等于会炸。会炸的是朝向。
POSITION_WARN_RATIO, POSITION_FAIL_RATIO = 0.10, 0.25
POSITION_FLOOR_MM = 2.0                     # 比这个还小一律绿：短骨的比例会被浮点噪声放大
POSITION_WARN_MM, POSITION_FAIL_MM = 5.0, 20.0   # 拿不到骨长时的兜底（四肢量级）
_GRADE_ORDER = {"red": 0, "yellow": 1, "green": 2}


def _worse(*grades):
    return min(grades, key=lambda grade: _GRADE_ORDER[grade])


def _angle_between(a, b):
    """两个向量的夹角（度），零向量返回 None。恒在 [0,180]。"""
    length_a = math.sqrt(sum(value * value for value in a))
    length_b = math.sqrt(sum(value * value for value in b))
    if length_a < 1e-9 or length_b < 1e-9:
        return None
    cosine = sum(a[i] * b[i] for i in range(3)) / (length_a * length_b)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _position_grade(millimetres, length_mm=0.0):
    """位置差的判级——上限是黄，见上面阈值那段。"""
    if millimetres <= POSITION_FLOOR_MM:
        return "green"
    warn = length_mm * POSITION_WARN_RATIO if length_mm > 0 else POSITION_WARN_MM
    return "yellow" if millimetres >= warn else "green"


def _orientation_grade(degrees):
    if degrees is None:
        return "green"                       # 末节骨没有人形子骨，量不了朝向，不冤枉它
    return ("red" if degrees >= ORIENTATION_FAIL_DEG
            else "yellow" if degrees >= ORIENTATION_WARN_DEG else "green")


def format_degrees(degrees):
    """朝向差的显示：末节骨没有人形子骨，量不了 —— 说"量不了"，别显示成 0°。"""
    return "量不了" if degrees is None else f"{degrees:.1f}°"


def rest_alignment(source_positions, target_positions, children=None, lengths=None):
    """逐骨的关节位置差(mm) / 静止朝向差(°) / 判级，最差的排前面。

    三个入参都以**目标骨名**为键、都在 Unity 空间（游戏骨位置用 `bindPose` 求逆得到，
    别按层级累加 `localPosition`）：

    `source_positions` {目标骨名: 对应源骨的静止位置}
    `target_positions` {目标骨名: 游戏骨的静止位置}
    `children`         {目标骨名: [人形子骨名]} —— 朝向取「本骨 → 子骨」，多个子骨取最差那个
    `lengths`          {目标骨名: 骨节长度（米）}，只用于把位置差判成比例

    纯函数：源就是目标自己时应得 0.0mm / 0.0° / 全绿。
    """
    rows = []
    for name, source in source_positions.items():
        target = target_positions.get(name)
        if target is None:
            continue
        millimetres = math.sqrt(sum((source[i] - target[i]) ** 2
                                    for i in range(3))) * 1000.0
        worst_angle, worst_child = None, None
        for child in (children or {}).get(name, ()):
            child_source, child_target = source_positions.get(child), target_positions.get(child)
            if child_source is None or child_target is None:
                continue
            angle = _angle_between([child_source[i] - source[i] for i in range(3)],
                                   [child_target[i] - target[i] for i in range(3)])
            if angle is not None and (worst_angle is None or angle > worst_angle):
                worst_angle, worst_child = angle, child
        length_mm = float((lengths or {}).get(name) or 0.0) * 1000.0
        rows.append({
            "bone": name, "mm": millimetres, "deg": worst_angle, "child": worst_child,
            "grade": _worse(_position_grade(millimetres, length_mm),
                            _orientation_grade(worst_angle)),
        })
    rows.sort(key=lambda row: (_GRADE_ORDER[row["grade"]], -(row["deg"] or 0.0), -row["mm"]))
    return rows


# 跨关节权重混合带：关节两侧都沾到权重的顶点占比。唯一能**预判**"肩膀会不会崩"的数字 ——
# 作者那句"A→T 之后肩膀变小崩坏"，量出来就是源自己跨肩带只有 4.9%（原版 13.3%）。
# 关节定义与原版基线来自 research/ab-consolidated-facts-and-evidence-2026-08-16.md；
# 当前生产检查统一在这里按骨名计算。
CROSS_JOINT_BANDS = (
    ("肩", "LeftShoulder", "LeftArm"), ("肩", "RightShoulder", "RightArm"),
    ("肘", "LeftArm", "LeftForeArm"), ("肘", "RightArm", "RightForeArm"),
    ("腕", "LeftForeArm", "LeftHand"), ("腕", "RightForeArm", "RightHand"),
    ("膝", "LeftUpLeg", "LeftLeg"), ("膝", "RightUpLeg", "RightLeg"),
)
# 原版真值。场景里有带权重参考体时用参考体现算，拿不到才用这张表；
# 数字与 research 事实文档记录的是同一套量法。
VANILLA_CROSS_JOINT_SHARE = {"肩": 0.133, "肘": 0.039, "腕": 0.062, "膝": 0.095}
BAND_FLOOR = 0.02      # 原版自己都低于这个数的关节不做判断（那里本来不靠权重过渡）
BAND_FAIL_RATIO = 0.4  # 掉到原版同关节的四成以下 = 会崩


def joint_band_sides(parent_of):
    """{关节: {骨名: 1 近侧 | 2 远侧}}。近侧 = 近端骨子树减去远侧子树。"""
    def ancestry(name):
        result, current, seen = [name], parent_of.get(name), {name}
        while current and current not in seen:
            result.append(current)
            seen.add(current)
            current = parent_of.get(current)
        return result

    chains = {name: ancestry(name) for name in parent_of}
    sides = {}
    for label, near, far in CROSS_JOINT_BANDS:
        table = sides.setdefault(label, {})
        for name, up in chains.items():
            if far in up:
                table[name] = 2
            elif near in up:
                table[name] = 1
    return sides


def cross_joint_bands(influences, sides, threshold=0.01):
    """每个关节：两侧都沾到权重的顶点占比。`influences` = 逐顶点的 {骨名: 权重}。

    纯函数（原版数据喂进来也能跑，INV-8）。
    """
    counters = {label: [0, 0] for label in sides}
    for vertex in influences:
        pairs = vertex.items() if isinstance(vertex, dict) else vertex
        bones = [name for name, weight in pairs if float(weight) > threshold]
        for label, table in sides.items():
            seen = {table[name] for name in bones if name in table}
            if seen == {1, 2}:
                counters[label][0] += 1
            elif seen:
                counters[label][1] += 1
    return {label: {"cross": cross, "total": cross + same,
                    "share": (cross / (cross + same) if cross + same else 0.0)}
            for label, (cross, same) in counters.items()}


def cross_joint_band_findings(mod_bands, vanilla_bands=None):
    """把两组带宽拼成「肩 4.9%（原版 13.3%）」+ 判级；没有基线的关节判 green 不冤枉人。"""
    baseline = dict(VANILLA_CROSS_JOINT_SHARE)
    baseline.update({label: values["share"]
                     for label, values in (vanilla_bands or {}).items()
                     if values.get("total")})
    rows = []
    for label in dict.fromkeys(item[0] for item in CROSS_JOINT_BANDS):
        band = mod_bands.get(label)
        if band is None or not band.get("total"):
            continue
        base = float(baseline.get(label) or 0.0)
        share = float(band["share"])
        grade = "green"
        if base >= BAND_FLOOR and share < base:
            grade = "red" if share < base * BAND_FAIL_RATIO else "yellow"
        rows.append({"joint": label, "share": share, "vanilla": base, "grade": grade})
    return rows


# ---------------------------------------------------------- 结构分组（一行一组）
# 痛点：表单一行一根骨 —— chisaki 那条 MMD 裙子作者手点了几十次。分组信号**一个骨名都不读**
# （原来的正则剥 left/right 在日语/中文/乱码骨名下全废）：
#   锚点  沿父链向上第一根身体骨 —— 天然分开"挂 Pelvis 的裙"和"挂 ForeArm 的袖"
#   链    连通分支，分叉即断（与"不建分叉链"的规矩对齐）
#   归组  同锚点 + 链长相同 ±1
# 父链上没权重的中间骨不算断链：按"最近的在册祖先"接，否则一个空骨就把裙摆劈成两组。
# ponytail: §4.3 的第三个信号"影响顶点在网格上连片"没做 —— 锚点+链长已经把 12 片裙摆并成
# 一行；同锚点同链长的尾巴混进裙摆那一行时，作者拆开逐根覆盖即可。真需要再加顶点连通性。
def resolve_chains(bones, parent_of, body_bones=()):
    """把装饰骨切成链：返回 `(chains, anchor)`，`chains` = {链根: [成员，保持输入顺序]}。

    **链是部件类型、物理指令、分组三者共同的语义单位**，所以只能有一个切法：
    最近的在册祖先接父子（父链上没权重的中间骨不算断链），分叉即断。
    """
    order = [str(name) for name in bones if str(name)]
    body = {str(name) for name in body_bones}
    garment = [name for name in order if name not in body]
    pool = set(garment)

    def ancestor_in(name, wanted):
        seen, current = {name}, parent_of.get(name)
        while current and current not in seen:
            if current in wanted:
                return current
            seen.add(current)
            current = parent_of.get(current)
        return None

    parent = {name: ancestor_in(name, pool) for name in garment}
    anchor = {name: ancestor_in(name, body) or "" for name in garment}
    children = {}
    for name, up in parent.items():
        if up:
            children[up] = children.get(up, 0) + 1

    def root_of(name):
        seen = set()
        while name not in seen:
            seen.add(name)
            up = parent.get(name)
            if not up or children.get(up, 0) > 1:   # 分叉即断
                return name
            name = up
        return name

    chains = {}
    for name in garment:
        chains.setdefault(root_of(name), []).append(name)
    return chains, anchor


def structural_bone_groups(bones, parent_of, body_bones=()):
    """把装饰骨按结构并成组，返回 [{key, anchor, chains, depth, members}]（成员保持输入顺序）。"""
    order = [str(name) for name in bones if str(name)]
    chains, anchor = resolve_chains(bones, parent_of, body_bones)

    by_anchor = {}
    for root, members in chains.items():
        by_anchor.setdefault(anchor.get(root, ""), []).append((len(members), root))

    groups = []
    for anchor_name, items in sorted(by_anchor.items()):
        buckets = []
        for length, root in sorted(items):
            # 跟**桶里第一条**比，不是跟上一条比：跟上一条比会像多米诺一样串起来，
            # 长度 1,2,3,4,5 的链全并成一组（chs-sucu 实测 12 条链 → 24 根一组，
            # 裙摆和尾巴、飘带混在一起）。规矩本来就是"链长相同 ±1"。
            if buckets and length - buckets[-1][0][0] <= 1:
                buckets[-1].append((length, root))
            else:
                buckets.append([(length, root)])
        for bucket in buckets:
            members = {name for _length, root in bucket for name in chains[root]}
            groups.append({
                "key": f"{anchor_name or 'root'}|L{bucket[0][0]}",
                "anchor": anchor_name,
                "chains": len(bucket),
                "depth": max(length for length, _root in bucket),
                "members": [name for name in order if name in members],
            })
    return groups


# §4.2 的五档：每根骨最终只能处于其一，**不允许"未决定"进入导出**（硬闸门在批次 3）。
# 这一版先把它显示出来 —— 现在 72 根静默塌 Hips 的骨和真映射在表单里长得一模一样，
# 排错只能去 dump JSON。`bake` / `reject` 现在都有算子和闸门（`gmi.bake_rest_offset`；
# 未烘/拒绝在 operators.py 的导出前检查里拦）。
ROW_STATE_LABELS = {
    "direct": "直接映射", "merge": "合并", "helper": "辅助骨",
    "bake": "烘焙", "reject": "拒绝", "undecided": "未决定",
}


def row_state(target, strategy="auto", shared_target=False):
    """一行（= 一组）的五档状态。`shared_target` = 别的行也用这根目标骨（多对一）。"""
    strategy = str(strategy or "auto")
    # bake / reject 是**决定**，比"填了目标骨"更强：bake 是"先把静止形变烘进网格再并到父骨"，
    # reject 是"这根骨处理不了，禁止导出"。所以它们排在 target 之前判。
    if strategy in ("bake", "reject"):
        return strategy
    if str(target or "").strip():
        return "merge" if shared_target else "direct"
    if strategy in ("integrate", "native_driver"):
        return "helper"
    if strategy in ("rigid", "follow_skirt", "follow_nearest") or strategy.startswith("follow:"):
        return "merge"
    return "undecided"


def empty_swing_chain_error(empty_chains, limit=12):
    """闸门①：一条自建摇物链上一个带权重的骨都没有 —— 建了也没人看得见。

    这类链在日志里全绿（`swingPrepared` / `modBonesRegistered` 照常计数），
    画面上什么都不会发生，是纯粹的静默洞，所以拦。
    """
    names = [str(n) for n in empty_chains or ()]
    if not names:
        return None
    shown = "、".join(names[:limit]) + ("…" if len(names) > limit else "")
    return (f"{len(names)} 条自建摇物链上没有任何带权重的骨：{shown}。"
            "这些链在游戏里会被建出来、被解算、日志全绿，但画面上什么都不会动。"
            "要么把这些骨的策略改成刚性跟父骨，要么先在 Blender 里把权重画上去。")


def anchor_only_roots(members, parent_of, dominant_by_name):
    """这一组里"几何全在链根、子骨是空的"那些链根（表单上要常驻标黄的那一行的判据）。

    链根按原版是惰性锚（`spring/mass` 近 0，自身不摆、由子骨摆）。几何全绑在链根上时，
    照拓扑出参数就是"摆的骨没几何、有几何的骨不摆" —— 装了摇物画面纹丝不动，而日志全绿。
    以前这条只在**导出后**报一句 WARNING（状态栏一闪就没），作者很容易错过；有了这个
    判据，表单里那一行可以一直标着。
    """
    pool = {str(name) for name in members or ()}
    dominant = {str(k): int(v) for k, v in (dominant_by_name or {}).items()}
    parents = parent_of or {}

    def descendants(name):
        found, stack = set(), [name]
        while stack:
            current = stack.pop()
            for candidate in pool:
                if candidate not in found and parents.get(candidate) == current:
                    found.add(candidate)
                    stack.append(candidate)
        return found

    roots = []
    for name in sorted(pool):
        if parents.get(name) in pool or dominant.get(name, 0) <= 0:
            continue
        if any(dominant.get(child, 0) > 0 for child in descendants(name)):
            continue
        roots.append(name)
    return roots


def anchor_only_chain_note(anchor_only, applied=False, limit=12):
    """链根自己扛着全部几何 —— 这条链装了摇物也不会动。只报，不替作者决定。"""
    names = [str(n) for n in anchor_only or ()]
    if not names:
        return None
    shown = "、".join(names[:limit]) + ("…" if len(names) > limit else "")
    if applied:
        return (f"{len(names)} 条链已按「链根自己摆」出参数：{shown}。"
                "这是显式开关的结果，这几块几何在游戏里会晃起来。")
    return (f"{len(names)} 条链的几何全绑在链根上、子骨是空的：{shown}。"
            "链根是惰性锚（自身不摆、由子骨摆），所以**这几条链装了摇物也不会动**。"
            "想让它们动，三选一：勾「链根自己摆」、在 Blender 里把根的权重分一部分给子骨、"
            "或者把策略改成刚性跟父骨（省掉不起作用的摇物骨）。"
            "不管它也行 —— 那几块几何就是跟着父骨刚性走。")

def new_bone_name_collision_error(new_bones, target_bones, limit=12):
    """闸门：自建骨的名字不许和目标骨架里已有的骨重名（契约 §4.1 的防撞名）。

    重名的后果实测过（chs-sucu → hmsz-cstm-0059）：目标服装自己也有 `RightFrontSkirt1_S`，
    导出器于是拿**目标那根**的 local 变换去填 renderer 的 `bones[]`（localPosition 变成 0，
    即胯中心），而 `newBones` 段里记的还是我们自己的位置 —— 两处打架，运行时那片裙板绕胯
    中心摆，画面上是"先向上折再垂下来"。游戏侧同样按名字建索引（`RegisterBone` 遇到重名
    整根跳过），所以这不是风格问题，是硬冲突。
    """
    taken = {str(name) for name in target_bones or ()}
    hit = sorted({str(name) for name in new_bones or () if str(name) in taken})
    if not hit:
        return None
    shown = "、".join(hit[:limit]) + ("…" if len(hit) > limit else "")
    return (f"{len(hit)} 根自建摇物骨与目标骨架里的骨重名：{shown}。"
            "自建骨要么改个名（加 mod 前缀），要么就别自建、直接映射到那根同名的目标骨 —— "
            "两者同名会让 renderer 的 bones[] 取到目标骨的变换，装饰件绕错枢轴摆")


def undecided_export_error(rows, allow=False, limit=12):
    """闸门 9（§8.1 第 9 条 / 契约 §4.2）：`undecided` 不许静默进导出。

    `rows` = [(组名, 状态)]。返回错误文案，`None` 表示放行。

    默认拦：未决定的组会被静默塌成兜底骨（实测 2a 那份 `25.9%` 的权重就是这么出去的），
    而塌错是"有值但错"，别的闸门永远抓不到 —— 只有这一档能看见。

    `allow=True` = 作者显式选了"我知道，继续导"。这时不拦，但**必须留痕**：
    调用方要把 `undecided_export_record()` 写进 sidecar 和权重报告，否则等于没拦也没记，
    下一个人看到的包和"作者逐组决定过"的包长得一模一样。
    """
    pending = [str(name) for name, state in rows if state == "undecided"]
    if not pending or allow:
        return None
    shown = "、".join(pending[:limit]) + ("…" if len(pending) > limit else "")
    return (f"{len(pending)} 组骨还没决定怎么处理：{shown}。"
            "每组挑一个：填目标骨（并到人体骨）/ 刚性跟父骨 / 自建摇物链 / 蹭原版裙摆 / 烘焙。"
            "不决定就导出的话，这些骨会被静默塌到兜底骨上，几何跟着别的骨乱跑，"
            "而且没有任何闸门抓得到。"
            "确实想先导一版看画面：勾上「允许未决定的骨导出」，那一版会在 sidecar 和"
            "权重报告里标明这件事。")


def undecided_export_record(rows, allow=False):
    """导出时留痕：这一版有没有未决定的骨、是不是走了显式放行。"""
    pending = [str(name) for name, state in rows if state == "undecided"]
    return {"count": len(pending), "allowed": bool(allow), "bones": pending}

def merge_accessory_bone_remap(body_remap, *accessory_maps):
    """Add accessory guesses without overriding an explicit body mapping."""
    result = dict(body_remap or {})
    for mapping in accessory_maps:
        for name, target in (mapping or {}).items():
            result.setdefault(name, target)
    return result


def _named_positions(items):
    if isinstance(items, dict):
        items = [{"name": name, "position": position} for name, position in items.items()]
    result = {}
    for item in items or ():
        if isinstance(item, str):
            continue
        name = str(item.get("name") or "")
        position = item.get("position", item.get("worldPosition"))
        if name and position is not None and len(position) >= 3:
            result[name] = tuple(float(value) for value in position[:3])
    return result


def target_swing_bones(target_bones):
    """Return target bones eligible for Track B physics inheritance."""
    names = _named_positions(target_bones)
    return [name for name in names if (
        name.lower().endswith("_s")
        or "cloth" in name.lower()
        or re.fullmatch(r"bone_[0-9a-f]+", name, re.IGNORECASE)
    )]


def build_accessory_physics_remap(
    source_bones, target_bones, accessory_bones, parent_by_name=None,
    body_remap=None, group_by_name=None, max_distance=0.18, overrides=None,
):
    """Classify each Track B accessory into a physics strategy, then resolve targets.

    Per bone/group the strategy is chosen by precedence — **author override >
    built-in semantic/name rule > source-parent fallback** — so a wrong auto-guess is
    always correctable without touching code (the general escape hatch). Strategies:

      - ``integrate``      新骨 + 自己的 ActorSwing 链（自由悬垂：飘带/蝴蝶结）
      - ``follow_nearest`` 蹭最近摇物骨；超过最大距离则刚性跟父骨
      - ``follow_skirt``   蹭最近**裙摆**摇物骨，无视距离（裙摆镶边：花边）
      - ``follow:<bone>``  蹭指定目标骨
      - ``rigid``          无物理，跟源父骨映射到的游戏骨

    ``overrides`` = ``{骨名或前缀: 策略}``（作者显式，最高优先；前缀取最长匹配）。
    默认不再用位置猜测：源链→integrate、lace→follow_skirt、胸/Bust→对应 Bust*_S，
    其余装饰→源父骨；位置匹配只能通过 ``follow_nearest`` override 显式启用。
    """
    source = _named_positions(source_bones)
    target = _named_positions(target_bones)
    swing_names = target_swing_bones(target_bones)
    skirt_swing_names = [name for name in swing_names if "skirt" in name.lower()]
    accessory = [str(name) for name in accessory_bones if str(name) in source]
    parents = parent_by_name or {}
    body = body_remap or {}
    explicit_groups = group_by_name or {}
    overrides = {str(k): str(v) for k, v in (overrides or {}).items()}
    max_distance_sq = float(max_distance) ** 2

    def nearest(position, candidates=None):
        pool = candidates if candidates else swing_names
        if not pool:
            return None, None
        name = min(pool, key=lambda candidate: sum(
            (position[index] - target[candidate][index]) ** 2 for index in range(3)
        ))
        distance_sq = sum(
            (position[index] - target[name][index]) ** 2 for index in range(3)
        )
        return name, distance_sq

    def rigid_parent(name):
        parent = parents.get(name)
        visited = set()
        while parent and parent not in visited:
            visited.add(parent)
            if parent in body:
                return body[parent]
            parent = parents.get(parent)
        return "Hips"

    def group_key(name):
        if name in explicit_groups:
            return str(explicit_groups[name])
        # 兜底：调用方没给结构分组时才走名字（`structural_bone_groups()` 是生产路径）。
        # 正则剥 left/right 对日语/中文/乱码骨名全废，所以它只是兜底，不是判据。
        return re.sub(r"(?:left|right|_l|_r)(?=_|$)", "", name.lower())

    def override_for(name):
        # exact name wins; else the longest matching prefix (so "Lace" covers Lace_R_*).
        if name in overrides:
            return overrides[name]
        best_key = None
        for key in overrides:
            if name.lower().startswith(key.lower()) and (
                    best_key is None or len(key) > len(best_key)):
                best_key = key
        return overrides[best_key] if best_key else None

    def semantic_for(name):
        lower = name.lower()
        # Free-hanging source chains own their physics; lace is skirt-hem trim.
        if any(token in lower for token in
               ("spine2_bow", "spine_bow", "streamer", "sstreamer")):
            return "integrate"
        if "lace" in lower:
            return "follow_skirt"
        return None

    def bust_target(position):
        candidates = [name for name in swing_names if "bust" in name.lower()]
        return nearest(position, candidates)[0] if candidates else None

    def centroid(names):
        return tuple(sum(source[name][axis] for name in names) / len(names)
                     for axis in range(3))

    def units_for(names):
        """一个结构组 → `[(骨名列表, 指令)]`，**按链切**。

        作用域三档：作者覆盖 > 内置名字规则 > 无（走刚性跟父骨）。三档都**只在自己那条链上**生效。

        以前是"整组一个指令、第一个带覆盖的骨说了算"。结构分组按「锚点 + 链长 + 网格连片」
        归组，在真模型上一组能装下整条下半身 —— 实测 `Hips_1|L2` 一组 57 根骨：裙板 + 腰带 +
        飘带 + 挂坠 + 蝴蝶结。于是

        - 作者把 `Bag_R/Chain_R/Key_R` 点成刚性，却被同组 `Spine_Bow_L_B0` 的 `integrate` 吞掉；
        - 把 `Spine2_Bow_*` 点成刚性，同组的 `OPAI_*` 跟着变刚性、骨直接消失；
        - 花边的 `follow_skirt` 顺着组跑到腿部挂坠身上（左右不对称那次）。

        链是自然的作用域：一条链必须整条同一个指令（拆开等于劈断链），而两条链之间没有理由串。
        `kind`（逐骨蹭 / 按质心蹭）仍按**整个结构组**算 —— 一圈裙摆有几条链是结构信号，
        拆成单链后每条都变成"按质心蹭"，那会把 40 根骨全绑到同一根摇物骨上。
        """
        by_chain = {}
        for name in names:
            by_chain.setdefault(chain_root_of(name), []).append(name)

        units = []
        for root, members in by_chain.items():
            directive, best_depth = None, None
            for name in members:  # 作者覆盖：取最靠近链根的那次点名
                explicit_directive = override_for(name)
                if not explicit_directive:
                    continue
                depth = chain_depth_of(name, root)
                if best_depth is None or depth < best_depth:
                    directive, best_depth = explicit_directive, depth
            if directive is None:
                semantics = [semantic_for(name) for name in members]
                if "integrate" in semantics:  # 源链整条一起 integrate
                    directive = "integrate"
                else:
                    directive = next((s for s in semantics if s), None)
            units.append((members, directive))
        return units

    def chain_root_of(name):
        current, visited = name, set()
        while current not in visited:
            visited.add(current)
            parent = parents.get(current)
            if parent not in accessory_set:
                return current
            current = parent
        return name

    def chain_depth_of(name, root):
        depth, current, guard = 0, name, 0
        while current != root and guard < 512:
            current = parents.get(current)
            if current is None:
                return 10 ** 9
            depth += 1
            guard += 1
        return depth
    accessory_set = set(accessory)
    groups = {}
    for name in accessory:
        groups.setdefault(group_key(name), []).append(name)

    mapping, strategies, rigid, new_bones = {}, {}, {}, []
    # `kind` 按**整个结构组**算：一组里有几条链（成员的父不在本组 = 一条链的根），
    # 决定"逐骨蹭最近"还是"按质心蹭"。从前这里按 skirt/dress/cloth 词表判 —— 外语命名的
    # 裙摆全落进"按质心"，40 根骨一起蹭同一根摇物骨。链数是同一件事的结构信号，不读名字。
    # 指令按**链**算（见 units_for），两者作用域不同，别合并。
    plan = []
    for members in groups.values():
        group_kind = "segment" if sum(
            1 for name in members if parents.get(name) not in members) > 1 else "group"
        plan.extend((unit_names, unit_directive, group_kind)
                    for unit_names, unit_directive in units_for(members))

    for names, directive, kind in plan:

        if directive == "integrate":
            new_bones.extend(names)
            for name in names:
                strategies[name] = "new_source_chain"
            continue
        if directive and directive.startswith("follow:"):
            target_bone = directive.split(":", 1)[1]
            for name in names:
                mapping[name] = target_bone
                strategies[name] = "override_follow"
            continue

        if directive == "follow_nearest":
            candidate, distance_sq = nearest(centroid(names))
            if candidate is not None and distance_sq <= max_distance_sq:
                for name in names:
                    mapping[name] = candidate
                    strategies[name] = "override_nearest"
                continue
            directive = "rigid"

        if directive == "rigid":
            for name in names:
                rigid[name] = rigid_parent(name)
                strategies[name] = "rigid_parent"
            continue

        if directive is None and any(
                any(token in name.lower() for token in ("胸", "bust", "chest"))
                for name in names):
            candidate = bust_target(centroid(names))
            if candidate is not None:
                for name in names:
                    mapping[name] = candidate
                    strategies[name] = "name_bust"
                continue

        if directive is None:
            for name in names:
                rigid[name] = rigid_parent(name)
                strategies[name] = "source_parent"
            continue

        follow_skirt = directive == "follow_skirt"
        pool = skirt_swing_names if follow_skirt else None
        # 一组多条链（一圈裙摆、一圈花边）就逐骨蹭自己那边最近的摇物骨；整组只有一条链才按
        # 质心蹭。拿质心去蹭一整圈，等于把 40 根骨全绑到同一根摇物骨上。
        parcels = ([(name, source[name]) for name in names] if kind == "segment"
                   else [(None, centroid(names))])
        for owner, position in parcels:
            batch = [owner] if owner else list(names)
            candidate, distance_sq = nearest(position, pool)
            if candidate is None:
                new_bones.extend(batch)
                for name in batch:
                    strategies[name] = "new_bone"
                continue
            # follow_skirt (lace) rides the skirt even past max_distance — its bones sit at the
            # hem, farther from the skirt bones' anchors than the cutoff. Position-default falls
            # back to a rigid body parent when the nearest swing bone is too far.
            if distance_sq > max_distance_sq and not follow_skirt:
                for name in batch:
                    rigid[name] = rigid_parent(name)
                    strategies[name] = "rigid_parent"
                continue
            for name in batch:
                mapping[name] = candidate
                strategies[name] = ("segment_nearest" if kind == "segment"
                                    else "group_centroid")

    return {
        "targetSwingBones": swing_names,
        "bones": mapping,
        "strategies": strategies,
        "rigidParent": rigid,
        "newBones": new_bones,
        "unmapped": [name for name in accessory if name not in mapping and name not in rigid],
        "maxDistance": float(max_distance),
    }


def load_swing_presets(path=None):
    """学马原生摆动参数基准表（`tools/scan_vanilla_swing_bones.py` 扫 530 套原版 body 得出）。"""
    source = Path(path) if path else Path(__file__).with_name("swing_presets.json")
    return load_json(source)["categories"]


# 部件类别：决定用哪一档原版参数，以及要不要建 ActorSwingChain。判定顺序有意义
# （LegSleeve 是袖不是裙）。认不出来落 ribbon —— 最保守的一档：自由悬垂、不建链。
_SWING_CATEGORY_RULES = (
    ("sleeve", ("sleeve", "cuff", "袖")),
    ("skirt", ("skirt", "pants", "smock", "jacket", "coat", "dress", "hakama",
               "裙", "裤")),
    # 词表**和顺序**都必须和 tools/scan_vanilla_swing_bones.py 的 CATEGORY_RULES 一致 ——
    # 基准表按那边的分类聚合，这边分错就等于查错档。顺序同样要紧：`BeltChain` /
    # `CapeRibbon` / `CollarBow` 这种两边词表都命中的名字，先判哪个就归哪类，
    # ribbon 必须排在 cloth 前面。
    ("ribbon", ("ribbon", "string", "lace", "bow", "tie", "cord", "strap", "tassel",
                "rope", "chain", "acce", "neckless", "带", "结", "绳")),
    ("cloth", ("cloth", "poncho", "frill", "cape", "apron", "muffler", "scarf",
               "stole", "hood", "collar", "belt", "sash", "furisode", "gown",
               "shirt", "inner", "披风", "围")),
)


# 按几何判部件类型，不读名字。
#
# 按名字判有个硬伤：**只对恰好用本作命名习惯的源有效**。原神 rip 把裙摆叫 `Bone_HemA01_L`，
# MMD 叫 `スカート` —— 词表两个都不认，于是整条链拿不到物理。而且按名字猜已经翻过车：
# `lace` 可能长在靴口上，原神的 `Hair` 图集里有整条腿。
#
# 三个信号，按可信度排（判据与 SDK 侧 ChainClassifier 同源，那边在 381 套原版上量过）：
#   1. 挂在哪根身体骨上 —— 每条衣物链最终都会 parent 进一根 humanoid 骨，那根骨就说明了大半。
#      原版 1537 条链的锚点分布：Pelvis 758、Spine2 86、Spine 82、UpLeg_H 80、Shoulder 50。
#   2. 同一个锚点上有几条 —— 裙摆是一圈，原版一个锚点挂 4–8 片；胯上只挂一两条的是
#      围裙/尾巴/腰带，属 cloth 不属 skirt。
#   3. 往哪个方向垂 —— 只用来拆胸口那一族：向下垂是披挂，朝前是胸，朝后/朝外是翅膀/披肩。
#
# 名字仍然保留为**兜底**：几何信息拿不全时（比如没有锚点）退回词表，总比什么都不判强。
# 匹配方式不是随手定的：手臂/腿那两行用**子串**（LeftForeArm、RightUpLeg_H 都要命中），
# 头颈和胯部那两行用**精确相等** —— `Spine2` 必须**落不进** `Spine`，因为胸口一族
# （披风 / 翅膀 / 胸）要靠垂向再分一次，混进胯部一族就全被判成裙摆了。
_ANCHOR_CATEGORY = (
    (("Hand", "ForeArm", "Arm", "Shoulder"), "sleeve", "contains"),
    (("Head", "Neck"), "ribbon", "exact"),            # 头饰按最软的一档处理
    (("Leg", "Foot", "Toe"), "skirt", "contains"),    # 靴口、腿环 —— 和裙摆同一套限位
    (("Hips", "Pelvis", "Spine"), "skirt", "exact"),
)

# 一圈裙摆至少几片。少于这个数的按 cloth（围裙/尾巴/腰带）。
SKIRT_RING_MIN = 4


def swing_category_by_geometry(anchor, direction=None, siblings=None, fallback_name=None):
    """锚点 + 垂向 + 同锚点条数 → 部件类型；判不出来时退回按名字。

    `direction` 是链的整体走向（单位向量，y 向下为负、z 向前为正），可以不给。
    `siblings`  同一个锚点上有几条链，可以不给（不给就不做"一圈"判定）。
    """
    anchor = str(anchor or "")
    category = None
    for tokens, resolved, mode in _ANCHOR_CATEGORY:
        hit = (anchor in tokens) if mode == "exact" else any(t in anchor for t in tokens)
        if hit:
            category = resolved
            break
    if category == "skirt" and siblings is not None and siblings < SKIRT_RING_MIN:
        # 裙摆是一圈；胯上只挂一两条的是围裙/尾巴/腰带。
        category = "cloth"
    if category is None and direction is not None and len(direction) >= 3:
        x, y, z = (float(v) for v in direction[:3])
        if y < -0.6:
            category = "cloth"             # 向下垂的整片：披风/大衣
        else:
            category = "ribbon"            # 朝前=胸口一带，朝后/朝外=翅膀/披挂，都按软饰品
    if category is None:
        category = swing_category(fallback_name if fallback_name is not None else anchor)
    return category


def geometric_swing_categories(bones, parent_of, positions, body_remap=None):
    """{骨名: 部件类型} —— 按**几何**给每条衣物链定档，一个骨名都不读（除了兜底）。

    `positions` = {骨名: Unity 空间位置}（用 `bone.head_local` 换算，别按 localPosition 累加）。
    三个信号见 `swing_category_by_geometry`：锚点（沿父链第一根身体骨，映射成游戏骨名）、
    同锚点上有几条链、链的整体垂向。判不出来才退回按名字。

    这一层的意义：按名字判**只对恰好用本作命名习惯的源有效** —— 原神 rip 的裙摆叫
    `Bone_HemA01_L`、MMD 叫 `スカート`，词表两个都不认，于是整条链拿到最保守的一档
    （飘带：不建链），裙摆该有的环形碰撞和限位全丢。
    """
    body = body_remap or {}
    groups = structural_bone_groups(bones, parent_of, body)
    chains, _anchor_of = resolve_chains(bones, parent_of, body)
    chain_of = {name: root for root, members in chains.items() for name in members}
    result = {}

    def centre(names):
        picked = [positions[name] for name in names if name in (positions or {})]
        if not picked:
            return None
        return [sum(item[axis] for item in picked) / len(picked) for axis in range(3)]

    for group in groups:
        # 锚点要换成**游戏骨名**：`_ANCHOR_CATEGORY` 那张表按游戏骨名匹配（Hips / Spine2 / …）
        anchor = body.get(group["anchor"], group["anchor"])
        # **一条链一个类别，不是一组一个**：类别决定这条链要不要挂环形碰撞链、取哪一档
        # 参数，语义单位就是链。一组一档时，同锚点的裙摆会把混进同组的尾巴/飘带一起
        # 判成 skirt（chs-sucu 实测 24 根一组）—— 和物理指令按组发是同一类错误。
        # 「同锚点有几条链」这个信号仍然取组级：一圈裙板本来就是靠"有几条"认出来的。
        for root in dict.fromkeys(chain_of[name] for name in group["members"]
                                  if name in chain_of):
            members = chains[root]
            pool = set(members)
            tips = [name for name in members
                    if not any((parent_of or {}).get(child) == name for child in pool)]
            start, end = centre([root]), centre(tips)
            direction = None
            if start and end:
                delta = [end[axis] - start[axis] for axis in range(3)]
                length = math.sqrt(sum(value * value for value in delta))
                if length > 1e-6:
                    direction = [value / length for value in delta]
            category = swing_category_by_geometry(
                anchor, direction=direction, siblings=group["chains"],
                fallback_name=root)
            for name in members:
                result[name] = category
    return result


def swing_category(name):
    lower = str(name).lower()
    for category, tokens in _SWING_CATEGORY_RULES:
        if any(token in lower for token in tokens):
            return category
    return "ribbon"


# P3：链类别 → 学马自己的布料驱动器。
#
# **只收参考骨是通用身体骨的三种。**530 套原版实测，各驱动器的 setting 引用指向：
#   Skirt.referenceBone           → Left/RightUpLeg      通用 ✅
#   Frill.referenceBone           → Left/RightArm        通用 ✅
#   HumanoidSleeve.referenceBone  → Left/RightHand       通用 ✅
#   Waist    → LeftWaist_O / LeftThigh_O                 每套服装自己的偏移骨 ❌
#   Furisode → LeftFurisodeA_O …                         同上 ❌
#   Poncho   → RightBackPoncho_move_in_O … 六个引用全是 *_O   同上 ❌
# 后三种装到别的服装上只会得到一串空引用，表现是"这块布不动"，日志还全绿 —— 那正是这一版
# 要消灭的静默洞，所以宁可不支持。ribbon 也不给驱动器：原版的蝴蝶结/飘带就是裸的
# ActorSwingDynamicBone，本来就该走摇物。
_DRIVER_BY_CATEGORY = {
    "skirt": ("Skirt", "{side}UpLeg"),
    "cloth": ("Frill", "{side}Arm"),
    "sleeve": ("HumanoidSleeve", "{side}Hand"),
}
# 有原版驱动器可用的部件类型。UI 拿它置灰、导出器拿它过滤 —— 两边读同一份，
# 免得表单让作者选一个"选了什么也不会发生"的组合（ribbon 就是这种）。
DRIVER_CATEGORIES = tuple(_DRIVER_BY_CATEGORY)


def load_driver_presets(path=None):
    """原版驱动器 setting 基准表（tools/scan_vanilla_drivers.py --install 产出）。"""
    target = Path(path) if path else Path(__file__).with_name("driver_presets.json")
    try:
        with open(target, "r", encoding="utf-8") as stream:
            return (json.load(stream) or {}).get("drivers") or {}
    except (OSError, ValueError):
        return {}


def build_driver_block(category, side, presets=None):
    """一根衣物骨的 `driver` 块；类别没有对应驱动器就返回 None。

    `side` 是 "Left"/"Right"；判不出边就不给驱动器 —— 参考骨是分左右的，猜错等于把裙子
    绑到另一条腿上。
    """
    entry = _DRIVER_BY_CATEGORY.get(str(category))
    if not entry or side not in ("Left", "Right"):
        return None
    kind, reference_template = entry
    presets = presets if presets is not None else load_driver_presets()
    setting = presets.get(kind)
    if not setting:
        return None
    bones = {name: reference_template.format(side=side) for name in (setting.get("bones") or {})}
    return {
        "type": kind,
        "ints": dict(setting.get("ints") or {}),
        "floats": dict(setting.get("floats") or {}),
        "vectors": {k: list(v) for k, v in (setting.get("vectors") or {}).items()},
        "bones": bones,
    }


_SIDE_SUFFIX = re.compile(r"[._](l|r)(?=$|[._\d])", re.IGNORECASE)


def bone_side(name):
    """骨名判左右。判不出返回 None —— 驱动器的参考骨分左右，猜错等于绑到另一条腿上。

    单字母缩写必须**卡边界**：`Cloth_Ribbon` 里有个 `_r`，按子串匹配会被判成右侧，
    然后裙子/袖子就绑到另一边去，而且离线完全看不出来。
    """
    text = str(name)
    lower = text.lower()
    if "左" in text:
        return "Left"
    if "右" in text:
        return "Right"
    if "left" in lower:
        return "Left"
    if "right" in lower:
        return "Right"
    match = _SIDE_SUFFIX.search(text)
    return None if not match else ("Left" if match.group(1).lower() == "l" else "Right")


def build_source_extra_bones(source_bones, extra_names, parent_by_name=None,
                             body_remap=None, default_swing=None, categories=None,
                             presets=None, driver_bones=None, weight_by_name=None,
                             dominant_by_name=None, swing_anchor_bones=None,
                             tip_offset_by_name=None):
    """Build runtime-created source bones plus a synthetic tip per leaf.

    每根骨的摆动参数按 **部件类别 × 链上角色** 从原版基准表取（`swing_presets.json`，
    530 套原版 body 的中位数）。角色由链结构定，不靠骨名：

      root  链根（父不是新骨）—— 原版基本都是惰性锚(spring/mass 近 0)，自身不摆、由子骨摆
      mid   链中段 —— 真正在摆的
      tip   合成链尾 `*_End` —— 定义末节朝向并补齐最后一层；缺了它会少一节有效链段

    以前这里只写 damping/stiffness/spring/mass/rootWeight/pendulum 六项，其余交给运行时
    `SetDefaultValues`。对照原版数据那是错的：`pendulumRange` 原版 84.6% 取 1.0（它是 pendulum
    的作用范围，留 0 等于重力项被乘没了）、`wind` 84.6% 取 1.0、`useLimit` 88.3% 是 1 且带真实
    角度限位。少写这几项，骨在数据上"参数齐全"，实际却既不下垂也不受风。

    ``categories`` = ``{骨名: 类别}``（作者显式指定，最高优先）；不给就按骨名猜。
    """
    records = {
        str(item["name"]): dict(item) for item in source_bones or ()
        if isinstance(item, dict) and item.get("name")
    }
    wanted = {str(name) for name in extra_names if str(name) in records}
    parents = parent_by_name or {}
    body = body_remap or {}
    presets = presets or load_swing_presets()
    explicit = {str(k): str(v) for k, v in (categories or {}).items()}
    # 手写覆盖文件里拼错的类别以前会原样留在 sidecar 里：参数悄悄回退到 ribbon，还因为
    # 非法类别查不到 useChain 而不建链 —— 两处静默降级。UI 枚举不会产出这种输入，外部
    # JSON 会，所以在这里挡住。
    unknown = sorted({value for value in explicit.values() if value not in presets})
    if unknown:
        raise ValueError(
            f"未知的部件类型 {unknown}；可用的是 {sorted(presets)}（检查装饰物理覆盖 JSON 的 swingCategories）")

    def parent_name(name):
        parent = parents.get(name)
        visited = set()
        while parent and parent not in visited:
            visited.add(parent)
            if parent in wanted:
                return parent
            if parent in body:
                return body[parent]
            parent = parents.get(parent)
        return "Hips"

    def chain_root(name):
        """这根骨所属链的链根（父不在新骨集合里的那根）。"""
        current, visited = name, set()
        while current not in visited:
            visited.add(current)
            parent = parents.get(current)
            if parent not in wanted:
                return current
            current = parent
        return name

    # 作者点名的类别要对**整条链**生效，不管点的是链根还是中段。以前只沿父链往上找，
    # 点中段时链根找不到 → 链根仍按名字猜成 ribbon → build_swing_chains 看链根的类别 →
    # 该建的链没建（实测 categories=['ribbon','skirt'] 而 swingChains=[]）。
    # 冲突时取**最靠近链根**的那次点名，保证同一条链只有一个类别。
    chain_category = {}
    for name in sorted(wanted):
        if name not in explicit:
            continue
        root = chain_root(name)
        depth, current = 0, name
        while current != root:
            current = parents.get(current)
            depth += 1
        if depth < chain_category.get(root, (10 ** 9, None))[0]:
            chain_category[root] = (depth, explicit[name])

    def category_of(name):
        root = chain_root(name)
        if root in chain_category:
            return chain_category[root][1]
        return swing_category(root)

    def swing_for(name, role, category):
        preset = dict(presets.get(category, presets["ribbon"])["roles"][role])
        preset.pop("range", None)
        # useWindGlobalForce 在游戏里是 bool。基准表按众数统计出来是 1/0，源模型抽出来
        # 也常是 1 —— 写成数字会让运行时的 nlohmann 抛 type_error.302，而那会让**整份
        # sidecar 解析失败、骨架 graft 整个跳过**（表现是网格根本没换、只有贴图生效）。
        preset["useWindGlobalForce"] = bool(preset.get("useWindGlobalForce", True))
        # 角度限位默认关掉：它是**按骨轴授权**的，而作者的骨轴和学马的不一样。实测原版
        # 摇物骨的子骨 100% 在 local -X（X=骨轴/扭转轴，所以锁成 [0,0]），MMD 源的子骨在
        # local -Z。原样搬过去等于把两条真·摆动轴一条锁死一条夹紧、反而放开扭转轴——
        # dress-2219/fuyuko 的飘带"参数全对却纹丝不动"就是这么来的。
        # 不做主轴置换：作者 rig 的骨轴可能是任意斜向，枚举不完，而猜错的代价正是"完全
        # 不动"这种最难查的故障。限位只是防穿模的精修，原版自己也有 18% 的飘带骨不开。
        # 源模型显式给了 useLimit 的（IP 源同用 ActorAnimation 中间件，轴向一致）照它的来。
        preset["useLimit"] = 0
        # 碰撞分组：原版是逐服装归属（Skirt0/Tops0/Custm0…），对 mod 新骨没有对应语义。
        # 显式写 -1(Everything) 而不是靠运行时兜底缺省 —— 缺省值不进 sidecar 就查不出来。
        preset.setdefault("collisionMask", -1)
        # 源模型自带 swing（IP 源同用 ActorAnimation 中间件，能直接抽出授权值）优先，
        # 但只覆盖它真给了的那几项，其余仍走原版基准 —— 源里没有 pendulumRange/wind/limit。
        override = dict(records.get(name, {}).get("swing") or {})
        if default_swing:
            override = {**dict(default_swing), **override}
        preset.update(override)
        preset["useWindGlobalForce"] = bool(preset["useWindGlobalForce"])
        return preset

    # P3 预设只在作者点名了骨时才载入 —— 不点名就完全不碰这条路径。
    driver_bones = {str(k): (str(v) if v else "") for k, v in (driver_bones or {}).items()}
    driver_presets = load_driver_presets() if driver_bones else {}

    is_leaf = {
        name: not any(parents.get(child) == name for child in wanted)
        for name in wanted
    }
    role_of = {
        name: "root" if parent_name(name) not in wanted else "mid" for name in wanted
    }
    # 链根按原版是**惰性锚**（spring/mass 近 0，自身不摆、由子骨摆）。可源模型常见一种链：
    # 几何全绑在链根上、子骨是空的末端骨（实测 Chain_R 66 顶点全在根、Chain_R_Aend 0 个）。
    # 那种链照拓扑出参数就是"摆的骨没有几何、有几何的骨不摆" —— 装了摇物画面纹丝不动，
    # 而 swingPrepared / modBonesRegistered 全绿，闸门一条都不报。
    # 所以参数档看几何在哪：根自己**主导**着顶点就按 mid 出（它自己摆）。
    # 判据必须是主导而不是有权重 —— 纯配角骨（有权重、从不主导）改了求解器，
    # 拖坏的是别人的形状，症状离被改的骨很远。
    # `swingRole` 仍是拓扑真值 —— build_swing_chains 要靠它找链根，不能动。
    # 两个判据分开，混用会各错一次：
    #   `weights`   任意权重 —— 判"这条链上一根有几何的骨都没有"（闸门①）
    #   `dominant`  主导顶点 —— 判"这块几何属于谁"（要不要让链根自己摆）
    # 用 dominant 判闸门①会误伤纯配角骨（`Spine_Bow_*_A` 主导 0 却带着 613 个顶点的权重）；
    # 用 weights 判角色降档会误伤同一批骨，让它们去拖别人的形状。
    weights = {str(k): float(v) for k, v in (weight_by_name or {}).items()}
    dominant = {str(k): float(v) for k, v in (dominant_by_name or {}).items()}

    def has_weight(name):
        return weights.get(name, 0.0) > 0.0

    def holds_geometry(name):
        return dominant.get(name, 0.0) > 0.0

    def descendants(name):
        stack, seen = [name], set()
        while stack:
            current = stack.pop()
            for child in wanted:
                if parents.get(child) == current and child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    anchor_swing = {str(n) for n in (swing_anchor_bones or ())}
    param_role = dict(role_of)
    anchor_only, anchor_applied = [], []
    if dominant:
        for name, role in role_of.items():
            if role != "root" or not holds_geometry(name):
                continue
            if any(holds_geometry(child) for child in descendants(name)):
                continue
            anchor_only.append(name)
            # **默认只报不改**：让链根自己摆是在替作者决定物理，而他可能就是要这块不动
            # （实机验过：开了之后腰侧挂坠/腰包/胸前蝴蝶结全晃起来，作者说不需要，
            # 而同一个模型里靴口花边恰恰要摆 —— 所以这是**逐链**的决定，不是全局开关）。
            if name in anchor_swing or any(child in anchor_swing
                                           for child in descendants(name)):
                param_role[name] = "mid"
                anchor_applied.append(name)

    result = []
    pending = set(wanted)
    while pending:
        ready = [name for name in pending if parents.get(name) not in pending]
        if not ready:
            raise ValueError("新骨骼父链存在循环，无法生成 sidecar")
        for name in sorted(ready):
            item = records[name]
            category = category_of(name)
            result.append({
                "name": name,
                "parentName": parent_name(name),
                "localPosition": list(item.get("localPosition") or [0.0, 0.0, 0.0]),
                "localRotation": list(item.get("localRotation") or [0.0, 0.0, 0.0, 1.0]),
                "localScale": list(item.get("localScale") or [1.0, 1.0, 1.0]),
                "swingCategory": category,
                "swingRole": role_of[name],
                "swing": swing_for(name, param_role[name], category),
            })
            if param_role[name] != role_of[name]:
                # 留痕：这根骨是链根，但几何全在它身上，所以按 mid 出参数让它自己摆
                result[-1]["swingParamRole"] = param_role[name]
            # P3：**作者点名的那几根骨**才改走姿势驱动器。以前这里收的是"类别集合"，
            # 于是一行选了 skirt，全模型所有 skirt 类别的新骨都跟着走 —— 作者点的是一条链，
            # 拿到的是整件衣服。默认空 dict：不点名就和以前逐字节一样，现有成品重导无差异。
            # 驱动器和摇物二选一（运行时也这么执行），所以挂上驱动器就把 swing 去掉。
            if name in driver_bones:
                block = build_driver_block(driver_bones[name] or category,
                                           bone_side(name), driver_presets)
                if block:
                    result[-1]["driver"] = block
                    result[-1].pop("swing", None)
            if item.get("bindPose") is not None:
                result[-1]["bindPose"] = item["bindPose"]
            pending.remove(name)

    extra_tips = []
    for name in sorted(wanted):
        if not is_leaf[name]:
            continue
        length = float(records[name].get("length") or 0.0)
        # 链尾位置按几何来（该骨主导顶点的质心，见 `operators._dominant_group_tip_offsets`）。
        # 兜底才用骨长沿局部 -Z：那是 Blender 骨的默认轴，源骨的轴是任意的，硬写会让
        # 解算按错的方向拽（实测：前裙板链尾指向正侧向 → 裙片整体偏一边）。
        offset = (tip_offset_by_name or {}).get(name)
        if offset is None:
            if length <= 1e-8:
                continue
            offset = [0.0, 0.0, -length]
        category = category_of(name)
        extra_tips.append({
            "name": f"{name}_End",
            "parentName": name,
            "localPosition": [float(value) for value in offset],
            "localRotation": [0.0, 0.0, 0.0, 1.0],
            "localScale": [1.0, 1.0, 1.0],
            "swingCategory": category,
            "swingRole": "tip",
            "swing": swing_for(f"{name}_End", "tip", category),
        })
    return {
        "newBones": result,
        "extraSwingBones": extra_tips,
        "swingChains": build_swing_chains(result, extra_tips, presets),
        "anchorOnlyChains": sorted(anchor_only),
        "anchorSwingApplied": sorted(anchor_applied),
        "emptyChains": sorted(
            name for name, role in role_of.items()
            if weights and role == "root"
            and not has_weight(name)
            and not any(has_weight(child) for child in descendants(name))),
    }


def build_swing_chains(new_bones, extra_tips, presets=None):
    """哪些新骨要挂 `ActorSwingChain`，挂在哪根宿主骨上，按链长分组。

    原版实测：裙类 94% 挂链、披风类 54% 挂链，而**飘带/绳结类只有 2.6%**——蝴蝶结和
    飘带在原版里就是裸 `ActorSwingDynamicBone`，靠 `swingDynamicBones` 逐骨模拟，
    根本没有链。链多带一层 `around/radius` 的环形碰撞解算，那是裙摆专用的。所以这里
    只给 `useChain` 的类别建链。

    **必须按链长分组**：`UpdateChainInfo` 只给一条链它最短成员那么多层，长短混在一条
    链里会把长链截断。分组在这里离线算，运行时照单执行、不做启发式。
    """
    presets = presets or load_swing_presets()
    parent_of = {item["name"]: item["parentName"] for item in new_bones}
    parent_of.update({item["name"]: item["parentName"] for item in extra_tips})
    category_of = {item["name"]: item.get("swingCategory") for item in new_bones}
    created = set(parent_of)

    children_of = {}
    for child, parent in parent_of.items():
        children_of.setdefault(parent, []).append(child)

    def depth(name):
        # 含链尾 tip 的链长，和 UpdateChainInfo 的走法一致。
        return 1 + max((depth(child) for child in children_of.get(name, ())), default=0)

    def forked(name):
        """链上有没有分叉。UpdateChainInfo 只沿**第一个**子节点建层，所以一根骨带两个子分支
        时，另一支不可能进入链层 —— 而我们却按"最深那支"报了个链长，等于静默建了条只覆盖
        一半的链。分叉的链干脆不建：那些骨照样进 swingDynamicBones 逐骨模拟（原版飘带就是
        这么摆的），只是没有链那层环形碰撞，属于安全降级。"""
        stack = [name]
        while stack:
            current = stack.pop()
            branches = children_of.get(current, ())
            if len(branches) > 1:
                return True
            stack.extend(branches)
        return False

    groups = {}
    for item in new_bones:
        if item["swingRole"] != "root":
            continue
        category = category_of.get(item["name"]) or "ribbon"
        if not presets.get(category, {}).get("useChain"):
            continue
        # 链长 1 = 只有一根骨、没有链尾 → 没有可摆的骨，建了也是空转。
        length = depth(item["name"])
        if length < 2 or forked(item["name"]):
            continue
        groups.setdefault((item["parentName"], category, length), []).append(item["name"])

    return [{"host": host, "category": category, "chainLength": length,
             "rootBones": sorted(roots)}
            for (host, category, length), roots in sorted(groups.items())
            if host not in created]


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
