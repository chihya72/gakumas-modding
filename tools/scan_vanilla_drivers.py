# -*- coding: utf-8 -*-
"""扫原版 body bundle 里的姿势驱动器，产出「学马原生驱动器参数基准表」。

学马自己的 bundle **内嵌 typetree**，所以 `setting` 的每个字段都能按名字读，不用猜偏移
（这也是运行时 `AttachQuartzDriver` 按名字写值的前提：两边都只认名字）。

输出 `gakumas_mi/driver_presets.json`，形状**就是 sidecar 里 `driver` 块的形状**，
导出器抄进去即可：

    {
      "Skirt": {
        "hosts": {"LeftFrontSkirt_A": 363, ...},
        "setting": {
          "ints":    {"rotationOrder": 0, "connectionAxis": 0},
          "floats":  {},
          "vectors": {"innerCoefficient": [0.0, 0.1, 0.1], ...},
          "bones":   ["referenceBone"]          # 只记字段名，值由导出器按目标骨填
        }
      }
    }

标量取**众数**不取平均：`rotationOrder` 这类是枚举，平均出来的 0.37 是个不存在的值。
向量逐轴取中位数。对象引用只记字段名——PathID 换一套服装就没意义。

    python tools/scan_vanilla_drivers.py [--bodies 0] [--install]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import statistics

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.67f1"

LIBRARY = "D:/GIT/gakumas-modding/mod-workspace/libraries/all_body"
OUTPUT = "reference/vanilla-driver-presets.json"
INSTALL = "gakumas_mi/driver_presets.json"
PREFIX = "ActorAnimationQuartzDriver"
SUFFIX = "Bone"


def _classify(values):
    """一个字段的所有观测值 → ('ints'|'floats'|'vectors'|'bones', 代表值)。

    对象引用不能只记字段名就完事：导出器得知道**它该指向哪根骨**。PathID 本身跨服装无意义，
    所以扫描时就地解成骨名，这里统计的是名字的众数（`referenceBone` 之类在原版里是有定式的）。
    """
    sample = values[0]
    if isinstance(sample, dict):
        if {"x", "y", "z"} <= set(sample):
            axes = [[float(v[k]) for v in values if isinstance(v, dict) and k in v]
                    for k in ("x", "y", "z")]
            return "vectors", [round(statistics.median(a), 4) if a else 0.0 for a in axes]
        if "m_PathID" in sample:
            return "bones", None
        return None, None
    if isinstance(sample, str):                      # 已经解过引用的骨名
        counted = collections.Counter(values).most_common(4)
        return "bones", [{"name": n, "n": c} for n, c in counted]
    if isinstance(sample, bool):
        return "ints", int(collections.Counter(values).most_common(1)[0][0])
    if isinstance(sample, int):
        return "ints", collections.Counter(values).most_common(1)[0][0]
    if isinstance(sample, float):
        # 浮点也取众数：原版这些系数是美术手填的常量，不是连续分布，中位数会造出没人用过的值。
        return "floats", round(float(collections.Counter(values).most_common(1)[0][0]), 4)
    return None, None


def scan(limit=0):
    paths = sorted(glob.glob(os.path.join(LIBRARY, "*")))
    if limit:
        paths = paths[:limit]
    fields = collections.defaultdict(lambda: collections.defaultdict(list))
    hosts = collections.defaultdict(collections.Counter)
    costumes = collections.defaultdict(set)
    scanned = failed = 0
    for path in paths:
        try:
            env = UnityPy.load(path)
            names = {o.path_id: o.read_typetree()["m_Name"]
                     for o in env.objects if o.type.name == "GameObject"}
            # setting 里的骨引用是 GameObject 的 PathID —— 直接查 names 就是骨名。
            scripts = {o.path_id: o.read_typetree()["m_ClassName"]
                       for o in env.objects if o.type.name == "MonoScript"}
            for obj in env.objects:
                if obj.type.name != "MonoBehaviour":
                    continue
                tree = obj.read_typetree()
                klass = scripts.get(tree.get("m_Script", {}).get("m_PathID"), "")
                if not klass.startswith(PREFIX) or not klass.endswith(SUFFIX):
                    continue
                kind = klass[len(PREFIX):-len(SUFFIX)]
                setting = tree.get("setting")
                if not isinstance(setting, dict):
                    continue
                host = names.get(tree.get("m_GameObject", {}).get("m_PathID"), "?")
                hosts[kind][host] += 1
                costumes[kind].add(os.path.basename(path))
                for key, value in setting.items():
                    # 对象引用当场解成骨名；解不出来（跨文件引用）就跳过，别把 PathID 存下去。
                    if isinstance(value, dict) and "m_PathID" in value:
                        resolved = names.get(value.get("m_PathID"))
                        if resolved:
                            fields[kind][key].append(resolved)
                        continue
                    fields[kind][key].append(value)
            scanned += 1
        except BaseException:
            failed += 1
    presets = {}
    for kind, per_field in sorted(fields.items()):
        block = {"ints": {}, "floats": {}, "vectors": {}, "bones": {}}
        for key, values in sorted(per_field.items()):
            if not values:
                continue
            bucket, representative = _classify(values)
            if bucket == "bones":
                block["bones"][key] = representative or []
            elif bucket:
                block[bucket][key] = representative
        presets[kind] = {
            "costumes": len(costumes[kind]),
            "instances": sum(hosts[kind].values()),
            "hosts": dict(hosts[kind].most_common(8)),
            "setting": block,
        }
    return {"scanned": scanned, "failed": failed, "drivers": presets}


def main(argv=None):
    parser = argparse.ArgumentParser(description="扫原版姿势驱动器参数")
    parser.add_argument("--bodies", type=int, default=0, help="只扫前 N 套（0 = 全部）")
    parser.add_argument("--install", action="store_true", help="一并写进 gakumas_mi/driver_presets.json")
    args = parser.parse_args(argv)
    report = scan(args.bodies)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f"扫了 {report['scanned']} 套（{report['failed']} 套读不出），"
          f"{len(report['drivers'])} 种驱动器 → {OUTPUT}")
    for kind, item in sorted(report["drivers"].items(), key=lambda kv: -kv[1]["costumes"]):
        block = item["setting"]
        print(f"  {kind:22s} 服装 {item['costumes']:3d}  "
              f"int {len(block['ints'])} float {len(block['floats'])} "
              f"vec {len(block['vectors'])} bone {len(block['bones'])}  "
              f"宿主例 {list(item['hosts'])[:2]}")
    if args.install:
        payload = {kind: item["setting"] for kind, item in report["drivers"].items()}
        with open(INSTALL, "w", encoding="utf-8") as stream:
            json.dump({"schemaVersion": 1, "drivers": payload}, stream,
                      ensure_ascii=False, indent=2)
        print(f"已装到 {INSTALL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
