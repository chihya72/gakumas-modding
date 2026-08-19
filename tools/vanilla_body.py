# -*- coding: utf-8 -*-
"""读一套原版 body bundle：骨架拓扑、静止世界变换、每根骨上挂了什么组件。

AB 路线的 mod 只交 mesh + sidecar，**骨架拓扑不在 sidecar 里**（sidecar 的 `parentIndex`
全是 -1，它只是渲染器骨序名单）。所以任何"跨关节权重带""bindpose 是否自洽""这根骨上
已经有没有驱动器"之类的判断，都必须回到被替换的那套原版 bundle 上取真值。

原版 bundle **内嵌 typetree**，MonoBehaviour 的字段能按名字读，不用猜偏移。

三个消费者：tools/audit_ab_rig.py（闸门）、P1 的权重重分配、以后的驱动器装配。
"""
from __future__ import annotations

import glob
import os

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"

LIBRARY = "D:/GIT/gakumas-modding/mod-workspace/libraries/all_body"


def resolve(target: str) -> str:
    """`mdl_chr_atbm-cstm-0140_body` 或一个直接路径 → 库里的文件路径。"""
    if os.path.isfile(target):
        return target
    candidate = os.path.join(LIBRARY, target)
    if os.path.isfile(candidate):
        return candidate
    # 空名字曾经在这里 glob 成 `*`，静默拿库里第一套 body 当对照，报告照样打印得像模像样。
    # 判据的对照物错了比不判更坏，所以宁可硬失败。
    if not target.strip():
        raise ValueError("没有指定原版 body（mod.json 的 replacements[].source 为空？）")
    matches = glob.glob(os.path.join(LIBRARY, f"*{target}*"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"原版 body 名字 {target!r} 在库里匹配到 {len(matches)} 套，必须唯一（{LIBRARY}）")
    return matches[0]


def _quat_matrix(q, t):
    x, y, z, w = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), t[0]],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), t[1]],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), t[2]],
    ]


def _matmul(a, b):
    out = [[0.0] * 4 for _ in range(3)]
    for row in range(3):
        for col in range(4):
            out[row][col] = sum(a[row][k] * (b[k][col] if k < 3 else (0, 0, 0, 1)[col])
                                for k in range(3))
            if col == 3:
                out[row][col] += a[row][3]
    return out


class VanillaBody:
    """骨名 → 父骨 / 静止世界矩阵 / 该骨上的组件类名集合。"""

    def __init__(self, path: str):
        self.path = path
        env = UnityPy.load(path)
        go_name, transform_owner, children, local = {}, {}, {}, {}
        scripts = {}
        for obj in env.objects:
            if obj.type.name == "GameObject":
                go_name[obj.path_id] = obj.read_typetree()["m_Name"]
            elif obj.type.name == "MonoScript":
                scripts[obj.path_id] = obj.read_typetree()["m_ClassName"]
        for obj in env.objects:
            if obj.type.name != "Transform":
                continue
            tree = obj.read_typetree()
            name = go_name.get(tree["m_GameObject"]["m_PathID"])
            transform_owner[obj.path_id] = name
            children[obj.path_id] = [c["m_PathID"] for c in tree["m_Children"]]
            local[name] = tree
        self.parent = {}
        for path_id, kids in children.items():
            for kid in kids:
                self.parent[transform_owner.get(kid)] = transform_owner.get(path_id)
        self.local = local
        self.components = {}
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            tree = obj.read_typetree()
            owner = go_name.get(tree.get("m_GameObject", {}).get("m_PathID"))
            klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"))
            if owner and klass:
                self.components.setdefault(owner, []).append(klass)
        smr = next((o.read_typetree() for o in env.objects
                    if o.type.name == "SkinnedMeshRenderer"), {})
        self.renderer_bones = [transform_owner.get(b["m_PathID"])
                               for b in smr.get("m_Bones", [])]
        self.mesh = None
        for obj in env.objects:
            if obj.type.name != "Mesh":
                continue
            try:
                candidate = obj.read()
            except Exception:
                continue
            if getattr(candidate, "m_Vertices", None) and getattr(candidate, "m_Skin", None):
                if self.mesh is None or candidate.m_VertexCount > self.mesh.m_VertexCount:
                    self.mesh = candidate
        self._world_cache = {}

    # --- 拓扑 -------------------------------------------------------------

    def ancestors(self, bone: str):
        out, seen = [], set()
        node = bone
        while node and node not in seen:
            seen.add(node)
            out.append(node)
            node = self.parent.get(node)
        return out

    def is_under(self, bone: str, root: str, stop: str | None = None) -> bool:
        """`bone` 在 `root` 子树里，且（给了 stop 时）不在 `stop` 子树里。"""
        chain = self.ancestors(bone)
        return root in chain and (stop is None or stop not in chain)

    # --- 变换 -------------------------------------------------------------

    def world(self, bone: str):
        if bone in self._world_cache:
            return self._world_cache[bone]
        chain = list(reversed(self.ancestors(bone)))
        matrix = None
        for node in chain:
            tree = self.local.get(node)
            if tree is None:
                return None
            step = _quat_matrix([tree["m_LocalRotation"][k] for k in "xyzw"],
                                [tree["m_LocalPosition"][k] for k in "xyz"])
            matrix = step if matrix is None else _matmul(matrix, step)
        self._world_cache[bone] = matrix
        return matrix

    def position(self, bone: str):
        matrix = self.world(bone)
        return None if matrix is None else [matrix[r][3] for r in range(3)]
