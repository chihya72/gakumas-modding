# -*- coding: utf-8 -*-
"""扫原版 body bundle 里的 ActorSwingDynamicBone，产出「学马原生摆动参数基准表」。

学马自己的 bundle **内嵌 typetree**，所以 MonoBehaviour 的每个字段都能按名字读，
不需要按偏移猜（早期笔记里那张「按 248 字节定长偏移统计」的分布表可以作废）。

输出两个文件：
  <out>/vanilla-swing-bones.json    每根骨一条完整记录（查证用）
  <out>/vanilla-swing-by-part.json  按原始部件名聚合（查证用）
  <out>/vanilla-swing-presets.json  按 部件类别 × 链上角色 聚合的分位数（中间产物）
  <out>/swing_presets.json          **插件直接读的生产文件**；加 --install 一并写回
                                    gakumas_mi/swing_presets.json

用法：
  python tools/scan_vanilla_swing_bones.py --bundles mod-workspace/libraries/all_body \
      --output mod-workspace/libraries/vanilla-swing
"""
from pathlib import Path
import argparse
import json
import re
import statistics

import UnityPy

UNITY_VERSION = "2022.3.57f1"

# ActorSwingDynamicBone 的 typetree 签名。m_Script 指向的 CAB 依赖不在包里 → 拿不到类名，
# 按字段签名认（与 export_ip_swing_bones.py 同一手法）。pendulumRange + dynamicCollider
# 一起出现足以和 ActorSwingBreastBone / ActorSwingStaticBone 区分开。
BONE_KEYS = ("damping", "stiffness", "spring", "pendulum", "pendulumRange",
             "mass", "rootWeight", "dynamicCollider")
SCALARS = ("damping", "stiffness", "spring", "pendulum", "pendulumRange", "mass",
           "axisAddXToY", "axisAddXToZ", "wind", "rootWeight", "seatDynamicCorrection")

# 骨名构词：<方位前缀>* <部件> <层号> _S [_End]。剥掉方位和层号剩下的就是部件类别，
# 这样分类不靠我们维护一张词表，是数据自己给的。
SIDE_TOKENS = ("Left", "Right", "Center", "Front", "Back", "Side", "Upper", "Lower",
               "Inside", "Outside", "Body", "Arm", "Up")
NAME_RE = re.compile(r"^(?P<stem>.+?)(?P<tier>\d+)_S(?P<end>_End)?$")


def part_of(name):
    """'LeftBackSideSkirt2_S' -> ('Skirt', 2, False)；认不出来返回 (None, ...)。"""
    match = NAME_RE.match(name)
    if not match:
        return None, None, name.endswith("_End")
    stem = match.group("stem")
    changed = True
    while changed:
        changed = False
        for token in SIDE_TOKENS:
            if stem.startswith(token) and len(stem) > len(token):
                stem, changed = stem[len(token):], True
                break
    return (stem or None), int(match.group("tier")), bool(match.group("end"))


