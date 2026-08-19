"""How much of this game's deformation quality lives in the 18 bones Unity's Humanoid rig has no
concept of — measured on the game's own bodies, not on any one import.

An external model can only ever arrive with the 52 Humanoid bones mapped; the corrective `*_H` bones
are this game's own invention and no FBX carries them. So the architectural question is: take a stock
costume, fold its corrective weights back onto the humanoid bone it hangs off — which is exactly what
that same costume would look like if it had been authored with 52 bones — bend a joint the way the
game does, and compare against the real thing.

Both sides are skinned with plain linear blending, the way the game does.

**The upper arm's helpers do not move under a bend, and that is not a simplification.** This file used
to turn `Arm_H` / `Arm_Roll_H` by their coefficient about the *bend* axis, which produced readings of
+60% to +166% "extra volume" — an artifact of dragging a bone at 60% of the arm's length off the arm's
own axis. Read out of the game instead (`il2cpp.cs`, 3.2.3): `ActorAnimationQuartzDriverHumanoidArmBone`
is `Calc(muscleValue, muscleConvertCoefficient, rotateCoefficient)` fed by a `MuscleHandle` — muscle
41/50, Arm Twist In-Out. A pure bend leaves that muscle at zero, so the helper inherits the arm rigidly
and deforms exactly like the humanoid bone it was carved out of. The gap this file measures at the
shoulder is therefore expected to be 0.0%: swinging a joint is not what the corrective rig is for.

The rig's own motion is *twist*, and that is measured by `probe_joint_collapse.py --motion=twist`.

    python tools/measure_rig_gap.py [--bodies 12] [--degrees 67]
"""
import argparse
import glob
import json
import math
import os

import numpy as np

BASE = 'D:/GIT/gakumas-modding/mod-workspace/libraries/assetstudio-body-json'
# helper -> (bone whose weight it came out of, share of the joint's rotation it takes)
FOLD = {"Arm_H": ("Arm", -0.8), "Arm_Roll_H": ("Arm", -0.3),
        "ForeArm_H": ("ForeArm", -0.4), "ForeArm_Roll_H": ("ForeArm", 0.5),
        "Hand_H": ("Hand", 0.9),
        "UpLeg_H": ("UpLeg", -1.0), "UpLeg_Roll_H": ("UpLeg", -0.6), "Leg_H": ("Leg", -0.5)}


def quat_matrix(q, t):
    x, y, z, w = q
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, 3] = t
    return m


