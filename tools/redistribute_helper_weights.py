# -*- coding: utf-8 -*-
"""P1b：把 humanoid 肢体骨上的权重按原版剖面分给 `*_H` 矫正骨。

**先看 P1a。** 源模型自带捩骨（MMD `腕捩/手捩`、原神 `+UpperArmTwist`、多数 rip 都有）时，
`gakumas_mi` 的骨名映射已经把权重落到 `*_Roll_H` 上了，那是纯换落点、不改数值，**不用跑这个**。
这里只给**源模型压根没有捩骨**的情况兜底。

破坏性：它改作者的权重。所以按 INV-7 —— 默认不跑，必须显式 `--write`，且把移走多少、
截断多少逐条打出来。

剖面来自 `tools/measure_helper_rig.py`（1060 条肢体的中位数，四位小数跨服装一致），
与 SDK 侧 `HelperBoneRigger.cs` 是同一张表。桶按顶点在 `骨→子骨` 轴上的投影分十档。

    python tools/redistribute_helper_weights.py <mod目录> [--write] [--vanilla <名字>]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# `vanilla_body` 要 UnityPy，而下面两个纯函数只按鸭子类型要一个 `.position(骨名)`。
# 放到 main() 里再导，单测就不用把 UnityPy 拖进来。

# (肢体骨, 子骨, [矫正骨...], [每档在 {肢体骨} ∪ {矫正骨} 上的权重份额])
FAMILIES = [
    ("{0}Arm", "{0}ForeArm", ["{0}Arm_H", "{0}Arm_Roll_H"], [
        [0.00, 0.99, 0.01], [0.00, 0.92, 0.08], [0.00, 0.81, 0.19], [0.00, 0.63, 0.37],
        [0.00, 0.48, 0.52], [0.00, 0.15, 0.85], [0.16, 0.02, 0.82], [0.54, 0.01, 0.45],
        [0.72, 0.00, 0.28], [0.77, 0.00, 0.23]]),
    ("{0}ForeArm", "{0}Hand", ["{0}ForeArm_H", "{0}ForeArm_Roll_H", "{0}Hand_H"], [
        [0.50, 0.49, 0.01, 0.00], [0.89, 0.04, 0.07, 0.00], [0.82, 0.00, 0.18, 0.00],
        [0.61, 0.00, 0.39, 0.00], [0.30, 0.00, 0.70, 0.00], [0.07, 0.00, 0.89, 0.04],
        [0.00, 0.00, 0.82, 0.18], [0.00, 0.00, 0.58, 0.42], [0.00, 0.00, 0.25, 0.75],
        [0.00, 0.00, 0.00, 1.00]]),
    ("{0}UpLeg", "{0}Leg", ["{0}UpLeg_H", "{0}UpLeg_Roll_H"], [
        [0.00, 0.93, 0.07], [0.00, 0.79, 0.21], [0.00, 0.51, 0.49], [0.01, 0.24, 0.75],
        [0.12, 0.04, 0.84], [0.37, 0.00, 0.63], [0.73, 0.00, 0.27], [0.91, 0.00, 0.09],
        [0.99, 0.00, 0.01], [1.00, 0.00, 0.00]]),
    ("{0}Leg", "{0}Foot", ["{0}Leg_H"], [
        [0.71, 0.29], [1.00, 0.00], [1.00, 0.00], [1.00, 0.00], [1.00, 0.00],
        [1.00, 0.00], [1.00, 0.00], [1.00, 0.00], [1.00, 0.00], [1.00, 0.00]]),
]

MAX_INFLUENCES = 4


def _bucket(position, origin, axis, length):
    t = sum((position[i] - origin[i]) * axis[i] for i in range(3)) / length
    return max(0, min(9, int(t * 10)))


def plan_redistribution(bone_names, vertices, skin, vanilla):
    """返回 {顶点下标: {骨名: 权重}} 的改写计划 + 统计。纯函数，便于测试和试跑。"""
    index_of = {name: i for i, name in enumerate(bone_names) if name}
    families = []
    for side in ("Left", "Right"):
        for bone_t, child_t, helpers_t, profile in FAMILIES:
            bone, child = bone_t.format(side), child_t.format(side)
            helpers = [h.format(side) for h in helpers_t]
            if bone not in index_of or not all(h in index_of for h in helpers):
                continue
            origin, tip = vanilla.position(bone), vanilla.position(child)
            if origin is None or tip is None:
                continue
            axis = [tip[i] - origin[i] for i in range(3)]
            length = sum(v * v for v in axis) ** 0.5
            if length < 1e-6:
                continue
            families.append((index_of[bone], [origin, [v / length for v in axis], length],
                             [bone] + helpers, profile))
    plan, moved, touched = {}, 0.0, 0
    total = 0.0
    for vi, influence in enumerate(skin or []):
        indices = influence.get("boneIndex") or []
        weights = influence.get("weight") or []
        acc = {}
        changed = False
        for index, weight in zip(indices, weights):
            index, weight = int(index), float(weight)
            if weight <= 0.0:
                continue
            total += weight
            family = next((f for f in families if f[0] == index), None)
            if family is None or vi * 3 + 2 >= len(vertices):
                acc[bone_names[index]] = acc.get(bone_names[index], 0.0) + weight
                continue
            _, (origin, axis, length), names, profile = family
            row = profile[_bucket(vertices[vi * 3:vi * 3 + 3], origin, axis, length)]
            for name, share in zip(names, row):
                if share > 0.0:
                    acc[name] = acc.get(name, 0.0) + weight * share
                    if name != bone_names[index]:
                        moved += weight * share
            changed = True
        if changed:
            plan[vi] = acc
            touched += 1
    return plan, {"movedMass": moved, "totalMass": total, "touchedVertices": touched}


def apply_plan(bone_names, skin, plan):
    """写回 m_Skin，超过 4 骨的按权重截断并归一。返回被截断的顶点数。"""
    index_of = {name: i for i, name in enumerate(bone_names) if name}
    truncated = 0
    for vi, acc in plan.items():
        ranked = sorted(acc.items(), key=lambda kv: -kv[1])
        if len(ranked) > MAX_INFLUENCES:
            truncated += 1
            ranked = ranked[:MAX_INFLUENCES]
        total = sum(w for _, w in ranked) or 1.0
        indices = [index_of[name] for name, _ in ranked]
        weights = [w / total for _, w in ranked]
        while len(indices) < MAX_INFLUENCES:
            indices.append(0)
            weights.append(0.0)
        skin[vi]["boneIndex"] = indices
        skin[vi]["weight"] = weights
    return truncated


def main(argv=None):
    parser = argparse.ArgumentParser(description="把肢体权重按原版剖面分给 *_H 矫正骨（破坏性）")
    parser.add_argument("root", type=Path)
    parser.add_argument("--vanilla", default=None)
    parser.add_argument("--write", action="store_true", help="不加就是试跑，只报数不落盘")
    args = parser.parse_args(argv)
    from vanilla_body import VanillaBody, resolve

    bundle_src = args.root / "bundle-src"
    if not (bundle_src / "mod.json").is_file():
        bundle_src = args.root
    manifest = json.loads((bundle_src / "mod.json").read_text(encoding="utf-8"))
    replacement = (manifest.get("replacements") or [{}])[0]
    vanilla = VanillaBody(resolve(args.vanilla or replacement.get("source") or ""))
    sidecar = json.loads(
        (bundle_src / Path(str(replacement.get("skeleton", ""))).name).read_text(encoding="utf-8"))
    bone_names = [item.get("name") for item in sidecar.get("bones", [])]

    for geo_path in sorted(bundle_src.glob("*.geojson.txt")):
        geo = json.loads(geo_path.read_text(encoding="utf-8"))
        skin = geo.get("m_Skin") or []
        plan, stats = plan_redistribution(bone_names, geo.get("m_Vertices") or [], skin, vanilla)
        share = stats["movedMass"] / stats["totalMass"] if stats["totalMass"] else 0.0
        print(f"{geo_path.name}: 触及 {stats['touchedVertices']} 个顶点，"
              f"搬走 {share:.1%} 的全身权重")
        if not args.write:
            print("  （试跑，没落盘；加 --write 才改）")
            continue
        truncated = apply_plan(bone_names, skin, plan)
        geo["m_Skin"] = skin
        geo_path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
        print(f"  已写回；{truncated} 个顶点超过 {MAX_INFLUENCES} 骨被截断")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