def scan_bundle(path):
    """一个 bundle 的 (骨记录列表, 链记录列表)。"""
    env = UnityPy.load(str(path))
    go_name, transforms, bones, chains = {}, {}, {}, []
    for obj in env.objects:
        kind = obj.type.name
        if kind == "GameObject":
            go_name[obj.path_id] = obj.read_typetree()["m_Name"]
        elif kind == "Transform":
            tree = obj.read_typetree()
            transforms[obj.path_id] = (tree["m_GameObject"]["m_PathID"],
                                       tree["m_Father"]["m_PathID"])
        elif kind == "MonoBehaviour":
            tree = obj.read_typetree()
            if all(key in tree for key in BONE_KEYS):
                bones[obj.path_id] = tree
            elif "rootBones" in tree and "chains" in tree:
                chains.append(tree)

    # 一根骨在不在链上、链宿主是谁 —— 由 rootBones/layers 直接给，不靠名字猜。
    chain_host, chain_root = {}, set()
    for chain in chains:
        host = go_name.get(chain["m_GameObject"]["m_PathID"], "?")
        members = [ptr["m_PathID"] for ptr in chain["rootBones"]]
        chain_root.update(members)
        for layer in chain["chains"]["layers"]:
            members += [ptr["m_PathID"] for ptr in layer["bones"]]
        for path_id in members:
            chain_host[path_id] = host

    records = []
    for path_id, tree in bones.items():
        name = go_name.get(tree["m_GameObject"]["m_PathID"], "?")
        part, tier, is_end = part_of(name)
        collider = tree["dynamicCollider"]
        limit = tree["limitInfo"]
        record = {
            "bundle": path.name,
            "name": name,
            "part": part,
            "tier": tier,
            "isTip": is_end,
            "isChainRoot": path_id in chain_root,
            "chainHost": chain_host.get(path_id),
            "useWindGlobalForce": int(tree["useWindGlobalForce"]),
            "resetType": int(tree["resetType"]),
            "dynamicType": int(tree["dynamicType"]),
            "colliderType": int(collider["type"]),
            "collisionMask": int(collider["collisionMask"]),
            "colliderRadius": float(collider["float_A"]),
            "colliderRadiusSub": float(collider["float_B"]),
            "useLimit": int(limit["useLimit"]),
            "limitX": [int(limit["axisX"]["x"]), int(limit["axisX"]["y"])],
            "limitY": [int(limit["axisY"]["x"]), int(limit["axisY"]["y"])],
            "limitZ": [int(limit["axisZ"]["x"]), int(limit["axisZ"]["y"])],
        }
        record.update({key: float(tree[key]) for key in SCALARS})
        records.append(record)

    chain_records = [{
        "bundle": path.name,
        "host": go_name.get(chain["m_GameObject"]["m_PathID"], "?"),
        "roots": len(chain["rootBones"]),
        "layers": [{
            "active": int(layer["active"]), "around": int(layer["around"]),
            "radius": float(layer["radius"]), "smoothing": float(layer["smoothing"]),
            "bones": len(layer["bones"]),
        } for layer in chain["chains"]["layers"]],
    } for chain in chains]
    return records, chain_records


def role_of(record):
    """链上角色：root(锚) / tip(链尾) / mid(真正在摆的)。"""
    if record["isTip"]:
        return "tip"
    if record["tier"] == 1:
        return "root"
    return "mid"


# 319 个原始部件名归成作者能选的几档。命中顺序有意义：skin 先判（LegSkin 不是袖子），
# sleeve 先于 skirt（LegSleeve 不是裙）。覆盖率实测 96%，剩下的落 ribbon（最保守的一档：
# 不建链、自由悬垂）。
CATEGORY_RULES = (
    ("skin", ("skin",)),
    ("sleeve", ("sleeve", "cuff")),
    ("skirt", ("skirt", "pants", "smock", "jacket", "coat", "dress", "hakama")),
    ("ribbon", ("ribbon", "string", "lace", "bow", "tie", "cord", "strap", "tassel",
                "rope", "chain", "acce", "neckless")),
    ("cloth", ("cloth", "poncho", "frill", "cape", "apron", "muffler", "scarf",
               "stole", "hood", "collar", "belt", "sash", "furisode", "gown",
               "shirt", "inner")),
)


def category_of(part):
    lower = (part or "").lower()
    for name, tokens in CATEGORY_RULES:
        if any(token in lower for token in tokens):
            return name
    return "ribbon"


