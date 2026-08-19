"""Offline verifier for an AB bundle source directory.

Stdlib only.  It checks the export contract that can be checked without Unity:
manifest/sidecar handshake, t4 size, m_Colors shape/channel loss, weighted
critical joints, declared new-bone ownership, and optional log/artifact hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


CRITICAL_BONES = (
    "Hips", "Spine",
    "LeftArm", "LeftForeArm", "LeftHand",
    "RightArm", "RightForeArm", "RightHand",
    "LeftUpLeg", "LeftLeg", "LeftFoot",
    "RightUpLeg", "RightLeg", "RightFoot",
)


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_src(root: Path) -> Path:
    root = root.resolve()
    candidate = root / "bundle-src"
    if (candidate / "mod.json").is_file():
        return candidate
    if (root / "mod.json").is_file():
        return root
    raise FileNotFoundError(f"找不到 bundle-src/mod.json: {root}")


# 每条结论都带一句"下一步做什么"。
#
# 作者拿到 "*_H 矫正骨一份权重都没拿到" 之后仍然不知道该干嘛 —— 而每次进游戏试的成本很高
# （workspace 实测：54 个候选 blend 才收敛出 7 个成品）。所以瓶颈是**往返次数**，
# 让每条报错自带修法比再加一条闸门更省。`action` 为空表示"没有已知的通用修法"，
# 那本身也是信息，不要拿一句空话填。
def _record(report, level: str, message: str, action: str = ""):
    report[level].append(message)
    report.setdefault("findings", []).append(
        {"level": level, "message": message, "action": action})


def _asset_path(bundle_src: Path, asset: str) -> Path:
    return bundle_src / Path(str(asset)).name


def _new_bone_records(sidecar: dict):
    records = []
    for field in ("newBones", "extraSwingBones"):
        values = sidecar.get(field) or []
        if isinstance(values, list):
            records.extend(item for item in values if isinstance(item, dict))
    source_report = sidecar.get("sourceRigRemap") or {}
    nested = source_report.get("newBones") if isinstance(source_report, dict) else None
    if isinstance(nested, dict):
        for field in ("newBones", "extraSwingBones"):
            values = nested.get(field) or []
            if isinstance(values, list):
                records.extend(item for item in values if isinstance(item, dict))
    return records


def _check_colors(report, geo: dict):
    vertex_count = int(geo.get("m_VertexCount") or 0)
    colors = list(geo.get("m_Colors") or [])
    check = {
        "vertexCount": vertex_count,
        "valueCount": len(colors),
        "expectedValueCount": vertex_count * 4,
        "zeroByChannel": {name: 0 for name in "RGBA"},
        "allZeroVertices": 0,
    }
    if len(colors) != vertex_count * 4:
        _record(report, "errors", "m_Colors 数量与 m_VertexCount 不匹配")
        report["colors"] = check
        return
    for offset in range(0, len(colors), 4):
        values = colors[offset:offset + 4]
        for index, value in enumerate(values):
            if float(value) == 0.0:
                check["zeroByChannel"]["RGBA"[index]] += 1
        if not any(float(value) for value in values):
            check["allZeroVertices"] += 1
    check["zeroChannelValues"] = sum(check["zeroByChannel"].values())

    # G8：顶点 COLOR 的语义，不只是形状。
    #
    # 这游戏的描边宽度、rim、`_RampAddMap` 的行号全打包在 COLOR 的 nibble 里
    # （R=描边色 / G 低 4 位=RampAdd 行 / B 低 4 位=描边宽 / A 高 4 位=rim）。
    # 一个没有顶点色的网格导进来会拿到**纯白** (255,255,255,255)，于是描边被冲掉、
    # 行号读到 15、rim 读到 15 —— 画面上就是"换完模型没描边"。
    #
    # 判据取自 22 套原版实测：**纯白顶点 0 个**（行号用到 {0,1,2,3,6,9,12,15}，
    # rim 以 9 为主、0 也占三分之一，所以不能拿 rim 当判据；纯白才是干净的红线）。
    rows = {}
    rims = {}
    white = 0
    for offset in range(0, len(colors), 4):
        red, green, blue, alpha = (int(round(float(v) * 255)) if float(v) <= 1.0 else int(float(v))
                                   for v in colors[offset:offset + 4])
        rows[green & 15] = rows.get(green & 15, 0) + 1
        rims[alpha >> 4] = rims.get(alpha >> 4, 0) + 1
        if (red, green, blue, alpha) == (255, 255, 255, 255):
            white += 1
    check["rampAddRows"] = dict(sorted(rows.items()))
    check["rimNibbles"] = dict(sorted(rims.items()))
    check["pureWhiteVertices"] = white
    if white:
        _record(report, "errors",
                f"{white} 个顶点是纯白 COLOR（原版 22 套实测 0 个）"
                "—— 描边宽/rim/RampAdd 行都会读错，画面上表现为没有描边",
                "导出前把「描边颜色」设成「取自基础色」或「按材质预设」，"
                "并确认每个材质槽都标了「材质类型」")
    report["colors"] = check


def _check_weights(report, geo: dict, sidecar: dict, is_body: bool):
    bone_names = [item.get("name") for item in sidecar.get("bones", [])
                  if isinstance(item, dict) and item.get("name")]
    active = [0.0] * len(bone_names)
    invalid = 0
    for influence in geo.get("m_Skin", []) or []:
        indices = influence.get("boneIndex", []) if isinstance(influence, dict) else []
        weights = influence.get("weight", []) if isinstance(influence, dict) else []
        for index, weight in zip(indices, weights):
            index = int(index)
            if index < 0 or index >= len(active):
                invalid += 1
                continue
            if float(weight) > 0.0:
                active[index] += float(weight)
    missing = [name for name in CRITICAL_BONES if name in bone_names
               and active[bone_names.index(name)] <= 0.0]
    absent = [name for name in CRITICAL_BONES if name not in bone_names]
    check = {
        "boneCount": len(bone_names),
        "activeBoneCount": sum(value > 0.0 for value in active),
        "invalidInfluenceCount": invalid,
        "criticalMissingWeight": missing,
        "criticalAbsent": absent,
    }
    if invalid:
        _record(report, "errors", f"boneWeights 有 {invalid} 个越界索引")
    if is_body and (missing or absent):
        _record(report, "errors", "身体承重骨缺失或零权重: " + ", ".join(missing + absent))
    report["weights"] = check


# G1.  Stock bodies skin their joints to a corrective helper rig — 16 `*_H` bones per body,
# 530/530 costumes carry all of them, and ~17% of the whole body's weight mass sits there
# (tools/measure_helper_rig.py, 1060 limbs).  A converted mod inherits the target's skeleton, so
# those bones are *already present* in the sidecar — but the source's own weights never land on
# them, and both shipped mods measure a flat 0.00%.  What that costs is twist distribution: the
# forearm shears and the shoulder/elbow crease instead of folding, which is what the author sees.
#
# This is a share, not a count: the bones being listed proves nothing, only weight on them does.
#
# The floor is measured, not picked.  Running this same function over 49 stock bodies that load
# cleanly out of `mod-workspace/libraries/all_body`: min 6.02% (amao-cstm-0062), P5 7.43%,
# median 11.28%, max 21.00% (atbm-othr-0002), none at zero.  A first cut at 8% would have fired on
# 13 of those 49 — a quarter of the stock population — so it sits at 4%, below the observed
# minimum with margin.  The hard error stays at *exactly zero*, which no stock body is.
# (17% appears in measure_helper_rig.py over a different denominator; do not reuse it here.)
HELPER_FLOOR = 0.04
VANILLA_HELPER_SHARE = 0.1128


def helper_rig_share(bone_names, skin):
    """Fraction of total weight mass carried by `*_H` bones.  Pure function of the two inputs so
    the same judge can be run against a stock body's own data (see INV-8 in research/ab-v2-plan.md)."""
    total = 0.0
    helper = 0.0
    for influence in skin or []:
        indices = influence.get("boneIndex", []) if isinstance(influence, dict) else []
        weights = influence.get("weight", []) if isinstance(influence, dict) else []
        for index, weight in zip(indices, weights):
            index = int(index)
            weight = float(weight)
            if weight <= 0.0 or index < 0 or index >= len(bone_names):
                continue
            total += weight
            if str(bone_names[index]).endswith("_H"):
                helper += weight
    return (helper / total if total else 0.0), total


