"""Judge a built body bundle offline, against a stock body of the costume it replaces.

Going into the game to find out whether a mod is broken costs a launch, a load and a scene change per
attempt, and most breakage is visible in the file: a missing bone the actor build binds, a skeleton
at the wrong scale, vertex COLOR left at Unity's default white (which is what "no outline" looks
like), a material with no base map, a mesh whose bind poses do not match its bones.

    python tools/audit_body_bundle.py <built.bundle> [--vanilla <stock bundle>]

Exit code is non-zero if any hard check fails, so it can gate a deploy.
"""
import collections
import math
import sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"

# Bound by the actor build; a missing one is the "PropertySceneHandle is invalid" class of crash.
REQUIRED_NODES = ["Reference", "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
                  "LeftArm", "RightArm", "LeftForeArm", "RightForeArm", "LeftHand", "RightHand",
                  "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot",
                  "IKGoal_LeftFoot", "IKGoal_RightFoot", "IKGoal_LeftHand", "IKGoal_RightHand",
                  "IKHint_LeftKnee", "IKHint_RightKnee", "IKHint_LeftElbow", "IKHint_RightElbow",
                  "IKBody", "LookAt", "Move"]

# The humanoid skeleton itself: everything else a mesh is weighted to is garment or accessory.
BODY_BONES = {"Hips", "Pelvis", "Spine", "Spine1", "Spine2", "Neck", "Head", "Reference"} | {
    f"{side}{bone}" for side in ("Left", "Right") for bone in
    ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")} | {
    f"{side}Hand{finger}{joint}" for side in ("Left", "Right")
    for finger in ("Index", "Middle", "Ring", "Pinky", "Thumb") for joint in (1, 2, 3)}

# The corrective bones the QuartzDrivers drive, carried by 530/530 stock bodies.
HELPER_BONES = [f"{side}{bone}" for side in ("Left", "Right") for bone in
                ("Arm_H", "Arm_Roll_H", "ForeArm_H", "ForeArm_Roll_H", "Hand_H",
                 "UpLeg_H", "UpLeg_Roll_H", "Leg_H")]


def qmul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def transpose(matrix):
    return [[matrix[c][r] for c in range(4)] for r in range(4)]


def invert_translation(matrix):
    """inverse(bindpose) 的平移 —— 骨在绑定时的世界位置。"""
    rotation = [row[:3] for row in matrix[:3]]
    translation = [matrix[r][3] for r in range(3)]
    # 逆的平移 = -R^T · t（bindpose 只有刚体变换）
    return [-sum(rotation[k][c] * translation[k] for k in range(3)) for c in range(3)]


def world_transforms(env, names, with_rotation=False):
    """每根骨的静止世界位置（按层级累加，含旋转）；with_rotation 时返回 (位置, 四元数)。"""
    import math as _math
    entries = {}
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        tree = obj.read_typetree()
        entries[obj.path_id] = (
            tuple(tree["m_LocalRotation"][k] for k in "xyzw"),
            tuple(tree["m_LocalPosition"][k] for k in "xyz"),
            tree["m_Father"]["m_PathID"])
    cache = {}

    def rotate(q, v):
        x, y, z, w = q
        ux, uy, uz = x, y, z
        cx = uy * v[2] - uz * v[1]
        cy = uz * v[0] - ux * v[2]
        cz = ux * v[1] - uy * v[0]
        cx, cy, cz = cx + w * v[0], cy + w * v[1], cz + w * v[2]
        dx = uy * cz - uz * cy
        dy = uz * cx - ux * cz
        dz = ux * cy - uy * cx
        return (v[0] + 2 * dx, v[1] + 2 * dy, v[2] + 2 * dz)

    def world(path_id, guard=0):
        if path_id in cache:
            return cache[path_id]
        rotation, position, father = entries[path_id]
        if father in entries and guard < 64:
            parent_pos, parent_rot = world(father, guard + 1)
            spun = rotate(parent_rot, position)
            result = (tuple(p + s for p, s in zip(parent_pos, spun)), qmul(parent_rot, rotation))
        else:
            result = (position, rotation)
        cache[path_id] = result
        return result

    if with_rotation:
        return {path_id: world(path_id) for path_id in entries}
    return {path_id: world(path_id)[0] for path_id in entries}


