"""Which chains actually moved in game, from the probe's own snapshots.

The question "is this bone being simulated" keeps coming back (wings, skirt panels, now a back
strip), and the answer is not visible in a screenshot: a bone that rides its parent rigidly and a
bone whose solver is running both change world position when the character moves.

What separates them is the **local** rotation. A bone that only follows its parent keeps its local
rotation constant frame to frame; a bone the swing solver drives does not. So this diffs each bone's
local rotation between two probe dumps and reports it per chain.

    python tools/measure_live_swing.py [older.json newer.json] [--prefix Bone_]

Defaults to the two newest dumps in the probe directory.
"""
import glob
import json
import math
import os
import sys

PROBE = "D:/Games/gakumas/BepInEx/config/gakumas-avatar-probe"


def rotations(path):
    """bone path -> local rotation quaternion, for every node in the actor's hierarchy."""
    with open(path, encoding="utf-8") as handle:
        dump = json.load(handle)
    out = {}
    for animator in dump.get("animators", []):
        for node in animator.get("hierarchy", []):
            # The probe flattens the transform: px/py/pz, rx/ry/rz/rw, sx/sy/sz.
            local = node.get("local") or {}
            if "rw" not in local:
                continue
            # Key on the path *below* the actor root: the root reads
            # `atbm | CampusActorController[0]`, and that index is reused across respawns, so two
            # dumps of the same character can disagree on the prefix and share nothing.
            path = node.get("path") or ""
            key = path.split("/", 1)[1] if "/" in path else path
            out.setdefault(key, [local["rx"], local["ry"], local["rz"], local["rw"]])
    return out


def angle_between(a, b):
    dot = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2 * math.acos(max(-1.0, min(1.0, dot))))


def chain_of(path):
    """Group `Bone_SkirtA01_L` and `Bone_SkirtA02_L` under one name."""
    leaf = path.split("/")[-1]
    stripped = leaf.rstrip("_LRM").rstrip("0123456789")
    return stripped or leaf


def main():
    prefix = next((a.split("=")[1] for a in sys.argv if a.startswith("--prefix=")), "")
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(files) < 2:
        # The probe snapshots on a timer, so most dumps catch a menu or a loading screen with no
        # actor in them at all. Take the two newest that actually hold this skeleton.
        candidates = []
        for dump in sorted(glob.glob(f"{PROBE}/*avatars.json"), key=os.path.getmtime):
            found = rotations(dump)
            if sum(1 for k in found if k.split("/")[-1].startswith(prefix or "Bone_")) > 20:
                candidates.append(dump)
        if len(candidates) < 2:
            raise SystemExit("探针目录里不足两份带这套骨架的 dump —— 进游戏站一会儿再看")
        files = candidates[-2:]

    older, newer = rotations(files[0]), rotations(files[1])
    shared = [k for k in newer if k in older]
    if not shared:
        raise SystemExit("两份 dump 没有共同的骨路径，可能不是同一个角色")

    chains = {}
    for path in shared:
        leaf = path.split("/")[-1]
        if prefix and not leaf.startswith(prefix):
            continue
        delta = angle_between(older[path], newer[path])
        chains.setdefault(chain_of(path), []).append((delta, leaf))

    print(f"{os.path.basename(files[0])} → {os.path.basename(files[1])}，共同骨 {len(shared)} 根")
    print("每条链的局部旋转变化（>0.5° 才算在动；跟着父骨刚性走的骨恒为 0）:\n")
    rows = sorted(chains.items(), key=lambda item: -max(d for d, _ in item[1]))
    for chain, entries in rows:
        peak, where = max(entries)
        moving = sum(1 for d, _ in entries if d > 0.5)
        flag = "  ← 不动" if peak <= 0.5 else ""
        print(f"  {chain:28} 最大 {peak:6.2f}°  在动 {moving}/{len(entries)} 根  ({where}){flag}")


if __name__ == "__main__":
    main()
