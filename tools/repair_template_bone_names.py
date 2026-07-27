"""Repair placeholder bone names in a Unity template bundle.

The mesh bone-hash order and the runtime profile bone order are authoritative.
This only changes GameObject names and the bundled template sidecar; hierarchy,
bind poses, meshes, and materials are left untouched.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import UnityPy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.patch_unity_bundle import _bone_name, _object_by_container, _template_renderer


PLACEHOLDER = re.compile(r"^bone_-?\d+$", re.IGNORECASE)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def profile_bone_names(profile: dict, renderer_name: str) -> list[str]:
    for renderer in profile.get("renderers") or []:
        if renderer.get("name") == renderer_name or renderer.get("renderer") == renderer_name:
            names = renderer.get("bones") or []
            break
    else:
        renderers = profile.get("renderers") or []
        if len(renderers) != 1:
            raise ValueError(f"profile 中找不到 renderer {renderer_name!r}")
        names = renderers[0].get("bones") or []
    names = [str(name) for name in names]
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("profile bones 为空或含重复/空骨名")
    return names


def _apply_sidecar_renames(sidecar: dict, rename: dict[str, str]) -> int:
    bones = list(sidecar.get("bones") or [])
    changed = 0
    for item in bones:
        old = str(item.get("name") or "")
        if old in rename:
            item["name"] = rename[old]
            changed += 1
    for item in bones:
        if item.get("parentName") in rename:
            item["parentName"] = rename[item["parentName"]]
    if sidecar.get("rootBone") in rename:
        sidecar["rootBone"] = rename[sidecar["rootBone"]]
    return changed


def _rename_sidecar_by_index(sidecar: dict, names: list[str]) -> int:
    bones = list(sidecar.get("bones") or [])
    if len(bones) != len(names):
        raise ValueError(f"模板 sidecar 骨数 {len(bones)} != profile 骨数 {len(names)}")
    rename = {
        str(item.get("name") or ""): names[index]
        for index, item in enumerate(bones)
        if str(item.get("name") or "") != names[index]
    }
    return _apply_sidecar_renames(sidecar, rename)


def _rename_sidecar_by_hash(sidecar: dict, hash_to_name: dict[int, str]) -> int:
    rename = {}
    for item in sidecar.get("bones") or []:
        old = str(item.get("name") or "")
        match = PLACEHOLDER.fullmatch(old)
        if match and int(match.group(0).split("_", 1)[1]) in hash_to_name:
            rename[old] = hash_to_name[int(match.group(0).split("_", 1)[1])]
    return _apply_sidecar_renames(sidecar, rename)


def repair(template: Path, mesh_json: Path, profile_json: Path, output: Path,
           renderer_name: str, mode: str) -> int:
    mesh = read_json(mesh_json)
    hashes = [int(value) for value in mesh.get("m_BoneNameHashes") or []]
    names = profile_bone_names(read_json(profile_json), renderer_name)
    if len(hashes) != len(names):
        raise ValueError(f"Mesh hash 数 {len(hashes)} != profile 骨数 {len(names)}")

    env = UnityPy.load(str(template))
    objects, renderer = _template_renderer(env, renderer_name)
    renderer_tree = renderer.read_typetree()
    pointers = list(renderer_tree.get("m_Bones") or [])
    if len(pointers) != len(names):
        raise ValueError(f"模板 SMR 骨数 {len(pointers)} != profile 骨数 {len(names)}")

    old_names = [_bone_name(objects, pointer) for pointer in pointers]
    if any(not name for name in old_names) or len(set(old_names)) != len(old_names):
        raise ValueError("模板 SMR 含空骨名或重复骨名")
    hash_to_name = dict(zip(hashes, names))
    if mode == "index":
        target_names = names
    else:
        target_names = []
        for old in old_names:
            match = PLACEHOLDER.fullmatch(str(old))
            target_names.append(
                hash_to_name.get(int(match.group(0).split("_", 1)[1]), old)
                if match else old
            )
        if len(set(target_names)) != len(target_names):
            raise ValueError("按 hash 修名后模板/成品出现重复骨名")

    changed = 0
    for pointer, old, new in zip(pointers, old_names, target_names):
        if old == new:
            continue
        transform = objects[pointer["m_PathID"]]
        tree = transform.read_typetree()
        game_object = objects[tree["m_GameObject"]["m_PathID"]]
        go_tree = game_object.read_typetree()
        go_tree["m_Name"] = new
        game_object.save_typetree(go_tree)
        changed += 1

    _, _, entries = _object_by_container(env)
    sidecars = []
    for path, obj in entries:
        if obj.type.name != "TextAsset" or not path.endswith("_bones.json.txt"):
            continue
        try:
            sidecar = json.loads(obj.read().text)
        except (TypeError, json.JSONDecodeError):
            continue
        if len(sidecar.get("bones") or []) == len(names):
            sidecars.append((obj, sidecar))
    if len(sidecars) != 1:
        raise ValueError(f"模板中匹配到 {len(sidecars)} 个骨架 sidecar，期望 1 个")
    text_asset, sidecar = sidecars[0]
    changed += (_rename_sidecar_by_index(sidecar, names) if mode == "index"
                else _rename_sidecar_by_hash(sidecar, hash_to_name))
    text = text_asset.read()
    text.text = json.dumps(sidecar, ensure_ascii=False, separators=(",", ":"))
    text.save()

    remaining = [name for name in names if PLACEHOLDER.fullmatch(name)]
    if remaining:
        raise ValueError(f"profile 仍含占位骨名：{remaining[:3]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(env.file.save("original"))
    print(f"repaired {output}: renamed {changed} entries; placeholders=0")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--mesh-json", type=Path, required=True)
    parser.add_argument("--profile-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--renderer", default="Geo_Body")
    parser.add_argument("--mode", choices=("index", "hash"), default="index",
                        help="index 修 R32 模板；hash 修已经按拓扑序导出的成品 bundle")
    args = parser.parse_args()
    repair(args.template, args.mesh_json, args.profile_json, args.output, args.renderer, args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
