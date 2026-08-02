"""Blender-independent Profile, buffer, validation and package helpers."""

from __future__ import annotations

import hashlib
import json
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


def merge_material_groups(co_slots, target_submesh_count, materials):
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
    target = max(1, int(target_submesh_count or 1))
    group_of = lambda slot: 1 if int(slot) in co_slots else 0
    used = {group_of(slot) for slot in materials} if materials else {0}
    if target == 1 and 1 in used:
        raise ValueError(
            "目标 body 只有 bdy 一段，但你的网格含 co(NATIVE_CO)材质；"
            "请去掉 co 材质，或选一个带 bdyco 的目标服装")
    if max(used) >= target:
        raise ValueError(
            f"网格材质分组 {sorted(used)} 超出目标 body 的 {target} 段；"
            "请把材质合并到 bdy" + ("(和 bdyco)" if target > 1 else ""))
    return [group_of(slot) for slot in materials]


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


def write_bundle_source(
    output_root, package_id, source, component_id, name, author, data,
    mesh_json, skeleton_json, textures, material_slot_count=1, version="0.1.0",
):
    """Write the Unity-independent source files consumed by the Phase 2 build."""
    package_id = _sanitize_package_id(package_id)
    source = str(source or "").strip()
    if not source or Path(source).name != source:
        raise ValueError("bundle source 的 source 必须是单个资源名")
    bundle_dir = Path(output_root) / package_id / "bundle-src"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    source_mesh = load_json(Path(mesh_json))
    skeleton = load_json(Path(skeleton_json))
    extra_nodes = data.get("bundle_extra_skeleton_nodes") or []
    if extra_nodes:
        skeleton = dict(skeleton)
        skeleton["nodes"] = list(skeleton.get("nodes") or []) + extra_nodes
    geo, bones = _bundle_geojson(data, source_mesh, skeleton, material_slot_count)

    renderer_names = {"body": "Geo_Body", "hair": "Geo_Hair", "hairprop": "Geo_HairProp"}
    renderer_name = renderer_names.get(component_id, "Geo_Body")
    asset_root = f"Assets/Mods/{package_id}"
    geo_name = f"{source}.geojson.txt"
    bones_name = f"{package_id}_bones.json.txt"
    prefab_name = f"{source}.prefab"
    bundle_name = f"{package_id}.bundle"
    _write_json(bundle_dir / geo_name, geo)
    source_report = data.get("source_rig_report", {})
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
        if not extra_nodes:
            sidecar["newBones"] = source_report["newBones"].get("newBones", [])
        sidecar["extraSwingBones"] = source_report["newBones"].get("extraSwingBones", [])
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
    for value in (geo, sidecar, texture_entries):
        build_id_hash.update(json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))
        build_id_hash.update(b"\0")
    for item in sorted(texture_entries, key=lambda entry: entry["asset"]):
        path = bundle_dir / Path(item["asset"]).name
        build_id_hash.update(path.name.encode("utf-8"))
        build_id_hash.update(hashlib.sha256(path.read_bytes()).digest())
    build_id = build_id_hash.hexdigest()[:16]
    sidecar["buildId"] = build_id
    _write_json(bundle_dir / bones_name, sidecar)

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
            "part": "body" if component_id != "hair" else "hair",
            "priority": 0,
            "bundle": bundle_name,
            "asset": f"{asset_root}/{prefab_name}",
            "skeleton": f"{asset_root}/{bones_name}",
            "type": "GameObject",
            "renderers": [{
                "rendererId": component_id,
                "targetRenderer": renderer_name,
                "modRenderer": renderer_name,
            }],
            "replaceMaterials": False,
            "textures": texture_entries,
        }],
    }
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


def _best_preset(source, target, presets, preferred=None):
    """逐张表试算命中数，取最高的那张。

    嗅探（detect_source_rig）只用来打平手：这样以后支持一种新命名规范＝纯加一张表，
    不用再加嗅探分支，也不会因为嗅探探针没命中就让整张表空转。
    """
    def hits(key):
        bones = presets.get(key, {}).get("bones", {})
        return sum(1 for name in source if _preset_target(name, bones) in target)

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
        candidate = _preset_target(name, preset_bones)
        if candidate in target:
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


