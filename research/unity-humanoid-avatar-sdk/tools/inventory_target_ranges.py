"""What value range the target game itself ever ships, per component field.

Carrying a source model's own rig over works because both games run the same middleware — but "same
field name" is not "same units". A source value outside everything the target ever ships is the
signal that the two solvers disagree about that field, and it is not a theoretical worry: IDOLY
PRIDE's breast driver arrives at damping 0.15 / stiffness 0.03 when this game's 529 bodies only ever
use damping 0.20-0.35 and stiffness 0.06-0.12. Transferred as-is it is under-damped and jitters
forever; every one of the 42 swing bones from the same model, by contrast, lands inside range and
needs no clamping at all.

So ComponentTransfer clamps into these ranges, and this is where they come from. Both the SDK and
tools/verify_transfer.py read the output, so there is one copy of the numbers.

Only solver parameters are listed. Collider radii, angle limits and bone references are per-garment
geometry — the whole point of the transfer is that those come from the source.

    python tools/inventory_target_ranges.py        # 全 530 套，约 3 分钟
"""
import collections
import glob
import json

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"

LIBRARY = "D:/GIT/gakumas-modding/mod-workspace/libraries/all_body/*"
OUTPUT = "reference/target-value-ranges.json"

# Identified by a field only that class has, since the bundles carry no usable script names.
CLASSES = {
    "ActorSwingDynamicBone": ("dynamicCollider", ["damping", "stiffness", "spring", "mass"]),
    "ActorSwingBreastBone": ("breastCollider", ["damping", "stiffness", "spring", "average"]),
}

values = collections.defaultdict(list)
counts = collections.Counter()

for path in sorted(glob.glob(LIBRARY)):
    try:
        env = UnityPy.load(path)
    except Exception:
        continue
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        for klass, (marker, fields) in CLASSES.items():
            if marker not in tree:
                continue
            counts[klass] += 1
            for field in fields:
                if field in tree:
                    values[(klass, field)].append(float(tree[field]))

entries = []
for (klass, field), samples in sorted(values.items()):
    samples.sort()
    entries.append({
        "klass": klass, "field": field,
        "min": round(samples[0], 4), "max": round(samples[-1], 4),
        "median": round(samples[len(samples) // 2], 4), "samples": len(samples),
    })

with open(OUTPUT, "w", encoding="utf-8") as handle:
    json.dump({"entries": entries}, handle, ensure_ascii=False, indent=1)

print(f"-> {OUTPUT}")
for klass, count in counts.items():
    print(f"   {klass}: {count} 个实例")
for entry in entries:
    print(f"   {entry['klass'][-12:]:12} {entry['field']:10} {entry['min']:8.4f} ~ {entry['max']:8.4f}"
          f"   中位 {entry['median']:.4f}  样本 {entry['samples']}")
