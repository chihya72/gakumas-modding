"""Move the arm the way the game does and measure what the skin does.

The corrective rig has a strong paper case — 530/530 stock bodies carry it, 17% of their weight sits
on it, the humanoid bone holds none of the joint — and had never once been shown to change a
millimetre on a converted model. This is that test, offline: take the shipped rest pose, rotate the
upper arm down by the angle the game's idle actually uses, skin it with plain linear blending the way
the game does, and measure the arm's cross-section along its length. The candy-wrapper collapse is a
dip in that profile; a rig that works fills the dip in.

**Which motion matters was read out of the game, not guessed.** `il2cpp.cs` (3.2.3):
`ActorAnimationQuartzDriverHumanoidArmBone.Calc(muscleValue, muscleConvertCoefficient,
rotateCoefficient)` is fed by a `MuscleHandle` — muscle 41/50, *Arm Twist In-Out*. So `Arm_H` and
`Arm_Roll_H` respond to the arm **twisting**, not to it swinging: under a pure bend their local
rotation stays at rest and they ride the arm rigidly, deforming exactly like the humanoid bone would.
`--motion=bend` therefore measures the same thing with and without them, by construction (confirmed on
stock costumes by `measure_rig_gap.py`: 0.0% across 114 bands). `--motion=twist` is the one that can
see the rig at all — it turns the upper arm about its own long axis and lets each helper take its
share, which is the shear these bones exist to spread.

    python tools/probe_joint_collapse.py <built.bundle> [--degrees 67] [--side Left] [--motion twist]
"""
import math
import sys

import numpy as np
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"
# Stock coefficients are Arm_H −0.8 and Arm_Roll_H −0.3 — the shoulder end of the deltoid sees only
# 20% of a wrist-driven twist. They are not hardcoded here: each bundle's own drivers are read below,
# so a costume that tuned them is measured as tuned.


