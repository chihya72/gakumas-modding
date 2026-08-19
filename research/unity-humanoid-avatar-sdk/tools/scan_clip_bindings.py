"""Tell humanoid (muscle) clips from generic (transform-path) clips in any Unity file.

This is the evidence behind docs/rest-pose-dead-end.md §零: the body clips shipped in
`gakumas_Data/data.unity3d` bind nothing but Animator muscles, so the body is driven purely by
Humanoid retargeting and the rest pose we ship is what every clip plays against.

A humanoid clip binds classID 95 (Animator) at path 0 with attribute 7..136 — the muscle/goal index
space — and carries no rotation/position/euler curves. A generic clip binds a component classID at a
hashed transform path with a hashed property name. Run it on a motion bundle whenever one gets
decrypted: live/dance clips have never been checked, only the two common idles.

    python tools/scan_clip_bindings.py D:/Games/gakumas/gakumas_Data/data.unity3d
"""
import sys
from collections import Counter

import UnityPy

CURVES = ("m_RotationCurves", "m_CompressedRotationCurves", "m_PositionCurves",
          "m_ScaleCurves", "m_EulerCurves", "m_FloatCurves")


def main(path: str) -> int:
    found = 0
    for obj in UnityPy.load(path).objects:
        if obj.type.name != "AnimationClip":
            continue
        found += 1
        tree = obj.read_typetree()
        bindings = (tree.get("m_ClipBindingConstant") or {}).get("genericBindings") or []
        # UnityPy names this field `typeID` on some versions and `classID` on others.
        classes = Counter(b.get("typeID", b.get("classID")) for b in bindings)
        curves = sum(len(tree.get(k) or []) for k in CURVES)
        humanoid = bool(bindings) and curves == 0 and all(
            b.get("typeID", b.get("classID")) == 95 and b.get("path") == 0 for b in bindings)
        print(f"{tree.get('m_Name')}\n"
              f"  {'HUMANOID (muscle)' if humanoid else 'GENERIC (by path)'}"
              f"  bindings={len(bindings)} classIDs={dict(classes)} curves={curves}")
    print(f"\n{found} AnimationClip(s) in {path}")
    return 0 if found else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
