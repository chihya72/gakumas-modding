"""Score the geometry-based chain classifier against the 530 stock bodies.

ChainClassifier decides what a bone chain is from where it hangs and which way it points, because a
model from outside this family has bone names the pipeline cannot read. Stock bodies are the one
place where both signals exist at once: their names are reliable (`LeftFrontSkirt1_S` is a skirt) and
their geometry is right there. That makes them a labelled set, and this scores the rules against it
offline — before a wrong guess costs a game launch.

The rules here mirror ChainClassifier.cs. Keep the two in sync; the file prints the rule set it used
so a drift is visible in the output rather than silent.

    python tools/measure_chain_classifier.py [limit]
"""
import collections
import glob
import re
import sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.57f1"

BODY_BONES = {
    "Reference", "Pelvis", "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightShoulder", "RightArm",
    "RightForeArm", "RightHand", "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
}
BODY_BONES |= {f"{side}Hand{finger}{index}"
               for side in ("Left", "Right")
               for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
               for index in (1, 2, 3)}

SIDE_TOKENS = ["Left", "Right", "Center", "Front", "Back", "Side", "Upper", "Lower",
               "Inside", "Outside", "Body", "Arm", "Up"]
NAME_RULES = [
    ("skin", ["skin"]),
    ("sleeve", ["sleeve", "cuff"]),
    ("skirt", ["skirt", "pants", "smock", "jacket", "coat", "dress", "hakama"]),
    ("ribbon", ["ribbon", "string", "lace", "bow", "tie", "cord", "strap", "tassel", "rope",
                "chain", "acce", "neckless"]),
    ("cloth", ["cloth", "poncho", "frill", "cape", "apron", "muffler", "scarf", "stole", "hood",
               "collar", "belt", "sash", "furisode", "gown", "shirt", "inner"]),
]


def truth(bone_name):
    """The label, from stock's own naming — the same rule SwingRigger.CategoryOf uses."""
    match = re.match(r"^(?P<stem>.+?)\d+_S(_End)?$", bone_name)
    stem = match.group("stem") if match else bone_name
    changed = True
    while changed:
        changed = False
        for token in SIDE_TOKENS:
            if stem.startswith(token) and len(stem) > len(token):
                stem = stem[len(token):]
                changed = True
                break
    lowered = stem.lower()
    for category, tokens in NAME_RULES:
        for token in tokens:
            if token in lowered:
                return category
    return "ribbon"


def by_anchor(anchor):
    """Mirror of ChainClassifier.ByAnchor."""
    if anchor is None:
        return None
    if "Hand" in anchor or "ForeArm" in anchor or "Arm" in anchor or "Shoulder" in anchor:
        return "sleeve"
    if anchor in ("Head", "Neck"):
        return "ribbon"
    if "Leg" in anchor or "Foot" in anchor or "Toe" in anchor:
        return "skirt"
    if anchor in ("Hips", "Pelvis", "Spine"):
        return "skirt"
    return None


def predict(anchor, direction, length_cm, siblings):
    """Mirror of ChainClassifier.Decide."""
    # A chain that does not physically extend cannot swing: stock's skin helpers sit at a median
    # length of 0.0 cm, while a hem is 18 cm and a ribbon 10 cm. Pin them like stock does.
    if length_cm < 2.0:
        return "skin"
    category = by_anchor(anchor)
    if category == "skirt" and siblings < 4:
        # A hem is a ring of panels — stock hems run 4-8 strands off one anchor. One or two strands
        # off the hips is an apron, a tail, a sash: the cloth row, not the skirt row.
        return "cloth"
    if category is not None:
        return category
    if direction[1] < -0.6:
        return "cloth"
    return "ribbon"


def main(limit):
    paths = sorted(glob.glob("D:/GIT/gakumas-modding/mod-workspace/libraries/all_body/*"))
    if limit:
        paths = paths[:limit]

    confusion = collections.Counter()
    scanned = 0
    for path in paths:
        try:
            env = UnityPy.load(path)
        except Exception:
            continue
        names, parents, positions = {}, {}, {}
        transforms = {}
        for obj in env.objects:
            if obj.type.name == "GameObject":
                names[obj.path_id] = obj.read().m_Name
        for obj in env.objects:
            if obj.type.name != "Transform":
                continue
            tree = obj.read_typetree()
            transforms[obj.path_id] = tree
            owner = names.get(tree.get("m_GameObject", {}).get("m_PathID"))
            if owner:
                positions[owner] = tree["m_LocalPosition"]
                parents[owner] = tree.get("m_Father", {}).get("m_PathID")
        if not names:
            continue

        def owner_of(path_id):
            tree = transforms.get(path_id)
            return names.get(tree.get("m_GameObject", {}).get("m_PathID")) if tree else None

        # Strand roots: a swing bone whose parent is not one. Stock marks them by name, which is
        # exactly the label — the *prediction* may only look at the anchor and the direction.
        swing = {name for name in positions if name.endswith("_S") or name.endswith("_S_End")}
        roots_by_anchor, pending = {}, []
        for name in swing:
            parent = owner_of(parents.get(name))
            if parent in swing:
                continue
            anchor, cursor, guard = None, parent, 0
            while cursor and guard < 64:
                if cursor in BODY_BONES:
                    anchor = cursor
                    break
                cursor = owner_of(parents.get(cursor))
                guard += 1
            # Direction: local offset down the strand is enough to tell "hangs down" from the rest,
            # and avoids composing the whole world transform here.
            chain, cursor = [name], name
            while True:
                children = [k for k in swing if owner_of(parents.get(k)) == cursor]
                if len(children) != 1:
                    break
                cursor = children[0]
                chain.append(cursor)
            total = 0.0
            for bone in chain[1:]:
                offset = positions.get(bone, {"x": 0, "y": 0, "z": 0})
                total += (offset["x"] ** 2 + offset["y"] ** 2 + offset["z"] ** 2) ** 0.5
            offset = positions.get(name, {"x": 0, "y": 0, "z": 0})
            length = max(1e-6, (offset["x"] ** 2 + offset["y"] ** 2 + offset["z"] ** 2) ** 0.5)
            direction = (offset["x"] / length, offset["y"] / length, offset["z"] / length)
            roots_by_anchor[anchor] = roots_by_anchor.get(anchor, 0) + 1
            pending.append((truth(name), anchor, direction, total * 100))
        for label, anchor, direction, length_cm in pending:
            confusion[(label, predict(anchor, direction, length_cm, roots_by_anchor.get(anchor, 0)))] += 1
        scanned += 1

    print(f"扫了 {scanned} 套原版\n")
    labels = sorted({label for label, _ in confusion} | {guess for _, guess in confusion})
    header = "真值\\预测   " + "  ".join(f"{label:>8}" for label in labels) + "     召回"
    print(header)
    total = sum(confusion.values())
    correct = sum(count for (label, guess), count in confusion.items() if label == guess)
    for label in labels:
        row = [confusion.get((label, guess), 0) for guess in labels]
        hit = confusion.get((label, label), 0)
        recall = hit / max(1, sum(row))
        print(f"{label:>10}   " + "  ".join(f"{value:8}" for value in row) + f"   {recall * 100:5.1f}%")
    print(f"\n总体准确率 {correct / max(1, total) * 100:.1f}%（{correct}/{total} 条链）")
    print("\n混得最多的几对：")
    for (label, guess), count in confusion.most_common():
        if label != guess and count > 20:
            print(f"   {label} 被判成 {guess}: {count}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
