# -*- coding: utf-8 -*-
"""rui-nurs 贴图 → 学马 t0/t1/t4 + native-co(纯 Python/PIL,不进 Blender)。

对 body 与 bodyco 各一套:
  t0 = 源 _col(base color,原样;肤色校准留作进游戏后微调,需 hmsz-0000 皮肤采样)
  t1 = 逐像素分类(skin/metal/glossy/matte/cloth)→ material_presets 的
       (toonShadowThreshold, smoothness, metallic, ao) 写成 RGBA。t1.A 是数据遮罩不是透明度。
  t4 = 源 _sdw,A 通道改为皮肤二值 mask(t4.A=1 走皮肤暗色分支)。

分类判据与 process_geo_body.classify_pixel 完全一致(同源,保证 COLOR 与贴图不打架)。
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source"
TEX = SRC / "textures"
OUT = ROOT / "build" / "textures"
PRESETS = ROOT.parents[2] / "gakumas-modding" / "gakumas_mi" / "material_presets.json"


def load(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0


def save(arr, path):
    Image.fromarray(np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGBA").save(path)


def convert(base, defm, shade, presets):
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    cls = defm[..., 1]
    skin = (cls < 0.57) & (r > 0.65) & (r > g * 1.05) & (g > b * 1.03) & (b > 0.35)
    metal = cls >= 0.80
    glossy = (cls >= 0.70) & ~metal
    matte = (cls >= 0.62) & ~glossy & ~metal
    cloth = ~(skin | metal | glossy | matte)
    t1 = np.zeros_like(defm)
    for region, key in ((cloth, "cloth"), (matte, "leather_shoe"), (glossy, "leather_plastic"),
                        (metal, "metal"), (skin, "skin")):
        p = presets[key]["t1"]
        t1[region] = (p["toonShadowThreshold"], p["smoothness"], p["metallic"], p["ao"])
    t4 = shade.copy()
    t4[..., 3] = skin.astype(np.float32)
    counts = {k: int(v.sum()) for k, v in (("skin", skin), ("cloth", cloth),
              ("matte", matte), ("glossy", glossy), ("metal", metal))}
    return t1, t4, counts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    presets = json.loads(PRESETS.read_text(encoding="utf-8"))["presets"]
    report = {}
    for tag, col, dfn, sdw in (
        ("bdy", "t_chr_rui-nurs-00_bdy_col.png", "t_chr_rui-nurs-00_bdy_def.png",
         "t_chr_rui-nurs-00_bdy_sdw.png"),
        ("bdyco", "t_chr_rui-nurs-00_bdyco_col_alp.png", "t_chr_rui-nurs-00_bdyco_def.png",
         "t_chr_rui-nurs-00_bdyco_sdw.png"),
    ):
        base, defm, shade = load(TEX / col), load(TEX / dfn), load(TEX / sdw)
        t1, t4, counts = convert(base, defm, shade, presets)
        save(base, OUT / f"rui_{tag}_t0.png")   # base color;bdyco 保留 cutout alpha
        save(t1, OUT / f"rui_{tag}_t1.png")
        save(t4, OUT / f"rui_{tag}_t4.png")
        report[tag] = counts
    (ROOT / "build" / "texture-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("skinCalibration: SKIPPED (first pass; add after in-game check w/ hmsz-0000 skin sample)")


if __name__ == "__main__":
    main()
