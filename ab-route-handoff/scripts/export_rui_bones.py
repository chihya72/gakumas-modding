# -*- coding: utf-8 -*-
"""从 rui body bundle 导出带层级/TRS 的加权骨 sidecar。"""
from pathlib import Path
import json

import UnityPy


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT.parent / "source" / "mdl_chr_rui-nurs-00_body" / "bundles" / "mdl_chr_rui-nurs-00_body.unity3d"
TARGET_SKELETON = ROOT / "source" / "hmsz0000_skeleton.json"
OUT = ROOT / "build" / "rui_bones.json"


# An ActorSwingDynamicBone serialises exactly these params; the runtime's other
# swing fields (rootWeight, pendulum, wind...) are computed, not authored — note
# every source bone has m_Weight=1.0 while the live base bones read rootWeight=0.3,
# so m_Weight is NOT rootWeight. Only export what the source actually authored.
SWING_KEYS = ("damping", "stiffness", "spring", "mass")


def swing_params_by_gameobject(env):
    """path_id of GameObject -> swing params, for every swing bone in the bundle.

    Identified by typetree key signature: m_Script points into a CAB dependency we
    don't have, so the class name is unavailable.
    """
    out = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if not all(k in tree for k in SWING_KEYS):
            continue
        go = tree.get("m_GameObject")
        path_id = go.get("m_PathID") if isinstance(go, dict) else None
        if not path_id:
            continue
        params = {k: float(tree[k]) for k in SWING_KEYS}
        params["useWindGlobalForce"] = bool(tree.get("useWindGlobalForce", 0))
        out[path_id] = params
    return out


def vec3(value):
    return [float(value.X), float(value.Y), float(value.Z)]


def quat(value):
    return [float(value.X), float(value.Y), float(value.Z), float(value.W)]


def extra_swing_bones(env, swing_by_go, bone_names):
    """Swing bones absent from m_Bones — the unweighted tip of every chain.

    Skinning doesn't need them so they never reach m_Bones, but the sim does: a
    chain's last segment is defined by its tip, and without one the stethoscope
    diverges. They can't join `bones`, which must stay index-aligned with the mod
    mesh's bone array, so they ride in their own list and attach by parent name.
    Named '*_S_End' except RightFrontStethoscope3_S — match on absence, not suffix.
    """
    out = []
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        node = obj.read()
        params = swing_by_go.get(node.m_GameObject.path_id)
        if params is None:
            continue
        name = node.m_GameObject.read().m_Name
        if name in bone_names:
            continue
        father = node.m_Father
        if not (father and father.path_id):
            continue
        out.append({
            "name": name,
            "parentName": father.read().m_GameObject.read().m_Name,
            "localPosition": vec3(node.m_LocalPosition),
            "localRotation": quat(node.m_LocalRotation),
            "localScale": vec3(node.m_LocalScale),
            "swing": params,
        })
    return out


def main():
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"
    env = UnityPy.load(str(BUNDLE))
    target = json.loads(TARGET_SKELETON.read_text(encoding="utf-8"))
    target_names = {node["name"] for node in target["nodes"]}

    renderer = None
    for obj in env.objects:
        if obj.type.name != "SkinnedMeshRenderer":
            continue
        candidate = obj.read()
        if getattr(candidate, "m_Bones", None):
            renderer = candidate
            break
    if renderer is None:
        raise RuntimeError(f"未找到带骨骼的 SkinnedMeshRenderer: {BUNDLE}")

    swing_by_go = swing_params_by_gameobject(env)
    transforms = [ptr.read() for ptr in renderer.m_Bones]
    path_to_index = {node.path_id: index for index, node in enumerate(transforms)}
    bones = []
    for index, node in enumerate(transforms):
        name = node.m_GameObject.read().m_Name
        father = node.m_Father
        parent_index = path_to_index.get(father.path_id, -1) if father else -1
        parent_chain = []
        current = father.read() if father and father.path_id else None
        while current is not None:
            parent_chain.append(current.m_GameObject.read().m_Name)
            current = current.m_Father.read() if current.m_Father and current.m_Father.path_id else None
        bone = {
            "index": index,
            "name": name,
            "matched": name in target_names,
            "parentIndex": parent_index,
            "parentChain": parent_chain,
            "localPosition": vec3(node.m_LocalPosition),
            "localRotation": quat(node.m_LocalRotation),
            "localScale": vec3(node.m_LocalScale),
        }
        swing = swing_by_go.get(node.m_GameObject.path_id)
        if swing is not None:
            bone["swing"] = swing
        bones.append(bone)

    assert bones and all(b["index"] == i for i, b in enumerate(bones))
    assert all(b["parentIndex"] < b["index"] for b in bones if b["parentIndex"] >= 0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    swung = sum("swing" in b for b in bones)
    bone_names = {b["name"] for b in bones}
    extras = extra_swing_bones(env, swing_by_go, bone_names)
    assert all(e["parentName"] in bone_names for e in extras), "a chain tip has no parent in bones[]"
    assert swung + len(extras) == len(swing_by_go), "some swing bone reached neither list"

    OUT.write_text(json.dumps({
        "schemaVersion": 4,
        "boneCount": len(bones),
        "matchedInHmsz": sum(b["matched"] for b in bones),
        "rootBone": "Hips",
        "bones": bones,
        "extraSwingBones": extras,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: bones={len(bones)} matched={sum(b['matched'] for b in bones)} "
          f"swing={swung} extraSwingBones={len(extras)}")


if __name__ == "__main__":
    main()