def _check_helper_rig(report, geo: dict, sidecar: dict, is_body: bool):
    bone_names = [item.get("name") for item in sidecar.get("bones", [])
                  if isinstance(item, dict) and item.get("name")]
    present = sorted(name for name in bone_names if str(name).endswith("_H"))
    share, mass = helper_rig_share(bone_names, geo.get("m_Skin"))
    report["helperRig"] = {
        "presentCount": len(present),
        "weightShare": round(share, 4),
        "vanillaShare": VANILLA_HELPER_SHARE,
        "floor": HELPER_FLOOR,
    }
    if not is_body or not mass:
        return
    if not present:
        _record(report, "warnings", "骨架里没有 *_H 矫正骨，无法判断扭转分配")
    elif share <= 0.0:
        _record(report, "errors",
                f"{len(present)} 根 *_H 矫正骨一份权重都没拿到（原版 {VANILLA_HELPER_SHARE:.0%}）"
                "；肩/肘/腕在扭转时会剪切",
                "源模型自带捩骨（MMD 腕捩/手捩、原神 UpperArmTwist）的话，"
                "确认骨名映射把它们落到 *_Roll_H 而不是折叠进 LeftArm；"
                "源模型没有捩骨就跑 tools/redistribute_helper_weights.py（破坏性，先不加 --write 试跑）")
    elif share < HELPER_FLOOR:
        _record(report, "warnings",
                f"*_H 矫正骨只承重 {share:.1%}（原版 {VANILLA_HELPER_SHARE:.0%}）")


