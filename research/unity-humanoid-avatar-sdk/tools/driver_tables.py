"""Per-host-bone settings for the QuartzDriver families every stock body carries."""
import collections, glob, json
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"
WANT = {"ActorAnimationQuartzDriverHumanoidArmBone", "ActorAnimationQuartzDriverHumanoidUpLegBone",
        "ActorAnimationQuartzDriverHumanoidHandBone", "ActorAnimationQuartzDriverRotationBone"}

table = collections.defaultdict(collections.Counter)
refs = collections.defaultdict(collections.Counter)

for path in sorted(glob.glob("D:/GIT/gakumas-modding/mod-workspace/libraries/all_body/*"))[:120]:
    try:
        env = UnityPy.load(path)
    except Exception:
        continue
    names, scripts, behaviours, objs = {}, {}, [], {}
    for o in env.objects:
        objs[o.path_id] = o
        if o.type.name == "GameObject":
            names[o.path_id] = o.read_typetree()["m_Name"]
        elif o.type.name == "MonoScript":
            scripts[o.path_id] = o.read().m_ClassName
        elif o.type.name == "MonoBehaviour":
            behaviours.append(o)
    for o in behaviours:
        try:
            tree = o.read_typetree()
        except Exception:
            continue
        klass = scripts.get(tree["m_Script"]["m_PathID"])
        if klass not in WANT:
            continue
        host = names.get(tree["m_GameObject"]["m_PathID"], "?")
        setting = dict(tree["setting"])
        reference = setting.pop("referenceBone", None)
        table[(klass, host)][json.dumps(setting, sort_keys=True)] += 1
        if reference:
            target = objs.get(reference["m_PathID"])
            label = "?"
            if target is not None:
                t = target.read_typetree()
                label = t.get("m_Name") or names.get(t.get("m_GameObject", {}).get("m_PathID"), "?")
            refs[(klass, host)][label] += 1

for (klass, host), counter in sorted(table.items()):
    setting, hits = counter.most_common(1)[0]
    total = sum(counter.values())
    line = f"{klass.replace('ActorAnimationQuartzDriver', ''):22s} {host:24s} ×{total:4d}  {setting}"
    if (klass, host) in refs:
        line += f"  referenceBone={dict(refs[(klass, host)].most_common(2))}"
    print(line, f" (此值 {hits}/{total})")