def axis_angle(axis, degrees):
    axis = np.array(axis, float)
    axis /= np.linalg.norm(axis)
    s = math.sin(math.radians(degrees) / 2)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(math.radians(degrees) / 2))


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def measure(directory, side, degrees):
    skeleton = json.load(open(f'{directory}/Geo_Body.skeleton.json', encoding='utf-8'))
    mesh = json.load(open(f'{directory}/Geo_Body.json', encoding='utf-8'))
    nodes = skeleton['nodes']
    index_of = {n['name']: i for i, n in enumerate(nodes)}
    weighted = {n['weightedIndex']: n['name'] for n in nodes if n.get('weightedIndex') is not None}
    slot_of = {name: slot for slot, name in weighted.items()}

    def world(override):
        out = [None] * len(nodes)
        for i, n in enumerate(nodes):
            q = override.get(n['name'], n['localRotation'])
            m = quat_matrix(q, n['localPosition'])
            out[i] = m if n['parent'] < 0 else out[n['parent']] @ m
        return out

    rest = world({})

    # Pose in world space, not in the parent's. Rotating a child by pre-multiplying a world-axis
    # quaternion onto its local rotation turns it about the *parent's* axes — and `Shoulder`'s frame
    # is not the identity, so the arm swung somewhere diagonal and every reading was nonsense (it
    # reported the arm losing 65% of its radius). Here the whole arm subtree is rigidly rotated about
    # the shoulder joint by a world-space turn, which is unambiguous.
    def spin(theta, pivot):
        c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        r = np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], float)
        to = np.eye(4)
        to[:3, 3] = -np.array(pivot)
        back = np.eye(4)
        back[:3, 3] = np.array(pivot)
        return back @ r @ to

    theta = degrees if side == 'Left' else -degrees
    arm_index = index_of[f'{side}Arm']
    pivot = rest[arm_index][:3, 3]

    subtree = set()
    stack = [arm_index]
    while stack:
        node = stack.pop()
        subtree.add(node)
        stack += [i for i, n in enumerate(nodes) if n['parent'] == node]

    turn = spin(theta, pivot)
    plain = [turn @ m if i in subtree else m for i, m in enumerate(rest)]
    # The two helpers on this joint are twist distributors: their driver reads the Arm Twist In-Out
    # muscle, which a bend does not move. So they ride the arm rigidly, same as `plain` — see the
    # module docstring for why simulating them here was wrong rather than approximate.
    rigged = list(plain)

    direction = plain[index_of[f'{side}ForeArm']][:3, 3] - plain[arm_index][:3, 3]
    direction /= np.linalg.norm(direction)
    if degrees > 30 and direction[1] > -0.5:
        raise SystemExit(f'自检失败：手臂没有垂下去，方向 {direction.round(2)}（应当接近 (0,-1,0)）')

    flat = mesh['m_Vertices']
    points = np.array(flat, float).reshape(-1, 3)
    binds = []
    for raw in mesh['m_BindPose']:
        # AssetStudio names these transposed — `world @ bindpose` only comes out as the identity at
        # rest after transposing, which is the assertion below.
        b = np.array([[raw['M00'], raw['M01'], raw['M02'], raw['M03']],
                      [raw['M10'], raw['M11'], raw['M12'], raw['M13']],
                      [raw['M20'], raw['M21'], raw['M22'], raw['M23']],
                      [raw['M30'], raw['M31'], raw['M32'], raw['M33']]]).T
        binds.append(b)
    binds = np.array(binds)
    for slot, name in list(weighted.items())[:8]:
        error = np.abs(rest[index_of[name]] @ binds[slot] - np.eye(4)).max()
        if error > 1e-3:
            # Not SystemExit: `except Exception` in the caller does not catch that, so one costume
            # with a posed accessory bone used to end the whole sweep.
            raise ValueError(f'{name} 的 world@bindpose 不是单位阵（偏 {error:.3f}），bindpose 读法错了')

    weights = np.zeros((len(points), 4))
    slots = np.zeros((len(points), 4), dtype=np.int64)
    for i, s in enumerate(mesh['m_Skin']):
        weights[i] = s['weight']
        slots[i] = s['boneIndex']

    # The 52-bone version of this very costume: every corrective's weight goes back to the humanoid
    # bone it was carved out of.
    remap = np.arange(len(binds))
    folded = 0
    for helper, (owner, _) in FOLD.items():
        for s in ('Left', 'Right'):
            a, b = f'{s}{helper}', f'{s}{owner}'
            if a in slot_of and b in slot_of:
                remap[slot_of[a]] = slot_of[b]
                folded += 1

    def skin(matrices, slot_map):
        skinning = np.array([matrices[index_of[weighted[s]]] @ binds[s] if s in weighted else np.eye(4)
                             for s in range(len(binds))])
        homo = np.concatenate([points, np.ones((len(points), 1))], axis=1)
        out = np.zeros((len(points), 3))
        for k in range(4):
            out += weights[:, k, None] * np.einsum('nij,nj->ni', skinning[slot_map[slots[:, k]]][:, :3, :], homo)
        total = weights.sum(axis=1)
        out[total > 0] /= total[total > 0, None]
        return out

    identity = np.arange(len(binds))
    stock_rest = skin(rest, identity)
    stock_posed = skin(rigged, identity)
    plain_posed = skin(plain, remap)

    shoulder = rest[index_of[f'{side}Arm']][:3, 3]
    elbow = rest[index_of[f'{side}ForeArm']][:3, 3]
    axis = elbow - shoulder
    length = np.linalg.norm(axis)
    axis /= length
    # Only geometry the arm chain drives, so the torso and any hanging accessory stay out of it.
    family = {f'{side}Shoulder', f'{side}Arm', f'{side}ForeArm'} | {
        f'{side}{h}' for h in FOLD if FOLD[h][0] in ('Arm', 'ForeArm')}
    owned = np.zeros(len(points), bool)
    for i in range(len(points)):
        k = int(np.argmax(weights[i]))
        if weights[i][k] > 0:
            owned[i] = weighted.get(slots[i][k]) in family
    t = (stock_rest - shoulder) @ axis / length

    def profile(posed, frames):
        # Measured in the arm's own frame, both times. Against a fixed world axis, geometry that
        # legitimately stays behind (the shoulder cap) reads as a 65% "collapse" purely because the
        # axis swung away from it. In the bone's frame a vertex that follows rigidly lands on itself,
        # so what is left is deformation and nothing else.
        inverse = np.linalg.inv(frames[arm_index])
        homo = np.concatenate([posed, np.ones((len(posed), 1))], axis=1)
        local = (homo @ inverse.T)[:, :3]
        tip = (np.append(frames[index_of[f'{side}ForeArm']][:3, 3], 1.0) @ inverse.T)[:3]
        direction = tip / np.linalg.norm(tip)
        out = {}
        for lo in np.arange(0.0, 0.9, 0.15):
            pick = owned & (t >= lo) & (t < lo + 0.15)
            if pick.sum() < 12:
                continue
            rel = local[pick]
            perp = rel - np.outer(rel @ direction, direction)
            out[round(lo + 0.075, 3)] = np.percentile(np.linalg.norm(perp, axis=1), 90) * 100
        return out

    base = profile(stock_rest, rest)
    with_rig = profile(stock_posed, rigged)
    without = profile(plain_posed, plain)
    rows = []
    for station in sorted(base):
        if station in with_rig and station in without:
            rows.append((station, base[station],
                         (with_rig[station] - base[station]) / base[station] * 100,
                         (without[station] - base[station]) / base[station] * 100))
    return rows, folded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bodies', type=int, default=12)
    parser.add_argument('--degrees', type=float, default=67.0)
    options = parser.parse_args()
    directories = sorted(d for d in glob.glob(f'{BASE}/*_body')
                         if os.path.exists(f'{d}/Geo_Body.json'))[:options.bodies]

    print(f'原版模型自己的对照：同一件衣服，装矫正骨 vs 折成 52 骨，手臂下垂 {options.degrees:.0f}°')
    print('（数字是上臂截面半径相对静止的变化，负=塌陷）\n')
    print(f"{'服装':30} {'沿骨位置':>8} {'原版(有矫正骨)':>15} {'52骨版':>10} {'差':>8}")
    gaps = []
    for directory in directories:
        try:
            rows, folded = measure(directory, 'Left', options.degrees)
        except Exception as error:
            print(f'  跳过 {os.path.basename(directory)}: {error}')
            continue
        if not rows:
            continue
        name = os.path.basename(directory).replace('mdl_chr_', '').replace('_body', '')
        for station, _, rig, plain in rows:
            gaps.append(rig - plain)
            print(f'  {name:28} {station:8.2f} {rig:14.1f}% {plain:9.1f}% {rig - plain:+7.1f}%')
    if gaps:
        gaps.sort()
        print(f'\n共 {len(gaps)} 段。差值分布（正=矫正骨那版更饱满）：'
              f'中位 {gaps[len(gaps) // 2]:+.1f}%，最大 {gaps[-1]:+.1f}%，最小 {gaps[0]:+.1f}%')


if __name__ == '__main__':
    main()
