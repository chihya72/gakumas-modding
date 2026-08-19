"""Draw the body, posed the way the game had it, straight out of the bundle.

Every other check in this directory measures a number. Numbers kept coming back green while the
screenshots stayed wrong, and one of them (triangle area blow-up) turned out to be measuring a
mixture of five different actors' poses. This draws the thing instead, so a defect can be compared
against the screenshot that reported it.

    python tools/render_runtime_pose.py <built.bundle> --actor=atbm [--out shot.png] [--view=front|side]

Orthographic, z-buffered, flat-shaded per submesh. No dependencies beyond numpy.
"""
import glob
import os
import struct
import sys
import zlib

import numpy as np
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"
PROBE = "D:/Games/gakumas/BepInEx/config/gakumas-avatar-probe"
SIZE = 900
# One colour per submesh, so a piece of geometry ending up somewhere unexpected is obvious.
PALETTE = [(232, 178, 160), (70, 70, 78), (200, 200, 205), (176, 60, 60), (210, 170, 70),
           (90, 140, 190), (120, 190, 120), (190, 120, 190)]


def png(path, rgb):
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        handle.write(chunk(b"IEND", b""))


def main(bundle, *args):
    sys.argv = [sys.argv[0], bundle, ""] + [a for a in args]
    from replay_runtime_pose import load_bundle, quat_matrix, matmul, PROBE as _
    import json
    mesh, bones, parent, rest = load_bundle(bundle)
    actor = next((a.split("=", 1)[1] for a in args if a.startswith("--actor=")), None)
    view = next((a.split("=", 1)[1] for a in args if a.startswith("--view=")), "front")
    out = next((a.split("=", 1)[1] for a in args if a.startswith("--out=")), "pose.png")
    dump = sorted(glob.glob(f"{PROBE}/*avatars.json"), key=os.path.getmtime)[-1]
    data = json.load(open(dump, encoding="utf-8"))

    # Pinning a group back to its rest rotation is how a defect gets attributed: if the picture comes
    # right with the garment bones pinned, the swing solver put it there and nothing else did.
    body = {"Hips", "Pelvis", "Spine", "Spine1", "Spine2", "Neck", "Head", "Reference", "Move",
            "IKBody", "LookAt"} | {f"{s}{b}" for s in ("Left", "Right") for b in
            ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")} | {
            f"{s}Hand{f}{j}" for s in ("Left", "Right")
            for f in ("Index", "Middle", "Ring", "Pinky", "Thumb") for j in (1, 2, 3)}
    pin_swing = "--pin-swing" in args
    pose = {}
    for animator in data["animators"]:
        if actor and not animator["path"].startswith(actor):
            continue
        for node in animator.get("hierarchy", []):
            name = node["path"].rsplit("/", 1)[-1]
            if name in rest and name not in pose:
                if pin_swing and name not in body and not name.endswith("_H"):
                    continue
                pose[name] = node["local"]
    print(f"姿势 {os.path.basename(dump)} actor={actor or '(全部,危险)'} 命中 {len(pose)}/{len(rest)}")

    world = {}
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

    skin = np.zeros((len(bones), 3, 4))
    ok = np.zeros(len(bones), bool)
    for index, bone in enumerate(bones):
        matrix = resolve(bone)
        raw = mesh.m_BindPose[index]
        cell = ((lambda r, c: getattr(raw, f"M{r}{c}")) if hasattr(raw, "M00")
                else (lambda r, c: getattr(raw, f"e{r}{c}")))
        bind = [[cell(0, 0), cell(1, 0), cell(2, 0), cell(3, 0)],
                [cell(0, 1), cell(1, 1), cell(2, 1), cell(3, 1)],
                [cell(0, 2), cell(1, 2), cell(2, 2), cell(3, 2)]]
        if matrix:
            skin[index] = np.array(matmul(matrix, bind))
            ok[index] = True

    flat = np.array(mesh.m_Vertices, dtype=np.float64).reshape(-1, 3)
    weights = np.zeros((len(flat), 4))
    indices = np.zeros((len(flat), 4), dtype=np.int64)
    for i, s in enumerate(mesh.m_Skin):
        weights[i] = s.weight
        indices[i] = s.boneIndex
    weights[~ok[indices]] = 0.0
    homo = np.concatenate([flat, np.ones((len(flat), 1))], axis=1)
    posed = np.zeros((len(flat), 3))
    total = weights.sum(axis=1)
    for k in range(4):
        m = skin[indices[:, k]]
        posed += weights[:, k, None] * np.einsum("nij,nj->ni", m, homo)
    posed[total > 0] /= total[total > 0, None]
    posed[total <= 0] = flat[total <= 0]

    # Face the camera the same way every time. Without this the picture confuses "the costume is in
    # the wrong place" with "this idol happens to stand at an angle", and the two look identical.
    # The hip line is the character's own left-right axis, so rotating it onto screen-x normalises
    # facing for any actor, any pose, without needing to know where the scene camera was.
    hips = resolve("LeftUpLeg"), resolve("RightUpLeg")
    if all(hips):
        across = np.array([hips[1][r][3] - hips[0][r][3] for r in range(3)])
        across[1] = 0.0
        if np.linalg.norm(across) > 1e-6:
            across /= np.linalg.norm(across)
            yaw = np.arctan2(across[2], across[0])
            cos, sin = np.cos(-yaw), np.sin(-yaw)
            spin = np.array([[cos, 0, -sin], [0, 1, 0], [sin, 0, cos]])
            centre = np.array([(resolve("Hips") or [[0] * 4] * 3)[r][3] for r in range(3)])
            posed = (posed - centre) @ spin.T + centre
            print(f"已按胯线把朝向归一（转了 {np.degrees(yaw):.0f}°）")

    axis = (0, 1) if view == "front" else (2, 1)
    flip = -1 if view == "front" else 1
    px = posed[:, axis[0]] * flip
    py = posed[:, axis[1]]
    lo = np.array([px.min(), py.min()])
    hi = np.array([px.max(), py.max()])
    span = max(hi - lo) * 1.06 or 1.0
    sx = ((px - (lo[0] + hi[0]) / 2) / span + 0.5) * SIZE
    sy = (1 - ((py - (lo[1] + hi[1]) / 2) / span + 0.5)) * SIZE

    image = np.full((SIZE, SIZE, 3), 250, np.uint8)
    depth = np.full((SIZE, SIZE), -1e9)
    tri = np.array(mesh.m_Indices, dtype=np.int64).reshape(-1, 3)
    submesh = np.zeros(len(tri), np.int64)
    start = 0
    for slot, sm in enumerate(mesh.m_SubMeshes):
        count = sm.indexCount // 3
        submesh[start:start + count] = slot
        start += count
    depth_axis = 2 if view == "front" else 0

    for t in range(len(tri)):
        a, b, c = tri[t]
        xs = np.array([sx[a], sx[b], sx[c]])
        ys = np.array([sy[a], sy[b], sy[c]])
        x0, x1 = int(max(0, xs.min())), int(min(SIZE - 1, xs.max()))
        y0, y1 = int(max(0, ys.min())), int(min(SIZE - 1, ys.max()))
        if x1 < x0 or y1 < y0:
            continue
        area = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
        if abs(area) < 1e-9:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        w0 = ((xs[1] - xs[0]) * (yy - ys[0]) - (xx - xs[0]) * (ys[1] - ys[0])) / area
        w1 = ((xx - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (yy - ys[0])) / area
        inside = (w0 >= 0) & (w1 >= 0) & (w0 + w1 <= 1)
        if not inside.any():
            continue
        z = posed[[a, b, c], depth_axis].mean()
        hit = inside & (z > depth[y0:y1 + 1, x0:x1 + 1])
        if not hit.any():
            continue
        depth[y0:y1 + 1, x0:x1 + 1][hit] = z
        colour = PALETTE[submesh[t] % len(PALETTE)]
        image[y0:y1 + 1, x0:x1 + 1][hit] = colour
    png(out, image)
    print(f"已输出 {out}（{view} 视图，按子网格上色）")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main(sys.argv[1], *sys.argv[2:]))
