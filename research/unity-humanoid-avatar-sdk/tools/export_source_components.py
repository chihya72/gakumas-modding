"""Export a source body bundle's own rig as a transfer manifest the SDK can read.

The SDK used to rebuild the swing rig from the median of 530 stock costumes. A source model that
already ships a rig — IDOLY PRIDE does, 42 tuned dynamic bones on chs-sucu-00 — makes that both more
work and worse: the medians differ from the author's values by up to 7x (mass 0.1 vs 0.7). This is
the export half of carrying the source's rig over instead; see docs/component-transfer-route.md.

Three traps this file exists to avoid:

  * Read the ORIGINAL `.unity3d`. The `.cleartree` / `.resave` variants next to it have been through
    a re-save that drops the type trees, so every MonoBehaviour reads back with zero fields and the
    bundle looks like it carries no rig at all.
  * The previous exporter wrote one file per component *class* (`ActorSwingDynamicBone.json`, 28
    bytes, `{"m_GameObject": null}`). Per-instance, keyed by host bone name, is the whole point.
  * The output is shaped for Unity's JsonUtility, which cannot parse arbitrary nested objects — one
    flat typed array per component class, references as bone-name strings, vectors as float arrays.

Whatever this cannot map is listed under `skipped`, so a field that matters is loud rather than
silently dropped.

    python tools/export_source_components.py <bundle> <output.json>
"""
import json
import sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"


def vec(value):
    return [value["x"], value["y"], value["z"]]


def pair(value):
    return [value["x"], value["y"]]


def curve(value):
    return [{"time": k["time"], "value": k["value"], "inSlope": k["inSlope"], "outSlope": k["outSlope"]}
            for k in value["m_Curve"]]


def main(bundle_path, output_path):
    env = UnityPy.load(bundle_path)

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

    def reference(value):
        return bone_of(value["m_PathID"]) if value and value.get("m_PathID") else ""

    out = {"source": bundle_path.replace("\\", "/").split("/")[-1],
           "dynamicBones": [], "staticBones": [], "breastBones": [], "rotationDrivers": [], "skipped": []}

    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"))
        host = bone_of(tree.get("m_GameObject", {}).get("m_PathID"))
        if not klass or not host:
            continue

        if klass == "ActorSwingDynamicBone":
            collider, limit = tree["dynamicCollider"], tree["limitInfo"]
            out["dynamicBones"].append({
                "bone": host,
                "damping": tree["damping"], "stiffness": tree["stiffness"],
                "spring": tree["spring"], "mass": tree["mass"],
                "useWindGlobalForce": tree["useWindGlobalForce"],
                "colliderType": collider["type"], "colliderMask": collider["collisionMask"],
                "colliderVectorA": vec(collider["vector3_A"]), "colliderVectorB": vec(collider["vector3_B"]),
                "colliderRadius": collider["float_A"], "colliderRadiusSub": collider["float_B"],
                "useLimit": limit["useLimit"],
                "limitX": pair(limit["axisX"]), "limitY": pair(limit["axisY"]), "limitZ": pair(limit["axisZ"]),
            })

        elif klass == "ActorSwingStaticBone":
            collider = tree["staticCollider"]
            out["staticBones"].append({
                "bone": host, "type": collider["type"], "mask": collider["collisionMask"],
                "vectorA": vec(collider["vector3_A"]), "vectorB": vec(collider["vector3_B"]),
                "radius": collider["float_A"], "radiusSub": collider["float_B"],
            })

        elif klass == "ActorSwingBreastBone":
            collider, limit = tree["breastCollider"], tree["limitInfo"]
            out["breastBones"].append({
                "bone": host,
                "damping": tree["damping"], "stiffness": tree["stiffness"], "spring": tree["spring"],
                "average": tree["average"], "useArmCorrection": tree["useArmCorrection"],
                "useLimit": limit["useLimit"],
                "limitX": pair(limit["axisX"]), "limitY": pair(limit["axisY"]), "limitZ": pair(limit["axisZ"]),
                "colliderType": collider["type"], "colliderMask": collider["collisionMask"],
                "colliderRadius": collider["float_A"], "colliderRadiusSub": collider["float_B"],
                "leftBreast": reference(tree["leftBreast"]), "rightBreast": reference(tree["rightBreast"]),
                "leftBreastEnd": reference(tree["leftBreastEnd"]),
                "rightBreastEnd": reference(tree["rightBreastEnd"]),
                "leftLowerArm": reference(tree["leftLowerArm"]),
                "rightLowerArm": reference(tree["rightLowerArm"]),
                "upCurve": curve(tree["upCurve"]), "sideCurve": curve(tree["sideCurve"]),
            })

        elif klass == "VLActorExpressionBone":
            # A generic pose driver: follow `_referenceBone`, per axis, scaled and clamped. The target
            # game's equivalent is ActorAnimationQuartzDriverRotationBone, whose setting holds one
            # float3 of coefficients and a float3 min/max — i.e. input axis i drives output axis i.
            # The source can remap axes (`outputAxisType` per entry); when it does, there is nothing
            # to map onto, so those are skipped rather than silently flattened.
            axes = tree["_axisData"]
            remapped = any(entry["outputAxisType"] != index for index, entry in enumerate(axes))
            # `*_H` helper bones are the target game's own convention (528/530 stock bodies carry its
            # humanoid drivers on exactly these). The SDK synthesises those from the stock tables;
            # the source's versions are mostly zero-coefficient placeholders anyway.
            if host.endswith("_H"):
                out["skipped"].append(f"{klass} on {host}: `*_H` 走目标游戏的 humanoid driver 表")
                continue
            if tree["_transformType"] != 1:
                out["skipped"].append(f"{klass} on {host}: _transformType={tree['_transformType']} 不是旋转")
                continue
            if remapped:
                out["skipped"].append(f"{klass} on {host}: 轴重映射 "
                                      f"{[e['outputAxisType'] for e in axes]}，目标无对应字段")
                continue
            out["rotationDrivers"].append({
                "bone": host, "reference": reference(tree["_referenceBone"]),
                "rotationOrder": tree["_rotationOrder"],
                "coefficient": [entry["coefficient"] for entry in axes],
                "limitMin": [entry["min"] for entry in axes],
                "limitMax": [entry["max"] for entry in axes],
            })

        elif klass in ("IKGoalEffector", "IKHintEffector", "IKBodyEffector", "LookAtEffector"):
            # Deliberately not transferred: the SDK already synthesises all ten, and the values are
            # the same fixed table on both sides (goal/hint 0-3, LookAt weights 0). Nothing to gain.
            pass
        else:
            out["skipped"].append(f"{klass} on {host}: 没有映射")

    for key in ("dynamicBones", "staticBones", "breastBones", "rotationDrivers"):
        out[key].sort(key=lambda entry: entry["bone"])
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=1)

    print(f"-> {output_path}")
    for key in ("dynamicBones", "staticBones", "breastBones", "rotationDrivers"):
        print(f"   {key:16} {len(out[key]):3}")
    if out["skipped"]:
        print(f"   skipped         {len(out['skipped']):3}")
        for note in out["skipped"][:8]:
            print(f"      {note}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2])
