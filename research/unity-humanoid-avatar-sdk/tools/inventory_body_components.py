"""Closed inventory: every component every stock body part carries.

Scans all body bundles and records, per MonoBehaviour class: how many costumes carry it, how many
instances, which bones host it, and the exact serialized field set (plus one sample value set). The
point is to stop discovering required components one crash at a time — this is the complete list of
what a body part can hold, to diff against what the SDK emits.
"""
import collections, glob, json, sys, traceback
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"
SKIP = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance", "m_PrefabAsset",
        "m_GameObject", "m_Enabled", "m_Script", "m_Name", "m_EditorHideFlags",
        "m_EditorClassIdentifier"}

paths = sorted(glob.glob("D:/GIT/gakumas-modding/mod-workspace/libraries/all_body/*"))
classes = collections.defaultdict(lambda: {
    "costumes": set(), "instances": 0, "hosts": collections.Counter(),
    "fields": collections.Counter(), "assembly": "", "sample": None,
})
failed = []

for index, path in enumerate(paths):
    name = path.replace("\\", "/").split("/")[-1]
    if index % 25 == 0:
        print(f"[{index}/{len(paths)}] {name}", flush=True)
    try:
        env = UnityPy.load(path)
        names, scripts, behaviours = {}, {}, []
        for o in env.objects:
            if o.type.name == "GameObject":
                names[o.path_id] = o.read_typetree()["m_Name"]
            elif o.type.name == "MonoScript":
                d = o.read()
                scripts[o.path_id] = (d.m_ClassName, getattr(d, "m_AssemblyName", ""))
            elif o.type.name == "MonoBehaviour":
                behaviours.append(o)
        for o in behaviours:
            try:
                tree = o.read_typetree()
            except Exception:
                continue
            klass, assembly = scripts.get(tree["m_Script"]["m_PathID"], ("?unresolved", ""))
            entry = classes[klass]
            entry["assembly"] = assembly
            entry["costumes"].add(name)
            entry["instances"] += 1
            entry["hosts"][names.get(tree["m_GameObject"]["m_PathID"], "?")] += 1
            fields = tuple(sorted(set(tree) - SKIP))
            entry["fields"][fields] += 1
            if entry["sample"] is None:
                entry["sample"] = {k: v for k, v in tree.items() if k not in SKIP}
    except Exception as error:
        failed.append((name, str(error)[:80]))

out = {}
for klass, entry in sorted(classes.items(), key=lambda kv: -len(kv[1]["costumes"])):
    out[klass] = {
        "assembly": entry["assembly"],
        "costumes": len(entry["costumes"]),
        "instances": entry["instances"],
        "perCostume": round(entry["instances"] / max(len(entry["costumes"]), 1), 1),
        "hosts": dict(entry["hosts"].most_common(12)),
        "fields": [list(f) for f, _ in entry["fields"].most_common(2)],
        "sample": json.loads(json.dumps(entry["sample"], default=str)),
    }

json.dump({"scanned": len(paths), "failed": failed, "classes": out},
          open("body-component-inventory.json", "w", encoding="utf8"),
          ensure_ascii=False, indent=1)
print(f"完成: {len(paths)} 套, 失败 {len(failed)}, 组件类 {len(out)}", flush=True)
for klass, info in out.items():
    print(f"  {info['costumes']:4d}/{len(paths)} 套  {info['instances']:6d} 个  "
          f"{info['perCostume']:5.1f}/套  {klass}", flush=True)
