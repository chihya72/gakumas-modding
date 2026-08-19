"""Skin a built body with the pose the game actually had, and find what tears.

The probe writes every bone's runtime local transform into `avatars.json`. Feed that back through the
same linear blend the game runs and the result is what was on screen — offline, without a game run.
Triangles that blow up in area are exactly the smears and spikes a screenshot shows, and each one is
reported with the bone that dominates it, which is what says *why*.

    python tools/replay_runtime_pose.py <built.bundle> [avatars.json]

Defaults to the newest dump in the probe's config directory.
"""
import collections
import glob
import json
import math
import os
import sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"
PROBE = "D:/Games/gakumas/BepInEx/config/gakumas-avatar-probe"


def quat_matrix(q, t, s):
    x, y, z, w = q
    return [
        [(1 - 2 * (y * y + z * z)) * s[0], 2 * (x * y - z * w) * s[1], 2 * (x * z + y * w) * s[2], t[0]],
        [2 * (x * y + z * w) * s[0], (1 - 2 * (x * x + z * z)) * s[1], 2 * (y * z - x * w) * s[2], t[1]],
        [2 * (x * z - y * w) * s[0], 2 * (y * z + x * w) * s[1], (1 - 2 * (x * x + y * y)) * s[2], t[2]],
    ]


def matmul(a, b):
    out = [[0.0] * 4 for _ in range(3)]
    for row in range(3):
        for column in range(4):
            out[row][column] = sum(a[row][k] * (b[k][column] if k < 3 else (0, 0, 0, 1)[column])
                                   for k in range(3))
            if column == 3:
                out[row][column] += a[row][3]
    return out


def apply(m, v):
    return [m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] + m[r][3] for r in range(3)]