# G5/G6.  Bones reach the game through `BoneNameToTransformDictionary`, and body/face/hair are
# linked to each other by name as well (`VLActorModelParts.InitializeBones`), so a duplicate name
# silently overwrites rather than erroring.  `TransformCapacity = 256` is the stock capacity
# constant for that same class; whether it is a hard ceiling is unread (plan §P5), so going over
# is a warning with the number rather than a refusal.
TRANSFORM_CAPACITY = 256


def _check_skeleton_budget(report, sidecar: dict):
    names = [item.get("name") for item in sidecar.get("bones", [])
             if isinstance(item, dict) and item.get("name")]
    # 运行时真正建出来的节点 = bones（模板 + 已合并的源专属骨）+ 顶层 extraSwingBones（链尾）。
    # `sourceRigRemap.newBones` 是同一批骨的**报告视图**，导出器把它们同时写在两处；
    # 走 _new_bone_records() 会把每根新骨数两遍，于是任何带新骨的包都被判"骨名重复"、
    # 节点数也虚高（已发布的 hmsz-fuyuko-icu 成品同样中招：报 292，实际 192）。
    names += [item.get("name") for item in sidecar.get("extraSwingBones") or []
              if isinstance(item, dict) and item.get("name")]
    seen = {}
    for name in names:
        seen[name] = seen.get(name, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    report["skeletonBudget"] = {"nodeCount": len(names), "capacity": TRANSFORM_CAPACITY,
                                "duplicateNames": duplicates}
    if duplicates:
        _record(report, "errors",
                "骨名重复（按名字进字典，重名会互相覆盖）: " + ", ".join(duplicates[:10]),
                "游戏的 RegisterBone 遇到重名会**整根跳过**，那根骨上的摇物/驱动器/碰撞体"
                "一个都收不到。在 Blender 里把重名骨改掉，注意 body/face/hair 三个部件是一个命名空间")
    if len(names) > TRANSFORM_CAPACITY:
        _record(report, "warnings",
                f"骨节点 {len(names)} 超过原版容量常量 {TRANSFORM_CAPACITY}")


# G11：Avatar 建不起来，动画就一帧都不播。
#
# 判据是读出来的，不是抄 Unity 的：`VLActorDefine.ClearRequiredDescriptionFlags` 分配的
# `_requiredDescriptionFlags` 长度是 **19**（`sub_A845FF4` @0x0A845FF4），
# `AddRequiredDescriptionFlag(hbb)` 直接 `arr[(int)hbb] = 1`（@0x0A846130 —— 索引就是
# `HumanBodyBones` 枚举值），`IsValidHumanDescription()` 是这 19 位的全 AND（@0x0A846228）。
#
# 所以必备集合 = `HumanBodyBones` 0–18。**Unity 自己的必备集只有 15 根，不含 Chest / Neck /
# 两个 Shoulder** —— 这四根在这个游戏里是硬要求，缺一根 Avatar 就无效。
# 这是**存在性**检查，不是承重检查：Head/Neck 在 body 网格上完全可以零权重（脸是另一个部件）。
REQUIRED_HUMANOID_BONES = (
    "Hips",
    "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot",
    "Spine", "Spine1",                    # Spine / Chest
    "Neck", "Head",
    "LeftShoulder", "RightShoulder",
    "LeftArm", "RightArm", "LeftForeArm", "RightForeArm", "LeftHand", "RightHand",
)


def _check_required_humanoid(report, sidecar: dict, is_body: bool):
    names = {item.get("name") for item in sidecar.get("bones", [])
             if isinstance(item, dict) and item.get("name")}
    names |= {item.get("name") for item in _new_bone_records(sidecar) if item.get("name")}
    missing = [bone for bone in REQUIRED_HUMANOID_BONES if bone not in names]
    report["requiredHumanoid"] = {"required": len(REQUIRED_HUMANOID_BONES), "missing": missing}
    if is_body and missing:
        _record(report, "errors",
                "缺 Avatar 必备骨（19 根里少了 " + str(len(missing)) + " 根）: "
                + ", ".join(missing) + " —— IsValidHumanDescription() 会判失败，动画一帧都不播",
                "这 19 根是 HumanBodyBones 0–18，比 Unity 自己的必备集多 Chest/Neck/两个 Shoulder。"
                "在骨名映射里把源模型对应的骨补上；目标骨架本来就有这些骨，缺的是映射")


def _check_ownership(report, sidecar: dict):
    bone_names = {item.get("name") for item in sidecar.get("bones", [])
                  if isinstance(item, dict) and item.get("name")}
    source_report = sidecar.get("sourceRigRemap") or {}
    mapped = source_report.get("bones", {}) if isinstance(source_report, dict) else {}
    mapped_targets = set(mapped.values()) if isinstance(mapped, dict) else set()
    source_names = set(mapped) | set(source_report.get("accessoryBones", []) or [])
    declared_records = _new_bone_records(sidecar)
    declared = {item.get("name") for item in declared_records if item.get("name")}
    # The sidecar contains the full target template skeleton, not only bones that
    # received source weights.  Therefore an unreferenced target helper (e.g. *_H,
    # *_S, Spine2) is legal.  Leakage means a source name survived into that array
    # without being mapped to a target or declared as a runtime-created new bone.
    source_leaks = sorted((bone_names & source_names) - mapped_targets - declared)
    bad_parents = []
    known = bone_names | declared | mapped_targets | set(CRITICAL_BONES) | {"Hips"}
    for item in declared_records:
        name = item.get("name")
        parent = item.get("parentName")
        if not name or not parent or parent not in known:
            bad_parents.append({"name": name, "parentName": parent})
        if "swing" not in item:
            _record(report, "warnings", f"新骨 {name} 未声明 swing 参数")
    # 循环父链：A.parent=B、B.parent=A。运行时 buildBone 有 states 环检测会拒绝整份
    # sidecar，导出侧也不该产出它 —— 而验证器此前只查父名存不存在，环照样放行。
    parent_of = {item.get("name"): item.get("parentName") for item in declared_records}
    cycles = []
    for start in parent_of:
        seen, current = set(), start
        while current in parent_of:
            if current in seen:
                cycles.append(start)
                break
            seen.add(current)
            current = parent_of[current]
    if cycles:
        _record(report, "errors", "新骨父链存在循环: " + ", ".join(sorted(set(cycles))))
    check = {
        "boneCycles": sorted(set(cycles)),
        "sourceBoneLeaks": source_leaks,
        "declaredNewBones": sorted(declared),
        "invalidNewBoneParents": bad_parents,
    }
    if source_leaks:
        _record(report, "errors", "sidecar 存在未归属源骨名: " + ", ".join(source_leaks))
    if bad_parents:
        _record(report, "errors", "新骨存在无效父级")
    report["boneOwnership"] = check


def _side_of(name: str):
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    if normalized.startswith("left_") or normalized.startswith("left"):
        return "left"
    if normalized.startswith("right_") or normalized.startswith("right"):
        return "right"
    tokens = normalized.split("_")
    if "l" in tokens:
        return "left"
    if "r" in tokens:
        return "right"
    return "unclassified"


def _check_swing(report, sidecar: dict):
    bones = [item for item in sidecar.get("bones", []) if isinstance(item, dict)]
    # pendulumRange / wind / rootWeight / pendulum 少写一个骨就"参数齐全但不动"：
    # pendulumRange 留 0 等于把重力项乘没了，wind 留 0 = 不受风，rootWeight 留 1.0 =
    # 完全刚性跟随根骨。530 套原版实测这四项分别是 84.6% / 84.6% / 89.5% 取上述值
    # （中位数即取这几个值，不是「一律」）。
    required = {"damping", "stiffness", "spring", "mass", "useWindGlobalForce",
                "pendulum", "pendulumRange", "wind", "rootWeight",
                # 碰撞体三项也必须显式写出：靠运行时缺省的话，sidecar 里查不出来用的是什么
                "colliderRadius", "colliderType", "collisionMask"}
    # 只查 bones[] 是不够的：链尾走顶层 `extraSwingBones`，运行时同样会把它们建成
    # ActorSwingDynamicBone，缺参数照样落进默认值。最小复现里给链尾一个空 swing，
    # 旧版验证器返回 0 错 0 警 —— 正是"日志全绿画面不动"那一类的源头。
    # 顶层与 sourceRigRemap 下的嵌套写法都收：newBones 被并进 bones[] 时顶层那份会省掉，
    # 只查顶层就会漏掉整批运行时新建的骨。
    nested = sidecar.get("sourceRigRemap")
    nested = nested.get("newBones") if isinstance(nested, dict) else None
    nested = nested if isinstance(nested, dict) else {}

    def _records(field):
        """收集某个字段下的骨记录。**容器类型要防**：`extraSwingBones: 7` 之类会让
        `for item in source` 直接抛 TypeError —— 验证工具的职责是把坏包报成错误，
        不是自己崩掉。"""
        seen, out = set(), []
        for holder, source in (("顶层", sidecar.get(field)), ("sourceRigRemap", nested.get(field))):
            if source is None:
                continue
            if not isinstance(source, list):
                _record(report, "errors",
                        f"{holder} {field} 必须是数组，实际是 {type(source).__name__}")
                continue
            for item in source:
                if isinstance(item, dict) and item.get("name") not in seen:
                    seen.add(item.get("name"))
                    out.append(item)
        return out

    extras = _records("extraSwingBones")
    news = _records("newBones")
    counts = {"left": 0, "right": 0, "unclassified": 0}
    invalid_parents = []
    missing_parameters = []
    for item in bones:
        swing = item.get("swing")
        if not isinstance(swing, dict):
            continue
        name = item.get("name") or "<unnamed>"
        counts[_side_of(name)] += 1
        parent = item.get("parentIndex")
        if not isinstance(parent, int) or parent < -1 or parent >= len(bones):
            invalid_parents.append({"name": name, "parentIndex": parent})
        missing = sorted(required - set(swing))
        if missing:
            missing_parameters.append({"name": name, "missing": missing})
    # 运行时新建的骨（链尾 / newBones）必须自带 swing，缺整块也算缺参数
    runtime_created = 0
    for item in extras + news:
        name = item.get("name") or "<unnamed>"
        runtime_created += 1
        swing = item.get("swing")
        if not isinstance(swing, dict):
            missing_parameters.append({"name": name, "missing": ["swing"]})
            continue
        missing = sorted(required - set(swing))
        if missing:
            missing_parameters.append({"name": name, "missing": missing})
    check = {
        "total": sum(counts.values()),
        **counts,
        "runtimeCreated": runtime_created,
        "invalidParentCount": len(invalid_parents),
        "missingParameterCount": len(missing_parameters),
    }
    if invalid_parents:
        _record(report, "errors", "摇物骨存在无效 parentIndex")
    if missing_parameters:
        _record(report, "errors", "摇物骨缺少物理参数: " + ", ".join(item["name"] for item in missing_parameters))
    if counts["left"] and counts["left"] != counts["right"]:
        _record(report, "warnings", f"摇物骨左右数量不对称: Left={counts['left']} Right={counts['right']}")
    report["swing"] = check
    _check_swing_chains(report, sidecar, bones, extras + news)


def _check_swing_chains(report, sidecar: dict, bones, created):
    """`swingChains` 是运行时照单执行的建链规格，错了它不会自己纠正。

    运行时只按名字找宿主骨和链根、把链根塞进 rootBones —— 名字不存在就整条链落空（只留
    一行 warn），同一根骨被两条链认领则会被同时模拟。这些都得在导出期挡住。
    """
    raw = sidecar.get("swingChains")
    if raw is None:
        return
    problems = []
    if not isinstance(raw, list):
        # dict 之类会被 `for item in raw` 静默迭代成键，整段校验空转
        _record(report, "errors", f"swingChains 必须是数组，实际是 {type(raw).__name__}")
        report["swingChains"] = {"total": 0, "problems": ["容器类型错误"]}
        return
    for index, chain in enumerate(raw):
        if not isinstance(chain, dict):
            problems.append(f"chain[{index}] 不是对象（{type(chain).__name__}）")

    chains = [item for item in raw if isinstance(item, dict)]
    bone_names = {item.get("name") for item in bones}
    created_names = {item.get("name") for item in created}
    parent_of = {item.get("name"): item.get("parentName") for item in created}
    known = bone_names | created_names
    children = {}
    for name, parent in parent_of.items():
        children.setdefault(parent, []).append(name)

    def depth_of(root):
        """按真实父子拓扑算链深（含链尾），沿最深那支。

        **必须防环**：`A.parentName=B、B.parentName=A` 这种循环父链会让遍历永不终止
        （实测跑 3 秒不返回）。环本身是坏数据，由 _check_bone_cycles 报错，这里只保证
        不挂死。"""
        best, stack, seen = 0, [(root, 1)], set()
        while stack:
            current, length = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            best = max(best, length)
            for child in children.get(current, ()):
                stack.append((child, length + 1))
        return best

    seen_roots = {}
    for index, chain in enumerate(chains):
        host = chain.get("host")
        if not isinstance(host, str) or host not in known:
            problems.append(f"chain[{index}] 宿主骨 {host!r} 不在骨架里")
        roots = chain.get("rootBones")
        if not isinstance(roots, list):
            problems.append(f"chain[{index}] rootBones 必须是数组，实际是 {type(roots).__name__}")
            continue
        if not roots:
            problems.append(f"chain[{index}] 没有链根")
        depths = {}
        for root in roots:
            if not isinstance(root, str) or root not in known:
                problems.append(f"chain[{index}] 链根 {root!r} 不在骨架里")
                continue
            if root in seen_roots:
                problems.append(f"链根 {root!r} 同时被 chain[{seen_roots[root]}] 和 chain[{index}] 认领")
            seen_roots[root] = index
            # 链根的父必须是宿主骨，否则运行时挂上去的层级和导出器算的链长对不上
            if parent_of.get(root, host) != host:
                problems.append(
                    f"chain[{index}] 链根 {root!r} 的父是 {parent_of.get(root)!r}，不是宿主 {host!r}")
            depths[root] = depth_of(root)
            # 分叉：一根骨带两个子分支时 UpdateChainInfo 只走第一支，另一支不会进层。
            # visited 是防环用的 —— 循环父链会让这个遍历永远 ping-pong（环本身由
            # _check_ownership 报错，这里只保证不挂死）。
            stack, visited = [root], set()
            while stack:
                current = stack.pop()
                if current in visited:
                    break
                visited.add(current)
                branches = children.get(current, [])
                if len(branches) > 1:
                    problems.append(
                        f"chain[{index}] 从 {root!r} 起在 {current!r} 处分叉，只有一支会进链层")
                    break
                stack.extend(branches)
        # 混长：UpdateChainInfo 把整条链截到**最短成员**的长度，长链会被削掉尾部若干层
        if len(set(depths.values())) > 1:
            problems.append(
                f"chain[{index}] 链根深度不一致 {depths}，长链会被截到最短成员的长度")
        declared = chain.get("chainLength")
        # 类型先判：`"2"` 这种字符串以前直接跳过整段比对，验证器全绿而运行时按整数读
        # （bool 同理——nlohmann 的 get<int> 不收布尔）。
        if declared is not None and (isinstance(declared, bool) or not isinstance(declared, int)):
            problems.append(
                f"chain[{index}] chainLength 必须是整数，实际是 {type(declared).__name__}")
        elif depths and isinstance(declared, int) and declared != max(depths.values()):
            problems.append(
                f"chain[{index}] chainLength={declared} 与实际拓扑深度 {max(depths.values())} 不符")
    report["swingChains"] = {"total": len(chains), "problems": problems}
    if problems:
        _record(report, "errors", "swingChains 契约不符: " + "; ".join(problems))


def verify_package(root, log_paths=(), hash_paths=()):
    bundle_src = _bundle_src(Path(root))
    manifest_path = bundle_src / "mod.json"
    manifest = _read_json(manifest_path)
    report = {
        "ok": False,
        "bundleSource": str(bundle_src),
        "errors": [],
        "warnings": [],
        "findings": [],
        "files": {},
    }
    for path in sorted(bundle_src.iterdir()):
        if path.is_file():
            report["files"][path.name] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}

    replacements = manifest.get("replacements") or []
    replacement = replacements[0] if replacements else {}
    sidecar_path = _asset_path(bundle_src, replacement.get("skeleton", ""))
    geo_paths = sorted(bundle_src.glob("*.geojson.txt"))
    if not sidecar_path.is_file():
        _record(report, "errors", f"找不到骨骼 sidecar: {sidecar_path.name}")
        sidecar = {}
    else:
        sidecar = _read_json(sidecar_path)
    # 坏包要报成错误，不是让核包工具自己崩。`bones: 7` 会让下面三处
    # （_check_ownership/_check_swing/_check_weights）各自 `for item in 7` 抛 TypeError，
    # 所以在唯一的入口处归一化一次，别在每个检查里各防一遍。
    if not isinstance(sidecar, dict):
        _record(report, "errors", f"sidecar 顶层必须是对象，实际是 {type(sidecar).__name__}")
        sidecar = {}
    elif "bones" in sidecar and not isinstance(sidecar["bones"], list):
        _record(report, "errors", f"sidecar bones 必须是数组，实际是 {type(sidecar['bones']).__name__}")
        sidecar = {**sidecar, "bones": []}
    if not geo_paths:
        _record(report, "errors", "找不到 *.geojson.txt")

    manifest_protocol = manifest.get("runtimeProtocol")
    sidecar_protocol = sidecar.get("runtimeProtocol")
    manifest_build = manifest.get("buildId")
    sidecar_build = sidecar.get("buildId")
    report["handshake"] = {
        "manifestRuntimeProtocol": manifest_protocol,
        "sidecarRuntimeProtocol": sidecar_protocol,
        "manifestBuildId": manifest_build,
        "sidecarBuildId": sidecar_build,
    }
    if manifest_protocol != 1 or sidecar_protocol != 1:
        _record(report, "errors", "runtimeProtocol 缺失或不是 1")
    if not manifest_build or manifest_build != sidecar_build:
        _record(report, "errors", "manifest 与 sidecar 的 buildId 缺失或不一致")

    renderer_ids = {
        str(item.get("rendererId", "")).lower()
        for item in replacement.get("renderers", []) or []
    }
    is_body = (
        str(replacement.get("part", "body")).lower() == "body"
        and not renderer_ids.difference({"", "body"})
    )
    t4_files = []
    for item in replacement.get("textures", []) or []:
        prop = str(item.get("property", "")).lower()
        if "t4" in prop or "shade" in prop or "sdw" in prop:
            path = _asset_path(bundle_src, item.get("asset", ""))
            if path.is_file():
                t4_files.append({"name": path.name, "bytes": path.stat().st_size})
            else:
                _record(report, "errors", f"t4 贴图不存在: {path.name}")
    report["t4"] = {"files": t4_files, "mbLevel": any(item["bytes"] >= 1_000_000 for item in t4_files)}
    if is_body and not t4_files:
        _record(report, "errors", "身体替换没有 t4/ShadeMap 贴图")
    elif t4_files and not report["t4"]["mbLevel"]:
        _record(report, "warnings", "t4/ShadeMap 小于 1 MB，需确认不是纯黑/空图")

    if sidecar:
        _check_ownership(report, sidecar)
        _check_swing(report, sidecar)
        _check_skeleton_budget(report, sidecar)
        _check_required_humanoid(report, sidecar, is_body)
    geometry_reports = []
    for geo_path in geo_paths:
        geo = _read_json(geo_path)
        geometry_report = {"path": str(geo_path), "errors": [], "warnings": [], "findings": []}
        _check_colors(geometry_report, geo)
        if sidecar:
            _check_weights(geometry_report, geo, sidecar, is_body)
            _check_helper_rig(geometry_report, geo, sidecar, is_body)
        # 逐 geometry 的结论要连 action 一起搬上来 —— 只搬 message 的话，
        # 「下一步做什么」在这里被静默丢掉，而 G1/G8 这两条高频错误恰好都在这条路径上。
        for finding in geometry_report.get("findings", []):
            _record(report, finding["level"], f"{geo_path.name}: {finding['message']}",
                    finding.get("action", ""))
        geometry_reports.append({
            "path": geometry_report["path"],
            "colors": geometry_report.get("colors"),
            "weights": geometry_report.get("weights"),
            "helperRig": geometry_report.get("helperRig"),
        })
    report["geometries"] = geometry_reports
    # 保留单 Renderer 时代的顶层摘要，避免现有报告消费者失效；完整结果以上面的数组为准。
    if geometry_reports:
        report["colors"] = geometry_reports[0]["colors"]
        if geometry_reports[0]["weights"] is not None:
            report["weights"] = geometry_reports[0]["weights"]

    for path in log_paths:
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        found = bool(sidecar_build and sidecar_build in text)
        report.setdefault("logs", []).append({"path": str(path), "exists": path.is_file(), "buildIdFound": found})
        if not found:
            _record(report, "errors", f"日志未找到 buildId={sidecar_build}: {path}")
    report["artifacts"] = [{"path": str(path), "exists": Path(path).is_file(),
                            "sha256": _sha256(Path(path)) if Path(path).is_file() else None}
                           for path in hash_paths]
    report["ok"] = not report["errors"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="核对 AB bundle 源/发布包的离线契约")
    parser.add_argument("root", type=Path, help="包目录或 bundle-src 目录")
    parser.add_argument("--log", action="append", default=[], type=Path, help="可重复；检查日志是否含 buildId")
    parser.add_argument("--hash", action="append", default=[], type=Path, dest="hash_paths", help="可重复；输出 ZIP/DLL/bundle SHA-256")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)
    try:
        report = verify_package(args.root, args.log, args.hash_paths)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"核包失败: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"AB package: {'PASS' if report['ok'] else 'FAIL'}")
        for message in report["errors"]:
            print(f"ERROR: {message}")
        for message in report["warnings"]:
            print(f"WARN: {message}")
        if report.get("handshake"):
            print("buildId:", report["handshake"].get("sidecarBuildId"))
        if report.get("swing"):
            swing = report["swing"]
            print("swing:", "total={total} left={left} right={right} unclassified={unclassified}".format(**swing))
        print("files:", len(report["files"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
