# -*- coding: utf-8 -*-
"""离线重建 atbm-cstm-0140 的 GakumasMI profile(带原生 co 第二材质段的 body 默认档)。

原始抓帧目录已清理;注入 hash 取自已导出包 Mods/千咲泳装 的 mod.ini/manifest.json,
主/co 材质段几何取自 body JSON 库 mdl_chr_atbm-cstm-0140_body 的 m_SubMeshes
(主段 0..76890 + co 段 76890..77961,与 mod.ini 的 match_first_index=76890 一致)。
Reference + 逆算子由库再生。
Run: blender -b --python profiles/atbm-cstm-0140/rebuild_profile.py
"""
import json, sys, traceback
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\GIT\gakumas-modding")
PROFILE_DIR = Path(__file__).resolve().parent
LIBRARY_DIR = r"D:\GIT\gakumas-modding\build\assetstudio-body-json"

IB_HASH = "d43e51c9"
VERTICES, INDICES = 18972, 77961
MAIN_COUNT = 76890            # 库 m_SubMeshes[0]
CO_FIRST, CO_COUNT = 76890, 1071  # 库 m_SubMeshes[1] = m_bdyco
CO_DRAWS = [85, 227, 291, 414, 671]  # mod.ini 注释里的 co source draws
MAIN_DRAW = 414
VS_HASHES = ["436f9c16af3b54cf", "221c573337491c78", "5b7fff8ecccaf579",
             "fe50b7a82b0f37be", "e0ceaa854f457e74", "49d37c76b70addad"]
TEXTURES = {  # Mods/千咲泳装 manifest.json materials
    "body.baseColor": {"slot": "ps-t0", "semantic": "baseColor", "hash": "5ac4ddf8"},
    "body.packedMask": {"slot": "ps-t1", "semantic": "packedMask", "hash": "32e027a9"},
    "body.shadeColor": {"slot": "ps-t4", "semantic": "shadeColor", "hash": "8321a82b"},
    "body.section1.baseColor": {"slot": "ps-t0", "semantic": "baseColor", "hash": "68c7e560"},
    "body.section1.packedMask": {"slot": "ps-t1", "semantic": "packedMask", "hash": "96cf1a19"},
    "body.section1.shadeColor": {"slot": "ps-t4", "semantic": "shadeColor", "hash": "66573a90"},
}


def write(name, data):
    (PROFILE_DIR / name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


try:
    note = ("离线重建: hash 取自已导出包 千咲泳装 的 mod.ini/manifest.json;"
            "材质段几何取自库 mdl_chr_atbm-cstm-0140_body m_SubMeshes;"
            "Reference/逆算子由 body JSON 库再生。作为带原生 co 的 body 默认配置档。")
    write("profile.json", {
        "schemaVersion": 1,
        "id": "rebuilt-atbm-cstm-0140-body-" + IB_HASH,
        "status": "runtime-only-frame-extracted",
        "target": {"actorId": "atbm", "costumeId": "cstm-0140",
                   "bodyResource": "mdl_chr_atbm-cstm-0140_body", "note": note},
        "capture": {"directory": "reconstructed", "note": "抓帧目录已删除,仅存元数据",
                    "stableSignatureCaptures": []},
        "layout": {"topology": "trianglelist", "indexFormat": "R16_UINT",
                   "positionNormalTangentStride": 40, "colorUvStride": 12,
                   "inference": "reconstructed-from-exported-package"},
        "skinning": {"drawInput": "CPU-skinned or runtime-skinned final vertex buffer",
                     "status": "runtime-only; pending complete_inverse_skin_profile",
                     "inverseSkin": {"meshJson": None, "skeletonJson": None}},
        "components": [{
            "id": "body", "confidence": "reconstructed", "ibHash": IB_HASH,
            "vbHashes": {"positionNormalTangent": f"draw:{MAIN_DRAW:06d}:vb0",
                         "colorUv": f"draw:{MAIN_DRAW:06d}:vb1"},
            "resourceFiles": {}, "vertices": VERTICES, "indices": INDICES,
            "mainFirstIndex": 0, "tailFirstIndices": [],
            "materialSections": [
                {"id": "body.section0", "role": "main", "firstIndex": 0,
                 "indexCount": MAIN_COUNT, "representativeDraw": MAIN_DRAW,
                 "textureKeyPrefix": "body"},
                {"id": "body.section1", "role": "co", "firstIndex": CO_FIRST,
                 "indexCount": CO_COUNT, "representativeDraw": CO_DRAWS[-1],
                 "textureKeyPrefix": "body.section1", "draws": CO_DRAWS},
            ],
            "draws": sorted(set([MAIN_DRAW] + CO_DRAWS)), "mainDraw": MAIN_DRAW,
        }],
    })
    write("drawcall_map.json", {
        "schemaVersion": 1, "capture": "reconstructed", "generatedFrom": note,
        "components": {"body": {
            "mainDraw": MAIN_DRAW,
            "passBindings": {
                f"draw_{i:06d}": {"role": "reconstructed", "draw": i,
                                  "vertexShader": vs, "pixelShader": None}
                for i, vs in enumerate(VS_HASHES, start=1)
            },
            "sectionBindings": {
                "body.section1": {"role": "co", "firstIndex": CO_FIRST,
                                  "indexCount": CO_COUNT, "draws": CO_DRAWS,
                                  "representativeDraw": CO_DRAWS[-1]},
            },
        }},
    })
    write("texture_map.json", {"schemaVersion": 1, "capture": "reconstructed",
                               "textures": TEXTURES})

    from gakumas_mi import core
    result = core.complete_inverse_skin_profile(
        str(PROFILE_DIR), LIBRARY_DIR, component_id="body",
        body_resource="mdl_chr_atbm-cstm-0140_body")
    print("COMPLETE:", {k: result[k] for k in ("body", "vertexCount", "weightedBoneCount",
                                               "activeBoneCount", "operatorBytes")})
    print("unobservable:", result.get("unobservableBones"))
    print("REBUILD OK", PROFILE_DIR)
except Exception:
    traceback.print_exc()
    sys.exit(1)