def load(path):
    env = UnityPy.load(path)
    names = {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            names[obj.path_id] = obj.read_typetree()["m_Name"]
    local, parent, owner = {}, {}, {}
    children = {}
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        tree = obj.read_typetree()
        name = names.get(tree["m_GameObject"]["m_PathID"])
        owner[obj.path_id] = name
        local[name] = tree
        children[obj.path_id] = [c["m_PathID"] for c in tree["m_Children"]]
    for path_id, kids in children.items():
        for kid in kids:
            parent[owner.get(kid)] = owner.get(path_id)
    smr = next(o.read_typetree() for o in env.objects if o.type.name == "SkinnedMeshRenderer")
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
    bones = [owner.get(b["m_PathID"]) for b in smr["m_Bones"]]

    # Which bones host an arm twist driver, by component rather than by name. A converted model keeps
    # the source's own bone names on purpose (`TwistAdopter` adopts, it does not rename), so looking
    # for `LeftArm_H` reports "no rig" on a bundle that has the full rig — `+UpperArmTwist L A01` is
    # the same bone doing the same job.
    scripts = {o.path_id: o.read().m_ClassName for o in env.objects if o.type.name == "MonoScript"}
    driven = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        klass = scripts.get(tree.get("m_Script", {}).get("m_PathID")) or ""
        if "QuartzDriverHumanoidArmBone" not in klass:
            continue
        host = names.get(tree.get("m_GameObject", {}).get("m_PathID"))
        # −0.8 is the half-angle bone, −0.3 the roll bone; the coefficient is what tells them apart.
        driven[host] = (tree.get("setting") or {}).get("coefficient")
    return mesh, bones, parent, local, driven


def trs(q, t, s=(1, 1, 1)):
    x, y, z, w = q
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.array(s)
    m[:3, 3] = t
    return m


def axis_angle(axis, degrees):
    axis = np.array(axis, float)
    axis /= np.linalg.norm(axis)
    half = math.radians(degrees) / 2
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def main(bundle, degrees=67.0, side="Left", motion="twist", use_rig=True):
    degrees = float(degrees)
    mesh, bones, parent, local, driven = load(bundle)
    # Only the drivers on this side's arm: walk up from each host until the arm is reached.
    def on_this_arm(name):
        for _ in range(8):
            if name == f"{side}Arm":
                return True
            name = parent.get(name)
            if name is None:
                return False
        return False

    helpers = {name: coefficient for name, coefficient in driven.items()
               if coefficient is not None and on_this_arm(name)}
    # `--rig=off` runs the same bundle with its drivers ignored: the A/B for "is the twist rig worth
    # anything", on one model, with everything else held identical.
    if not use_rig:
        helpers = {}
    rig = len(helpers) > 0

    def world(name, override, cache):
        if name in cache or name is None:
            return cache.get(name)
        tree = local[name]
        q = override.get(name) or tuple(tree["m_LocalRotation"][k] for k in "xyzw")
        t = tuple(tree["m_LocalPosition"][k] for k in "xyz")
        s = tuple(tree["m_LocalScale"][k] for k in "xyz")
        above = world(parent.get(name), override, cache)
        m = trs(q, t, s)
        cache[name] = m if above is None else above @ m
        return cache[name]

    def skinned(override):
        cache = {}
        matrices = []
        for index, bone in enumerate(bones):
            m = world(bone, override, cache)
            raw = mesh.m_BindPose[index]
            cell = ((lambda r, c: getattr(raw, f"M{r}{c}")) if hasattr(raw, "M00")
                    else (lambda r, c: getattr(raw, f"e{r}{c}")))
            bind = np.array([[cell(0, 0), cell(1, 0), cell(2, 0), cell(3, 0)],
                             [cell(0, 1), cell(1, 1), cell(2, 1), cell(3, 1)],
                             [cell(0, 2), cell(1, 2), cell(2, 2), cell(3, 2)],
                             [0, 0, 0, 1]])
            matrices.append((m if m is not None else np.eye(4)) @ bind)
        matrices = np.array(matrices)
        flat = np.array(mesh.m_Vertices, float).reshape(-1, 3)
        homo = np.concatenate([flat, np.ones((len(flat), 1))], axis=1)
        weights = np.zeros((len(flat), 4))
        indices = np.zeros((len(flat), 4), dtype=np.int64)
        for i, s in enumerate(mesh.m_Skin):
            weights[i] = s.weight
            indices[i] = s.boneIndex
        out = np.zeros((len(flat), 3))
        for k in range(4):
            out += weights[:, k, None] * np.einsum("nij,nj->ni", matrices[indices[:, k]][:, :3, :], homo)
        total = weights.sum(axis=1)
        out[total > 0] /= total[total > 0, None]
        return out, cache

    def qmul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)

    def local_rotation(name):
        q = local[name]["m_LocalRotation"]
        return (q["x"], q["y"], q["z"], q["w"])

    rest_points, rest_cache = skinned({})

    def axis_in_parent_frame(name, world_axis):
        """A bone's local rotation is applied in its parent's frame, so the axis has to go there."""
        above = parent.get(name)
        if above is None or above not in rest_cache:
            return world_axis
        return np.linalg.inv(rest_cache[above][:3, :3]) @ world_axis

    if motion == "bend":
        # Swing the arm down about the character's forward axis, the motion a standing idle applies.
        # The helpers are twist distributors and stay at rest through this — see the module docstring.
        turn = axis_angle(axis_in_parent_frame(f"{side}Arm", np.array([0.0, 0.0, 1.0])),
                          degrees if side == "Left" else -degrees)
        override = {f"{side}Arm": qmul(turn, local_rotation(f"{side}Arm"))}
    else:
        # Twist the upper arm about its own long axis — the motion the drivers actually read. Each
        # helper then takes its coefficient's share, so the bone nearest the shoulder ends up with
        # (1 + coefficient) of it and the shear is spread down the limb instead of piling on one joint.
        shoulder = rest_cache[f"{side}Arm"][:3, 3]
        elbow = rest_cache[f"{side}ForeArm"][:3, 3]
        world_axis = (elbow - shoulder) / np.linalg.norm(elbow - shoulder)
        override = {f"{side}Arm": qmul(axis_angle(axis_in_parent_frame(f"{side}Arm", world_axis), degrees),
                                       local_rotation(f"{side}Arm"))}
        for name, coefficient in helpers.items():
            if name not in local:
                continue
            back = axis_angle(axis_in_parent_frame(name, world_axis), degrees * coefficient)
            override[name] = qmul(back, local_rotation(name))

    posed, cache = skinned(override)

    # Self-check: a twist about the arm's own axis leaves the elbow exactly where it was. Getting this
    # axis into the wrong frame is the failure that produced this file's old readings, and it is silent
    # — the profile still prints, it just measures a bone swinging somewhere diagonal.
    if motion != "bend":
        drift = np.linalg.norm(cache[f"{side}ForeArm"][:3, 3] - rest_cache[f"{side}ForeArm"][:3, 3])
        if drift > 0.001:
            raise SystemExit(f"自检失败：扭转把肘关节挪了 {drift * 1000:.1f}mm（应当为 0），旋转轴算错了")

    # Cross-section radius along the upper arm, measured in the posed shape.
    shoulder = rest_cache[f"{side}Arm"][:3, 3]
    elbow = rest_cache[f"{side}ForeArm"][:3, 3]
    axis = elbow - shoulder
    length = np.linalg.norm(axis)
    axis /= length
    t = (rest_points - shoulder) @ axis / length
    # Selecting by geometry alone was wrong twice over. A slab through the shoulder caught the whole
    # torso (it reported a 71 cm "arm radius"); adding a 10 cm cylinder still caught the shoulder
    # armour and the veil that hangs off the head past the arm — 44% and 23% of the band — and their
    # not following the arm read as a 28% "collapse". What belongs to the arm is what the arm's bones
    # *drive*, so select by dominant bone, and take that set from the untouched build so both runs
    # measure the same vertices.
    family = {f"{side}Shoulder", f"{side}Arm", f"{side}ForeArm", f"{side}Arm_H",
              f"{side}Arm_Roll_H", f"{side}ForeArm_H", f"{side}ForeArm_Roll_H"} | set(helpers)
    arm = local.get(f"{side}Arm")
    owned = np.zeros(len(rest_points), bool)
    for i, s in enumerate(mesh.m_Skin):
        best = max(range(4), key=lambda k: s.weight[k])
        if s.weight[best] <= 0 or s.boneIndex[best] >= len(bones):
            continue
        name = bones[s.boneIndex[best]]
        # A source twist bone hanging under the arm is part of the arm too.
        node = name
        depth = 0
        while node is not None and depth < 8:
            if node in family:
                owned[i] = True
                break
            node = parent.get(node)
            depth += 1
    near = (t > -0.05) & (t < 1.05) & owned
    # Follow the same vertices after posing, so this compares one piece of geometry with itself.
    p_shoulder = cache[f"{side}Arm"][:3, 3]
    p_elbow = cache[f"{side}ForeArm"][:3, 3]
    p_axis = (p_elbow - p_shoulder) / np.linalg.norm(p_elbow - p_shoulder)

    verb = "上臂扭转" if motion != "bend" else "手臂下垂"
    print(f"{bundle.split('/')[-1]}   矫正骨 {'有' if rig else '无'}   {verb} {degrees:.0f}°")
    print("   沿骨位置    静止半径    下垂后半径    变化")
    worst = 0.0
    for lo in np.arange(0.0, 0.95, 0.1):
        pick = near & (t >= lo) & (t < lo + 0.1)
        if pick.sum() < 12:
            continue
        def radius(points, origin, direction):
            rel = points[pick] - origin
            along = rel @ direction
            perp = rel - np.outer(along, direction)
            return np.percentile(np.linalg.norm(perp, axis=1), 90) * 100
        a = radius(rest_points, shoulder, axis)
        b = radius(posed, p_shoulder, p_axis)
        change = (b - a) / a * 100
        worst = min(worst, change)
        print(f"     {lo + 0.05:.2f}      {a:6.2f}cm     {b:6.2f}cm    {change:+6.1f}%")
    print(f"   最严重的一段：{worst:+.1f}%（负数=塌陷）")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    degrees = next((a.split("=")[1] for a in sys.argv if a.startswith("--degrees=")), 67.0)
    side = next((a.split("=")[1] for a in sys.argv if a.startswith("--side=")), "Left")
    motion = next((a.split("=")[1] for a in sys.argv if a.startswith("--motion=")), "twist")
    use_rig = next((a.split("=")[1] for a in sys.argv if a.startswith("--rig=")), "on") != "off"
    raise SystemExit(main(args[0], degrees, side, motion, use_rig))
