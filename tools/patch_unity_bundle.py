"""Patch a Unity 6 template bundle from a Phase 1 bundle-src directory."""

from __future__ import annotations

import argparse
import copy
import json
import re
import struct
from pathlib import Path

from PIL import Image
import UnityPy
from UnityPy.enums import TextureFormat
from UnityPy.export import Texture2DConverter


FORMAT_SIZE = {0: 4, 2: 1, 10: 4}  # Float32, UNorm8, UInt32


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _asset(path: str) -> str:
    return str(path).replace("\\", "/").lower()


_PROP_CANON = {
    "_basemap": "basecolor", "basecolor": "basecolor",
    "_defmap": "packedmask", "packedmask": "packedmask",
    "_shademap": "shadecolor", "shadecolor": "shadecolor",
}


def _tex_key(item: dict):
    """Texture identity keyed by renderer+slot+canonical semantic. P1 writes Unity
    property names (_BaseMap/_DefMap/_ShadeMap); the template's throwaway manifest
    uses semantic names (baseColor/packedMask/shadeColor). Canonicalise so they match."""
    prop = str(item.get("property", "")).lower()
    return (item.get("rendererName", ""), int(item.get("materialSlot", -1)),
            _PROP_CANON.get(prop, prop))


def _replacement(manifest: dict) -> dict:
    items = manifest.get("replacements") or []
    if len(items) != 1:
        raise ValueError("2B currently accepts exactly one replacement")
    return items[0]


def _input_files_for(mod_root: Path, source: str, skeleton: str):
    geo = mod_root / f"{source}.geojson.txt"
    if not geo.is_file():
        matches = list(mod_root.glob("*.geojson.txt"))
        if len(matches) != 1:
            raise FileNotFoundError(f"cannot find one geojson in {mod_root}")
        geo = matches[0]

    skeleton_name = Path(skeleton or "").name
    bones = mod_root / skeleton_name
    if not bones.is_file():
        matches = list(mod_root.glob("*_bones.json.txt"))
        if len(matches) != 1:
            raise FileNotFoundError(f"cannot find one bones sidecar in {mod_root}")
        bones = matches[0]
    return geo, bones


def _input_files(mod_root: Path, replacement: dict):
    return _input_files_for(mod_root, replacement.get("source") or "", replacement.get("skeleton") or "")


def _renderer_rules(replacement: dict):
    rules = replacement.get("renderers") or []
    return rules or [{
        "targetRenderer": replacement.get("source") or "",
        "source": replacement.get("source") or "",
        "skeleton": replacement.get("skeleton") or "",
    }]


def _renderer_inputs(mod_root: Path, replacement: dict):
    result = []
    seen_sources = set()
    for rule in _renderer_rules(replacement):
        source = rule.get("source") or replacement.get("source") or ""
        if not source or source in seen_sources:
            continue
        skeleton = rule.get("skeleton") or replacement.get("skeleton") or ""
        geo, bones = _input_files_for(mod_root, source, skeleton)
        result.append({"rule": rule, "source": source, "skeleton": skeleton, "geo": geo, "bones": bones})
        seen_sources.add(source)
    if not result:
        raise ValueError("replacement has no renderer inputs")
    return result


def _values(geo: dict, key: str, width: int, count: int):
    values = geo.get(key) or []
    if len(values) != width * count:
        raise ValueError(f"{key} has {len(values)} values; expected {width * count}")
    return values


def _color(values):
    if max(values, default=0) > 1.0:
        values = [float(value) / 255.0 for value in values]
    return [max(0, min(255, int(float(value) * 255.0 + 0.5))) for value in values]


