# HSKI Body 游戏数据契约审计

Profile：`gakumas-20260615-hski-cstm-0000`  
结果：**PASS**（60 通过 / 0 警告 / 0 失败）

## 已冻结的输入契约

- Geometry：17615 vertices / 74664 indices / `R16_UINT`；
- VB0：`e189fd22`，stride 40；
- VB1：`9c40798a`，stride 12；
- IB：`4d5dfe7b`；
- Skeleton：152 bind poses / 167 hierarchy nodes；
- Inverse operator：`25429F069261F2170498CBBA44888D7824899EE001B4029109F7D74C677EE385`。

## 自动检查

| 状态 | 检查 | 结果 |
| --- | --- | --- |
| pass | `document.profile.json` | Found profile.json |
| pass | `document.drawcall_map.json` | Found drawcall_map.json |
| pass | `document.material_map.json` | Found material_map.json |
| pass | `document.texture_map.json` | Found texture_map.json |
| pass | `profile.body` | Body component is defined |
| pass | `source.mesh` | Found D:\GIT\gakumas-modding\profiles\hski-cstm-0000\Reference\Geo_Body.json |
| pass | `source.skeleton` | Found D:\GIT\gakumas-modding\profiles\hski-cstm-0000\Reference\Geo_Body.skeleton.json |
| pass | `inverse.operator` | Found D:\GIT\gakumas-modding\profiles\hski-cstm-0000\Buffers\InverseOperator.R32_FLOAT.buf |
| pass | `mesh.vertexCount` | Vertex count is 17615 |
| pass | `mesh.indexCount` | Index count is 74664 |
| pass | `mesh.indexBounds` | Indices address [0, 17614] |
| pass | `mesh.array.positions` | positions: 52845 scalar/records |
| pass | `mesh.array.normals` | normals: 52845 scalar/records |
| pass | `mesh.array.tangents` | tangents: 70460 scalar/records |
| pass | `mesh.array.colors` | colors: 70460 scalar/records |
| pass | `mesh.array.uv0` | uv0: 35230 scalar/records |
| pass | `mesh.array.uv1` | uv1: 35230 scalar/records |
| pass | `mesh.array.skin` | skin: 17615 scalar/records |
| pass | `skeleton.bindPoseCount` | Bind poses: 152 |
| pass | `skeleton.weightedIndices` | Weighted indices are contiguous 0..151 |
| pass | `skeleton.nodeCount` | Hierarchy nodes: 167 |
| pass | `skin.fourInfluences` | Every source vertex has four valid influence slots |
| pass | `skin.weightSums` | Maximum |sum(weights)-1| is 1.46e-07 |
| pass | `skin.activeBones` | Active weighted bones: 147 |
| pass | `skin.inactiveBones` | Source-inactive bones: ['LeftUpLegSkin1_S', 'RightUpLegSkin1_S', 'RightLegSkin1_S', 'LeftLegSkin1_S', 'LeftSideStrap1_S'] |
| pass | `inverse.unobservableBones` | Numerically unobservable bones are declared: ['RightFrontRibbon1_S'] |
| pass | `inverse.operatorSize` | Inverse operator is 42839680 bytes (608 x 17615 float32) |
| pass | `regions.schema` | Found region schema D:\GIT\gakumas-modding\profiles\hski-cstm-0000\body-regions.json |
| pass | `regions.count` | Connected regions: 387 |
| pass | `regions.vertexMap` | Vertex region map: 17615 R16_UINT entries |
| pass | `regions.triangleMap` | Triangle region map: 24888 R16_UINT entries |
| pass | `capture.geometry.exists` | Found geometry capture D:\Games\gakumas\FrameAnalysis-2026-06-21-105931 |
| pass | `draw.passBindings` | Body pass bindings cover draws [2, 335, 347] |
| pass | `capture.draw2.ib` | Draw 2 ib: 149328 bytes |
| pass | `capture.draw2.vb0` | Draw 2 vb0: 704600 bytes |
| pass | `capture.draw2.vb1` | Draw 2 vb1: 211380 bytes |
| pass | `capture.draw335.ib` | Draw 335 ib: 149328 bytes |
| pass | `capture.draw335.vb0` | Draw 335 vb0: 704600 bytes |
| pass | `capture.draw335.vb1` | Draw 335 vb1: 211380 bytes |
| pass | `capture.draw347.ib` | Draw 347 ib: 149328 bytes |
| pass | `capture.draw347.vb0` | Draw 347 vb0: 704600 bytes |
| pass | `capture.draw347.vb1` | Draw 347 vb1: 211380 bytes |
| pass | `draw.shadowOrDepth.shaders` | shadowOrDepth: VS 221c573337491c78 / PS a04da6e49886b206 |
| pass | `draw.shadowOrDepth.arguments` | shadowOrDepth: DrawIndexed(74664, 0, 0) |
| pass | `draw.main.shaders` | main: VS fe50b7a82b0f37be / PS 9ab6fcdf2237a70a |
| pass | `draw.main.arguments` | main: DrawIndexed(74664, 0, 0) |
| pass | `draw.outline.shaders` | outline: VS e0ceaa854f457e74 / PS 58352a72263d897c |
| pass | `draw.outline.arguments` | outline: DrawIndexed(74664, 0, 0) |
| pass | `stability.FrameAnalysis-2026-06-21-105931` | Stable Body signature in FrameAnalysis-2026-06-21-105931: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-085440` | Stable Body signature in FrameAnalysis-2026-06-22-085440: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-091856` | Stable Body signature in FrameAnalysis-2026-06-22-091856: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-093546` | Stable Body signature in FrameAnalysis-2026-06-22-093546: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-103150` | Stable Body signature in FrameAnalysis-2026-06-22-103150: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-104227` | Stable Body signature in FrameAnalysis-2026-06-22-104227: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-105206` | Stable Body signature in FrameAnalysis-2026-06-22-105206: shadowOrDepth, main, outline |
| pass | `stability.FrameAnalysis-2026-06-22-105210` | Stable Body signature in FrameAnalysis-2026-06-22-105210: shadowOrDepth, main, outline |
| pass | `capture.material.exists` | Found material capture D:\Games\gakumas\FrameAnalysis-2026-06-21-111608 |
| pass | `material.body.t0` | t0 950989c5: 2048x2048 BC7_UNORM_SRGB |
| pass | `material.body.t1` | t1 1fefdc77: 2048x2048 BC7_UNORM |
| pass | `material.body.t4` | t4 69492ed7: 2048x2048 BC7_UNORM_SRGB |

## 尚需游戏内研究

- Resolve Body t1 packed-mask channel semantics and verify Body t4 by controlled channel replacements.
- Record exact main/outline/shadow draw arguments and resource bindings in the Profile instead of relying on draw numbers alone.
- Capture and compare a second clean scene entry to prove Body IB/VB/shader hashes are stable across sessions.
- Classify native Body geometry regions (hands, neck, skin, clothing) for Blender-side retention and weight-transfer masks.

此文件由 `tools/audit_profile.py` 生成，不应手工维护。
