"""默认配置档(atbm-cstm-0140,带原生 co)的数据契约冒烟。

旧版本审计的是 hski-cstm-0000 PoC 冻结契约(tools.audit_profile 的全量 schema);
该档随 profiles 精简已删除。现在直接锁默认档的关键契约:几何、骨架、逆算子、
co 第二材质段。数据缺失(如 CI 无本地 Buffers)时自动降级/SKIP。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
profile_dir = ROOT / "profiles" / "atbm-cstm-0140"

profile_path = profile_dir / "profile.json"
if not profile_path.is_file():
    print("GMI_PROFILE_CONTRACT_SKIP no local profile data")
    raise SystemExit(0)

profile = json.loads(profile_path.read_text(encoding="utf-8"))
component = profile["components"][0]
assert component["id"] == "body"
assert component["ibHash"] == "d43e51c9"
assert component["vertices"] == 18972
assert component["indices"] == 77961

sections = {section["role"]: section for section in component["materialSections"]}
assert sections["main"]["firstIndex"] == 0
assert sections["main"]["indexCount"] == 76890
assert sections["co"]["firstIndex"] == 76890
assert sections["co"]["indexCount"] == 1071
assert sections["co"]["id"] == "body.section1"

textures = json.loads((profile_dir / "texture_map.json").read_text(encoding="utf-8"))["textures"]
for key in ("body.baseColor", "body.packedMask", "body.shadeColor",
            "body.section1.baseColor", "body.section1.packedMask", "body.section1.shadeColor"):
    assert key in textures, key

inverse = profile["skinning"]["inverseSkin"]
operator = profile_dir / "Buffers" / "InverseOperator.R32_FLOAT.buf"
if not operator.is_file():
    print("GMI_PROFILE_CONTRACT_OK (schema only; operator buffers not present locally)")
    raise SystemExit(0)
assert inverse["sourceVertexCount"] == 18972
assert inverse["weightedBoneCount"] == 132
assert inverse["unobservableBones"] == []
assert (profile_dir / "Reference" / "Geo_Body.json").is_file()
print("GMI_PROFILE_CONTRACT_OK geometry+skinning+co-section+operator")