def _pack_vertex_data(template_channels: list[dict], geo: dict) -> bytes:
    count = int(geo.get("m_VertexCount") or 0)
    if count <= 0:
        raise ValueError("m_VertexCount must be positive")
    values = {
        0: _values(geo, "m_Vertices", 3, count),
        1: _values(geo, "m_Normals", 3, count),
        2: _values(geo, "m_Tangents", 4, count),
        3: _color(_values(geo, "m_Colors", 4, count)),
        4: _values(geo, "m_UV0", 2, count),
        12: [value for skin in geo.get("m_Skin", []) for value in skin["weight"]],
        13: [value for skin in geo.get("m_Skin", []) for value in skin["boneIndex"]],
    }
    if len(values[12]) != count * 4 or len(values[13]) != count * 4:
        raise ValueError("m_Skin count does not match m_VertexCount")

    active = []
    strides = {}
    for index, channel in enumerate(template_channels):
        dimension = int(channel.get("dimension") or 0)
        if not dimension:
            continue
        if index not in values:
            raise ValueError(f"template channel {index} is not in the Phase 1 schema")
        fmt = int(channel["format"])
        size = FORMAT_SIZE.get(fmt)
        if size is None:
            raise ValueError(f"unsupported Unity vertex format {fmt} in channel {index}")
        stream = int(channel["stream"])
        offset = int(channel["offset"])
        strides[stream] = max(strides.get(stream, 0), offset + size * dimension)
        active.append((index, channel, fmt, stream, offset, dimension))

    buffers = {stream: bytearray(stride * count) for stream, stride in strides.items()}
    for vertex in range(count):
        for index, channel, fmt, stream, offset, dimension in active:
            item = values[index][vertex * dimension:(vertex + 1) * dimension]
            if index == 3:
                payload = bytes(item)
            elif fmt == 0:
                payload = struct.pack("<" + "f" * dimension, *(float(value) for value in item))
            elif fmt == 10:
                payload = struct.pack("<" + "I" * dimension, *(int(value) for value in item))
            else:
                raise ValueError(f"channel {index} cannot encode format {fmt}")
            struct.pack_into(f"{len(payload)}s", buffers[stream], vertex * strides[stream] + offset, payload)

    result = bytearray()
    for stream in sorted(buffers):
        result.extend(b"\0" * ((-len(result)) % 16))
        result.extend(buffers[stream])
    result.extend(b"\0" * ((-len(result)) % 16))
    return bytes(result)


def _aabb(points):
    xyz = [points[i:i + 3] for i in range(0, len(points), 3)]
    lo = [min(point[i] for point in xyz) for i in range(3)]
    hi = [max(point[i] for point in xyz) for i in range(3)]
    return {
        "m_Center": {axis: (lo[i] + hi[i]) * 0.5 for i, axis in enumerate("xyz")},
        "m_Extent": {axis: (hi[i] - lo[i]) * 0.5 for i, axis in enumerate("xyz")},
    }


def _identity_bind_pose():
    return {
        f"e{row}{column}": 1.0 if row == column else 0.0
        for row in range(4) for column in range(4)
    }