def summarize(records, key):
    """按 key(骨) × 角色 聚合。median 做默认值，min/max 做导出闸门的允许区间。"""
    buckets = {}
    for record in records:
        if not record["part"]:
            continue
        buckets.setdefault((key(record), role_of(record)), []).append(record)

    presets = {}
    for (part, role), group in sorted(buckets.items()):
        entry = {"samples": len(group)}
        for key in SCALARS + ("colliderRadius", "colliderRadiusSub"):
            values = sorted(item[key] for item in group)
            # p10/p90 是「摆动幅度」档位的取值来源：档位=在原版分布上取哪个分位，
            # 这样每一档都还在原版包络内，不引入编造的数字。min/max 太极端（stiffness
            # 最小 0.0001、mass 最大 15），不能直接当档位用。
            deciles = statistics.quantiles(values, n=10) if len(values) >= 10 else None
            entry[key] = {
                "median": round(statistics.median(values), 6),
                "p10": round(deciles[0] if deciles else values[0], 6),
                "p90": round(deciles[8] if deciles else values[-1], 6),
                "min": round(values[0], 6),
                "max": round(values[-1], 6),
            }
        for key in ("useWindGlobalForce", "useLimit", "colliderType", "collisionMask",
                    "dynamicType", "resetType"):
            counts = {}
            for item in group:
                counts[item[key]] = counts.get(item[key], 0) + 1
            entry[key] = {"mode": max(counts, key=counts.get), "counts": counts}
        for axis in ("limitX", "limitY", "limitZ"):
            counts = {}
            for item in group:
                counts[tuple(item[axis])] = counts.get(tuple(item[axis]), 0) + 1
            mode = max(counts, key=counts.get)
            entry[axis] = {"mode": list(mode), "distinct": len(counts)}
        presets.setdefault(part, {})[role] = entry
    return presets


def chain_usage(records):
    """每档在原版里到底挂不挂 ActorSwingChain —— 这决定我们建不建链。

    实测：skirt 94% 挂、ribbon 1% 挂。飘带蝴蝶结在原版里就是裸 ActorSwingDynamicBone，
    给它建链是照着裙摆抄错了对象（链多带一层 around/radius 的环形碰撞解算）。
    """
    usage = {}
    for record in records:
        if not record["part"]:
            continue
        slot = usage.setdefault(category_of(record["part"]), {"total": 0, "inChain": 0,
                                                             "hosts": {}})
        slot["total"] += 1
        if record["chainHost"]:
            slot["inChain"] += 1
            slot["hosts"][record["chainHost"]] = slot["hosts"].get(record["chainHost"], 0) + 1
    for slot in usage.values():
        slot["chainRatio"] = round(slot["inChain"] / slot["total"], 4)
        slot["useChain"] = slot["chainRatio"] >= 0.5
        slot["hosts"] = dict(sorted(slot["hosts"].items(), key=lambda kv: -kv[1])[:5])
    return usage


# 插件生产文件里的人工决策，集中在这里，别再散落到临时脚本里
PLUGIN_CATEGORIES = ("ribbon", "cloth", "sleeve", "skirt")
# 原版 collisionMask 是逐服装的碰撞分组归属（Skirt0 26% / Everything 19% / None 17% …），
# 对 mod 新骨没有对应语义。统一 -1(Everything)：碰撞组我们判断不了，宁可什么都撞。
PLUGIN_COLLISION_MASK = -1
# 运行时只读这几个标量；axisAddXToY/axisAddXToZ/seatDynamicCorrection 原版中位数都是 0
# 且运行时不消费，写进每份 sidecar 只是噪音。
PLUGIN_SCALARS = ("damping", "stiffness", "spring", "pendulum", "pendulumRange",
                  "mass", "wind", "rootWeight")


