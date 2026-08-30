"""不看名字，从骨架结构认出人形骨。

八张预设表覆盖 MMD / mixamo / rigify / vrm / biped / auto-rig-pro / scsp / unity —— 名字落在
这八家之外就全落空。而「骨名混乱、骨架也混乱」恰恰是最需要自动化的那类模型。

结构比名字稳定，但 Unity/Cygames 骨架常在躯干根部分叉：Hip 挂两条腿，Waist 与 Hip 是
Root 下的兄弟，而不一定是 Hip 的子骨。先用腿反算真正的上轴，再从 Hip 的祖先附近寻找
向上的中央链；手臂取中央链同一节上成对的横向长链，左右沿稳定的局部横轴判断。

只认 15 根必需骨（Unity 建 Humanoid 的下限）+ 肩和脚趾。手指不认：它们对姿势和体检都没有
影响，而且认错的代价比不认高。
"""
REQUIRED = ["Hips", "Spine", "Head",
            "LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm", "RightHand",
            "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]


def _chain_from(bone, depth=0):
    """这根骨往下最长的一条链（遇到分叉走子树最深的那支）。"""
    chain = [bone]
    cursor = bone
    while cursor.children and depth < 64:
        cursor = max(cursor.children, key=_subtree_size)
        chain.append(cursor)
        depth += 1
    return chain


def _subtree_size(bone):
    return 1 + sum(_subtree_size(child) for child in bone.children)


def _direction(bone):
    """这根骨自己的朝向（骨架物体空间）。"""
    return (bone.tail_local - bone.head_local)


def build(armature):
    """返回 {人形骨名: 源骨名}；认不出来就返回空表。"""
    bones = list(armature.data.bones)
    if len(bones) < 15:
        return {}
    roots = [b for b in bones if b.parent is None]
    if not roots:
        return {}
    root = max(roots, key=_subtree_size)

    # 先拿最长链估一个“上”。它只负责找到胯和腿，腿找到以后会用两条腿反算真正的上轴。
    # 不能一直信最长链：衣物链可能比腿长，手指子树也可能把它拐进胳膊。
    spine_guess = _chain_from(root)
    if len(spine_guess) < 4:
        return {}
    up = (spine_guess[-1].head_local - root.head_local)
    if up.length < 1e-6:
        return {}
    up = up.normalized()

    # 胯：从根往下走，第一根「有两个子树都朝 up 的反方向长」的骨。
    def downward_children(bone):
        out = []
        for child in bone.children:
            tip = _chain_from(child)[-1]
            span = tip.head_local - child.head_local
            if span.length > 1e-6 and span.normalized().dot(up) < -0.5 and len(_chain_from(child)) >= 3:
                out.append(child)
        return out

    hips = None
    queue = [root]
    while queue and hips is None:
        bone = queue.pop(0)
        if len(downward_children(bone)) >= 2:
            hips = bone
        else:
            queue += list(bone.children)
    if hips is None:
        return {}

    legs = sorted(downward_children(hips), key=_subtree_size, reverse=True)[:2]
    if len(legs) < 2:
        return {}
    # 两条腿的前三节比“根到全树最深叶子”可靠：最深叶子可能是膝盖挂件。大腿到脚的
    # 平均方向就是下，用它把前面可能斜进手臂的粗略 up 拉正。
    down = None
    for leg in legs:
        chain = _chain_from(leg)
        probe = chain[min(2, len(chain) - 1)]
        span = probe.head_local - leg.head_local
        if span.length > 1e-6:
            value = span.normalized()
            down = value if down is None else down + value
    if down is None or down.length < 1e-6:
        return {}
    up = (-down).normalized()

    # 左右：沿「两条腿之间」的方向定左轴，再用它给所有部位分边。
    left = (legs[0].head_local - legs[1].head_local)
    if left.length < 1e-6:
        return {}
    left = (left - up * left.dot(up)).normalized()
    # 仅靠一对镜像点只能得到“左右轴”，得不到正负语义。Blender/FBX 人形约定角色左侧为
    # 骨架局部横轴的正方向；把 left 的主分量定为正，避免某侧挂件让 subtree 排序把左右翻掉。
    components = (left.x, left.y, left.z)
    if components[max(range(3), key=lambda index: abs(components[index]))] < 0.0:
        left = -left
    legs = sorted(legs, key=lambda bone: bone.head_local.dot(left), reverse=True)
    # legs[0] 在 +left 一侧 —— 那是角色自己的左。

    mapping = {"Hips": hips.name}
    for side, leg in (("Left", legs[0]), ("Right", legs[1])):
        chain = _chain_from(leg)
        if len(chain) < 3:
            return {}
        mapping[f"{side}UpLeg"] = chain[0].name
        mapping[f"{side}Leg"] = chain[1].name
        mapping[f"{side}Foot"] = chain[2].name
        if len(chain) > 3:
            mapping[f"{side}ToeBase"] = chain[3].name

    def upward_chain(start):
        """沿中央、向上的子骨走；不用子树大小，避免 Chest 拐进手臂/手指。"""
        chain = [start]
        cursor = start
        for _ in range(16):
            choices = []
            for child in cursor.children:
                delta = child.head_local - cursor.head_local
                if delta.length < 1e-6:
                    continue
                vertical = delta.dot(up)
                alignment = vertical / delta.length
                if vertical <= 1e-6 or alignment < 0.25:
                    continue
                lateral = (delta - up * vertical).length
                # 先看实际向上跨度，再罚离中央轴的距离。只按“方向有多直”会把胸前短挂件
                # （方向很直但只有一小截）压过真正的 Neck。
                score = vertical - 0.5 * lateral + alignment * 1e-5
                score += min(_subtree_size(child), 8) * 1e-7
                choices.append((score, vertical, child))
            if not choices:
                break
            cursor = max(choices, key=lambda item: (item[0], item[1]))[2]
            chain.append(cursor)
        return chain

    # 正常骨架的 Spine 是 Hip 子骨；Cygames/部分 Unity 导出的骨架则是
    # Root -> {Hip(腿), Waist(躯干)}。沿胯的祖先向上两层找兄弟分支，二者都覆盖。
    trunk_roots = [child for child in hips.children if child not in legs]
    branch, ancestor = hips, hips.parent
    for _ in range(2):
        if ancestor is None:
            break
        trunk_roots.extend(child for child in ancestor.children if child != branch)
        branch, ancestor = ancestor, ancestor.parent

    spine = None
    best_score = None
    for candidate in dict.fromkeys(trunk_roots):
        chain = upward_chain(candidate)
        span = chain[-1].head_local - candidate.head_local
        vertical = span.dot(up)
        if vertical <= 1e-6:
            continue
        start = candidate.head_local - hips.head_local
        start_vertical = start.dot(up)
        lateral = (start - up * start_vertical).length
        score = vertical - lateral * 0.5 + min(len(chain), 8) * 1e-4
        if best_score is None or score > best_score:
            best_score, spine = score, chain
    if not spine:
        return {}

    # 手臂必须是一对、挂在同一节中央脊柱上并分别朝 ±left。这样不会拿单侧胸饰或
    # 一条横向飘带凑数；每支只量前四节，手指再深也不参与评分。
    arms = None
    chest = None
    arm_score = None
    for index, vertebra in enumerate(spine):
        next_central = spine[index + 1] if index + 1 < len(spine) else None
        positive, negative = [], []
        for child in vertebra.children:
            if child == next_central:
                continue
            chain = _chain_from(child)
            if len(chain) < 3:
                continue
            probe = chain[min(3, len(chain) - 1)]
            span = probe.head_local - child.head_local
            if span.length < 1e-6:
                continue
            lateral = span.dot(left)
            if abs(lateral) / span.length < 0.6:
                continue
            (positive if lateral > 0 else negative).append((abs(lateral), child))
        if not positive or not negative:
            continue
        left_arm = max(positive, key=lambda item: item[0])
        right_arm = max(negative, key=lambda item: item[0])
        score = left_arm[0] + right_arm[0] - abs(left_arm[0] - right_arm[0]) * 0.25
        if arm_score is None or score > arm_score:
            arm_score = score
            arms = [left_arm[1], right_arm[1]]
            chest = vertebra
    if arms is None or chest is None:
        return {}

    # 胸椎 = 两臂共同挂点。脊椎到此为止，再往上第一节是脖，第二节是头；后面即使继续
    # 走进头发也不再覆盖 Head。
    vertebrae = spine[:spine.index(chest) + 1] if chest in spine else spine[:3]
    mapping["Spine"] = vertebrae[0].name
    if len(vertebrae) > 1:
        mapping["Spine1"] = vertebrae[1].name
    if len(vertebrae) > 2:
        mapping["Spine2"] = vertebrae[2].name

    for side, arm in (("Left", arms[0]), ("Right", arms[1])):
        chain = _chain_from(arm)
        # 有的骨架把锁骨也算进来：锁骨很短，手臂那一段才长。
        if len(chain) >= 4 and (chain[1].head_local - chain[0].head_local).length < \
                (chain[2].head_local - chain[1].head_local).length * 0.6:
            mapping[f"{side}Shoulder"] = chain[0].name
            chain = chain[1:]
        if len(chain) < 3:
            return {}
        mapping[f"{side}Arm"] = chain[0].name
        mapping[f"{side}ForeArm"] = chain[1].name
        mapping[f"{side}Hand"] = chain[2].name

    above = spine[spine.index(chest) + 1:]
    if not above:
        return {}
    if len(above) >= 2:
        mapping["Neck"] = above[0].name
        mapping["Head"] = above[1].name
    else:
        mapping["Head"] = above[0].name

    if any(bone not in mapping for bone in REQUIRED):
        return {}
    # 反过来：源骨名 -> 人形骨名，和预设表一个方向。
    return {source: humanoid for humanoid, source in mapping.items()}
