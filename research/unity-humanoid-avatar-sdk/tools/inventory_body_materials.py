"""Closed inventory of the body material path: every slot, float and colour a stock body material
carries, and — the part that matters — which of them vary per costume.

A property that varies per costume is one the author must produce; inheriting the replaced character's
value there is a colour bug waiting for the right scene. A property that is constant across 530
costumes is safe to inherit from the cloned vanilla material.
"""
import collections, glob, json
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"

slots = collections.defaultdict(collections.Counter)      # material name -> slot -> bound count
slot_targets = collections.defaultdict(collections.Counter)  # (material, slot) -> texture stem
floats = collections.defaultdict(collections.Counter)     # (material, prop) -> value
colors = collections.defaultdict(collections.Counter)
mat_names = collections.Counter()
costumes = 0


def stem(name, costume):
    """Strip the costume/character id so 'per-costume vs shared' is visible."""
    body = costume.replace("mdl_chr_", "").replace("_body", "")
    character = body.split("-")[0]
    if body in name:
        return "<本套>" + name.split(body)[-1]
    if character in name:
        return "<本角色>" + name.split(character)[-1]
    return name


for path in sorted(glob.glob("D:/GIT/gakumas-modding/mod-workspace/libraries/all_body/*")):
    costume = path.replace("\\", "/").split("/")[-1]
    try:
        env = UnityPy.load(path)
    except Exception:
        continue
    costumes += 1
    textures = {}
    materials = []
    for o in env.objects:
        if o.type.name == "Texture2D":
            textures[o.path_id] = o.read_typetree()["m_Name"]
        elif o.type.name == "Material":
            materials.append(o)
    for o in materials:
        tree = o.read_typetree()
        name = tree["m_Name"]
        mat_names[name] += 1
        saved = tree["m_SavedProperties"]
        for slot, value in saved["m_TexEnvs"]:
            path_id = value["m_Texture"]["m_PathID"]
            if not path_id:
                continue
            slots[name][slot] += 1
            slot_targets[(name, slot)][stem(textures.get(path_id, "?外部"), costume)] += 1
        for prop, value in saved["m_Floats"]:
            floats[(name, prop)][round(value, 4)] += 1
        for prop, value in saved["m_Colors"]:
            colors[(name, prop)][tuple(round(value[c], 3) for c in "rgba")] += 1

print(f"扫了 {costumes} 套，材质名: {mat_names.most_common()}")
print()
for name, _ in mat_names.most_common():
    total = mat_names[name]
    print(f"===== {name}（{total} 套有）")
    print("  绑定的贴图槽:")
    for slot, hits in slots[name].most_common():
        targets = slot_targets[(name, slot)].most_common(3)
        print(f"    {slot:20s} {hits:4d}/{total} 套绑定   目标: {targets}")
    varying = [(prop, counter) for (mat, prop), counter in floats.items()
               if mat == name and len(counter) > 1]
    print(f"  float: {sum(1 for (m, _) in floats if m == name)} 个，其中随服装变的 {len(varying)} 个")
    for prop, counter in sorted(varying, key=lambda kv: -len(kv[1]))[:12]:
        print(f"    {prop:24s} {len(counter)} 种值  {counter.most_common(3)}")
    varying = [(prop, counter) for (mat, prop), counter in colors.items()
               if mat == name and len(counter) > 1]
    print(f"  color: {sum(1 for (m, _) in colors if m == name)} 个，其中随服装变的 {len(varying)} 个")
    for prop, counter in sorted(varying, key=lambda kv: -len(kv[1]))[:12]:
        print(f"    {prop:24s} {len(counter)} 种值  {counter.most_common(3)}")
    print()

json.dump({
    "costumes": costumes,
    "materials": dict(mat_names),
    "slots": {f"{m}|{s}": dict(c) for (m, s), c in slot_targets.items()},
    "floats": {f"{m}|{p}": dict(c) for (m, p), c in floats.items()},
    "colors": {f"{m}|{p}": {str(k): v for k, v in c.items()} for (m, p), c in colors.items()},
}, open("body-material-inventory.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