def build_plugin_presets(summary):
    """把扫描结果转成插件读的形状（`gakumas_mi/swing_presets.json`）。"""
    presets, usage = summary["presets"], summary["chainUsage"]
    out = {
        "_source": "tools/scan_vanilla_swing_bones.py --install 生成，别手改",
        "_amplitude": ("range 里的分位数只作参考/闸门，代码不用它调幅度。2026-08-11 试过做"
                       "弱/标准/强三档，实测五个参数从分布一端拉到另一端摆幅只动 ±35% 且方向"
                       "与预期相反，档位已撤销，只保留标准档（中位数）。"),
        "_collisionMask": ("原版逐服装的碰撞分组归属，对 mod 新骨无对应语义；"
                           f"统一取 {PLUGIN_COLLISION_MASK}(Everything)。"),
        "categories": {},
    }
    for category in PLUGIN_CATEGORIES:
        # 局部样本（`--limit N` 调试扫）不保证四档齐全，缺档跳过而不是 KeyError 崩掉。
        # 生产文件只由全量扫产出，缺档的产物会被 main() 拦住不让 --install。
        if category not in presets or category not in usage:
            continue
        roles = {}
        for role in ("root", "mid", "tip"):
            if role not in presets[category]:
                continue
            stats = presets[category][role]
            entry = {key: stats[key]["median"] for key in PLUGIN_SCALARS}
            entry["useWindGlobalForce"] = bool(int(stats["useWindGlobalForce"]["mode"]))
            entry["useLimit"] = int(stats["useLimit"]["mode"])
            for axis in ("limitX", "limitY", "limitZ"):
                entry[axis] = stats[axis]["mode"]
            entry["colliderType"] = int(stats["colliderType"]["mode"])
            entry["colliderRadius"] = stats["colliderRadius"]["median"]
            entry["colliderRadiusSub"] = stats["colliderRadiusSub"]["median"]
            entry["collisionMask"] = PLUGIN_COLLISION_MASK
            entry["dynamicType"] = int(stats["dynamicType"]["mode"])
            entry["range"] = {
                key: {quantile: stats[key][quantile]
                      for quantile in ("p10", "median", "p90", "min", "max")}
                for key in PLUGIN_SCALARS + ("colliderRadius",)
            }
            roles[role] = entry
        out["categories"][category] = {
            "useChain": usage[category]["useChain"],
            "chainRatio": usage[category]["chainRatio"],
            "samples": sum(presets[category][role]["samples"] for role in roles),
            "roles": roles,
        }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundles", type=Path, required=True, help="原版 body bundle 目录")
    parser.add_argument("--output", type=Path, required=True, help="输出目录")
    parser.add_argument("--limit", type=int, default=0, help="只扫前 N 个（调试用）")
    parser.add_argument("--install", action="store_true",
                        help="同时写入 gakumas_mi/swing_presets.json（插件生产文件）")
    args = parser.parse_args()

    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    files = sorted(path for path in args.bundles.iterdir() if path.is_file())
    if args.limit:
        files = files[:args.limit]

    records, chains, failed = [], [], []
    for index, path in enumerate(files, 1):
        try:
            bones, bundle_chains = scan_bundle(path)
        except Exception as error:  # 单个包坏了不该中断整轮扫描
            failed.append((path.name, str(error)))
            continue
        records += bones
        chains += bundle_chains
        if index % 50 == 0:
            print(f"  {index}/{len(files)} bundles, {len(records)} bones", flush=True)

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "vanilla-swing-bones.json").write_text(
        json.dumps({"bones": records, "chains": chains, "failed": failed},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (args.output / "vanilla-swing-by-part.json").write_text(
        json.dumps(summarize(records, lambda item: item["part"]),
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    presets = {
        "source": "530 原版 body bundle 的内嵌 typetree（不是按偏移猜的）",
        "chainUsage": chain_usage(records),
        "presets": summarize(records, lambda item: category_of(item["part"])),
    }
    (args.output / "vanilla-swing-presets.json").write_text(
        json.dumps(presets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 插件读的是**另一种形状**（扁平字段 + roles + useChain），此前只有一段临时脚本做转换，
    # 生产文件因此无法一键重建。这里直接产出它。
    plugin_presets = build_plugin_presets(presets)
    (args.output / "swing_presets.json").write_text(
        json.dumps(plugin_presets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.install:
        incomplete = [category for category in PLUGIN_CATEGORIES
                      if len(plugin_presets["categories"].get(category, {}).get("roles", {})) < 3]
        if incomplete:
            raise SystemExit(f"样本不全（{', '.join(incomplete)} 缺档/缺角色），拒绝写入插件生产文件。"
                             "生产基线必须来自全量扫描（别带 --limit）。")
        target = Path(__file__).resolve().parents[1] / "gakumas_mi" / "swing_presets.json"
        target.write_text(json.dumps(plugin_presets, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
        print(f"已写入插件生产文件 {target}")

    chained = sum(1 for item in records if item["chainHost"])
    unnamed = sum(1 for item in records if not item["part"])
    print(f"bundles={len(files)} failed={len(failed)} bones={len(records)} "
          f"inChain={chained} unparsedNames={unnamed} chains={len(chains)} "
          f"categories={sorted(presets['presets'])}")


if __name__ == "__main__":
    main()
