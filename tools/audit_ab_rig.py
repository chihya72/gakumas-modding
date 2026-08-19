# -*- coding: utf-8 -*-
"""AB 成品的 rig 级闸门：拿被替换的那套原版 body 当对照，判 mod 的骨/权重/bindpose。

`verify_ab_package.py` 只查源目录里自洽的东西（stdlib，不依赖 UnityPy）。这里查的是
**必须回到原版 bundle 才能判**的四件事：

  G2  跨关节权重混合带 —— 和被替换的那套原版逐关节对比，不用全局阈值
  G3  一根骨一个姿势驱动器
  G4  摇物 / 驱动器 / 静态碰撞体的互斥摆放
  G7  bindpose 自洽 —— 运行时算 `原版活体骨ᵢ × mod_bindposeᵢ`，所有骨该得到同一个空间校正

阈值策略：**能和"这一件原版"对比就不用总体阈值。**总体阈值标定错过一次
（`*_H` 承重定 8% 会误报 27% 的原版），逐件对比没有这个风险。

    python tools/audit_ab_rig.py <mod目录|bundle-src目录> [--vanilla <名字或路径>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vanilla_body import VanillaBody, resolve

# 关节：(名字, 近端骨, 远端骨)。远端骨的子树算"远侧"，近端骨子树减去远侧算"近侧"。
JOINTS = [
    ("左肩", "LeftShoulder", "LeftArm"),
    ("左肘", "LeftArm", "LeftForeArm"),
    ("左腕", "LeftForeArm", "LeftHand"),
    ("右肩", "RightShoulder", "RightArm"),
    ("右肘", "RightArm", "RightForeArm"),
    ("右腕", "RightForeArm", "RightHand"),
    ("左膝", "LeftUpLeg", "LeftLeg"),
    ("右膝", "RightUpLeg", "RightLeg"),
]

# 原版自己的带宽低于这个数时不做判断——那个关节本来就几乎不靠权重过渡（原版靠 *_H 矫正骨）。
BAND_FLOOR = 0.02
# mod 的带宽掉到原版同关节的这个比例以下算不合格。
BAND_RATIO = 0.4


# G10：绑定姿势 vs 目标静止姿势。
#
# 运行时算 `原版活体骨ᵢ × mod_bindposeᵢ`，所以源模型是按什么姿势绑的**直接决定**它在游戏里
# 摆成什么样：源在 A-pose、目标静止在 T-pose，胳膊就整体偏那个角度差。
#
# 判据在原版上标定过：由 bindpose 反推的骨位置（`inverse(bindpose)` 的平移）连成的肢体方向，
# 与 bundle 里 Transform 的静止方向，在原版 atbm-0140 上**逐根 0.00°**。
# 前提是矩阵按**转置**读 —— 导出的 `M<行><列>` 名字是转置过的，原样读会退化成无效向量。
# （G7 那条"共享空间校正"的错误判据就是栽在没先做这一步标定。）
LIMBS = [
    ("LeftArm", "LeftForeArm"), ("LeftForeArm", "LeftHand"),
    ("RightArm", "RightForeArm"), ("RightForeArm", "RightHand"),
    ("LeftUpLeg", "LeftLeg"), ("RightUpLeg", "RightLeg"),
    ("LeftLeg", "LeftFoot"), ("RightLeg", "RightFoot"),
]
POSE_WARN_DEG = 5.0     # 原版自己的静止姿势量级就是 4°
POSE_FAIL_DEG = 15.0


def _bind_positions(bone_names, bindposes):
    """由 bindpose 反推每根骨的绑定世界位置：`inverse(bindpose)` 的平移 = -Rᵀt。"""
    positions = {}
    for index, name in enumerate(bone_names):
        if not name or index >= len(bindposes):
            continue
        raw = bindposes[index]
        if not isinstance(raw, dict):
            continue
        try:                                    # 转置读：导出的字段名是转置过的
            matrix = [[float(raw[f"M{c}{r}"]) for c in range(4)] for r in range(3)]
        except (KeyError, TypeError, ValueError):
            continue
        translation = [matrix[r][3] for r in range(3)]
        positions[name] = [-sum(matrix[k][i] * translation[k] for k in range(3))
                           for i in range(3)]
    return positions


def _angle_between(a, b):
    import math
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return None
    cosine = max(-1.0, min(1.0, sum(a[i] * b[i] for i in range(3)) / (na * nb)))
    return math.degrees(math.acos(cosine))


def bind_pose_deviation(bone_names, bindposes, vanilla):
    """每根肢体骨：绑定方向与目标静止方向差多少度。纯函数，原版数据喂进去应得 0°。"""
    bind = _bind_positions(bone_names, bindposes)
    result = {}
    for near, far in LIMBS:
        if near not in bind or far not in bind:
            continue
        rest_near, rest_far = vanilla.position(near), vanilla.position(far)
        if rest_near is None or rest_far is None:
            continue
        angle = _angle_between([bind[far][i] - bind[near][i] for i in range(3)],
                               [rest_far[i] - rest_near[i] for i in range(3)])
        if angle is not None:
            result[near] = angle
    return result


def _iter_influences(skin):
    for influence in skin or []:
        if not isinstance(influence, dict):
            continue
        yield (influence.get("boneIndex") or []), (influence.get("weight") or [])


def cross_joint_bands(bone_names, skin, vanilla: VanillaBody):
    """每个关节：两侧都沾到权重的顶点占比。纯函数，原版数据喂进来也能跑（INV-8）。"""
    sides = {}
    for label, near, far in JOINTS:
        if near not in vanilla.parent and near not in vanilla.local:
            continue
        sides[label] = [
            1 if (name and vanilla.is_under(name, near, far)) else
            2 if (name and vanilla.is_under(name, far)) else 0
            for name in bone_names
        ]
    result = {}
    for label, table in sides.items():
        cross = same = 0
        for indices, weights in _iter_influences(skin):
            seen = set()
            for index, weight in zip(indices, weights):
                index = int(index)
                if float(weight) <= 0.01 or index < 0 or index >= len(table):
                    continue
                if table[index]:
                    seen.add(table[index])
            if seen == {1, 2}:
                cross += 1
            elif seen:
                same += 1
        total = cross + same
        result[label] = {"cross": cross, "total": total,
                         "share": (cross / total if total else 0.0)}
    return result


def _bindpose_corrections(bone_names, bindposes, skin, vanilla: VanillaBody):
    """运行时算 `原版世界骨ᵢ × mod_bindposeᵢ`；所有承重骨应得到同一个空间校正矩阵。"""
    used = set()
    for indices, weights in _iter_influences(skin):
        for index, weight in zip(indices, weights):
            if float(weight) > 0.01 and 0 <= int(index) < len(bone_names):
                used.add(int(index))
    products = []
    for index in sorted(used):
        name = bone_names[index]
        world = vanilla.world(name) if name else None
        if world is None or index >= len(bindposes):
            continue
        bind = bindposes[index]
        if not isinstance(bind, dict):
            continue
        # geojson 的 bindpose 写成 `M<行><列>`（Unity Matrix4x4 的字段名），平移在第 3 列。
        try:
            matrix = [[float(bind[f"M{r}{c}"]) for c in range(4)] for r in range(3)]
        except (KeyError, TypeError, ValueError):
            continue
        origin = [sum(world[r][k] * matrix[k][3] for k in range(3)) + world[r][3]
                  for r in range(3)]
        products.append((name, origin))
    return products


# 出包后看一眼几何。
#
# workspace 实测 54 个候选 blend 才收敛出 7 个成品 —— 瓶颈是往返次数，而"整体崩了"这类错误
# 本来不该占用一次进游戏的机会。这张图**只能抓粗错误**（丢了半身、整体错位、镜像反了），
# 抓不到合身/破面/飞点 —— 那些仍然只能人眼在 Blender 或游戏里看。别拿它当验收。
#
# 正交、按子网格上色、不打光；顶点直接取 geojson 的静止姿势，不做蒙皮（蒙皮要姿势，
# 那是 render_runtime_pose.py 的活）。
PREVIEW_SIZE = 720
PREVIEW_PALETTE = [(232, 178, 160), (70, 70, 78), (200, 200, 205), (176, 60, 60),
                   (210, 170, 70), (120, 150, 190), (150, 120, 170), (110, 170, 130)]


def write_preview(geo, out_path):
    try:
        import numpy as np
    except ImportError:
        return None
    vertices = np.asarray(geo.get("m_Vertices") or [], dtype=np.float32).reshape(-1, 3)
    indices = np.asarray(geo.get("m_Indices") or [], dtype=np.int64)
    if len(vertices) < 3 or len(indices) < 3:
        return None
    submeshes = geo.get("m_SubMeshes") or []
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1])) or 1.0
    centre = (lo + hi) / 2.0
    sx = ((vertices[:, 0] - centre[0]) / span * 0.9 + 0.5) * PREVIEW_SIZE
    sy = (1.0 - ((vertices[:, 1] - centre[1]) / span * 0.9 + 0.5)) * PREVIEW_SIZE
    image = np.full((PREVIEW_SIZE, PREVIEW_SIZE, 3), 250, np.uint8)
    depth = np.full((PREVIEW_SIZE, PREVIEW_SIZE), -1e9, np.float32)

    # geojson 的子网格用 `firstByte`（索引缓冲的**字节**偏移）+ `indexCount`，没有 `firstIndex`
    # —— 第一版按 firstIndex 取，永远落在 0，整个模型一个颜色，"某一段几何跑到别处去了"
    # 这种错就白检查了。
    #
    # 步长不写死：索引可能是 uint16 也可能是 uint32（chisaki 实测 firstByte 338826，
    # 除以 4 不是整数、除以 2 正好等于前一段的 indexCount → 那份是 uint16）。
    # 用最后一段能不能对齐到索引总数来判，判不出就退回不分色（宁可少一个颜色，
    # 不要画出一张假的分段图）。
    stride = 0
    for candidate in (2, 4):
        if not submeshes:
            break
        last = submeshes[-1]
        if int(last.get("firstByte", 0)) % candidate:
            continue
        if int(last.get("firstByte", 0)) // candidate + int(last.get("indexCount", 0)) == len(indices):
            stride = candidate
            break
    bounds = []
    if stride:
        for sub in submeshes:
            first = int(sub.get("firstByte", 0)) // stride
            bounds.append((first, first + int(sub.get("indexCount", 0))))

    def slot_of(triangle_start):
        for order, (first, stop) in enumerate(bounds):
            if first <= triangle_start < stop:
                return order
        return 0

    for start in range(0, len(indices) - 2, 3):
        tri = indices[start:start + 3]
        if tri.max() >= len(vertices):
            continue
        colour = PREVIEW_PALETTE[slot_of(start) % len(PREVIEW_PALETTE)]
        xs, ys = sx[tri], sy[tri]
        z = float(vertices[tri, 2].mean())
        x0, x1 = int(max(0, xs.min())), int(min(PREVIEW_SIZE - 1, xs.max()))
        y0, y1 = int(max(0, ys.min())), int(min(PREVIEW_SIZE - 1, ys.max()))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        d = ((ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])) or 1e-9
        a = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        b = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        inside = (a >= 0) & (b >= 0) & (a + b <= 1) & (z > depth[y0:y1 + 1, x0:x1 + 1])
        if not inside.any():
            continue
        depth[y0:y1 + 1, x0:x1 + 1][inside] = z
        image[y0:y1 + 1, x0:x1 + 1][inside] = colour

    import struct
    import zlib
    raw = b"".join(bytes([0]) + image[row].tobytes() for row in range(PREVIEW_SIZE))
    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))
    png = (bytes([137, 80, 78, 71, 13, 10, 26, 10])
           + chunk(b"IHDR", struct.pack(">IIBBBBB", PREVIEW_SIZE, PREVIEW_SIZE, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    Path(out_path).write_bytes(png)
    return out_path


def audit(mod_root: Path, vanilla_name: str | None, preview_dir: Path | None = None):
    bundle_src = mod_root / "bundle-src"
    if not (bundle_src / "mod.json").is_file():
        bundle_src = mod_root
    manifest = json.loads((bundle_src / "mod.json").read_text(encoding="utf-8"))
    replacement = (manifest.get("replacements") or [{}])[0]
    target = vanilla_name or replacement.get("source") or ""
    sidecar_name = Path(str(replacement.get("skeleton", ""))).name
    sidecar = json.loads((bundle_src / sidecar_name).read_text(encoding="utf-8"))
    bone_names = [item.get("name") for item in sidecar.get("bones", [])]

    vanilla = VanillaBody(resolve(target))
    if vanilla.mesh is None:
        raise SystemExit(f"原版 {target} 的网格读不出来（多半缺 .resS），无法做对照 —— "
                         "补齐 all_body 库里的资源文件再跑")
    problems, notes = [], []

    # --- G2 ---------------------------------------------------------------
    van_skin = [{"boneIndex": [w.boneIndex[i] for i in range(4)],
                 "weight": [w.weight[i] for i in range(4)]} for w in vanilla.mesh.m_Skin]
    van_bands = cross_joint_bands(vanilla.renderer_bones, van_skin, vanilla)
    for geo_path in sorted(bundle_src.glob("*.geojson.txt")):
        geo = json.loads(geo_path.read_text(encoding="utf-8"))
        if preview_dir is not None:
            shot = write_preview(geo, preview_dir / (geo_path.name.split(".")[0] + ".preview.png"))
            notes.append(f"  预览图 {shot}" if shot
                         else "  预览图跳过（缺 numpy 或几何为空）")
        bands = cross_joint_bands(bone_names, geo.get("m_Skin"), vanilla)
        weak = []
        for label, mod_band in bands.items():
            base = van_bands.get(label, {}).get("share", 0.0)
            if base < BAND_FLOOR:
                continue
            if mod_band["share"] < base * BAND_RATIO:
                weak.append(f"{label} {mod_band['share']:.1%}(原版 {base:.1%})")
        notes.append("  跨关节带 " + "  ".join(
            f"{k} {v['share']:.1%}/{van_bands.get(k, {}).get('share', 0):.1%}"
            for k, v in bands.items()))
        if weak:
            problems.append(f"{geo_path.name}: 跨关节权重带远低于原版同关节 —— " + "，".join(weak))

        # --- G7 未实现（不是忘了，是试过并且证伪了）---------------------------
        # 第一版假设：运行时算 `原版活体骨ᵢ × mod_bindposeᵢ`，所以所有承重骨应该得到同一个
        # mod→renderer 空间校正矩阵，离散度大 = bindpose 坏。
        # 拿**原版自己的** bindpose 喂这个判据（INV-8 反证）：
        #     原样  样本 132  最大离散 1088.6mm (LeftToeBase)  中位 261.3mm
        #     转置  样本 132  最大离散  748.2mm (RightHandThumb2) 中位 6.7mm
        # 两种矩阵约定都不成立 —— 前提本身错：bindpose 编码的是**绑定时**的骨世界变换，
        # 与 bundle 里 Transform 的**当前静止**变换不必相等（原版静止姿势本来就有量级 4° 的偏差），
        # 而且只比平移列会把旋转差异混进来。三个已出货成品全被判 ~1000mm 就是这个前提的产物。
        # 上一个在原版上也报的闸门比没有闸门更坏（风险登记 V5），所以撤掉。
        # 要重做就照 SDK 侧那条已验证的做法：在 renderer 空间里比 bindpose 推出的骨位置
        # 与实际骨位置（原版 sucu 标定 4/98、28.7mm），不要再走"共享校正矩阵"这条。
        notes.append("  bindpose 空间校正检查：未实现（原判据已在原版上证伪，见上方注释）")

        # --- G10 绑定姿势 vs 目标静止姿势 ---------------------------------
        deviation = bind_pose_deviation(bone_names, geo.get("m_BindPose") or [], vanilla)
        if deviation:
            worst = max(deviation.items(), key=lambda kv: kv[1])
            notes.append("  绑定姿势偏差 " + "  ".join(f"{k} {v:.1f}°"
                                                  for k, v in sorted(deviation.items())))
            if worst[1] >= POSE_FAIL_DEG:
                problems.append(
                    f"{geo_path.name}: 绑定姿势与目标静止姿势差 {worst[1]:.1f}°（{worst[0]}）"
                    f"——运行时按 `原版活体骨 × mod_bindpose` 蒙皮，这个角度会 1:1 显示在游戏里")
            elif worst[1] >= POSE_WARN_DEG:
                problems_warn = f"绑定姿势最大偏 {worst[1]:.1f}°（{worst[0]}，原版量级 4°）"
                notes.append("  ⚠ " + problems_warn)
        else:
            notes.append("  绑定姿势检查跳过：bindpose 里取不到肢体骨")

    # --- G3 / G4 ----------------------------------------------------------
    driver_hosts, swing_hosts, collider_hosts = {}, set(), set()
    for name, klasses in vanilla.components.items():
        drivers = [k for k in klasses if "QuartzDriver" in k]
        if drivers:
            driver_hosts[name] = drivers
        if any("ActorSwing" in k for k in klasses):
            swing_hosts.add(name)
        if any("StaticBone" in k for k in klasses):
            collider_hosts.add(name)
    doubled = sorted(f"{name}×{len(v)}" for name, v in driver_hosts.items() if len(v) > 1)
    if doubled:
        problems.append("原版侧同骨多驱动器（读错了才会出现）: " + ", ".join(doubled))

    declared = []
    for field in ("newBones", "extraSwingBones"):
        declared += [item for item in (sidecar.get(field) or []) if isinstance(item, dict)]
    nested = (sidecar.get("sourceRigRemap") or {}).get("newBones") or []
    declared += [item for item in nested if isinstance(item, dict)]
    for item in declared:
        name = item.get("name")
        if not name:
            continue
        if name in driver_hosts:
            problems.append(
                f"新骨/摇物骨 {name} 撞上原版已有的姿势驱动器（{', '.join(driver_hosts[name])}）"
                "——一根骨只能有一个求解器")
        if name.endswith("_H") and item.get("swing"):
            problems.append(f"{name} 是矫正骨（*_H），不该挂摇物")
    for chain in (sidecar.get("chains") or []):
        host = chain.get("host") if isinstance(chain, dict) else None
        if host and host in driver_hosts:
            problems.append(f"摇物链宿主 {host} 上原版已有 {', '.join(driver_hosts[host])}")
    notes.append(f"  原版组件：驱动器骨 {len(driver_hosts)} 根，摇物骨 {len(swing_hosts)} 根，"
                 f"静态骨 {len(collider_hosts)} 根")

    return {"target": target, "problems": problems, "notes": notes}


def main(argv=None):
    parser = argparse.ArgumentParser(description="AB 成品的 rig 级闸门（对照原版）")
    parser.add_argument("root", type=Path)
    parser.add_argument("--vanilla", default=None, help="原版 body 名字或路径；默认从 mod.json 取")
    parser.add_argument("--preview", type=Path, default=None,
                        help="出一张正交剪影 PNG 到这个目录。只能抓粗错误，别当验收")
    args = parser.parse_args(argv)
    report = audit(args.root, args.vanilla, args.preview)
    print(f"对照原版：{report['target']}")
    for note in report["notes"]:
        print(note)
    if report["problems"]:
        print(f"\n{len(report['problems'])} 项不合格：")
        for item in report["problems"]:
            print(f"   [X] {item}")
        return 1
    print("\n全部检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
