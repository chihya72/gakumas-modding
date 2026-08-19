// Vertex COLOR in this game's own semantics.
//
// Gakumas reads COLOR as four UNORM8 fields, each split into a high and a low nibble
// (frozen in research/hair-pipeline.md, from frame analysis — not guessed):
//
//   R high / R low / G high  outline colour, 0-15 each
//   G low                    row of the optional t7 LUT
//   B low                    outline width (the outline is an inverted hull; 0 turns it off)
//   A high                   the main material's rim / backlight term
//
// A model from another game carries COLOR that means something else there, so there is nothing to
// convert: IP's most common value (91,19,9,255) decodes here as outline (5,11,1) at full rim — a
// yellow-green edge on everything, and on a wing thin enough for the hull to swallow it, a solid
// neon-green wing. So the import overwrites COLOR with this game's values.
//
// The values themselves live in SurfacePresets, keyed by the author's surface label: cloth gets black
// ink and no rim, skin a warm edge with rim, metal and leather their own. One constant for the whole
// mesh is what "描边偏橙" looked like — every seam of a black dress inked in skin brown.
using UnityEngine;

namespace GakumasSdk
{
    public static class GakumasVertexColor
    {
        public static string Describe(Color32 color) =>
            $"描边({color.r >> 4},{color.r & 15},{color.g >> 4}) 宽 {color.b & 15} rim {color.a >> 4} " +
            $"LUT {color.g & 15} → 字节 ({color.r},{color.g},{color.b},{color.a})";
    }
}
