// Per-surface constants: what the author's label resolves to.
//
// Source: gakumas_mi/material_presets.json, derived from frame analysis of stock draws, cross-checked
// here against the raw textures of four stock costumes (fktn-cstm-0001, jsna-casl-0002,
// ttmr-cstm-0119, hmsz-cstm-0059).
//
// One correction to the preset library, on our own measurement: its `metal` row carries
// metallic 0.75, which comes from hair accessories. Every stock *body* measures t1.B = 0.000, on both
// skin and cloth, in all four costumes — and a metallic body surface indoors mixes in enough of the
// dark environment probe to render black (that is exactly what a foreign model's 0.486 did). So
// metallic is pinned to 0 here regardless of surface.
using UnityEngine;

namespace GakumasSdk
{
    public readonly struct SurfacePreset
    {
        /// <summary>Vertex COLOR: outline nibbles / LUT row / outline width / rim. See GakumasVertexColor.</summary>
        public readonly Color32 Color;

        /// <summary>t1 = _DefMap: R toon threshold · G smoothness · B metallic · A AO.</summary>
        public readonly Color32 Def;

        /// <summary>t4 = _ShadeMap RGB multiplier over the base map, used only when the source has no shade map.</summary>
        public readonly float Darken;

        public SurfacePreset(Color32 color, float toon, float smoothness, float ao, float darken)
        {
            Color = color;
            Def = new Color32(Byte(toon), Byte(smoothness), 0, Byte(ao));
            Darken = darken;
        }

        private static byte Byte(float value) => (byte)Mathf.Clamp(Mathf.RoundToInt(value * 255f), 0, 255);
    }

    public static class SurfacePresets
    {
        public static SurfacePreset Of(SurfaceClass surface) => surface switch
        {
            // Stock skin measures toon 0.486-0.494 and smoothness 0.498-0.502 across all four
            // costumes — flat, and notably not the preset library's 0.45 / 0.13. Measurement wins.
            SurfaceClass.Skin => new SurfacePreset(new Color32(81, 0, 15, 144), 0.49f, 0.50f, 0f, 1.0f),
            // Measured against the costume this replaces (hmsz-cstm-0059, AssetStudio dump) and against
            // the population in `reference/body-color-inventory.json` — 410 stock bodies, 7.06M
            // vertices, `tools/inventory_body_colors.py`:
            //
            //   G low  = 15  row of `_RampAddMap`, the per-costume 128×16 additive-ambient strip. Row 0
            //               is solid black. 0059's dominant cloth is (51,79,15,144) → row 15, so 15 is
            //               right *for the map we inherit*; the population uses only 0/3/6/9/12/15.
            //   A high = 9   the rim / backlight term. 65.9% of all stock vertices carry 9, and 23 of
            //               the 24 scanned hmsz costumes have it in their dominant value. The preset
            //               library's 0 came from the 3Dmigoto route and is the one field a bright room
            //               hides: with no backlight term the body reads as a black silhouette the
            //               moment the scene light drops.
            //   B      = 15  only the low nibble is outline width, but stock writes the byte as 15, not
            //               255 — the high nibble is undocumented, so match what stock does.
            //
            // R and G high stay 0 (black outline). 0059's cloth inks (3,3,4), a dark grey, but ink
            // colour is per-garment art and black is the safe default for a mod.
            SurfaceClass.Cloth => new SurfacePreset(new Color32(0, 15, 15, 144), 0.38f, 0.40f, 0f, 0.45f),
            SurfaceClass.LeatherPlastic => new SurfacePreset(new Color32(0, 28, 15, 144), 0.50f, 0.70f, 0.54f, 0.59f),
            SurfaceClass.LeatherShoe => new SurfacePreset(new Color32(33, 6, 15, 0), 0.42f, 0.38f, 0.10f, 0.45f),
            SurfaceClass.Metal => new SurfacePreset(new Color32(17, 16, 15, 144), 0.34f, 0.73f, 0.57f, 0.32f),
            _ => Of(SurfaceClass.Cloth),
        };

        /// <summary>
        /// Vertex COLOR for a hair part. Hair is a *different population* from the body, measured over
        /// the 379 stock hair parts by `tools/inventory_hair_colors.py`
        /// (`reference/hair-color-inventory.json`) — not assumed to match the body:
        ///
        ///   G low  = 0   the `_RampAddMap` row. **99.6% of stock hair vertices carry row 0**, against
        ///                the body's spread over 0/3/6/9/12/15. Reusing the body's cloth preset here
        ///                would point hair at row 15 of a strip hair does not use.
        ///   A high = 9   the rim term, 58.1% of hair vertices and 73.9% of hair-prop vertices — the
        ///                same value the body lands on. Worth stating plainly because the 3Dmigoto-era
        ///                hair preset pinned A = 0: that was a workaround for shipping without t6, not
        ///                this game's semantics, and the population says so.
        ///   R, G high = 0  black ink. Stock hair inks in colour (r_hi spreads 0-4) because the outline
        ///                is tinted to that character's hair; black is the safe default for a mod whose
        ///                hair colour is unknown.
        ///   B      = 15  outline width. This is the one field with **no stock constant** — hair widths
        ///                are authored per vertex and spread flat across 0-15, unlike the body's 49.5%
        ///                at 15. 15 matches what the body preset writes and stays inside the stock
        ///                range; an author who wants stock's tapering has to paint COLOR.B themselves.
        /// </summary>
        public static readonly Color32 Hair = new Color32(0, 0, 15, 144);
    }
}