def _patch_mesh(mesh_object, geo: dict, allow_bindpose_growth=False):
    tree = mesh_object.read_typetree()
    vertices = _values(geo, "m_Vertices", 3, int(geo["m_VertexCount"]))
    tree["m_VertexData"]["m_VertexCount"] = int(geo["m_VertexCount"])
    tree["m_VertexData"]["m_DataSize"] = _pack_vertex_data(tree["m_VertexData"]["m_Channels"], geo)

    index_format = int(tree.get("m_IndexFormat", 1))
    index_width = 4 if index_format == 1 else 2 if index_format == 0 else 0
    if not index_width:
        raise ValueError(f"unsupported Unity index format {index_format}")
    indices = [int(index) for index in geo.get("m_Indices") or []]
    if index_width == 2 and max(indices, default=0) > 0xFFFF:
        raise ValueError("template uses R16 indices but input exceeds 65535")
    tree["m_IndexBuffer"] = b"".join(
        struct.pack("<I" if index_width == 4 else "<H", index) for index in indices
    )

    submeshes = geo.get("m_SubMeshes") or []
    template_submeshes = tree.get("m_SubMeshes") or []
    # 自建半透明段比原版多出材质段（原版 body 只有 bdy(+bdyco)），所以允许**变多**：
    # 复制最后一段当模板再逐字段覆盖。变少仍然报错——那是归并出错的信号，不是新功能。
    if len(submeshes) > len(template_submeshes) and template_submeshes:
        for _ in range(len(submeshes) - len(template_submeshes)):
            template_submeshes.append(copy.deepcopy(template_submeshes[-1]))
        tree["m_SubMeshes"] = template_submeshes
        print(f"[patch] submesh grown to {len(template_submeshes)} (自建半透明段)")
    if len(submeshes) != len(template_submeshes):
        raise ValueError(f"submesh count changed: template={len(template_submeshes)} input={len(submeshes)}")
    for target, source in zip(template_submeshes, submeshes):
        start_byte = int(source["firstByte"])
        if start_byte % 2:
            raise ValueError("Phase 1 firstByte must be an R16 byte offset")
        target["firstByte"] = (start_byte // 2) * index_width
        target["indexCount"] = int(source["indexCount"])
        target["firstVertex"] = int(source.get("firstVertex", 0))
        target["vertexCount"] = int(source.get("vertexCount", 0))
        target["baseVertex"] = int(source.get("baseVertex", 0))
        first = target["firstVertex"] * 3
        last = first + target["vertexCount"] * 3
        target["localAABB"] = _aabb(vertices[first:last]) if last > first else _aabb(vertices)
    tree["m_LocalAABB"] = _aabb(vertices)
    bindposes = []
    for pose in geo.get("m_BindPose") or []:
        bindposes.append({f"e{row}{column}": float(pose[f"M{column}{row}"])
                          for row in range(4) for column in range(4)})
    template_bindposes = tree.get("m_BindPose") or []
    if len(bindposes) > len(template_bindposes) and allow_bindpose_growth:
        template_bindposes.extend(
            _identity_bind_pose() for _ in range(len(bindposes) - len(template_bindposes))
        )
    if len(bindposes) != len(template_bindposes):
        raise ValueError("bindpose count changed; use a matching body template")
    tree["m_BindPose"] = bindposes
    bone_aabbs = tree.get("m_BonesAABB")
    if isinstance(bone_aabbs, list):
        if len(bindposes) > len(bone_aabbs) and allow_bindpose_growth:
            bone_aabbs.extend({
                "m_Min": {axis: float("inf") for axis in "xyz"},
                "m_Max": {axis: float("-inf") for axis in "xyz"},
            } for _ in range(len(bindposes) - len(bone_aabbs)))
        if len(bone_aabbs) != len(bindposes):
            raise ValueError("bone AABB count changed; use a matching body template")
        tree["m_BonesAABB"] = bone_aabbs
    mesh_object.save_typetree(tree)


def _bone_name(objs, pptr):
    transform = objs.get(pptr.get("m_PathID"))
    if transform is None:
        return None
    game_object = objs.get(transform.read_typetree().get("m_GameObject", {}).get("m_PathID"))
    return game_object.read_typetree().get("m_Name") if game_object else None


def _read_tree(obj):
    tree = vars(obj).get("_gmi_typetree")
    return tree if tree is not None else obj.read_typetree()


def _template_renderer(env, renderer_name=""):
    objects = {obj.path_id: obj for obj in env.objects}
    renderers = [obj for obj in objects.values()
                 if obj.type.name == "SkinnedMeshRenderer"]
    target = None
    for renderer in renderers:
        game_object = objects.get(
            renderer.read_typetree().get("m_GameObject", {}).get("m_PathID")
        )
        if game_object and game_object.read_typetree().get("m_Name") == renderer_name:
            target = renderer
            break
    if target is None and len(renderers) == 1:
        target = renderers[0]
    if target is None:
        raise ValueError(f"template SkinnedMeshRenderer not found for renderer '{renderer_name}'")
    return objects, target


def _template_bone_hash_map(env, renderer_name="", fallback_hashes=None):
    """Map Mesh m_BoneNameHashes to the target SMR Transform names.

    Mesh-only source libraries may synthesize ``bone_<hash>`` names when their
    costume-specific skeleton sidecar is absent. The R32 template still has
    the authoritative hash order and Transform names.
    """
    objects, renderer = _template_renderer(env, renderer_name)
    renderer_tree = _read_tree(renderer)
    mesh = objects.get(renderer_tree.get("m_Mesh", {}).get("m_PathID"))
    if mesh is None or mesh.type.name != "Mesh":
        return {}
    hashes = list(_read_tree(mesh).get("m_BoneNameHashes") or [])
    pptrs = list(renderer_tree.get("m_Bones") or [])
    if not hashes:
        hashes = list(fallback_hashes or [])
    if len(hashes) != len(pptrs):
        return {}
    result = {}
    for bone_hash, pptr in zip(hashes, pptrs):
        name = _bone_name(objects, pptr)
        if name is not None:
            result.setdefault(int(bone_hash), name)
    return result


_HASH_BONE_NAME = re.compile(r"^bone_(-?\d+)$", re.IGNORECASE)


def _resolve_hash_bone_names(sidecar, hash_to_name):
    """Replace synthetic bone_<hash> names with template Transform names."""
    if not hash_to_name:
        return 0
    bones = list(sidecar.get("bones") or [])
    rename = {}
    existing = {str(item.get("name")) for item in bones if item.get("name")}
    for item in bones:
        old_name = str(item.get("name") or "")
        match = _HASH_BONE_NAME.fullmatch(old_name)
        if not match:
            continue
        new_name = hash_to_name.get(int(match.group(1)))
        if not new_name or new_name == old_name:
            continue
        if new_name in existing and new_name not in rename:
            raise ValueError(
                f"template hash bone rename collides: {old_name} -> {new_name}"
            )
        rename[old_name] = str(new_name)
    if not rename:
        return 0

    def rename_item(item):
        for key in ("name", "parentName"):
            if item.get(key) in rename:
                item[key] = rename[item[key]]

    for item in bones:
        rename_item(item)
    for key in ("newBones", "extraSwingBones"):
        for item in sidecar.get(key) or []:
            rename_item(item)
    if sidecar.get("rootBone") in rename:
        sidecar["rootBone"] = rename[sidecar["rootBone"]]
    report = sidecar.get("sourceRigRemap")
    if isinstance(report, dict) and isinstance(report.get("bones"), dict):
        for key, value in list(report["bones"].items()):
            if value in rename:
                report["bones"][key] = rename[value]
    return len(rename)


def _placeholder_names(sidecar):
    return [
        str(item.get("name")) for item in sidecar.get("bones") or []
        if _HASH_BONE_NAME.fullmatch(str(item.get("name") or ""))
    ]


def _reorder_smr_bones(env, renderer_name, bone_names, root_name):
    """把模板 prefab 的 SkinnedMeshRenderer.m_Bones 按 sidecar 骨序重排。

    模板 prefab 骨序 = 游戏 weightedIndex 序；P1 的 sidecar/mesh boneWeights = 拓扑序
    (父在子前，插件强制)。两者同骨不同序 → 插件无损嫁接逐位比名字会失配、跳过换网格。
    骨 Transform 都在 prefab 里，这里只按名字做一次置换，让 prefab 骨序 == sidecar ==
    mesh boneWeights，三者对齐。"""
    objs, target = _template_renderer(env, renderer_name)

    tree = _read_tree(target)
    by_name = {}
    for pptr in tree.get("m_Bones") or []:
        name = _bone_name(objs, pptr)
        if name and name not in by_name:
            by_name[name] = pptr
    # New/decoration bones (in sidecar, absent from the base body template) do NOT get
    # embedded as synthesized Transforms — Unity 6 native LoadAsset crashes on UnityPy-
    # added objects. The runtime graft (ModRuntime BuildHybridBoneArray) builds the real
    # skeleton from the sidecar JSON by name/order and creates the missing bones live, so
    # the carrier SMR only needs a valid pptr per slot. Point missing slots at the root
    # bone; the graft overwrites the whole bone array anyway.
    fallback = by_name.get(root_name) or next(iter(by_name.values()), None)
    if fallback is None:
        raise ValueError("template prefab 没有可用骨 Transform，无法构建 m_Bones")
    tree["m_Bones"] = [by_name.get(name, fallback) for name in bone_names]
    if root_name and root_name in by_name:
        tree["m_RootBone"] = by_name[root_name]
    target.save_typetree(tree)
    target._gmi_typetree = tree


def _object_by_container(env):
    bundle_object = next(o for o in env.objects if o.type.name == "AssetBundle")
    bundle_tree = bundle_object.read_typetree()
    objects = {o.path_id: o for o in env.objects}
    entries = []
    for path, value in bundle_tree["m_Container"]:
        entries.append((_asset(path), objects[value["asset"]["m_PathID"]]))
    return bundle_object, bundle_tree, entries


def _template_manifest(entries):
    for path, obj in entries:
        if not path.endswith("/mod.json") or obj.type.name != "TextAsset":
            continue
        return json.loads(obj.read().text)
    return None


def _asset_map(entries, old_manifest, new_manifest, geo: Path, replacement: dict):
    old_rep = _replacement(old_manifest) if old_manifest else {}
    old_root = _asset(Path(old_rep.get("asset") or "Assets/Mods/template").parent.as_posix())
    new_root = _asset(Path(replacement["asset"]).parent.as_posix())
    mapping = {}
    for old_path, _obj in entries:
        if old_path.startswith(old_root + "/"):
            mapping[old_path] = new_root + "/" + old_path.rsplit("/", 1)[-1]

    def pair(old_path, new_path):
        if old_path and new_path:
            mapping[_asset(old_path)] = _asset(new_path)

    if old_rep:
        pair(old_rep.get("asset"), replacement.get("asset"))
        pair(old_rep.get("skeleton"), replacement.get("skeleton"))
        old_textures = old_rep.get("textures") or []
        new_textures = replacement.get("textures") or []
        new_by_key = {_tex_key(item): item
                      for item in new_textures}
        for item in old_textures:
            key = _tex_key(item)
            target = new_by_key.get(key)
            if target:
                pair(item.get("asset"), target.get("asset"))

    for old_path, _obj in entries:
        if old_path.endswith(".geojson.txt"):
            pair(old_path, new_root + "/" + geo.name)
        elif old_path.endswith("_mesh.asset"):
            pair(old_path, new_root + "/" + (replacement["source"] + "_mesh.asset"))

    old_rules = _renderer_rules(old_rep) if old_rep else []
    new_rules = _renderer_rules(replacement)
    for old_rule in old_rules:
        old_key = old_rule.get("targetRenderer") or old_rule.get("renderer") or old_rule.get("rendererId") or ""
        new_rule = next((rule for rule in new_rules
                         if (rule.get("targetRenderer") or rule.get("renderer") or rule.get("rendererId") or "") == old_key), None)
        if new_rule is None:
            continue
        old_source = old_rule.get("source") or old_rep.get("source") or ""
        new_source = new_rule.get("source") or replacement.get("source") or ""
        if old_source and new_source:
            pair(old_root + "/" + old_source + ".geojson.txt", new_root + "/" + new_source + ".geojson.txt")
            pair(old_root + "/" + old_source + "_mesh.asset", new_root + "/" + new_source + "_mesh.asset")
        pair(old_rule.get("skeleton") or old_rep.get("skeleton"),
             new_rule.get("skeleton") or replacement.get("skeleton"))
    return mapping


def patch_bundle(template: Path, mod_root: Path, output: Path) -> None:
    manifest_path = mod_root / "mod.json"
    manifest = _json(manifest_path)
    replacement = _replacement(manifest)
    renderer_inputs = _renderer_inputs(mod_root, replacement)
    geo_path = renderer_inputs[0]["geo"]

    env = UnityPy.load(str(template))
    bundle_object, bundle_tree, entries = _object_by_container(env)
    old_manifest = _template_manifest(entries)
    mapping = _asset_map(entries, old_manifest, manifest, geo_path, replacement)

    for item in renderer_inputs:
        geo = _json(item["geo"])
        rule = item["rule"]
        target_renderer = rule.get("targetRenderer") or rule.get("modRenderer") or ""
        mesh_names = {f"{item['source']}_mesh", geo.get("m_Name"), item["source"]}
        mesh_paths = {f"{item['source']}_mesh.asset"}
        if target_renderer:
            mesh_names.add(f"{item['source']}__{target_renderer}_mesh")
            mesh_paths.add(f"{item['source']}__{target_renderer}_mesh.asset")
        mesh_object = next((obj for path, obj in entries
                            if obj.type.name == "Mesh"
                            and (path.rsplit("/", 1)[-1] in mesh_paths
                                 or getattr(obj.read(), "m_Name", "") in mesh_names)), None)
        if mesh_object is None:
            raise ValueError(f"template Mesh not found: {sorted(name for name in mesh_names if name)}")
        renderer_name = rule.get("modRenderer") or rule.get("targetRenderer") or item["source"]
        sidecar = _json(item["bones"])
        hash_to_name = _template_bone_hash_map(
            env, renderer_name, geo.get("m_BoneNameHashes")
        )
        resolved = _resolve_hash_bone_names(sidecar, hash_to_name)
        item["_sidecar"] = sidecar
        _patch_mesh(mesh_object, geo, allow_bindpose_growth=True)
        _reorder_smr_bones(env, renderer_name,
                           [bone["name"] for bone in sidecar.get("bones") or []],
                           sidecar.get("rootBone", ""))

    new_root = _asset(Path(replacement.get("asset", "")).parent.as_posix())
    input_text = {_asset(new_root + "/mod.json"): manifest_path.read_text(encoding="utf-8")}
    for item in renderer_inputs:
        input_text[_asset(new_root + "/" + item["geo"].name)] = item["geo"].read_text(encoding="utf-8")
        sidecar = item.get("_sidecar") or _json(item["bones"])
        input_text[_asset(item["skeleton"])] = json.dumps(
            sidecar, ensure_ascii=False, indent=2
        )
    for old_path, obj in entries:
        target_path = mapping.get(old_path)
        if obj.type.name == "TextAsset" and target_path in input_text:
            text_asset = obj.read()
            text_asset.text = input_text[target_path]
            text_asset.save()

    old_textures = {path: obj for path, obj in entries if obj.type.name == "Texture2D"}
    texture_items = replacement.get("textures") or []
    old_rep = _replacement(old_manifest) if old_manifest else {}
    old_by_key = {_tex_key(item): item
                  for item in old_rep.get("textures", [])}
    for item in texture_items:
        key = _tex_key(item)
        old_item = old_by_key.get(key)
        old_path = _asset(old_item["asset"]) if old_item else None
        texture_object = old_textures.get(old_path) if old_path else None
        if texture_object is None:
            raise ValueError(f"template texture not found for {key}")
        image_path = mod_root / Path(item["asset"]).name
        with Image.open(image_path) as image:
            image = image.convert("RGBA")
            texture = texture_object.read_typetree()
            target_format = TextureFormat(int(texture["m_TextureFormat"]))
            image_data, output_format = Texture2DConverter.image_to_texture2d(image, target_format)
            texture["m_Name"] = image_path.stem
            texture["m_Width"], texture["m_Height"] = image.size
            texture["m_CompleteImageSize"] = len(image_data)
            texture["m_TextureFormat"] = int(output_format.value)
            texture["m_MipCount"] = 1
            texture["image data"] = image_data
            texture["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
            texture_object.save_typetree(texture)

    bundle_tree["m_Container"] = [
        (mapping.get(path, path), value) for path, value in bundle_tree["m_Container"]
    ]
    bundle_tree["m_AssetBundleName"] = replacement.get("bundle", bundle_tree.get("m_AssetBundleName", ""))
    bundle_object.save_typetree(bundle_tree)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(env.file.save("original"))


def main(argv: list[str] | None = None) -> None:
    # argv 可传：插件在 Blender 自带 Python 里直接 import 这个模块调 main()，不起子进程
    # （UnityPy 的 wheel 随插件一起装，见 tools/package_blender_addon.py --with-unitypy）。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--mod-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    patch_bundle(args.template, args.mod_root, args.output)
    print(f"patched {args.output}")


if __name__ == "__main__":
    main()