def load_bundle(path):
    env = UnityPy.load(path)
    names, parent, local = {}, {}, {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            names[obj.path_id] = obj.read_typetree()["m_Name"]
    transform_owner, children = {}, {}
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        tree = obj.read_typetree()
        name = names.get(tree["m_GameObject"]["m_PathID"])
        transform_owner[obj.path_id] = name
        children[obj.path_id] = [c["m_PathID"] for c in tree["m_Children"]]
        local[name] = tree
    for path_id, kids in children.items():
        for kid in kids:
            parent[transform_owner.get(kid)] = transform_owner.get(path_id)
    smr = next(o.read_typetree() for o in env.objects if o.type.name == "SkinnedMeshRenderer")
    # Stock bundles carry more than one Mesh and some fail to parse (their vertex data lives in a
    # .resS this dump does not have); take the biggest one that actually came back with geometry.
    mesh = None
    for obj in env.objects:
        if obj.type.name != "Mesh":
            continue
        try:
            candidate = obj.read()
            if getattr(candidate, "m_Vertices", None) and getattr(candidate, "m_Skin", None):
                if mesh is None or candidate.m_VertexCount > mesh.m_VertexCount:
                    mesh = candidate
        except Exception:
            continue
    if mesh is None:
        raise SystemExit("包里没有可读的蒙皮网格")
    bones = [transform_owner.get(b["m_PathID"]) for b in smr["m_Bones"]]
    return mesh, bones, parent, local


def main(bundle, dump=None):
    mesh, bones, parent, rest = load_bundle(bundle)
    dump = dump or sorted(glob.glob(f"{PROBE}/*avatars.json"), key=os.path.getmtime)[-1]
    data = json.load(open(dump, encoding="utf-8"))
    pin = "--pin-helpers" in sys.argv
    # Which actor's pose to read. Without a control this whole measurement means nothing: a stock
    # body posed the same way is the only thing that says whether 500 stretched triangles is a defect
    # or just what a crease looks like at this threshold.
    actor = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--actor=")), None)
    pose = {}
    for animator in data["animators"]:
        if actor and not animator["path"].startswith(actor):
            continue
        for node in animator.get("hierarchy", []):
            name = node["path"].rsplit("/", 1)[-1]
            if name in rest and name not in pose:
                # A/B switch: dropping the `_H` bones back to their rest rotation removes the
                # corrective rig from the replay while keeping the same animation, which is the only
                # way to tell "the drivers tore this" from "the pose tore this".
                if pin and name.endswith("_H"):
                    continue
                pose[name] = node["local"]
    print(f"姿势来自 {os.path.basename(dump)}，命中 {len(pose)}/{len(rest)} 个骨")

    world, missing = {}, 0
    def resolve(name, guard=0):
        if name in world or name is None or guard > 64:
            return world.get(name)
        node = pose.get(name)
        if node is None:
            tree = rest[name]
            q = (tree["m_LocalRotation"]["x"], tree["m_LocalRotation"]["y"],
                 tree["m_LocalRotation"]["z"], tree["m_LocalRotation"]["w"])
            t = (tree["m_LocalPosition"]["x"], tree["m_LocalPosition"]["y"], tree["m_LocalPosition"]["z"])
            s = (tree["m_LocalScale"]["x"], tree["m_LocalScale"]["y"], tree["m_LocalScale"]["z"])
        else:
            q = (node["rx"], node["ry"], node["rz"], node["rw"])
            t = (node["px"], node["py"], node["pz"])
            s = (node["sx"], node["sy"], node["sz"])
        matrix = quat_matrix(q, t, s)
        above = resolve(parent.get(name), guard + 1)
        world[name] = matrix if above is None else matmul(above, matrix)
        return world[name]

    skinning = []
    for index, bone in enumerate(bones):
        matrix = resolve(bone)
        raw = mesh.m_BindPose[index]
        # UnityPy reads Matrix4x4 transposed, same trap as the audit. Field names differ between the
        # typed reader (M00) and the raw node reader (e00) depending on how the file was serialised.
        cell = ((lambda r, c: getattr(raw, f"M{r}{c}")) if hasattr(raw, "M00")
                else (lambda r, c: getattr(raw, f"e{r}{c}")))
        bind = [[cell(0, 0), cell(1, 0), cell(2, 0), cell(3, 0)],
                [cell(0, 1), cell(1, 1), cell(2, 1), cell(3, 1)],
                [cell(0, 2), cell(1, 2), cell(2, 2), cell(3, 2)]]
        skinning.append(matmul(matrix, bind) if matrix else None)
        if matrix is None:
            missing += 1

    flat = mesh.m_Vertices
    rest_points = [flat[i:i + 3] for i in range(0, len(flat), 3)]
    posed = []
    for index, skin in enumerate(mesh.m_Skin):
        v = rest_points[index]
        acc = [0.0, 0.0, 0.0]
        total = 0.0
        for weight, bone_index in zip(skin.weight, skin.boneIndex):
            if weight <= 0 or bone_index >= len(skinning) or skinning[bone_index] is None:
                continue
            moved = apply(skinning[bone_index], v)
            acc = [a + weight * m for a, m in zip(acc, moved)]
            total += weight
        posed.append([a / total for a in acc] if total > 0 else v)

    def area(a, b, c):
        u = [b[i] - a[i] for i in range(3)]
        w = [c[i] - a[i] for i in range(3)]
        cross = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
        return 0.5 * math.sqrt(sum(c * c for c in cross))

    indices = mesh.m_Indices
    blame = collections.Counter()
    worst = []
    for i in range(0, len(indices) - 2, 3):
        tri = indices[i:i + 3]
        before = area(*[rest_points[t] for t in tri])
        after = area(*[posed[t] for t in tri])
        if before < 1e-9:
            continue
        ratio = after / before
        if ratio > 4.0:
            # What the triangle *spans* is the diagnosis: three vertices on one limb tear because the
            # pose is extreme, but a triangle bridging two unrelated bones is a weighting fault.
            owners = []
            for vertex in tri:
                skin = mesh.m_Skin[vertex]
                heaviest = max(range(4), key=lambda k: skin.weight[k])
                owners.append(bones[skin.boneIndex[heaviest]])
            blame[" + ".join(sorted(set(owners)))] += 1
            worst.append((ratio, tri[0]))
    print(f"面积膨胀 >4× 的三角形 {len(worst)} 个（共 {len(indices)//3}）"
          + (f"，{missing} 根骨没有姿势" if missing else ""))
    for bone, count in blame.most_common(12):
        print(f"   {count:6d} 个  ←  {bone}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(*sys.argv[1:3]))
