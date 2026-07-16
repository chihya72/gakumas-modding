# -*- coding: utf-8 -*-
"""rui-nurs Geo_Body.json 处理器(纯 Python,不进 Blender)。

两件事,顶点/法线/切线/UV/权重一律不动:
  1. 保留源权重:无损 AB 路线由插件在运行时嫁接 IP 专属骨,这里不能再 reparent。
  2. COLOR 描边:按源 _def(t1 打包遮罩)+ _col 在每顶点 UV 处分类
     (skin/metal/glossy/matte/cloth → 学马描边类),只改描边 3 个半字节
     R.hi/R.lo/G.hi + 宽度 B.lo=15,保留源 ramp/rim 字段 G.lo/B.hi/A。
     方法标识 TEMPLATE_OUTLINE_RGB_WIDTH15_PRESERVE_GLOW_BHIGH_A(同 miku fktn-0119)。

用法:python process_geo_body.py   (路径写死本项目)
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source"
BUILD = ROOT / "build"
PRESETS = ROOT.parents[2] / "gakumas-modding" / "gakumas_mi" / "material_presets.json"
TEX = SRC / "textures"

TEMPLATE_CLASSES = ("skin", "cloth", "leather_shoe", "leather_plastic", "metal")
# 源像素 5 分类 → 描边类(见 fktn-0119 03 脚本:matte=leather_shoe, glossy=leather_plastic)
REGION_TO_CLASS = {"skin": "skin", "cloth": "cloth", "matte": "leather_shoe",
                   "glossy": "leather_plastic", "metal": "metal"}


def load_rgba(path):
    img = Image.open(path).convert("RGBA")
    return np.asarray(img, dtype=np.float32) / 255.0  # (h,w,4), row 0 = top


def sample(arr, u, v):
    h, w, _ = arr.shape
    x = min(w - 1, max(0, int((u % 1.0) * (w - 1))))
    y = min(h - 1, max(0, int(((1.0 - (v % 1.0)) % 1.0) * (h - 1))))  # Unity uv -> top-down row
    return arr[y, x]


def classify_pixel(base_rgb, def_g):
    """返回 skin/metal/glossy/matte/cloth 之一。与 convert_material_maps 同判据。"""
    r, g, b = base_rgb
    if def_g < 0.57 and r > 0.65 and r > g * 1.05 and g > b * 1.03 and b > 0.35:
        return "skin"
    if def_g >= 0.80:
        return "metal"
    if def_g >= 0.70:
        return "glossy"
    if def_g >= 0.62:
        return "matte"
    return "cloth"


def main():
    mesh = json.loads((SRC / "rui_Geo_Body.json").read_text(encoding="utf-8"))
    bones = json.loads((BUILD / "rui_bones.json").read_text(encoding="utf-8"))["bones"]
    presets = json.loads(PRESETS.read_text(encoding="utf-8"))["presets"]
    V = mesh["m_VertexCount"]

    # ---- 1. 源权重保持不变 ----
    skin = mesh["m_Skin"]
    for s in skin:
        assert len(s["weight"]) == 4 and len(s["boneIndex"]) == 4, "骨权重不是四影响"
        assert all(0 <= bi < len(bones) for bi in s["boneIndex"]), "骨索引越界"

    # ---- 2. COLOR 描边 ----
    base = load_rgba(TEX / "t_chr_rui-nurs-00_bdy_col.png")
    defm = load_rgba(TEX / "t_chr_rui-nurs-00_bdy_def.png")
    co_base = load_rgba(TEX / "t_chr_rui-nurs-00_bdyco_col_alp.png")
    co_def = load_rgba(TEX / "t_chr_rui-nurs-00_bdyco_def.png")
    # 每顶点材质:submesh0(m_bdy)=firstVertex 0..，submesh1(m_bdyco)=后段
    sm = mesh["m_SubMeshes"]
    co_first = sm[1]["firstVertex"] if len(sm) > 1 else V
    uv = mesh["m_UV0"]
    colors = mesh["m_Colors"]  # 扁平 RGBA float, 4/vertex
    outline_rgba = {k: bytes(presets[k]["color"]["rgba"]) for k in TEMPLATE_CLASSES}

    from collections import Counter
    cls_count = Counter()
    for vi in range(V):
        u, v = uv[vi * 2], uv[vi * 2 + 1]
        if vi >= co_first:
            reg = classify_pixel(sample(co_base, u, v)[:3], sample(co_def, u, v)[1])
        else:
            reg = classify_pixel(sample(base, u, v)[:3], sample(defm, u, v)[1])
        klass = REGION_TO_CLASS[reg]
        cls_count[klass] += 1
        tmpl = outline_rgba[klass]
        # 当前源字节
        o = [int(round(min(1.0, max(0.0, colors[vi * 4 + c])) * 255)) for c in range(4)]
        o[0] = tmpl[0]                              # R = 描边 R.hi<<4|R.lo(整字节取预设)
        o[1] = (tmpl[1] & 0xF0) | (o[1] & 0x0F)     # G.hi=描边 B nibble;G.lo 保留
        o[2] = (o[2] & 0xF0) | 0x0F                 # B.hi 保留;B.lo=宽度 15
        # A 保留
        for c in range(4):
            colors[vi * 4 + c] = o[c] / 255.0

    # 自检:抽样验证 nibble 语义
    for vi in (0, V // 2, V - 1):
        b2 = int(round(colors[vi * 4 + 2] * 255))
        assert b2 & 0x0F == 15, "宽度 nibble 未置 15"

    mesh["m_Skin"] = skin
    mesh["m_Colors"] = colors
    out = BUILD / "rui_Geo_Body.processed.json"
    out.write_text(json.dumps(mesh, ensure_ascii=False), encoding="utf-8")

    report = {
        "method_weight": "PRESERVE_SOURCE_BONE_WEIGHTS_FOR_HYBRID_SKELETON",
        "method_color": "TEMPLATE_OUTLINE_RGB_WIDTH15_PRESERVE_GLOW_BHIGH_A",
        "vertexCount": V,
        "reparentedVertices": 0,
        "reparentMap": {},
        "outlineClasses": dict(cls_count),
        "outlineNibblesByClass": {k: [outline_rgba[k][0] >> 4, outline_rgba[k][0] & 0x0F,
                                      outline_rgba[k][1] >> 4] for k in TEMPLATE_CLASSES},
        "widthNibble": 15,
        "output": str(out),
    }
    (BUILD / "process-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
