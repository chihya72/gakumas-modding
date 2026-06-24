# ttmr cstm-0119 Body replacement target

> **历史记录（2026-06-24）**：本文属于 TTMR→HSKI 运行时骨架重定向实验阶段，该重定向路线
> 已排除（同名骨直接映射导致大面积错位）。正确作者流程是在 Blender 中把衣服蒙皮到目标骨架
> 后再传权，见 [current-status-and-roadmap.md](current-status-and-roadmap.md)。

Source directory: `mdl_chr_ttmr-cstm-0119_body`

- FBX mesh: `Geo_Body`
- Vertices: 10,383
- Triangles: 12,587
- Indices: 37,761 (fits the verified Body draw capacity of 74,664)
- Armature: 200 bones; 123 mesh vertex groups
- Materials: `m_bdy`, `m_bdyco`
- UV layers: `UV0`
- Texture source: `mdl_chr_ttmr-cstm-0119_body.png`
- Local mesh bounds: `[-0.6812, 0.0, -0.2139]` to `[0.6812, 1.3442, 0.1881]`

The FBX imports with a root Armature scale of `0.01` and mesh scale of
`[1.015, 1.045, 1.0]`. Authoring/export must use the 1.344 m local mesh scale
or normalize/apply these transforms before surface mapping; raw world-space
import is approximately 100 times too small.

Planned workflow:

1. Finish the identity surface-map runtime validation.
2. Add normalized FBX import and triangulation to the Blender add-on.
3. Map `Geo_Body` to the verified hski Body reference surface.
4. Transfer/generate Body material selector colors and UV1 defaults.
5. Convert the PNG atlas to a compatible DDS replacement and package it.
6. Validate animation, seams, skirt offsets, outline and shadow passes in game.