def load(path):
    env = UnityPy.load(path)
    names, transforms, scripts = {}, {}, {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            names[obj.path_id] = obj.read().m_Name
        elif obj.type.name == "MonoScript":
            scripts[obj.path_id] = obj.read().m_ClassName
    for obj in env.objects:
        if obj.type.name == "Transform":
            transforms[obj.path_id] = obj.read_typetree().get("m_GameObject", {}).get("m_PathID")
    return env, names, transforms, scripts


def limb_under(name, parent_of, frames):
    """Which limb's frame an adopted bone should carry: the nearest named limb above it."""
    seen = 0
    node = parent_of.get(name)
    while node and seen < 16:
        if node in frames:
            return node
        node = parent_of.get(node)
        seen += 1
    return None


def main(bundle, vanilla=None):
    env, names, transforms, scripts = load(bundle)
    problems, notes = [], []

    node_names = list(names.values())
    duplicates = [name for name, count in collections.Counter(node_names).items() if count > 1]
    if duplicates:
        problems.append(f"骨名重复 {len(duplicates)} 个（跨部件骨名表会撞）：{duplicates[:6]}")
    for required in REQUIRED_NODES:
        if required not in node_names:
            problems.append(f"缺节点 {required}（actor build 会绑它）")

    # Scale on a bone is a hard floor: the game's bone maths, this file's world walk and the bind
    # poses all assume rigid transforms. A Blender FBX exported with the default unit option writes
    # the metre→centimetre conversion as ×100 node scales and everything downstream reads garbage.
    skin_renderer = next((o.read_typetree() for o in env.objects
                          if o.type.name == "SkinnedMeshRenderer"), None)
    skinned_names = set()
    if skin_renderer:
        for bone in skin_renderer["m_Bones"]:
            skinned_names.add(names.get(transforms.get(bone["m_PathID"])))
    scaled = []
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        tree = obj.read_typetree()
        scale = tree["m_LocalScale"]
        name = names.get(tree["m_GameObject"]["m_PathID"], "?")
        # Only bones the mesh is actually skinned to. A rip's AO proxies and nub bones carry scale by
        # design, deform nothing, and flagging them buries the one that matters.
        if name in skinned_names and any(abs(scale[k] - 1.0) > 0.001 for k in "xyz"):
            scaled.append(name)
    if scaled:
        problems.append(f"{len(scaled)} 个节点带非 1 缩放（骨上不能带缩放）：{scaled[:5]}"
                        " —— 导出前在 DCC 里冻结缩放，或者导出参数选按单位换算")

    mesh = next((o.read() for o in env.objects if o.type.name == "Mesh"), None)
    if mesh is None:
        problems.append("包里没有 Mesh")
        return report(problems, notes)

    colors = getattr(mesh, "m_Colors", None)
    if not colors:
        problems.append("网格没有顶点 COLOR —— 描边/ramp 全按白色走")
    else:
        stride = len(colors) // mesh.m_VertexCount
        packed = collections.Counter(
            tuple(min(255, max(0, round(colors[i * stride + c] * 255))) for c in range(4))
            for i in range(mesh.m_VertexCount))
        white = packed.get((255, 255, 255, 255), 0)
        if white > mesh.m_VertexCount * 0.5:
            problems.append(f"顶点 COLOR 有 {white * 100 // mesh.m_VertexCount}% 是纯白，等于没写")
        top = packed.most_common(3)
        notes.append("顶点 COLOR 主值 " + ", ".join(
            f"{value} {count * 100 // mesh.m_VertexCount}%" for value, count in top))

    smr = next((o.read_typetree() for o in env.objects if o.type.name == "SkinnedMeshRenderer"), None)
    if smr is None:
        problems.append("包里没有 SkinnedMeshRenderer")
    else:
        bones = len(smr["m_Bones"])
        if bones != len(mesh.m_BindPose):
            problems.append(f"蒙皮骨 {bones} 与 bindpose {len(mesh.m_BindPose)} 数量不一致")
        materials = smr["m_Materials"]
        notes.append(f"蒙皮骨 {bones}，子网格 {len(mesh.m_SubMeshes)}，材质槽 {len(materials)}")
        if len(materials) != len(mesh.m_SubMeshes):
            problems.append(f"材质槽 {len(materials)} ≠ 子网格 {len(mesh.m_SubMeshes)}")

    slots = collections.Counter()
    for obj in env.objects:
        if obj.type.name != "Material":
            continue
        material = obj.read_typetree()
        # m_TexEnvs comes back as a dict on some Unity versions and a list of (name, value) pairs on
        # others; both mean the same thing.
        envs = material["m_SavedProperties"]["m_TexEnvs"]
        pairs = envs.items() if isinstance(envs, dict) else envs
        bound = {name: entry["m_Texture"]["m_PathID"] for name, entry in pairs}
        for slot in ("_BaseMap", "_DefMap", "_ShadeMap"):
            if bound.get(slot):
                slots[slot] += 1
            else:
                problems.append(f"材质 {material['m_Name']} 的 {slot} 没绑贴图")

    components = collections.Counter()
    per_node = collections.defaultdict(collections.Counter)
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            tree = obj.read_typetree()
            klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"), "?")
            components[klass] += 1
            per_node[names.get(tree.get("m_GameObject", {}).get("m_PathID"))][klass] += 1
    notes.append("组件 " + ", ".join(f"{k} {v}" for k, v in components.most_common()))

    # One pose driver per bone. Two riggers reach the same bone by different routes — TwistAdopter
    # adopts whichever bone plays the role, QuartzDriverRigger looks the stock name up — so a
    # synthesised `LeftArm_Roll_H` gets claimed twice and ends up with two drivers writing one
    # transform. Stock has 16 drivers on 16 distinct bones and never doubles up; the build that did
    # never finished loading. Swing components legitimately repeat on a bone, drivers never do.
    doubled = sorted(f"{node}×{count} {klass}"
                     for node, klasses in per_node.items()
                     for klass, count in klasses.items()
                     if count > 1 and "QuartzDriver" in klass)
    if doubled:
        problems.append(f"同一根骨上挂了多个姿势驱动器（原版每根只有一个）: {', '.join(doubled)}")

    # No bone may host both a swing component and a pose driver. Two solvers writing one transform
    # every frame has no example in stock — 327 skirt drivers across 60 costumes, zero overlap — and
    # the build that did it hard-crashed 2.6 s after the swap, no dump, no managed stack.
    per_bone = collections.defaultdict(set)
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"))
        if klass:
            per_bone[names.get(tree.get("m_GameObject", {}).get("m_PathID"), "?")].add(klass)
    # ActorSwingChain is the ring container, not a per-bone solver, and stock does pair it with a
    # driver (UpLeg_H, Arm_H). What never happens is a driver sharing a bone with DynamicBone or
    # StaticBone — those are the ones that write the transform.
    overlap = [bone for bone, classes in per_bone.items()
               if any(k in ("ActorSwingDynamicBone", "ActorSwingStaticBone") for k in classes)
               and any("QuartzDriver" in k for k in classes)]
    if overlap:
        problems.append(f"{len(overlap)} 根骨同时挂了摇物组件和姿势驱动器（原版 327/327 从不重叠，"
                        f"两个求解器每帧写同一个 transform 会硬崩）：{overlap[:6]}")
    doubled = [bone for bone, classes in per_bone.items()
               if sum(1 for k in classes if "QuartzDriver" in k) > 1]
    if doubled:
        problems.append(f"{len(doubled)} 根骨挂了多个姿势驱动器（一条骨脉至多一个）：{doubled[:6]}")
    for required, why in (("ActorSwingDynamicBone", "一根摇物骨都没有"),
                          ("IKGoalEffector", "缺 IK goal，CreateFullBodyIK 会抛"),
                          ("ActorAnimationIKCorrectionGoal", "缺手部 IK 修正，PropertySceneHandle 会崩")):
        if components.get(required, 0) == 0:
            problems.append(f"{why}（{required} = 0）")

    # Bind poses vs the skeleton. Re-orienting a skeleton means recomputing these, and getting it
    # wrong moves or explodes the mesh — invisible in the inspector, fatal on screen.
    #
    # UnityPy's Matrix4x4 field names are transposed (the same trap AssetStudio's export has), so the
    # matrix is read as `.T`. Calibrated against a known-good build: chs-sucu-00 scores 4/90 bones off
    # by up to 28.7 mm, which is exactly what the SDK's own CheckBindPoses reports for it.
    if smr is not None:
        world_matrices = world_transforms(env, names)
        # A bind pose is `bone.worldToLocal · renderer.localToWorld`, so inverting it gives the bone's
        # rest position **in the renderer's space**, not in world space. Those are the same thing only
        # when the renderer node sits at identity — which stock does, and which the Genshin rip did by
        # accident (its two wrapper nodes cancelled the -90° X that Blender's FBX export leaves on the
        # mesh object). An MMD export has no such wrapper, so its renderer node really is turned 90°
        # and every bone read as 1-2 m out. Compare in the renderer's frame and the question is the
        # one this gate means to ask.
        renderer_rotation = None
        for obj in env.objects:
            if obj.type.name != "Transform":
                continue
            tree = obj.read_typetree()
            if tree["m_GameObject"]["m_PathID"] == smr["m_GameObject"]["m_PathID"]:
                oriented_all = world_transforms(env, names, with_rotation=True)
                renderer_rotation = oriented_all.get(obj.path_id, (None, None))[1]
                break

        def to_renderer(point):
            if renderer_rotation is None:
                return point
            x, y, z, w = renderer_rotation
            # inverse rotation = conjugate, applied to the point
            ux, uy, uz = -x, -y, -z
            cx, cy, cz = uy * point[2] - uz * point[1], uz * point[0] - ux * point[2], ux * point[1] - uy * point[0]
            cx, cy, cz = cx + w * point[0], cy + w * point[1], cz + w * point[2]
            return (point[0] + 2 * (uy * cz - uz * cy),
                    point[1] + 2 * (uz * cx - ux * cz),
                    point[2] + 2 * (ux * cy - uy * cx))

        off, worst, worst_bone, checked = 0, 0.0, "", 0
        for index, bone in enumerate(smr["m_Bones"]):
            path_id = bone["m_PathID"]
            if path_id not in world_matrices or index >= len(mesh.m_BindPose):
                continue
            raw = mesh.m_BindPose[index]
            matrix = [[raw.M00, raw.M01, raw.M02, raw.M03], [raw.M10, raw.M11, raw.M12, raw.M13],
                      [raw.M20, raw.M21, raw.M22, raw.M23], [raw.M30, raw.M31, raw.M32, raw.M33]]
            rest = invert_translation(transpose(matrix))
            position = to_renderer(world_matrices[path_id])
            distance = sum((a - b) ** 2 for a, b in zip(rest, position)) ** 0.5
            checked += 1
            if distance > 0.001:
                off += 1
            if distance > worst:
                worst, worst_bone = distance, names.get(
                    next((t for t in [path_id]), None), "?")
        notes.append(f"bindpose 与骨架：{off}/{checked} 根偏 >1mm，最大 {worst * 1000:.1f}mm")
        if worst > 0.2 or off > checked / 4:
            problems.append(f"bindpose 与骨架不符（{off}/{checked} 偏 >1mm，最大 {worst * 1000:.0f}mm）"
                            "—— 矩阵转置或骨序错位，网格会炸")

    # Rest pose. The body is driven by nothing but Humanoid muscle retargeting, and the game builds
    # the Avatar at runtime from whatever skeleton the bundle ships — so this pose *is* the reference
    # every clip plays against. Measured offline with AvatarBench: a model resting 69° off the
    # canonical T animated 69° wrong, the same number to the decimal.
    #
    # Bone *rotations* are deliberately not checked. The previous version of this compared them to a
    # stock body and it was measuring nothing: retargeting absorbs bone axes entirely, proven by
    # building the same model with and without axis alignment and getting identical bench numbers.
    # A Biped-axis model that rests in a T is correct and used to fail here.
    t_pose = [("Hips", "Head", (0, 1, 0), "躯干"),
              ("LeftArm", "LeftForeArm", (-1, 0, 0), "左大臂"),
              ("LeftForeArm", "LeftHand", (-1, 0, 0), "左小臂"),
              ("RightArm", "RightForeArm", (1, 0, 0), "右大臂"),
              ("RightForeArm", "RightHand", (1, 0, 0), "右小臂"),
              ("LeftUpLeg", "LeftLeg", (0, -1, 0), "左大腿"),
              ("LeftLeg", "LeftFoot", (0, -1, 0), "左小腿"),
              ("RightUpLeg", "RightLeg", (0, -1, 0), "右大腿"),
              ("RightLeg", "RightFoot", (0, -1, 0), "右小腿")]
    bone_positions = {}
    for path_id, position in world_transforms(env, names).items():
        name = names.get(transforms.get(path_id))
        if name and name not in bone_positions:
            bone_positions[name] = position
    offenders, worst_rest = [], 0.0
    for parent, child, expect, label in t_pose:
        if parent not in bone_positions or child not in bone_positions:
            continue
        delta = [b - a for a, b in zip(bone_positions[parent], bone_positions[child])]
        length = math.sqrt(sum(v * v for v in delta))
        if length < 1e-6:
            continue
        cosine = sum(v * e for v, e in zip(delta, expect)) / length
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        worst_rest = max(worst_rest, angle)
        # 20° is where AvatarBench calls it: a stock body rests within 4°, and past 20 the limb is
        # visibly in the wrong place in every clip.
        if angle > 20:
            offenders.append(f"{label} 偏 {angle:.0f}°")
    if offenders:
        problems.append("静止姿势不是 T-pose（Avatar 就是照它建的，动画会整体偏这么多）："
                        + ", ".join(offenders[:6]))
    elif bone_positions:
        notes.append(f"静止姿势是 T-pose（最大偏差 {worst_rest:.1f}°，原版量级 4°）")

    # Fingers, which the T-pose probes above do not cover. They are rest pose like everything else:
    # a rip modelled gripping a weapon rests in a fist, that fist becomes the zero the clip's finger
    # muscles play against, and the hands come out shredded. Stock measures 0.0° on every finger and
    # exactly 45° on the thumb — Unity's canonical humanoid hand.
    curled = []
    for side in ("Left", "Right"):
        if f"{side}Arm" not in bone_positions or f"{side}Hand" not in bone_positions:
            continue
        arm = [h - a for h, a in zip(bone_positions[f"{side}Hand"], bone_positions[f"{side}Arm"])]
        length = math.sqrt(sum(v * v for v in arm)) or 1.0
        arm = [v / length for v in arm]
        for finger in ("Index", "Middle", "Ring", "Pinky", "Thumb"):
            chain = [f"{side}Hand{finger}{k}" for k in (1, 2, 3)]
            if any(bone not in bone_positions for bone in chain):
                continue
            segments = []
            for first, second in zip(chain, chain[1:]):
                delta = [b - a for a, b in zip(bone_positions[first], bone_positions[second])]
                size = math.sqrt(sum(v * v for v in delta))
                if size < 1e-6:
                    break
                segments.append([v / size for v in delta])
            if len(segments) != 2:
                continue
            bend = math.degrees(math.acos(max(-1.0, min(1.0, sum(
                a * b for a, b in zip(segments[0], segments[1]))))))
            expect = 45.0 if finger == "Thumb" else 0.0
            off = math.degrees(math.acos(max(-1.0, min(1.0, sum(
                a * b for a, b in zip(segments[0], arm))))))
            if bend > 10 or abs(off - expect) > 10:
                curled.append(f"{side}{finger} 偏轴 {off:.0f}°(应 {expect:.0f}°) 弯 {bend:.0f}°")
    if curled:
        problems.append("手指静止姿势不是伸直的（游戏的手指肌肉是相对它播的，手会散）："
                        + ", ".join(curled[:6]))
    elif bone_positions:
        notes.append("手指静止姿势伸直（原版 0°，拇指 45°）")

    # Roll about the limb axis. The T-pose check above compares parent→child *directions*, and so does
    # AvatarBench — both are blind to rotation around the limb itself, and `FromToRotation` leaves that
    # roll wherever the source pose happened to put it, by a different amount on each side. It shipped
    # once with the arms 12–18° off and 6.4° apart while every direction probe read 0.0°. No reference
    # number is asserted here: a body is symmetric, and the stock reference measures 0.0° between its
    # sides, so the sides are compared against each other.
    rolls = {}
    for side in ("Left", "Right"):
        chain = [f"{side}Arm", f"{side}Hand", f"{side}HandThumb1", f"{side}HandPinky1"]
        if any(bone not in bone_positions for bone in chain):
            continue
        arm, hand, thumb, pinky = (bone_positions[bone] for bone in chain)
        axis = [h - a for h, a in zip(hand, arm)]
        length = math.sqrt(sum(v * v for v in axis)) or 1.0
        axis = [v / length for v in axis]
        across = [p - t for p, t in zip(pinky, thumb)]
        along = sum(a * b for a, b in zip(across, axis))
        across = [c - along * a for c, a in zip(across, axis)]
        span = math.sqrt(sum(v * v for v in across))
        if span < 1e-6:
            continue
        # No mirroring: the arm axis is ±x and has just been projected out, so what is left is the
        # world direction the palm faces — the same vector on both hands when the pose is symmetric
        # (the stock reference reads (0.00, 0.35, -0.94) on each side).
        rolls[side] = [v / span for v in across]
    if len(rolls) == 2:
        cosine = sum(a * b for a, b in zip(rolls["Left"], rolls["Right"]))
        skew = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        notes.append(f"手掌滚转左右差 {skew:.1f}°（原版参照 0.0°）")
        if skew > 5:
            problems.append(f"左右手掌滚转差 {skew:.0f}° —— 静止姿势两条胳膊拧的角度不一样，"
                            "袖子/肩甲会一边一个样（方向探针看不见这个）")

    # Head's axes, not just where it sits. Retargeting absorbs bone axes, so the body genuinely does
    # not care — but the actor build *parents* the hair and face parts under Head instead of skinning
    # them to it, and a child inherits its parent's world rotation raw, no Avatar in the path. A Biped
    # skeleton rests with Head's +Y forward and +Z left; that shipped once and the head came out
    # 121.7° round in-game while every offline check stayed green.
    head = next((path_id for path_id, transform_id in transforms.items()
                 if names.get(transform_id) == "Head"), None)
    if head is not None:
        _, rotation = world_transforms(env, names, with_rotation=True)[head]
        turn = math.degrees(2 * math.acos(max(-1.0, min(1.0, abs(rotation[3])))))
        notes.append(f"Head 静止朝向偏离本体坐标系 {turn:.1f}°")
        # Stock actors agree with each other within 3° even mid-animation.
        if turn > 15:
            problems.append(f"Head 静止朝向偏 {turn:.0f}° —— 头发/脸部件挂在它下面，会整个转这么多")

    # Does the drawn geometry actually cover the skeleton? A section filter that drops a whole
    # material can take a body part with it and nothing else here notices: the bones, bind poses and
    # T-pose all stay perfect while the legs are simply not in any submesh. Cost this one a game run
    # — the source's `..._Tex_Hair_Diffuse` atlas was hair *and* the entire lower body, so dropping
    # the section by name left a skeleton with nothing on its legs.
    #
    # Mesh bounds do not catch it: stray shards near the floor keep the AABB honest while the limb
    # itself is gone. What is missing is skin on a bone, so that is what is measured — a vertex the
    # index buffer never references is not drawn, whatever the bounds say.
    if smr is not None:
        bone_names = [names.get(transforms.get(b["m_PathID"]), "?") for b in smr["m_Bones"]]
        drawn_vertices = set(mesh.m_Indices)
        skinned = collections.Counter()
        for vertex in drawn_vertices:
            if vertex >= len(mesh.m_Skin):
                continue
            skin = mesh.m_Skin[vertex]
            heaviest = max(range(4), key=lambda i: skin.weight[i])
            if skin.weight[heaviest] > 0:
                skinned[bone_names[skin.boneIndex[heaviest]]] += 1
        # Limbs only: Head is legitimately bare (the game supplies its own face and hair parts).
        # Only a bone that *carries* weight can tell you its geometry went missing. Blender's FBX
        # export lists every deform bone whether or not anything is weighted to it, and this model
        # weights nothing to Hips (the pelvis is covered by garment bones) — which read as "the hips
        # were dropped" on a bundle that was fine.
        carried = collections.Counter()
        for skin in mesh.m_Skin:
            for weight, index in zip(skin.weight, skin.boneIndex):
                if weight > 0 and index < len(bone_names):
                    carried[bone_names[index]] += weight
        bare = [bone for bone in ("Hips", "Spine", "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg",
                                  "RightLeg", "RightFoot", "LeftArm", "LeftHand", "RightArm",
                                  "RightHand")
                if bone in bone_names and carried[bone] > 1.0 and skinned[bone] < 20]
        notes.append(f"被绘制的顶点 {len(drawn_vertices)}/{mesh.m_VertexCount}，"
                     f"腿部 {sum(skinned[b] for b in bone_names if 'Leg' in b or 'Foot' in b)} 个")
        if bare:
            problems.append(f"这些骨上没有被绘制的几何：{', '.join(bare)} —— 整段材质被丢了，这些部位不会显示")

    # Garment chains nothing drives. A weighted bone that is not part of the body, has a weighted
    # child, and neither it nor that child carries a swing component or a driver, is cloth welded to
    # the skeleton — it will pass through a leg rather than move out of its way.
    #
    # Stock reads 0.00% on this (four costumes sampled off all_body). This bundle read 19% once: the
    # chain classifier started a strand only where the parent was *not* a garment bone, so a fork
    # under a garment bone orphaned every branch below it and the entire front and back of the skirt
    # came out rigid. Anchors are deliberately not counted — a chain's layer 0 is meant to be still,
    # and it is told apart from dead cloth by whether the bones under it are driven.
    if smr is not None:
        driven = set()
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            tree = obj.read_typetree()
            klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"), "")
            if "Swing" in klass or "QuartzDriver" in klass:
                driven.add(names.get(tree.get("m_GameObject", {}).get("m_PathID")))
        bone_names = [names.get(transforms.get(b["m_PathID"]), "?") for b in smr["m_Bones"]]
        mass, carried = collections.Counter(), 0.0
        for skin in mesh.m_Skin:
            for weight, index in zip(skin.weight, skin.boneIndex):
                if weight > 0 and index < len(bone_names):
                    mass[bone_names[index]] += weight
                    carried += weight
        # `transforms` maps a Transform's path id to its GameObject's, and m_Children holds Transform
        # ids — going through the wrong one of those silently yields an empty tree, which made this
        # check pass on a bundle it was written to fail.
        children = collections.defaultdict(list)
        for obj in env.objects:
            if obj.type.name != "Transform":
                continue
            tree = obj.read_typetree()
            owner = names.get(tree["m_GameObject"]["m_PathID"])
            for child in tree["m_Children"]:
                children[owner].append(names.get(transforms.get(child["m_PathID"])))

        def garment(name):
            return (name and name in mass and name not in BODY_BONES
                    and not name.endswith("_H") and "Bust" not in name)

        # How low each bone's own geometry reaches, so "is this in the legs' way" is a measurement.
        lowest = {}
        for vertex, skin in enumerate(mesh.m_Skin):
            heaviest = max(range(4), key=lambda i: skin.weight[i])
            if skin.weight[heaviest] <= 0.5 or skin.boneIndex[heaviest] >= len(bone_names):
                continue
            name = bone_names[skin.boneIndex[heaviest]]
            y = mesh.m_Vertices[vertex * 3 + 1]
            if name not in lowest or y < lowest[name]:
                lowest[name] = y
        hip_height = bone_positions.get("Hips", (0, 0, 0))[1] if bone_positions else 0

        dead, stranded = [], []
        for bone in mass:
            if not garment(bone) or bone in driven:
                continue
            hangs = lowest.get(bone, hip_height + 1) < hip_height
            # Two consecutive undriven bones is a chain that could swing and does not — the fork bug.
            # One bone on its own is not: layer 0 of a chain is the anchored layer, so a lone bone
            # cannot move whatever it is given, and the classifier skips it deliberately.
            chained = any(garment(child) and child not in driven for child in children.get(bone, []))
            if hangs and chained:
                dead.append((mass[bone] / max(carried, 1e-6) * 100, bone))
            elif hangs:
                stranded.append((mass[bone] / max(carried, 1e-6) * 100, bone))
        dead.sort(reverse=True)
        stranded.sort(reverse=True)
        share = sum(value for value, _ in dead)
        notes.append(f"垂到胯下、没人驱动的衣物链权重 {share:.2f}%（原版 0.00%）")
        if stranded:
            # Not a failure: usually a leaf in the source rig too, so it never swung there either.
            notes.append("垂到胯下的孤立单骨（源模型里也是叶子，同样不动）："
                         + ", ".join(f"{name} {value:.1f}%" for value, name in stranded[:4]))
        if share > 1.0:
            problems.append(f"{share:.1f}% 的权重挂在没有任何摇物/驱动组件的衣物链上（原版 0.00%）："
                            + ", ".join(f"{name} {value:.1f}%" for value, name in dead[:5])
                            + " —— 这些布是焊死在骨架上的，腿会直接穿过去")

    parent_of = {}
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        tree = obj.read_typetree()
        child = names.get(tree["m_GameObject"]["m_PathID"])
        for entry in tree["m_Children"]:
            kid = names.get(transforms.get(entry["m_PathID"]))
            if kid:
                parent_of[kid] = child

    # Every weighted bone has to live under `Reference`. The actor's animation drives that subtree and
    # nothing else, so a skinned bone hanging off the source file's own leftover root is not animated
    # at all — its vertices stay pinned to the actor root object while the animated body walks away
    # from them, and the skin opens up until the character arrives. Found this way: `+PelvisTwist CF
    # A01` under `Bip001`, 0.86% of the body's weight over 392 vertices across the pelvis, lower belly
    # and thigh tops, which in game was a hole at the waist for the whole walk-in.
    if smr is not None:
        skinned = {names.get(transforms.get(b["m_PathID"])) for b in smr["m_Bones"]}
        skinned.discard(None)

        def under_reference(bone):
            for _ in range(32):
                if bone == "Reference":
                    return True
                bone = parent_of.get(bone)
                if bone is None:
                    return False
            return False

        stranded = sorted(bone for bone in skinned if not under_reference(bone))
        if stranded:
            problems.append(f"{len(stranded)} 根有权重的骨不在 Reference 子树里（游戏只驱动那棵树，"
                            "这些骨的皮会钉在角色根节点上、人一走就留在原地）："
                            f"{', '.join(stranded[:6])}{' …' if len(stranded) > 6 else ''}")
        else:
            notes.append(f"蒙皮骨全部在 Reference 子树里（{len(skinned)} 根）")

    # Driven-bone frames. Bone axes are absorbed by retargeting and do not matter anywhere else —
    # but a QuartzDriver's coefficient is a number in its host bone's own axes, and stock uses the
    # same sign on both sides (`Arm_H` −0.8 left and right) because stock's two sides are 180° apart.
    # A rip whose arms carry the same frame gets the correction inverted on one side: the shoulder
    # takes +0.8 of its own rotation instead of −0.8. That shipped once and the arm came out wrung
    # round while every other check here stayed green.
    frames = {"LeftArm": ((0, 0, 1), (0, 1, 0)), "LeftForeArm": ((0, 0, 1), (0, 1, 0)),
              "RightArm": ((0, 0, -1), (0, -1, 0)), "RightForeArm": ((0, 0, -1), (0, -1, 0)),
              "LeftUpLeg": ((1, 0, 0), (0, 0, 1)), "LeftLeg": ((1, 0, 0), (0, 0, 1)),
              "RightUpLeg": ((1, 0, 0), (0, 0, -1)), "RightLeg": ((1, 0, 0), (0, 0, -1))}
    # The hand too: nothing drives it through a QuartzDriver, but a rip that carries one frame on both
    # hands gets the muscles applied mirrored on one of them, and the fist tears itself apart.
    for side, forward, up, thumb_f, thumb_u in (
            ("Left", (0, 0, 1), (0, 1, 0), (0, -1, 0), (0.7071, 0, 0.7071)),
            ("Right", (0, 0, -1), (0, -1, 0), (0, 1, 0), (0.7071, 0, -0.7071))):
        frames[f"{side}Hand"] = (forward, up)
        for finger in ("Index", "Middle", "Ring", "Pinky", "Thumb"):
            for joint in (1, 2, 3):
                frames[f"{side}Hand{finger}{joint}"] = ((thumb_f, thumb_u) if finger == "Thumb"
                                                        else (forward, up))
    # Retargeting absorbs a bone's *direction* — that is why a baked T-pose is enough. It does not
    # absorb its *roll*: two bones pointing the same way but 180° apart about their own axis take the
    # same muscle with the sign flipped. So this is not only a driver question, and narrowing it to
    # driver hosts (which is what this gate did) is what let a bundle ship green with both hands, all
    # thirty finger joints and both legs 172-180° off. Measured on that bundle: replaying the game's
    # own recorded pose put 1061 triangles past 4× their rest area; aligning the frames took it to 339
    # and the wrung hand went away in game.
    has_drivers = any("QuartzDriver" in (scripts.get(o.read_typetree().get("m_Script", {}).get("m_PathID")) or "")
                      for o in env.objects if o.type.name == "MonoBehaviour")
    oriented = world_transforms(env, names, with_rotation=True) if has_drivers else {}
    # Every bone the muscle system or a driver reads raw: the eight limb bones, both hands, all
    # thirty finger joints, plus whatever source bone a driver was adopted onto.
    hosts = set()
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        if "QuartzDriver" in (scripts.get(tree.get("m_Script", {}).get("m_PathID")) or ""):
            hosts.add(names.get(tree.get("m_GameObject", {}).get("m_PathID")))
    limb_of = {}
    for path_id, value in oriented.items():
        name = names.get(transforms.get(path_id))
        if name:
            limb_of.setdefault(name, value[1])
    by_bone = {}
    for name in hosts | set(frames):
        # A driver on a bone we know the role of is checked against that limb's stock frame; an
        # adopted source bone inherits the frame of the limb it hangs under.
        limb = name if name in frames else limb_under(name, parent_of, frames)
        if limb and name in limb_of:
            by_bone[name] = (limb_of[name], limb)
    skewed = []
    for bone, (q, limb) in by_bone.items():
        forward, up = frames[limb]

        def turn(vector, q=q):
            x, y, z, w = q
            t = [2 * (y * vector[2] - z * vector[1]), 2 * (z * vector[0] - x * vector[2]),
                 2 * (x * vector[1] - y * vector[0])]
            cross = [y * t[2] - z * t[1], z * t[0] - x * t[2], x * t[1] - y * t[0]]
            return [vector[i] + w * t[i] + cross[i] for i in range(3)]

        for axis, expect in ((( 0, 0, 1), forward), ((0, 1, 0), up)):
            got = turn(axis)
            cosine = sum(a * b for a, b in zip(got, expect))
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
            # The stock legs carry up to 4° of splay; 20° is well clear of that and far below the
            # 180° that a non-mirrored side produces.
            if angle > 20:
                skewed.append(f"{bone} 偏 {angle:.0f}°")
                break
    if skewed:
        problems.append("肌肉/驱动器直接读坐标系的骨，静止坐标系不是原版那套（差 180° 的骨会把"
                        f"同一条肌肉反号作用，手就是这么被拧过去的），共 {len(skewed)} 根："
                        f"{', '.join(skewed[:8])}{' …' if len(skewed) > 8 else ''}")
    elif by_bone:
        notes.append(f"肌肉/驱动器读的骨坐标系与原版一致（{len(by_bone)} 根）")

    # The corrective rig. Every stock body skins its joints to `*_H` helper bones rather than to the
    # humanoid bone — 530/530 carry all fourteen, 17% of the body's weight mass sits on them, and at
    # the shoulder and hip the humanoid bone carries none of it (measured by tools/measure_helper_rig.py).
    # Without them the game's own re-pose to a standing idle rotates the joint the full 67° through
    # plain linear blend skinning and the shoulder collapses — half-width 12.6cm against 17.4cm on
    # this model. The bones alone are not enough: they have to hold the weight, so that is checked
    # too, and separately, because "created the bones, moved no weight" looks identical otherwise.
    if smr is not None:
        bone_names = [names.get(transforms.get(b["m_PathID"]), "?") for b in smr["m_Bones"]]
        absent = [bone for bone in HELPER_BONES if bone not in bone_names]
        # Not a failure. The corrective rig is opt-in: every stock body has it, and a converted model
        # without it collapses at a hard-rotated joint — but building it means rewriting the author's
        # weights, so it is a decision, not a requirement. Say which mode the bundle is in and move on.
        if len(absent) == len(HELPER_BONES):
            notes.append("没有关节矫正 rig（保留了源模型的权重；大角度关节会按线性蒙皮塌陷）")
        elif absent:
            problems.append(f"矫正骨只装了一半，缺 {len(absent)} 根：{absent[:6]}"
                            " —— 要么整套装上，要么一根都别装")
        mass = collections.Counter()
        total = 0.0
        for skin in mesh.m_Skin:
            for weight, index in zip(skin.weight, skin.boneIndex):
                if weight > 0 and index < len(bone_names):
                    mass[bone_names[index]] += weight
                    total += weight
        helper_share = sum(v for k, v in mass.items() if k.endswith("_H")) / max(total, 1e-6)
        notes.append(f"矫正骨承重 {helper_share * 100:.1f}%（原版量级 17%）")
        if not absent and helper_share < 0.05:
            problems.append(f"矫正骨只承了 {helper_share * 100:.1f}% 的权重 —— 骨建了但权重没移过去，等于没装")

        # The two joints where stock leaves the humanoid bone with nothing. The elbow and knee are
        # deliberately not checked: stock keeps 50% and 71% there, so there is no clean threshold.
        positions = {}
        for path_id, position in world_transforms(env, names).items():
            name = names.get(transforms.get(path_id))
            if name and name not in positions:
                positions[name] = position
        # Bone positions are in root space and body renderers sit unrotated at the root, so mesh
        # vertices and bone positions are directly comparable.
        for side in ("Left", "Right") if not absent else ():
            for bone, child in ((f"{side}Arm", f"{side}ForeArm"), (f"{side}UpLeg", f"{side}Leg")):
                if bone not in positions or child not in positions or bone not in bone_names:
                    continue
                origin, tip = positions[bone], positions[child]
                axis = [b - a for a, b in zip(origin, tip)]
                length = math.sqrt(sum(v * v for v in axis)) or 1.0
                axis = [v / length for v in axis]
                own = shared = 0.0
                for vertex in range(mesh.m_VertexCount):
                    skin = mesh.m_Skin[vertex]
                    point = mesh.m_Vertices[vertex * 3:vertex * 3 + 3]
                    if len(point) < 3:
                        continue
                    t = sum((p - o) * a for p, o, a in zip(point, origin, axis)) / length
                    if not 0.0 <= t < 0.15:
                        continue
                    for weight, index in zip(skin.weight, skin.boneIndex):
                        if weight <= 0 or index >= len(bone_names):
                            continue
                        name = bone_names[index]
                        if name == bone:
                            own += weight
                            shared += weight
                        elif name.startswith(bone + "_"):
                            shared += weight
                if shared < 1e-6:
                    # Reported rather than skipped in silence: no weight in the joint band means the
                    # probe found nothing, which is not the same as the joint being correct.
                    notes.append(f"{bone} 关节处没有可判定的权重（探针没测到东西，不等于合格）")
                    continue
                notes.append(f"{bone} 关节处人形骨占 {own / shared * 100:.0f}%（原版 0%）")
                if not absent and own / shared > 0.2:
                    problems.append(f"{bone} 关节处 {own / shared * 100:.0f}% 的权重还在人形骨上"
                                    f"（原版 0%）—— 那一段会跟着整根骨转，塌陷照旧")

    # Skeleton shape. Re-orienting bones can silently move them (setting a parent's world rotation
    # re-orients every child's local offset), and the bind poses recomputed afterwards make that
    # self-consistent — the mesh then looks right only in bind pose and explodes under animation.
    # Two cheap shape invariants catch it: a human is roughly mirror-symmetric, and its proportions
    # sit near the character it replaces.
    if smr is not None:
        world_matrices = world_transforms(env, names)
        by_name = {}
        for path_id, position in world_matrices.items():
            name = names.get(transforms.get(path_id))
            if name and name not in by_name:
                by_name[name] = position
        pairs = [("LeftHand", "RightHand"), ("LeftFoot", "RightFoot"), ("LeftArm", "RightArm")]
        for left, right in pairs:
            if left in by_name and right in by_name:
                lx, rx = by_name[left][0], by_name[right][0]
                if abs(lx + rx) > 0.1 or lx * rx > 0:
                    problems.append(f"{left}/{right} 不左右对称（x {lx:+.3f} / {rx:+.3f}）—— 骨架被打散了")
        if "Hips" in by_name and "Head" in by_name:
            height = by_name["Head"][1] - by_name["Hips"][1]
            notes.append(f"Hips→Head 高 {height * 100:.1f}cm")
            if not 0.25 < height < 0.75:
                problems.append(f"Hips→Head 高 {height * 100:.0f}cm，不像人体比例（原版 40cm 量级）")

    # Scale: the game animates this skeleton, so a model authored in centimetres or at a different
    # height than the character it replaces is visible immediately.
    heights = {}
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        tree = obj.read_typetree()
        name = names.get(tree.get("m_GameObject", {}).get("m_PathID"))
        if name in ("Hips", "Head"):
            heights[name] = tree["m_LocalPosition"]["y"]
    notes.append(f"Hips/Head 局部 y = {heights}")

    if vanilla:
        _, vnames, _, _ = load(vanilla)
        missing = [n for n in vnames.values() if n in REQUIRED_NODES and n not in node_names]
        if missing:
            problems.append(f"原版有而我们没有的必备节点: {missing}")
        notes.append(f"对照原版 {vanilla.split('/')[-1]}：节点 {len(vnames)} vs 我们 {len(names)}")

    return report(problems, notes)


def report(problems, notes):
    for note in notes:
        print(f"   - {note}")
    if problems:
        print(f"\n{len(problems)} 项不合格：")
        for problem in problems:
            print(f"   [X] {problem}")
        return 1
    print("\n全部检查通过")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    args = sys.argv[1:]
    vanilla_path = args[args.index("--vanilla") + 1] if "--vanilla" in args else None
    raise SystemExit(main(args[0], vanilla_path))
