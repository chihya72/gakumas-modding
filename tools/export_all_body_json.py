"""Batch export Gakumas Mesh JSON and optional skeleton sidecar JSON.

Defaults export body（--suffix _body --mesh-name Geo_Body）。发饰库示例：
  python tools/export_all_body_json.py --input all_hair --suffix _hair \
      --mesh-name Geo_HairProp --output .local/assetstudio-hairprop-json --skeleton

Input layout:
  all_body/
    mdl_chr_amao-cstm-0000_body
    mdl_chr_hski-cstm-0000_body

Output layout:
  .local/assetstudio-body-json/
    mdl_chr_amao-cstm-0000_body/
      Geo_Body.json
      Geo_Body.skeleton.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AS_CLI = Path(r"D:\GIT\AssetStudio-net10.0-win\AssetStudio.CLI.exe")
DEFAULT_UNITY_VERSION = "6000.0.67f1"


def log(message: str) -> None:
    print(message, flush=True)


def find_mesh_json(directory: Path, mesh_name: str = "Geo_Body") -> Path | None:
    direct = directory / f"{mesh_name}.json"
    if direct.is_file():
        return direct
    matches = list(directory.rglob(f"{mesh_name}.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(f"找到多个 {mesh_name}.json，无法判断使用哪一个：{directory}")
    return None


def remove_body_output(output_dir: Path, body_out: Path) -> None:
    root = output_dir.resolve()
    target = body_out.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"拒绝删除输出目录外的路径：{target}") from exc
    if target == root:
        raise RuntimeError(f"拒绝删除输出根目录：{target}")
    if target.exists():
        shutil.rmtree(target)


def run_assetstudio(
    assetstudio_cli: Path,
    bundle: Path,
    output_dir: Path,
    unity_version: str,
    game: str,
    mesh_name: str = "Geo_Body",
) -> tuple[int, str]:
    command = [
        str(assetstudio_cli),
        str(bundle),
        str(output_dir),
        "--game",
        game,
        "--unity_version",
        unity_version,
        "--types",
        "Mesh",
        "--names",
        f"^{mesh_name}$",
        "--export_type",
        "JSON",
        "--group_assets",
        "None",
    ]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout


def _vec3(value) -> list[float]:
    return [float(value.X), float(value.Y), float(value.Z)]


def _quat(value) -> list[float]:
    return [float(value.X), float(value.Y), float(value.Z), float(value.W)]


def is_valid_skeleton_json(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "文件不存在"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"JSON 无法读取：{exc}"

    weighted_count = int(data.get("weightedBoneCount") or 0)
    node_count = int(data.get("nodeCount") or 0)
    nodes = data.get("nodes") or []
    if weighted_count <= 0:
        return False, "weightedBoneCount 为空"
    if node_count <= 0 or not nodes:
        return False, "nodeCount/nodes 为空"
    if not any(node.get("weightedIndex") is not None for node in nodes):
        return False, "没有任何加权骨骼节点"
    return True, ""


def export_skeleton_json(
    bundle: Path, mesh_json: Path, output: Path, unity_version: str,
    mesh_name: str = "Geo_Body",
) -> dict:
    try:
        import UnityPy
    except ImportError as exc:
        raise RuntimeError("缺少 UnityPy，无法生成骨架 JSON。请先安装 UnityPy。") from exc

    UnityPy.config.FALLBACK_UNITY_VERSION = unity_version
    env = UnityPy.load(str(bundle))

    # _hair 包里有 Geo_Hair 和 Geo_HairProp 两个 renderer，
    # 必须选 m_Mesh 指向目标网格名的那个，不能取第一个带骨的。
    target_mesh_path_ids = set()
    for obj in env.objects:
        if obj.type.name != "Mesh":
            continue
        try:
            if obj.read().m_Name == mesh_name:
                target_mesh_path_ids.add(obj.path_id)
        except Exception:
            continue

    renderer_object = None
    renderer = None
    fallback = None  # (obj, candidate) 第一个带骨的，仅当按网格名匹配不到时使用
    last_error = None
    for obj in env.objects:
        if obj.type.name != "SkinnedMeshRenderer":
            continue
        try:
            candidate = obj.read()
            bones = list(getattr(candidate, "m_Bones", None) or [])
            if not bones:
                last_error = RuntimeError(f"SkinnedMeshRenderer {obj.path_id} 没有 m_Bones")
                continue
            mesh_ptr = getattr(candidate, "m_Mesh", None)
            if mesh_ptr is not None and getattr(mesh_ptr, "path_id", 0) in target_mesh_path_ids:
                renderer = candidate
                renderer_object = obj
                break
            if fallback is None:
                fallback = (obj, candidate)
        except Exception as exc:  # keep scanning; some bundles have stale/unreadable objects
            last_error = exc
    if renderer is None and fallback is not None and not target_mesh_path_ids:
        # 网格名匹配不可用（如 Mesh 对象不可读）时退回旧行为
        renderer_object, renderer = fallback
    if renderer_object is None or renderer is None:
        detail = f"；最后错误：{last_error}" if last_error else ""
        raise RuntimeError(
            f"没有 m_Mesh 指向 {mesh_name} 且带骨骼的 SkinnedMeshRenderer：{bundle}{detail}"
        )

    mesh = json.loads(mesh_json.read_text(encoding="utf-8"))
    weighted = []
    missing_bones = []
    for index, ptr in enumerate(renderer.m_Bones):
        if ptr is None or not getattr(ptr, "path_id", 0):
            missing_bones.append(f"#{index}: empty")
            continue
        try:
            bone = ptr.read()
        except Exception as exc:
            missing_bones.append(f"#{index}: path_id={ptr.path_id}, {exc}")
            continue
        if bone is None:
            missing_bones.append(f"#{index}: path_id={ptr.path_id}, read=None")
            continue
        weighted.append(bone)
    if missing_bones:
        preview = "; ".join(missing_bones[:8])
        suffix = f" ... 共 {len(missing_bones)} 个" if len(missing_bones) > 8 else ""
        raise RuntimeError(f"骨骼 Transform 引用不完整：{preview}{suffix}")
    if not weighted:
        raise RuntimeError("骨架为空：m_Bones 没有任何可读取 Transform")

    weighted_by_path = {bone.path_id: index for index, bone in enumerate(weighted)}

    needed = {}
    for bone in weighted:
        current = bone
        while current and current.path_id not in needed:
            needed[current.path_id] = current
            father = current.m_Father
            current = father.read() if father and father.path_id else None

    def depth(transform) -> int:
        result = 0
        father = transform.m_Father
        while father and father.path_id and father.path_id in needed:
            result += 1
            transform = father.read()
            father = transform.m_Father
        return result

    ordered = sorted(needed.values(), key=lambda item: (depth(item), item.path_id))
    node_index = {node.path_id: index for index, node in enumerate(ordered)}
    nodes = []
    for node in ordered:
        father_id = node.m_Father.path_id if node.m_Father else 0
        weighted_index = weighted_by_path.get(node.path_id)
        entry = {
            "name": node.m_GameObject.read().m_Name,
            "pathId": node.path_id,
            "parent": node_index.get(father_id, -1),
            "weightedIndex": weighted_index,
            "localPosition": _vec3(node.m_LocalPosition),
            "localRotation": _quat(node.m_LocalRotation),
            "localScale": _vec3(node.m_LocalScale),
        }
        if weighted_index is not None:
            entry["boneNameHash"] = mesh["m_BoneNameHashes"][weighted_index]
            entry["bindPose"] = mesh["m_BindPose"][weighted_index]
        nodes.append(entry)
    if not nodes:
        raise RuntimeError("骨架节点为空：没有生成任何 Transform 节点")
    if not any(node.get("weightedIndex") is not None for node in nodes):
        raise RuntimeError("骨架无效：没有任何节点对应加权骨骼")

    data = {
        "schemaVersion": 1,
        "unityVersion": unity_version,
        "rendererPathId": renderer_object.path_id,
        "rootBonePathId": renderer.m_RootBone.path_id,
        "weightedBoneCount": len(weighted),
        "nodeCount": len(nodes),
        "nodes": nodes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def body_files(input_dir: Path, suffix: str = "_body") -> list[Path]:
    return sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.name.startswith("mdl_chr_") and path.name.endswith(suffix)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="批量导出 Gakumas 所有 body 的 Geo_Body JSON。")
    parser.add_argument("--input", type=Path, default=ROOT / "all_body", help="body AB 目录，默认 ./all_body")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".local" / "assetstudio-body-json",
        help="输出目录，默认 ./.local/assetstudio-body-json",
    )
    parser.add_argument("--assetstudio", type=Path, default=DEFAULT_AS_CLI, help="AssetStudio.CLI.exe 路径")
    parser.add_argument("--unity-version", default=DEFAULT_UNITY_VERSION, help="Unity 版本，默认 6000.0.67f1")
    parser.add_argument("--game", default="Normal", help="AssetStudio --game 参数，默认 Normal")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个，调试用")
    parser.add_argument("--force", action="store_true", help="已存在也重新导出")
    parser.add_argument("--skeleton", action="store_true", help="同时生成 <mesh-name>.skeleton.json")
    parser.add_argument("--suffix", default="_body", help="bundle 文件名后缀过滤，默认 _body（发饰用 _hair）")
    parser.add_argument("--mesh-name", default="Geo_Body", help="要导出的网格名，默认 Geo_Body（发饰用 Geo_HairProp）")
    args = parser.parse_args()
    mesh_name = args.mesh_name

    input_dir = args.input.resolve()
    output_dir = args.output.resolve()
    assetstudio = args.assetstudio.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"输入目录不存在：{input_dir}")
    if not assetstudio.is_file():
        raise SystemExit(f"找不到 AssetStudio CLI：{assetstudio}")

    bundles = body_files(input_dir, args.suffix)
    if args.limit > 0:
        bundles = bundles[:args.limit]
    if not bundles:
        raise SystemExit(f"没有在 {input_dir} 找到 mdl_chr_*{args.suffix} 文件")

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for index, bundle in enumerate(bundles, 1):
        body_id = bundle.name
        body_out = output_dir / body_id
        mesh_json = body_out / f"{mesh_name}.json"
        skeleton_json = body_out / f"{mesh_name}.skeleton.json"
        body_out.mkdir(parents=True, exist_ok=True)

        status = "skipped"
        message = ""
        log(f"[{index}/{len(bundles)}] {body_id}")

        if mesh_json.is_file() and not args.force:
            status = "mesh-exists"
            log("  Mesh JSON 已存在，跳过；加 --force 可重导。")
        else:
            if args.force and mesh_json.exists():
                mesh_json.unlink()
            code, output = run_assetstudio(assetstudio, bundle, body_out, args.unity_version, args.game, mesh_name)
            found = find_mesh_json(body_out, mesh_name)
            if found is None:
                status = "mesh-missing"
                message = f"AssetStudio exit={code}，但没有生成 {mesh_name}.json"
                (body_out / "assetstudio.log").write_text(output, encoding="utf-8", errors="ignore")
                log(f"  失败：{message}")
                summary.append({
                    "body": body_id,
                    "meshJson": "",
                    "skeletonJson": "",
                    "status": status,
                    "message": message,
                })
                continue
            if found != mesh_json:
                shutil.copy2(found, mesh_json)
            (body_out / "assetstudio.log").write_text(output, encoding="utf-8", errors="ignore")
            status = "mesh-exported"
            log(f"  Mesh JSON：{mesh_json}")

        if args.skeleton:
            if skeleton_json.is_file() and not args.force:
                valid, reason = is_valid_skeleton_json(skeleton_json)
                if valid:
                    status = f"{status}+skeleton"
                    log("  骨架 JSON 已存在且有效，跳过；加 --force 可重导。")
                else:
                    skeleton_json.unlink()
                    log(f"  已删除无效骨架 JSON：{reason}")
                    try:
                        data = export_skeleton_json(bundle, mesh_json, skeleton_json, args.unity_version, mesh_name)
                        valid, reason = is_valid_skeleton_json(skeleton_json)
                        if not valid:
                            skeleton_json.unlink(missing_ok=True)
                            raise RuntimeError(f"生成后校验失败：{reason}")
                        status = f"{status}+skeleton"
                        log(f"  骨架 JSON：{skeleton_json} ({data['nodeCount']} nodes / {data['weightedBoneCount']} weighted)")
                    except Exception as exc:
                        skeleton_json.unlink(missing_ok=True)
                        status = "skeleton-skipped"
                        message = str(exc)
                        log(f"  骨架跳过：{message}")
            else:
                try:
                    if args.force:
                        skeleton_json.unlink(missing_ok=True)
                    data = export_skeleton_json(bundle, mesh_json, skeleton_json, args.unity_version, mesh_name)
                    valid, reason = is_valid_skeleton_json(skeleton_json)
                    if not valid:
                        skeleton_json.unlink(missing_ok=True)
                        raise RuntimeError(f"生成后校验失败：{reason}")
                    status = f"{status}+skeleton"
                    log(f"  骨架 JSON：{skeleton_json} ({data['nodeCount']} nodes / {data['weightedBoneCount']} weighted)")
                except Exception as exc:
                    skeleton_json.unlink(missing_ok=True)
                    status = "skeleton-skipped"
                    message = str(exc)
                    log(f"  骨架跳过：{message}")

        valid_skeleton = False
        if skeleton_json.is_file():
            valid_skeleton, reason = is_valid_skeleton_json(skeleton_json)
            if not valid_skeleton:
                skeleton_json.unlink(missing_ok=True)
                if not message:
                    message = f"已删除无效骨架 JSON：{reason}"
        if args.skeleton and not valid_skeleton:
            # 骨架只是可选 sidecar：Mesh JSON 自带 bind pose / 权重 / bindpose /
            # 骨骼 hash，逆解链不依赖骨架层级。保留 Mesh JSON 作为资源包对外提供，
            # 不再删除整个输出目录。
            if mesh_json.is_file() and status == "skeleton-skipped":
                status = "mesh-only"
            log("  骨架不可用，仅保留 Mesh JSON（逆解链不依赖骨架）。")

        summary.append({
            "body": body_id,
            "meshJson": str(mesh_json) if mesh_json.is_file() else "",
            "skeletonJson": str(skeleton_json) if valid_skeleton else "",
            "status": status,
            "message": message,
        })

    summary_path = output_dir / "export-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mesh_ok = sum(1 for item in summary if item["meshJson"])
    skeleton_ok = sum(1 for item in summary if item["skeletonJson"])
    mesh_failed = sum(1 for item in summary if item["status"] == "mesh-missing")
    log("")
    if args.skeleton:
        log(f"完成：Mesh JSON {mesh_ok}/{len(bundles)} 个（资源包）；其中 {skeleton_ok} 个带可用骨架；Mesh 导出失败 {mesh_failed} 个")
    else:
        log(f"完成：{mesh_ok}/{len(bundles)} 个 Mesh JSON")
    log(f"汇总：{summary_path}")
    return 0 if mesh_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
