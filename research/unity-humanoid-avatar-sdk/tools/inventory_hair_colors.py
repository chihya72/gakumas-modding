"""What vertex COLOR the stock *hair* parts carry — the same closed inventory
`inventory_body_colors.py` does for bodies, on the axis the hair path was shipping blind.

Why this is worth its own run: COLOR is nibble-packed material input (outline colour, LUT row,
outline width, rim — see GakumasVertexColor), a hair mesh imported from another game carries that
other game's packing, and nothing in the hair path overwrote it. The body's preset was measured over
530 costumes; hair had one costume's frame capture and a note saying the conclusion had been
overturned once. This measures the population instead.

Reads the AssetStudio JSON exports rather than bundles, because that is the hair library that exists
offline (`mod-workspace/libraries/assetstudio-hair-json`, 379 parts, `Geo_Hair` + `Geo_HairProp`).
`m_Colors` there is a flat float list, 4 per vertex.

    python tools/inventory_hair_colors.py [limit]
"""
import collections
import glob
import json
import os
import sys

LIBRARY = "D:/GIT/gakumas-modding/mod-workspace/libraries/assetstudio-hair-json/*_hair"
OUTPUT = "reference/hair-color-inventory.json"
MESHES = ("Geo_Hair", "Geo_HairProp")


def colours(path):
    """Packed RGBA -> vertex count, or None when the export has no COLOR."""
    with open(path, encoding="utf-8") as handle:
        mesh = json.load(handle)
    raw = mesh.get("m_Colors")
    count = mesh.get("m_VertexCount") or 0
    if not raw or not count:
        return None
    stride = len(raw) // count
    if stride < 4:
        return None
    local = collections.Counter()
    for index in range(0, count * stride, stride):
        local[tuple(min(255, max(0, round(raw[index + channel] * 255))) for channel in range(4))] += 1
    return local


limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
directories = sorted(glob.glob(LIBRARY))
if limit:
    directories = directories[:limit]

report = {"scanned": {}, "missing": [], "meshes": {}}
for mesh_name in MESHES:
    values = collections.Counter()          # packed RGBA -> vertices
    dominant = collections.Counter()        # packed RGBA -> parts where it is the most common
    fields = {name: collections.Counter() for name in
              ("outline_r_hi", "outline_r_lo", "outline_g_hi", "lut_row", "width", "rim")}
    scanned = 0
    for directory in directories:
        path = os.path.join(directory, f"{mesh_name}.json")
        if not os.path.exists(path):
            continue
        local = colours(path)
        if local is None:
            report["missing"].append(f"{os.path.basename(directory)}/{mesh_name}")
            continue
        values.update(local)
        dominant[local.most_common(1)[0][0]] += 1
        for (red, green, blue, alpha), count in local.items():
            fields["outline_r_hi"][red >> 4] += count
            fields["outline_r_lo"][red & 15] += count
            fields["outline_g_hi"][green >> 4] += count
            fields["lut_row"][green & 15] += count
            fields["width"][blue & 15] += count
            fields["rim"][alpha >> 4] += count
        scanned += 1
    report["scanned"][mesh_name] = scanned
    report["meshes"][mesh_name] = {
        "topValues": [{"rgba": list(c), "vertices": n} for c, n in values.most_common(20)],
        "dominantPerPart": [{"rgba": list(c), "parts": n} for c, n in dominant.most_common(20)],
        "fields": {name: dict(sorted(counter.items())) for name, counter in fields.items()},
    }

    total = sum(values.values()) or 1
    print(f"\n=== {mesh_name}：{scanned} 个部件，顶点 {total} ===")
    print("最常见的 COLOR 值（按顶点数）:")
    for (red, green, blue, alpha), count in values.most_common(6):
        print(f"  ({red},{green},{blue},{alpha})".ljust(22)
              + f"{count * 100 / total:5.1f}%  描边({red >> 4},{red & 15},{green >> 4}) "
                f"LUT {green & 15} 宽 {blue & 15} rim {alpha >> 4}")
    print("按部件的众数（每个部件投一票）:")
    for (red, green, blue, alpha), count in dominant.most_common(4):
        print(f"  ({red},{green},{blue},{alpha})".ljust(22) + f"{count} 个部件")
    print("各字段分布（顶点占比 %，只列 ≥1%）:")
    for name, counter in fields.items():
        subtotal = sum(counter.values()) or 1
        row = ", ".join(f"{value}:{count * 100 / subtotal:.1f}"
                        for value, count in sorted(counter.items()) if count * 100 / subtotal >= 1)
        print(f"  {name:13} {row}")

with open(OUTPUT, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=1)
print(f"\n写入 {OUTPUT}")
