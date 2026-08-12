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


def _record(report, level: str, message: str):
    report[level].append(message)


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
    geometry_reports = []
    for geo_path in geo_paths:
        geo = _read_json(geo_path)
        geometry_report = {"path": str(geo_path), "errors": [], "warnings": []}
        _check_colors(geometry_report, geo)
        if sidecar:
            _check_weights(geometry_report, geo, sidecar, is_body)
        for level in ("errors", "warnings"):
            for message in geometry_report[level]:
                _record(report, level, f"{geo_path.name}: {message}")
        geometry_reports.append({
            "path": geometry_report["path"],
            "colors": geometry_report.get("colors"),
            "weights": geometry_report.get("weights"),
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
