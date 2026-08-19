"""Check a built bundle against the source manifest: did the author's values actually survive?

The transfer runs inside Unity and logs counts, but a count is not a value — a field written to the
wrong member, or lost to a serializer mismatch, still counts as transferred. This reads the finished
AssetBundle back and compares every transferred field against `components.json`.

    python tools/verify_transfer.py <bundle> <components.json>

Exit code is non-zero when anything mismatches, so it can gate a build.
"""
import json
import sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"

TOLERANCE = 1e-4


def close(a, b):
    return abs(float(a) - float(b)) <= TOLERANCE


def load_ranges(path="reference/target-value-ranges.json"):
    """Same table the transfer clamps against — one copy, so the two cannot drift."""
    try:
        table = json.load(open(path, encoding="utf-8"))
    except OSError:
        return {}
    return {(entry["klass"], entry["field"]): (entry["min"], entry["max"]) for entry in table["entries"]}


def main(bundle_path, manifest_path):
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    ranges = load_ranges()
    env = UnityPy.load(bundle_path)

    def expect(klass, field, value):
        """What the bundle should hold: the source value, clamped into the target's range."""
        low, high = ranges.get((klass, field), (float("-inf"), float("inf")))
        return min(max(float(value), low), high)

    names, transforms, scripts = {}, {}, {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            names[obj.path_id] = obj.read().m_Name
        elif obj.type.name == "MonoScript":
            scripts[obj.path_id] = obj.read().m_ClassName
    for obj in env.objects:
        if obj.type.name == "Transform":
            transforms[obj.path_id] = obj.read_typetree().get("m_GameObject", {}).get("m_PathID")

    def bone_of(path_id):
        return names.get(path_id) or names.get(transforms.get(path_id), "")

    built = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"), "?")
        built.setdefault(klass, {})[bone_of(tree.get("m_GameObject", {}).get("m_PathID"))] = tree

    problems, checked = [], 0

    for entry in manifest["dynamicBones"]:
        component = built.get("ActorSwingDynamicBone", {}).get(entry["bone"])
        if component is None:
            problems.append(f"摇物骨 {entry['bone']}: 包里没有")
            continue
        collider, limit = component["dynamicCollider"], component["limitInfo"]
        klass = "ActorSwingDynamicBone"
        for name, want, got in (
            ("damping", expect(klass, "damping", entry["damping"]), component["damping"]),
            ("stiffness", expect(klass, "stiffness", entry["stiffness"]), component["stiffness"]),
            ("spring", expect(klass, "spring", entry["spring"]), component["spring"]),
            ("mass", expect(klass, "mass", entry["mass"]), component["mass"]),
            ("colliderRadius", entry["colliderRadius"], collider["float_A"]),
            ("limitX.min", entry["limitX"][0], limit["axisX"]["x"]),
            ("limitX.max", entry["limitX"][1], limit["axisX"]["y"]),
            ("limitZ.min", entry["limitZ"][0], limit["axisZ"]["x"]),
            ("limitZ.max", entry["limitZ"][1], limit["axisZ"]["y"]),
        ):
            checked += 1
            if not close(want, got):
                problems.append(f"摇物骨 {entry['bone']}.{name}: 源 {want} → 包 {got}")

    built_static = built.get("ActorSwingStaticBone", {})
    if len(built_static) != len(manifest["staticBones"]):
        problems.append(f"静态碰撞体个数: 源 {len(manifest['staticBones'])} → 包 {len(built_static)}")
    for entry in manifest["staticBones"]:
        component = built_static.get(entry["bone"])
        if component is None:
            problems.append(f"碰撞体 {entry['bone']}: 包里没有")
            continue
        collider = component["staticCollider"]
        for name, want, got in (("type", entry["type"], collider["type"]),
                                ("radius", entry["radius"], collider["float_A"]),
                                ("radiusSub", entry["radiusSub"], collider["float_B"])):
            checked += 1
            if not close(want, got):
                problems.append(f"碰撞体 {entry['bone']}.{name}: 源 {want} → 包 {got}")

    for entry in manifest["breastBones"]:
        component = built.get("ActorSwingBreastBone", {}).get(entry["bone"])
        if component is None:
            problems.append(f"胸部驱动 {entry['bone']}: 包里没有")
            continue
        klass = "ActorSwingBreastBone"
        for name, want, got in (("damping", expect(klass, "damping", entry["damping"]), component["damping"]),
                                ("stiffness", expect(klass, "stiffness", entry["stiffness"]), component["stiffness"]),
                                ("spring", expect(klass, "spring", entry["spring"]), component["spring"]),
                                ("average", expect(klass, "average", entry["average"]), component["average"])):
            checked += 1
            if not close(want, got):
                problems.append(f"胸部驱动.{name}: 源 {want} → 包 {got}")
        checked += 1
        if len(component["upCurve"]["m_Curve"]) != len(entry["upCurve"]):
            problems.append(f"胸部驱动.upCurve 关键帧数: 源 {len(entry['upCurve'])} → "
                            f"包 {len(component['upCurve']['m_Curve'])}")

    # Pose drivers are not checked entry-by-entry: nested drivers crash the game (AV at
    # UnityPlayer+0x143EF86, hit twice), so the transfer collapses each bone lineage into one. What
    # has to hold is the invariant, not equality — every lineage the source drove is still driven,
    # and no lineage is driven twice.
    drivers = built.get("ActorAnimationQuartzDriverRotationBone", {})
    parent_of = {}
    for path_id, owner in transforms.items():
        obj = next((o for o in env.objects if o.path_id == path_id), None)
        if obj is None:
            continue
        father = obj.read_typetree().get("m_Father", {}).get("m_PathID")
        parent_of[names.get(owner, "")] = bone_of(father) if father else ""

    def lineage(bone_name):
        chain, cursor, guard = [], bone_name, 0
        while cursor and guard < 64:
            chain.append(cursor)
            cursor = parent_of.get(cursor, "")
            guard += 1
        return chain

    for bone_name in drivers:
        checked += 1
        above = [name for name in lineage(bone_name)[1:] if name in drivers]
        if above:
            problems.append(f"姿势驱动 {bone_name}: 骨脉上层 {above[0]} 也有驱动（嵌套会崩）")
    for entry in manifest["rotationDrivers"]:
        checked += 1
        if not any(name in drivers for name in lineage(entry["bone"])):
            problems.append(f"姿势驱动 {entry['bone']}: 整条骨脉在包里都没有驱动，源的意图丢了")

    # The one thing that must NOT match the source: the collision channel.
    for entry in manifest["dynamicBones"][:1]:
        component = built.get("ActorSwingDynamicBone", {}).get(entry["bone"])
        if component and component["dynamicCollider"]["collisionMask"] == -1 and entry["colliderMask"] == -1:
            print("提示: collisionMask 仍是 -1（源也是 -1）。裙摆类应被目标表覆盖成 1，检查该骨类别。")

    print(f"对了 {checked} 个字段，{len(problems)} 处不符")
    for problem in problems[:40]:
        print(f"   ✗ {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