def critical_coverage_error(source_names, remap, target_bones):
    """承重关节零权重 → 返回报错文案，正常返回 None。

    不猜源骨语义，只查游戏侧的胳膊腿有没有拿到权重，所以对任何命名规范都适用；
    与目标骨架取交集，骨很少的测试/局部骨架不会误报。位置匹配永远能返回一个骨名，
    不拦就是静默出废品——这是唯一便宜且可靠的拦法。
    """
    target = set(target_bones)
    hit = {remap.get(name) for name in source_names}
    missing = [name for name in CRITICAL_TARGET_BONES
               if name in target and name not in hit]
    if not missing:
        return None
    return ("以下承重关节没有拿到任何权重：" + "、".join(missing)
            + f"（共 {len(missing)} 个）。源模型的骨名没有被识别，这样导出进游戏会让"
              "这些部位跟着别的骨乱跑。请在导出面板「骨骼映射表」里扫描并指定对应关系。")


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
        # ponytail: name-only grouping is a heuristic; provide group_by_name for
        # assets whose left/right pieces are not named symmetrically.
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

    def directive_for(names):
        for name in names:  # author override wins outright
            directive = override_for(name)
            if directive:
                return directive
        semantics = [semantic_for(name) for name in names]
        if "integrate" in semantics:  # preserve old any(is_source_chain) behaviour
            return "integrate"
        for directive in semantics:
            if directive:
                return directive
        return None

    groups = {}
    for name in accessory:
        lower = name.lower()
        kind = "segment" if any(token in lower for token in ("skirt", "dress", "cloth")) else "group"
        key = name if kind == "segment" else group_key(name)
        groups.setdefault((kind, key), []).append(name)

    mapping, strategies, rigid, new_bones = {}, {}, {}, []
    for (kind, _key), names in groups.items():
        directive = directive_for(names)

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
            position = tuple(
                sum(source[name][axis] for name in names) / len(names)
                for axis in range(3)
            )
            candidate, distance_sq = nearest(position)
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
            position = tuple(
                sum(source[name][axis] for name in names) / len(names)
                for axis in range(3)
            )
            candidate = bust_target(position)
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
        position = tuple(
            sum(source[name][axis] for name in names) / len(names)
            for axis in range(3)
        )
        candidate, distance_sq = nearest(
            position, skirt_swing_names if follow_skirt else None
        )
        if candidate is None:
            new_bones.extend(names)
            for name in names:
                strategies[name] = "new_bone"
            continue
        # follow_skirt (lace) rides the skirt even past max_distance — its bones sit at the
        # hem, farther from the skirt bones' anchors than the cutoff. Position-default falls
        # back to a rigid body parent when the nearest swing bone is too far.
        if distance_sq > max_distance_sq and not follow_skirt:
            for name in names:
                rigid[name] = rigid_parent(name)
                strategies[name] = "rigid_parent"
            continue
        for name in names:
            mapping[name] = candidate
            strategies[name] = "segment_nearest" if kind == "segment" else "group_centroid"

    return {
        "targetSwingBones": swing_names,
        "bones": mapping,
        "strategies": strategies,
        "rigidParent": rigid,
        "newBones": new_bones,
        "unmapped": [name for name in accessory if name not in mapping and name not in rigid],
        "maxDistance": float(max_distance),
    }


def build_source_extra_bones(source_bones, extra_names, parent_by_name=None,
                             body_remap=None, default_swing=None):
    """Build runtime-created source bones plus a synthetic tip per leaf."""
    records = {
        str(item["name"]): dict(item) for item in source_bones or ()
        if isinstance(item, dict) and item.get("name")
    }
    wanted = {str(name) for name in extra_names if str(name) in records}
    parents = parent_by_name or {}
    body = body_remap or {}
    swing = dict(default_swing or {
        "damping": 0.5, "stiffness": 0.02, "spring": 0.5,
        "mass": 0.15, "useWindGlobalForce": True,
    })

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

    result = []
    pending = set(wanted)
    while pending:
        ready = [name for name in pending if parents.get(name) not in pending]
        if not ready:
            raise ValueError("新骨骼父链存在循环，无法生成 sidecar")
        for name in sorted(ready):
            item = records[name]
            result.append({
                "name": name,
                "parentName": parent_name(name),
                "localPosition": list(item.get("localPosition") or [0.0, 0.0, 0.0]),
                "localRotation": list(item.get("localRotation") or [0.0, 0.0, 0.0, 1.0]),
                "localScale": list(item.get("localScale") or [1.0, 1.0, 1.0]),
                "swing": dict(item.get("swing") or swing),
            })
            if item.get("bindPose") is not None:
                result[-1]["bindPose"] = item["bindPose"]
            pending.remove(name)

    extra_tips = []
    for name in sorted(wanted):
        if not any(parent == name for parent in parents.values() if parent in wanted):
            item = records[name]
            length = float(item.get("length") or 0.0)
            if length <= 1e-8:
                continue
            extra_tips.append({
                "name": f"{name}_End",
                "parentName": name,
                "localPosition": [0.0, 0.0, -length],
                "localRotation": [0.0, 0.0, 0.0, 1.0],
                "localScale": [1.0, 1.0, 1.0],
                "swing": dict(swing),
            })
    return {"newBones": result, "extraSwingBones": extra_tips}


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
