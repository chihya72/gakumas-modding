"""The corrective helper rig, measured off the stock bodies: where the `*_H` bones sit and how much
of each humanoid bone's weight they carry.

Every stock body skins its joints to corrective bones rather than to the humanoid bone itself —
530/530 carry `Arm_H`, `Arm_Roll_H`, `ForeArm_H`, `ForeArm_Roll_H`, `Hand_H`, `UpLeg_H`,
`UpLeg_Roll_H` and `Leg_H` on both sides, 17% of the whole body's weight mass sits on them, and at
the shoulder joint the humanoid `Arm` carries none of it. That is this game's answer to the
candy-wrapper collapse a 67° shoulder rotation puts into linear blend skinning, and an imported model
that lacks it collapses no matter what pose it was authored in.

Two tables come out of here, both consumed by Editor/HelperBoneRigger.cs:

  placement  each helper's origin as a fraction along its parent bone (0 = joint, 1 = child joint)
  profile    how a humanoid bone's weight splits across its own helpers, bucketed along the bone

    python tools/measure_helper_rig.py [--bodies 40]
"""
import argparse
import collections
import glob
import json
import math
import os

BASE = 'D:/GIT/gakumas-modding/mod-workspace/libraries/assetstudio-body-json'

# bone -> child that defines its axis, plus the helpers whose weight comes out of that bone's share.
FAMILIES = [
    ('{side}Arm', '{side}ForeArm', ['{side}Arm_H', '{side}Arm_Roll_H']),
    ('{side}ForeArm', '{side}Hand', ['{side}ForeArm_H', '{side}ForeArm_Roll_H', '{side}Hand_H']),
    ('{side}UpLeg', '{side}Leg', ['{side}UpLeg_H', '{side}UpLeg_Roll_H']),
    ('{side}Leg', '{side}Foot', ['{side}Leg_H']),
]
BUCKETS = 10


def quat_rotate(q, v):
    x, y, z, w = q
    t = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])]
    cross = [y * t[2] - z * t[1], z * t[0] - x * t[2], x * t[1] - y * t[0]]
    return [v[i] + w * t[i] + cross[i] for i in range(3)]


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def world_positions(nodes):
    """World position of every node, walking the parent chain (nodes are parent-before-child)."""
    position, rotation = [None] * len(nodes), [None] * len(nodes)
    for index, node in enumerate(nodes):
        parent = node['parent']
        if parent < 0:
            position[index] = list(node['localPosition'])
            rotation[index] = list(node['localRotation'])
        else:
            offset = quat_rotate(rotation[parent], node['localPosition'])
            position[index] = [a + b for a, b in zip(position[parent], offset)]
            rotation[index] = quat_mul(rotation[parent], node['localRotation'])
    return position


def along(point, origin, axis, length):
    """Where a point falls along a bone, 0 at the joint and 1 at the child joint."""
    return sum((point[i] - origin[i]) * axis[i] for i in range(3)) / length


def measure(directory, placement, profile, lengths):
    skeleton = json.load(open(f'{directory}/Geo_Body.skeleton.json', encoding='utf-8'))
    nodes = skeleton['nodes']
    at = {node['name']: i for i, node in enumerate(nodes)}
    weighted = {node['weightedIndex']: node['name'] for node in nodes
                if node.get('weightedIndex') is not None}
    world = world_positions(nodes)

    mesh = None
    for side in ('Left', 'Right'):
        for bone, child, helpers in FAMILIES:
            bone, child = bone.format(side=side), child.format(side=side)
            helpers = [h.format(side=side) for h in helpers]
            if bone not in at or child not in at:
                continue
            origin, tip = world[at[bone]], world[at[child]]
            axis = [tip[i] - origin[i] for i in range(3)]
            length = math.sqrt(sum(c * c for c in axis))
            if length < 1e-4:
                continue
            axis = [c / length for c in axis]
            lengths[bone].append(length)

            for helper in helpers:
                if helper in at:
                    placement[helper].append(along(world[at[helper]], origin, axis, length))

            family = [bone] + [h for h in helpers if h in at]
            if len(family) < 2:
                continue
            if mesh is None:
                mesh = json.load(open(f'{directory}/Geo_Body.json', encoding='utf-8'))
                flat = mesh['m_Vertices']
                mesh['points'] = [flat[i:i + 3] for i in range(0, len(flat), 3)]
            buckets = collections.defaultdict(collections.Counter)
            for point, skin in zip(mesh['points'], mesh['m_Skin']):
                share = {weighted.get(index): weight
                         for weight, index in zip(skin['weight'], skin['boneIndex']) if weight > 0}
                owned = sum(share.get(name, 0.0) for name in family)
                # Vertices this limb does not really own would drag the split towards its neighbours.
                if owned < 0.5:
                    continue
                t = along(point, origin, axis, length)
                if not -0.05 <= t <= 1.05:
                    continue
                bucket = min(int(min(max(t, 0.0), 1.0) * BUCKETS), BUCKETS - 1)
                for name in family:
                    buckets[bucket][name] += share.get(name, 0.0)
            key = FAMILIES[[f[0].format(side=side) for f in FAMILIES].index(bone)][0]
            for bucket, counter in buckets.items():
                total = sum(counter.values())
                if total <= 0:
                    continue
                for name in family:
                    generic = name.replace(side, '{side}')
                    profile[(key, bucket, generic)].append(counter[name] / total)


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bodies', type=int, default=40)
    options = parser.parse_args()

    directories = sorted(d for d in glob.glob(f'{BASE}/*_body')
                         if os.path.exists(f'{d}/Geo_Body.skeleton.json'))[:options.bodies]
    placement = collections.defaultdict(list)
    profile = collections.defaultdict(list)
    lengths = collections.defaultdict(list)
    for directory in directories:
        try:
            measure(directory, placement, profile, lengths)
        except Exception as error:  # a costume with a trimmed dump is not worth aborting over
            print(f'  跳过 {os.path.basename(directory)}: {error}')
    print(f'样本 {len(directories)} 套服装\n')

    print('== 辅助骨位置（占父骨长的比例，0 = 关节，1 = 子关节）==')
    for helper in sorted(placement):
        if not helper.startswith('Left'):
            continue
        values = placement[helper] + placement.get(helper.replace('Left', 'Right'), [])
        print(f'  {helper.replace("Left", ""):18} {median(values):6.3f}   '
              f'（{min(values):.3f}–{max(values):.3f}，n={len(values)}）')

    print('\n== 权重剖面（沿骨 10 桶，每桶该骨家族权重的占比中位数）==')
    for key, _, _ in FAMILIES:
        names = [key] + [h for h in dict.fromkeys(
            n for (k, _, n) in profile if k == key and n != key)]
        print(f'\n  {key.format(side="")}')
        print('    t      ' + '  '.join(f'{n.format(side=""):>12}' for n in names))
        for bucket in range(BUCKETS):
            row = [median(profile.get((key, bucket, name), [])) for name in names]
            if not any(row):
                continue
            total = sum(row) or 1.0
            cells = '  '.join(f'{value / total:11.2f}%'.replace('%', '') for value in row)
            print(f'   {(bucket + 0.5) / BUCKETS:.2f}  {cells}')

    print('\n== 骨长（cm，供闸门参考）==')
    for bone in sorted(lengths):
        if bone.startswith('Left'):
            print(f'  {bone:14} {median(lengths[bone]) * 100:5.1f}')


if __name__ == '__main__':
    main()
