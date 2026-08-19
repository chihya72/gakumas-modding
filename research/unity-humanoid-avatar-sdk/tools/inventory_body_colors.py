"""Closed inventory of the fourth axis: the vertex COLOR every stock body mesh actually carries.

The component and material axes are inventoried in `inventory_body_components.py` /
`inventory_body_materials.py`. COLOR is the remaining input the import has to author from scratch,
and its fields are nibble-packed (see GakumasVertexColor): outline colour, LUT row, outline width,
rim. A preset that is wrong in one nibble is invisible in a bright room and wrong in a dark scene.

Reports, per field, how the 530 stock bodies are actually distributed — so a preset can be checked
against the population instead of against one costume someone happened to look at.

    python tools/inventory_body_colors.py [limit]
"""
import collections, glob, json, sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"

LIBRARY = "D:/GIT/gakumas-modding/mod-workspace/libraries/all_body/*"
OUTPUT = "reference/body-color-inventory.json"

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
paths = sorted(glob.glob(LIBRARY))
if limit:
    paths = paths[:limit]

values = collections.Counter()          # packed RGBA -> vertices
dominant = collections.Counter()        # packed RGBA -> costumes where it is the most common
fields = {name: collections.Counter() for name in
          ("outline_r_hi", "outline_r_lo", "outline_g_hi", "lut_row", "width", "rim")}
per_costume = {}
scanned = 0
missing = []

for path in paths:
    costume = path.replace("\\", "/").split("/")[-1]
    try:
        env = UnityPy.load(path)
    except Exception:
        missing.append(costume)
        continue
    mesh = None
    for object_info in env.objects:
        if object_info.type.name != "Mesh":
            continue
        candidate = object_info.read()
        if candidate.m_Name == "Geo_Body":
            mesh = candidate
            break
    if mesh is None or not getattr(mesh, "m_Colors", None):
        missing.append(costume)
        continue

    raw = mesh.m_Colors
    stride = len(raw) // mesh.m_VertexCount if mesh.m_VertexCount else 4
    local = collections.Counter()
    for index in range(0, len(raw), stride):
        packed = tuple(min(255, max(0, round(raw[index + channel] * 255))) if index + channel < len(raw) else 0
                       for channel in range(4))
        local[packed] += 1
    values.update(local)
    top = local.most_common(1)[0][0]
    dominant[top] += 1
    per_costume[costume] = {"vertices": mesh.m_VertexCount,
                            "top": [[list(colour), count] for colour, count in local.most_common(3)]}
    for colour, count in local.items():
        red, green, blue, alpha = colour
        fields["outline_r_hi"][red >> 4] += count
        fields["outline_r_lo"][red & 15] += count
        fields["outline_g_hi"][green >> 4] += count
        fields["lut_row"][green & 15] += count
        fields["width"][blue & 15] += count
        fields["rim"][alpha >> 4] += count
    scanned += 1
    if scanned % 25 == 0:
        print(f"  {scanned}/{len(paths)} ...", flush=True)

report = {
    "scanned": scanned,
    "missing": missing,
    "topValues": [{"rgba": list(colour), "vertices": count} for colour, count in values.most_common(20)],
    "dominantPerCostume": [{"rgba": list(colour), "costumes": count} for colour, count in dominant.most_common(20)],
    "fields": {name: dict(sorted(counter.items())) for name, counter in fields.items()},
    "perCostume": per_costume,
}
with open(OUTPUT, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=1)

total = sum(values.values())
print(f"\n扫描 {scanned} 套，顶点 {total}，写入 {OUTPUT}\n")
print("最常见的 COLOR 值（按顶点数）:")
for colour, count in values.most_common(8):
    red, green, blue, alpha = colour
    print(f"  {str(colour):22} {count*100/total:5.1f}%  描边({red>>4},{red&15},{green>>4}) "
          f"LUT {green&15} 宽 {blue&15} rim {alpha>>4}")
print("\n各字段分布（顶点占比 %）:")
for name, counter in fields.items():
    subtotal = sum(counter.values())
    row = ", ".join(f"{value}:{count*100/subtotal:.1f}" for value, count in sorted(counter.items()))
    print(f"  {name:13} {row}")
