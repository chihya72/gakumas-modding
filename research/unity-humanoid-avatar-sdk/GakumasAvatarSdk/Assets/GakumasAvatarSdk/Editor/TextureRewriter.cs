// Rewrite a foreign model's textures into this game's semantics.
//
// The frozen channel meanings (research/hair-pipeline.md + gakumas_mi/material_presets.json, both
// from frame analysis):
//
//   t1 = _DefMap   R toon shadow threshold · G smoothness · B metallic · A AO / indirect gate
//   t4 = _ShadeMap RGB the shade painting · A binary skin mask
//
// Measured on mdl_chr_hmsz-cstm-0059_body, which is the ground truth here:
//
//   t4.A    0 across 88.5% of the sheet, 254/255 on the rest; the accessory sheets are 100% zero.
//   t4.RGB  on skin it is *identical* to the base map (the darken factor solves to exactly 1.000);
//           on cloth it varies continuously between 0.44 and 0.79 — painted, not computed.
//   t1.B    0.000 everywhere. Bodies in this game are never metallic.
//   t1.A    0.000 on skin, ~0.11 on cloth.
//   t1.R/G  skin 0.494/0.502, cloth 0.412/0.529.
//
// A foreign model brings usable paint but its own meanings. IP's sucu sheet shades cloth at ~0.45 of
// base (same as this game) yet its t4 alpha is 13/255 across 82.6% of the sheet, so every bit of
// bare skin read as cloth and came out grey; and its t1.B puts metallic at 0.486 on skin, which in
// an indoor scene mixes in enough of the dark environment probe to render the skin nearly black.
//
// So: keep the paint, fix the fields whose meaning does not carry over.
using System.IO;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class TextureRewriter
    {
        private const string Suffix = ".gakumas";

        /// <summary>Corrected texture paths plus the skin mask, which the mesh needs too.</summary>
        public sealed class Rewrite
        {
            public string ShadePath;
            public string DefPath;
            public bool[] Mask;
            public int Width;
            public int Height;

            /// <summary>UV space matches GetPixels32: index 0 is the bottom-left pixel.</summary>
            public bool IsSkinAt(Vector2 uv)
            {
                if (Mask == null)
                    return false;
                var x = Mathf.Clamp(Mathf.FloorToInt(Mathf.Repeat(uv.x, 1f) * Width), 0, Width - 1);
                var y = Mathf.Clamp(Mathf.FloorToInt(Mathf.Repeat(uv.y, 1f) * Height), 0, Height - 1);
                return Mask[y * Width + x];
            }
        }

        /// <summary>
        /// Writes corrected _ShadeMap and _DefMap next to the sources, and returns them together
        /// with the skin mask. Never null: a sheet that cannot be rewritten comes back empty and the
        /// caller falls back to the source textures.
        /// </summary>
        /// <param name="label">The author's label for this material section; see GakumasBodyLabels.</param>
        /// <param name="model">Restricts every lookup to this model's own sheets. The external route
        /// stages all models into one shared directory, so an unscoped `*_bdy_sdw*.png` matched the
        /// *previous* build's shade map and the actor silently rendered with another model's t4 —
        /// which the log reported as a normal rewrite. Null keeps the old any-file behaviour for
        /// callers that already hand over a per-model directory (BodyImporter).</param>
        public static Rewrite Build(string directory, string group, SubmeshLabel label, string model = null)
        {
            var hasSkin = label.surface == SurfaceClass.Skin || label.hasBareSkin;
            var result = new Rewrite();
            var scope = model == null ? "*" : $"*{model}";
            var colPath = FirstMatch(directory, $"{scope}_{group}_col*.png");
            var sdwPath = FirstMatch(directory, $"{scope}_{group}_sdw*.png");
            if (colPath == null)
            {
                Debug.LogWarning($"[SDK] {group}: 缺 col，跳过贴图改写");
                return result;
            }

            var col = Load(colPath);
            if (col == null)
                return result;
            // A model from outside this family ships one map per material and nothing else — no shade
            // sheet, no def sheet. That is not a failure case, it is the common case: MMD, VRM and
            // game rips all look like this. The surface preset carries what to synthesise (`Darken`
            // exists for exactly this), so the missing sheets are built from the base map instead of
            // bailing out and leaving the actor wearing the replaced costume's maps on our UVs.
            var sdw = sdwPath == null ? null : Load(sdwPath);
            if (sdw != null && (col.width != sdw.width || col.height != sdw.height))
            {
                Debug.LogError($"[SDK] {group}: col {col.width}x{col.height} 与 sdw {sdw.width}x{sdw.height} 尺寸不同，无法逐像素改写");
                return result;
            }

            var mask = BuildMask(directory, scope, group, hasSkin, col, out var skinRatio, out var maskSource);
            result.Mask = hasSkin ? mask : null;
            result.Width = col.width;
            result.Height = col.height;
            result.ShadePath = sdw != null
                ? WriteShade(directory, sdwPath, col, sdw, mask)
                : SynthesizeShade(directory, colPath, col, mask, label);
            Debug.Log($"[SDK] {group}: 标注 {label.surface}{(label.hasBareSkin ? " + 含裸露皮肤" : "")}，" +
                      $"t4 已改写 → {Path.GetFileName(result.ShadePath)}，" +
                      $"皮肤 {skinRatio * 100f:F1}%（{maskSource}，原版 body 量级 11.3%）");

            result.DefPath = WriteDef(directory, scope, model, group, mask, label, col.width, col.height);
            return result;
        }

        // An author-painted mask always wins: the colour heuristic scores 0.94 precision / 0.95
        // recall against stock data, which is good but not a substitute for knowing.
        private static bool[] BuildMask(string directory, string scope, string group, bool hasSkin, Texture2D col,
            out float skinRatio, out string source)
        {
            var painted = hasSkin ? Load(FirstMatch(directory, $"{scope}_{group}_skin*.png")) : null;
            if (painted != null && (painted.width != col.width || painted.height != col.height))
            {
                Debug.LogError($"[SDK] {group}: 手绘 mask 尺寸与 col 不同，忽略");
                painted = null;
            }

            var basePixels = col.GetPixels32();
            var paintedPixels = painted?.GetPixels32();
            var mask = new bool[basePixels.Length];
            var skin = 0;
            for (var index = 0; index < mask.Length; index++)
            {
                mask[index] = hasSkin && (paintedPixels != null
                    ? paintedPixels[index].r > 127
                    : LooksLikeSkin(basePixels[index]));
                if (mask[index])
                    skin++;
            }
            skinRatio = skin / (float)mask.Length;
            source = paintedPixels != null ? "手绘 mask" : hasSkin ? "颜色启发式" : "无皮肤(配件)";
            return mask;
        }

        private static string WriteShade(string directory, string sdwPath, Texture2D col, Texture2D sdw, bool[] mask)
        {
            var basePixels = col.GetPixels32();
            var pixels = sdw.GetPixels32();
            for (var index = 0; index < pixels.Length; index++)
                if (mask[index])
                {
                    // Stock skin carries the base colour verbatim here, alpha marking it as skin.
                    var lifted = basePixels[index];
                    lifted.a = 255;
                    pixels[index] = lifted;
                }
                else
                {
                    pixels[index].a = 0;
                }
            return Write(directory, sdwPath, col.width, col.height, pixels, srgb: true);
        }

        // No source shade sheet: build one. Stock skin carries the base colour verbatim (the darken
        // factor solves to exactly 1.000 on hmsz-cstm-0059) and stock cloth sits at 0.44-0.79 of base,
        // which is the `Darken` figure in the surface preset. Multiplying in linear space and coming
        // back to sRGB is what `gakumas_mi`'s own shade_color_from_base does — the same formula the
        // 3Dmigoto route has shipped with for a year.
        private static string SynthesizeShade(string directory, string colPath, Texture2D col, bool[] mask,
            SubmeshLabel label)
        {
            var darken = SurfacePresets.Of(label.surface).Darken;
            var pixels = col.GetPixels32();
            // If the source shipped its own shading sheet, let it vary the darken per pixel rather
            // than applying one constant everywhere — a flat multiplier is what made the costume
            // read grey and lifeless next to stock art, which has per-region shading painted in.
            //
            // Modulated AROUND the measured constant, not replacing it: the preset's darken is
            // grounded in stock bodies, while the source's channel is only known to be a smooth
            // AO-like field. +-25% keeps the average where it was measured and cannot blow up if
            // the channel means something slightly different on another rip.
            var lightmapPath = FirstMatch(directory, Path.GetFileName(colPath).Replace("_col", "_lightmap"));
            var lightmap = lightmapPath == null ? null : Load(lightmapPath);
            var shading = lightmap == null || lightmap.width != col.width || lightmap.height != col.height
                ? null : lightmap.GetPixels32();
            var ceiling = 1;
            if (shading != null)
                foreach (var texel in shading)
                    ceiling = Mathf.Max(ceiling, texel.g);

            for (var index = 0; index < pixels.Length; index++)
            {
                var source = pixels[index];
                if (mask[index])
                {
                    source.a = 255;               // skin: base verbatim, alpha marks it
                    pixels[index] = source;
                    continue;
                }
                var local = shading == null
                    ? darken
                    : darken * (0.75f + 0.5f * shading[index].g / ceiling);
                pixels[index] = new Color32(Shade(source.r, local), Shade(source.g, local),
                    Shade(source.b, local), 0);
            }
            if (shading != null)
                Debug.Log($"[SDK] {label.material}: 用源自带明暗图逐像素调制 t4（darken {darken:F2} ±25%，"
                          + $"G 上界 {ceiling}）← {Path.GetFileName(lightmapPath)}");
            var path = Write(directory, colPath.Replace("_col", "_sdw"), col.width, col.height, pixels, srgb: true);
            Debug.Log($"[SDK] {label.material}: 源模型没有 sdw 贴图，按标注 {label.surface} 用 base×{darken:F2} 合成 t4 "
                      + $"→ {Path.GetFileName(path)}");
            return path;
        }

        private static byte Shade(byte channel, float darken)
        {
            var linear = Mathf.GammaToLinearSpace(channel / 255f) * darken;
            return (byte)Mathf.Clamp(Mathf.RoundToInt(Mathf.LinearToGammaSpace(linear) * 255f), 0, 255);
        }

        // Stock skin is a flat constant across every costume measured (fktn-cstm-0001, jsna-casl-0002,
        // ttmr-cstm-0119, hmsz-cstm-0059): toon 0.486-0.494, smoothness 0.498-0.502, metallic 0, AO 0.
        // A foreign sheet paints variation into the skin region for its own shader, which shows up
        // here as hard-edged bands across the thighs, so overwrite it with the constant.
        private static readonly Color32 SkinDef = new Color32(125, 128, 0, 0);

        // Non-skin texels keep the *source's* own t1 painting when the source has one — stock cloth t1
        // is painted per region too (buckles, leather, fabric all differ), so flattening it to one
        // constant would throw away detail we have. Two channels are not left alone: metallic is forced
        // to zero (stock bodies are never metallic, and a metallic body indoors mixes in enough of the
        // dark environment probe to render black), and smoothness is capped at the surface's stock
        // value. "Measures near the stock range" was assumed, not measured, and chs-sucu-00 disproves
        // it — latex sources paint gloss far past anything a stock body wears.
        //
        // A source with no t1 at all (an MMD or VRM model has only a base map) gets the author's
        // surface preset instead — flat, but the right flat.
        private static string WriteDef(string directory, string scope, string model, string group, bool[] mask,
            SubmeshLabel label, int width, int height)
        {
            var preset = SurfacePresets.Of(label.surface);
            var defSource = FirstMatch(directory, $"{scope}_{group}_def*.png");
            var def = Load(defSource);
            if (def == null)
            {
                // Flat, but the right flat: the preset's toon/smoothness for this surface, metallic
                // zero, AO zero on skin. The size comes from the mask, which is the base map's.
                var flat = new Color32[mask.Length];
                for (var index = 0; index < flat.Length; index++)
                    flat[index] = mask[index] ? SkinDef : preset.Def;
                var name = model == null ? $"t_{group}_def.png" : $"t_{model}_{group}_def.png";
                var synthesized = Write(directory, $"{directory}/{name}", width, height, flat, srgb: false);
                Debug.Log($"[SDK] {group}: 源模型没有 def 贴图，按标注 {label.surface} 合成常量 t1 "
                          + $"（toon {preset.Def.r / 255f:F2}/smooth {preset.Def.g / 255f:F2}）→ {Path.GetFileName(synthesized)}");
                return synthesized;
            }
            var pixels = def.GetPixels32();
            if (pixels.Length != mask.Length)
            {
                Debug.LogError($"[SDK] {group}: def 尺寸与 col 不同，跳过 t1 改写");
                return null;
            }
            for (var index = 0; index < pixels.Length; index++)
                if (mask[index])
                    pixels[index] = SkinDef;
                else
                {
                    pixels[index].b = 0;
                    // Ceiling, not overwrite: painted variation below the surface's stock smoothness
                    // survives, only the blow-out is cut. chs-sucu-00's G sits at 184 (0.72) over 37%
                    // of the sheet and reaches 220 — the stock *metal* level worn by a whole costume,
                    // and it renders as bright specular streaks along every limb.
                    //
                    // A source sheet cannot be carried over as-is, because the two games do not share
                    // a shader. Gakumas runs `Campus/Actor/Default` (live-probed) with
                    // `_SpecularThreshold=(0.6, 0.05, 0, 0)` and no `_Smoothness` property at all;
                    // IDOLY PRIDE runs a URP Lit derivative whose material carries `_Smoothness = 0.5`,
                    // which halves this very sheet to ~0.36. Nothing here reproduces that scalar, so a
                    // sheet authored past the 0.6 threshold lights up where stock cloth (0.40) never does.
                    pixels[index].g = System.Math.Min(pixels[index].g, preset.Def.g);
                    if (label.surface != SurfaceClass.Cloth)
                        pixels[index].a = preset.Def.a;
                }
            var path = Write(directory, defSource, def.width, def.height, pixels, srgb: false);
            Debug.Log($"[SDK] {group}: t1 已改写 → {Path.GetFileName(path)}（皮肤写常量 " +
                      $"toon {SkinDef.r / 255f:F2}/smooth {SkinDef.g / 255f:F2}，其余保留源绘制、" +
                      $"光泽封顶 {preset.Def.g / 255f:F2}、清 metallic" +
                      $"{(label.surface != SurfaceClass.Cloth ? $"、AO 按 {label.surface} 取 {preset.Def.a / 255f:F2}" : "")}）");
            return path;
        }

        /// <summary>
        /// Copies a foreign model's base map in as t0, forcing alpha opaque.
        /// </summary>
        /// <remarks>
        /// This game alpha-tests the body against `_Cutoff = 0.5` on every material except the plain
        /// `m_bdy` (vanilla `m_bdyco` carries `_ALPHATEST_ON`), and a foreign model's diffuse alpha is
        /// not opacity — a Genshin sheet stores a mask there and reads 0 over 97% of its area. Copied
        /// through unchanged it clips the whole section away: that is what "上半身有、下半身没有"
        /// was, three sections clipped to nothing while only the one on `m_bdy` survived.
        /// </remarks>
        public static void CopyOpaqueBaseMap(string sourcePath, string targetPath)
        {
            var source = Load(sourcePath);
            if (source == null)
            {
                File.Copy(sourcePath, targetPath, true);
                return;
            }
            var pixels = source.GetPixels32();
            var clipped = 0;
            for (var index = 0; index < pixels.Length; index++)
            {
                if (pixels[index].a < 128)
                    clipped++;
                pixels[index].a = 255;
            }
            var texture = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(targetPath, texture.EncodeToPNG());
            Object.DestroyImmediate(texture);
            Object.DestroyImmediate(source);
            if (clipped > pixels.Length / 100)
                Debug.Log($"[SDK] {Path.GetFileName(targetPath)}: 源图 {clipped * 100 / pixels.Length}% 的 alpha "
                          + "低于裁剪阈值，已整张改为不透明（源模型的 alpha 不是透明度）");
        }

        private static string Write(string directory, string sourcePath, int width, int height, Color32[] pixels, bool srgb)
        {
            var output = $"{directory}/{Path.GetFileNameWithoutExtension(sourcePath)}{Suffix}.png";
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(output, texture.EncodeToPNG());
            Object.DestroyImmediate(texture);
            AssetDatabase.ImportAsset(output, ImportAssetOptions.ForceUpdate);
            ConfigureImport(output, srgb);
            return output;
        }

        // Bare skin on these sheets is warm (R clearly above B), gently saturated and bright; cloth
        // sits near-neutral and metal near-monochrome. Verified against hmsz-cstm-0059's real mask.
        // ponytail: colour is a proxy for material, so a warm-toned costume will confuse it — drop a
        // `*_<group>_skin.png` next to the textures to override.
        private static bool LooksLikeSkin(Color32 color)
        {
            var max = Mathf.Max(color.r, Mathf.Max(color.g, color.b));
            var min = Mathf.Min(color.r, Mathf.Min(color.g, color.b));
            var saturation = max == 0 ? 0f : (max - min) / (float)max;
            return color.r - color.b > 12 && saturation > 0.04f && saturation < 0.30f && max > 150;
        }

        private static string FirstMatch(string directory, string pattern)
        {
            foreach (var candidate in Directory.GetFiles(directory, pattern))
            {
                var path = candidate.Replace('\\', '/');
                if (path.Contains(Suffix + "."))
                    continue;
                return path;
            }
            return null;
        }

        // Read the file rather than the imported asset: LoadImage gives readable pixels without
        // touching every source texture's importer settings.
        private static Texture2D Load(string path)
        {
            if (path == null)
                return null;
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            if (texture.LoadImage(File.ReadAllBytes(path)))
                return texture;
            Debug.LogError($"[SDK] 读不出图片: {path}");
            return null;
        }

        /// <summary>t0/t4 are sRGB, t1 (def) is packed data — decoding t1 as sRGB dims everything.</summary>
        public static void ConfigureImport(string assetPath, bool srgb)
        {
            if (AssetImporter.GetAtPath(assetPath) is not TextureImporter importer)
                return;
            if (importer.sRGBTexture == srgb && !importer.alphaIsTransparency)
                return;
            importer.sRGBTexture = srgb;
            importer.alphaIsTransparency = false;
            importer.SaveAndReimport();
        }
    }
}
