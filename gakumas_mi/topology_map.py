"""不看名字，从骨架结构认出人形骨。

八张预设表覆盖 MMD / mixamo / rigify / vrm / biped / auto-rig-pro / scsp / unity —— 名字落在
这八家之外就全落空。而「骨名混乱、骨架也混乱」恰恰是最需要自动化的那类模型。

结构是骗不了人的：人体只有一种拓扑。从骨架自己量出上/左两个方向，然后
胯 = 同时挂着两条向下长链和一条向上链的那根骨；腿 = 两条向下的；脊椎 = 向上的；
手臂 = 从脊椎上段横着分出去的两条；左右 = 沿左轴的正负。

只认 15 根必需骨（Unity 建 Humanoid 的下限）+ 肩和脚趾。手指不认：它们对姿势和体检都没有
影响，而且认错的代价比不认高。
"""
import math

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

    # 上 = 整副骨架最长那条链的方向；左 = 待定，先找到两条腿再说。
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
    # 左右：沿「两条腿之间」的方向定左轴，再用它给所有部位分边。
    left = (legs[0].head_local - legs[1].head_local)
    if left.length < 1e-6:
        return {}
    left = (left - up * left.dot(up)).normalized()
    if legs[0].head_local.dot(left) < legs[1].head_local.dot(left):
        legs = [legs[1], legs[0]]
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

    # 脊椎：胯上面那条朝 up 的链。手臂从它中上段横着分出去。
    spine_root = None
    for child in hips.children:
        if child in legs:
            continue
        tip = _chain_from(child)[-1]
        span = tip.head_local - child.head_local
        if span.length > 1e-6 and span.normalized().dot(up) > 0.5:
            if spine_root is None or _subtree_size(child) > _subtree_size(spine_root):
                spine_root = child
    if spine_root is None:
        return {}
    # 这条链会一路走进头发和配饰（`_chain_from` 只认子树大小），所以它不是「脊椎」，
    # 而是「从脊椎起步的最深链」。真正的胸椎由手臂挂在谁身上决定，见下面。
    spine = _chain_from(spine_root)

    # 手臂：脊椎上任何一根骨的子骨里，朝向以 ±left 为主的那两条。
    arms = []
    for vertebra in spine:
        for child in vertebra.children:
            if child in spine:
                continue
            chain = _chain_from(child)
            if len(chain) < 3:
                continue
            span = chain[-1].head_local - child.head_local
            if span.length < 1e-6:
                continue
            if abs(span.normalized().dot(left)) > 0.6:
                arms.append(child)
    arms = sorted(arms, key=_subtree_size, reverse=True)[:2]
    if len(arms) < 2:
        return {}
    if arms[0].head_local.dot(left) < arms[1].head_local.dot(left):
        arms = [arms[1], arms[0]]
    # 胸椎 = 手臂挂上去的那根。脊椎到此为止，再往上是脖子和头。
    chest = arms[0].parent if arms[0].parent in spine else spine[min(2, len(spine) - 1)]
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

    # 头：脊椎顶上朝 up 的那一支。别跟着最长链走——头发和配饰挂在头下面，最深的那条会一路
    # 走进蝴蝶结里（实测就认到了 `Bone_BowknotB02_L`）。头的特征是**直接子骨最多**：
    # 头发、眼、颌、耳都挂在它下面。
    # 方向一律用「子骨的位置」量，不用 bone.tail：FBX 按原轴导入时，叶子骨的 tail 全是同一个
    # 默认长度，实测 `Bip001 Neck` 自身朝向读出来是向下的，而胸骨读出来朝上 dot=+0.98 —— 用
    # tail 判会把胸骨当成脖子。链尾也不行：头发往下垂，用链尾会把整条脖子滤掉。
    # 再加一条硬条件：脖子下面一定挂着头，所以叶子骨（胸骨、挂点、AO 代理）直接出局。
    neck_root = None
    for child in chest.children:
        if child in arms or not child.children:
            continue
        span = max(child.children, key=_subtree_size).head_local - child.head_local
        if span.length < 1e-6 or span.normalized().dot(up) < 0.3:
            continue
        if neck_root is None or _subtree_size(child) > _subtree_size(neck_root):
            neck_root = child
    if neck_root is not None:
        mapping["Neck"] = neck_root.name
        cursor, head = neck_root, neck_root
        for _ in range(6):
            children = [c for c in cursor.children]
            if not children:
                break
            if len(children) > len(head.children):
                head = cursor
            cursor = max(children, key=_subtree_size)
        if len(cursor.children) > len(head.children):
            head = cursor
        mapping["Head"] = head.name
    else:
        mapping["Head"] = chest.name

    if any(bone not in mapping for bone in REQUIRED):
        return {}
    # 反过来：源骨名 -> 人形骨名，和预设表一个方向。
    return {source: humanoid for humanoid, source in mapping.items()}
