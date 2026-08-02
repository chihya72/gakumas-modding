"""Build the Phase 3 body/hair template bundles in Unity-sized batches."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BODY_JSON = ROOT.parent / "mod-workspace" / "libraries" / "assetstudio-body-json"
HAIR_JSON = ROOT.parent / "mod-workspace" / "libraries" / "assetstudio-hair-json"
DEFAULT_UNITY_PROJECT = ROOT.parent / "mod-workspace" / "pipelines" / "ip" / "unity-template-builder"
DEFAULT_TEMPLATE_LIBRARY = ROOT.parent / "mod-workspace" / "templates" / "unity"
TEXTURE_ROOT = ROOT / ".local" / "p3-textures"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def safe_remove(path: Path, parent: Path) -> None:
    target = path.resolve()
    root = parent.resolve()
    if target == root or root not in target.parents:
        raise RuntimeError(f"refusing to remove outside generated root: {target}")
    if target.exists():
        shutil.rmtree(target)


def unlink_with_retry(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def cleanup_unity_work(unity_project: Path, clean_project_cache: bool) -> None:
    stage_root = unity_project / "Assets" / "Mods" / "p3_templates"
    if stage_root.exists():
        safe_remove(stage_root, unity_project / "Assets" / "Mods")
    stage_meta = stage_root.with_name(stage_root.name + ".meta")
    if stage_meta.is_file():
        stage_meta.unlink()
    mods_root = stage_root.parent
    if mods_root.is_dir() and not any(mods_root.iterdir()):
        mods_root.rmdir()
        mods_meta = mods_root.with_name(mods_root.name + ".meta")
        if mods_meta.is_file():
            mods_meta.unlink()
    generated_names = ["GakumasTemplateBuild"]
    if clean_project_cache:
        generated_names.extend(("Library", "Logs", "Temp", "UserSettings"))
    for name in generated_names:
        path = unity_project / name
        if path.exists():
            safe_remove(path, unity_project)


def mesh_path(directory: Path, name: str) -> Path:
    exact = directory / f"{name}.json"
    if exact.is_file():
        return exact
    matches = [p for p in directory.iterdir() if p.is_file() and p.name.lower() == f"{name}.json".lower()]
    if len(matches) != 1:
        raise FileNotFoundError(f"missing unique {name}.json in {directory}")
    return matches[0]


def skeleton_path(directory: Path, name: str) -> Path | None:
    exact = directory / f"{name}.skeleton.json"
    if exact.is_file():
        return exact
    matches = [p for p in directory.iterdir() if p.is_file() and p.name.lower() == f"{name}.skeleton.json".lower()]
    return matches[0] if len(matches) == 1 else None


def skeleton_name_template(root: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        for sidecar in directory.glob("*.skeleton.json"):
            try:
                data = read_json(sidecar)
            except Exception:
                continue
            for node in data.get("nodes") or []:
                name = str(node.get("name") or "")
                if (node.get("boneNameHash") is None or not name
                        or re.fullmatch(r"bone_-?\d+", name, re.IGNORECASE)):
                    continue
                result.setdefault(int(node["boneNameHash"]), name)
    return result


def bones_from_mesh(mesh: dict, sidecar: dict | None, names: dict[int, str]) -> dict:
    bindposes = mesh.get("m_BindPose") or []
    count = len(bindposes)
    nodes = (sidecar or {}).get("nodes") or []
    by_weight = {
        int(node["weightedIndex"]): node
        for node in nodes
        if node.get("weightedIndex") is not None
    }
    hashes = mesh.get("m_BoneNameHashes") or []
    weighted = []
    for index in range(count):
        bone_hash = int(hashes[index]) if index < len(hashes) else index
        node = by_weight.get(index) or {}
        # A hair-prop renderer may omit its own skeleton sidecar.  Do not reuse
        # the primary renderer's node merely because its weightedIndex matches:
        # the two renderer meshes can have different hash orders.
        if node.get("boneNameHash") is not None and int(node["boneNameHash"]) != bone_hash:
            node = {}
        node_name = str(node.get("name") or "")
        if re.fullmatch(r"bone_-?\d+", node_name, re.IGNORECASE):
            node_name = ""
        bone_name = node_name or names.get(bone_hash) or f"bone_{bone_hash}"
        weighted.append({"index": index, "name": str(bone_name)})

    root_name = None
    if sidecar:
        root_path_id = sidecar.get("rootBonePathId")
        for node in nodes:
            if root_path_id is not None and node.get("pathId") == root_path_id:
                root_name = node.get("name")
                break
    if not root_name:
        root_name = next((item["name"] for item in weighted if item["name"] == "Hips"), None)
    if not root_name and weighted:
        root_name = weighted[0]["name"]
    return {
        "schemaVersion": 2,
        "boneCount": len(weighted),
        "rootBone": root_name or "Hips",
        "bones": weighted,
    }


def validate_template_bone_names(bones: dict, asset_id: str) -> None:
    """Validate the carrier skeleton without requiring unavailable game names.

    Mesh-only game assets legitimately expose only bone-name hashes.  Since the
    runtime graft builds the live skeleton from the sidecar, the Unity template
    may carry deterministic ``bone_<hash>`` Transform names; rejecting those
    here made the documented 908-template batch impossible to rebuild.
    """
    items = list(bones.get("bones") or [])
    names = [str(item.get("name") or "") for item in items]
    if len(names) != len(set(names)) or any(not name for name in names):
        raise ValueError(f"{asset_id}: 模板骨架含空骨名或重复骨名")


def phase1_geo(mesh: dict) -> dict:
    count = int(mesh.get("m_VertexCount") or 0)
    if count <= 0:
        raise ValueError(f"invalid vertex count: {mesh.get('m_VertexCount')}")
    required = ["m_Vertices", "m_Normals", "m_Tangents", "m_UV0", "m_Indices", "m_Skin", "m_BindPose", "m_SubMeshes"]
    for key in required:
        if key not in mesh:
            raise ValueError(f"{mesh.get('m_Name')} missing {key}")
    colors = mesh.get("m_Colors") or [1.0, 1.0, 1.0, 1.0] * count
    if len(colors) != count * 4:
        raise ValueError(f"{mesh.get('m_Name')} m_Colors length mismatch")
    return {
        "m_VertexCount": count,
        "m_Vertices": mesh["m_Vertices"],
        "m_Normals": mesh["m_Normals"],
        "m_Tangents": mesh["m_Tangents"],
        "m_UV0": mesh["m_UV0"],
        "m_Colors": colors,
        "m_Indices": mesh["m_Indices"],
        "m_Skin": mesh["m_Skin"],
        "m_BindPose": mesh["m_BindPose"],
        "m_BoneNameHashes": mesh.get("m_BoneNameHashes") or [],
        "m_SubMeshes": mesh["m_SubMeshes"],
        "m_Name": mesh.get("m_Name") or "Mesh",
    }


def asset_ids(other: Path) -> list[tuple[str, str, Path, Path]]:
    result = []
    for kind, root, mesh_name in [("body", BODY_JSON, "Geo_Body"), ("hair", HAIR_JSON, "Geo_Hair")]:
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            bundle = other / directory.name
            if not bundle.is_file():
                raise FileNotFoundError(f"missing source bundle: {bundle}")
            result.append((kind, directory.name, directory, bundle))
    return result


def prepare_texture_inputs(items: list[tuple[str, str, Path, Path]], force: bool, assetstudio: Path) -> None:
    if force and TEXTURE_ROOT.exists():
        safe_remove(TEXTURE_ROOT, ROOT / ".local")
    TEXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    links = TEXTURE_ROOT / "bundles"
    links.mkdir(parents=True, exist_ok=True)
    for _kind, asset_id, _directory, bundle in items:
        link = links / asset_id
        if link.exists():
            continue
        try:
            os.link(bundle, link)
        except OSError:
            shutil.copy2(bundle, link)
    marker = TEXTURE_ROOT / ".complete"
    if marker.is_file() and not force:
        return
    command = [
        str(assetstudio), str(links), str(TEXTURE_ROOT),
        "--game", "Normal", "--unity_version", "6000.0.67f1",
        "--types", "Texture2D", "--export_type", "Convert",
        "--group_assets", "None", "--image_format", "Png", "--silent",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (TEXTURE_ROOT / "assetstudio.log").write_text(result.stdout, encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        raise RuntimeError(f"AssetStudio texture export failed: {result.returncode}")
    marker.write_text("complete\n", encoding="ascii")


def texture_candidates(asset_id: str, renderer: str, property_name: str) -> list[Path]:
    stem = asset_id.removeprefix("mdl_chr_")
    if asset_id.endswith("_body"):
        tag = "bdy"
    elif renderer == "Geo_HairProp":
        tag = "hirco"
    else:
        tag = "hir"
    suffix = {"baseColor": "col", "packedMask": "def", "shadeColor": "sdw"}[property_name]
    pattern = re.compile(rf"^t_chr_{re.escape(stem.rsplit('_', 1)[0])}_{tag}_{suffix}(?:_|\.)", re.IGNORECASE)
    return sorted(p for p in TEXTURE_ROOT.glob("*.png") if pattern.search(p.name))


def neutral_texture(path: Path, packed: bool) -> None:
    if path.is_file():
        return
    color = (255, 255, 255, 255) if not packed else (128, 128, 128, 255)
    Image.new("RGBA", (4, 4), color).save(path)


def copy_texture(asset_id: str, renderer: str, property_name: str, destination: Path) -> None:
    candidates = texture_candidates(asset_id, renderer, property_name)
    if candidates:
        shutil.copy2(candidates[0], destination)
    else:
        neutral_texture(destination, property_name == "packedMask")


def stage_item(kind: str, asset_id: str, source_dir: Path, package_dir: Path) -> None:
    mesh_name = "Geo_Body" if kind == "body" else "Geo_Hair"
    mesh = read_json(mesh_path(source_dir, mesh_name))
    templates = skeleton_name_template(BODY_JSON if kind == "body" else HAIR_JSON)
    primary_skeleton = read_json(skeleton_path(source_dir, mesh_name)) if skeleton_path(source_dir, mesh_name) else None
    primary_geo_name = asset_id
    primary_geo_file = package_dir / f"{primary_geo_name}.geojson.txt"
    primary_bones_file = package_dir / f"{primary_geo_name}_bones.json.txt"
    write_json(primary_geo_file, phase1_geo(mesh))
    primary_bones = bones_from_mesh(mesh, primary_skeleton, templates)
    validate_template_bone_names(primary_bones, asset_id)
    write_json(primary_bones_file, primary_bones)

    renderer_specs = [{"renderer": "Geo_Body" if kind == "body" else "Geo_Hair", "source": primary_geo_name, "mesh": mesh}]
    if kind == "hair":
        prop_file = next((p for p in source_dir.iterdir() if p.is_file() and p.name.lower() == "geo_hairprop.json"), None)
        if prop_file is not None:
            prop_mesh = read_json(prop_file)
            prop_source = asset_id + "__Geo_HairProp"
            prop_skeleton_file = next((p for p in source_dir.iterdir() if p.is_file() and p.name.lower() == "geo_hairprop.skeleton.json"), None)
            prop_skeleton = read_json(prop_skeleton_file) if prop_skeleton_file else primary_skeleton
            prop_geo_file = package_dir / f"{prop_source}.geojson.txt"
            prop_bones_file = package_dir / f"{prop_source}_bones.json.txt"
            write_json(prop_geo_file, phase1_geo(prop_mesh))
            prop_bones = bones_from_mesh(prop_mesh, prop_skeleton, templates)
            validate_template_bone_names(prop_bones, prop_source)
            write_json(prop_bones_file, prop_bones)
            renderer_specs.append({"renderer": "Geo_HairProp", "source": prop_source, "mesh": prop_mesh})

    asset_root = f"Assets/Mods/p3_templates/{asset_id}"
    renderers = []
    textures = []
    for spec in renderer_specs:
        renderer = spec["renderer"]
        renderers.append({
            "rendererId": "body" if renderer == "Geo_Body" else "hairprop" if renderer == "Geo_HairProp" else "hair",
            "targetRenderer": renderer,
            "modRenderer": renderer,
            **({"source": spec["source"], "skeleton": f"{asset_root}/{spec['source']}_bones.json.txt"} if spec["source"] != primary_geo_name else {}),
        })
        slot_count = len(spec["mesh"].get("m_SubMeshes") or [])
        for slot in range(slot_count):
            for property_name, suffix in [("baseColor", "t0"), ("packedMask", "t1"), ("shadeColor", "t4")]:
                filename = f"{renderer}_slot{slot}_{suffix}.png"
                copy_texture(asset_id, renderer, property_name, package_dir / filename)
                textures.append({
                    "rendererName": renderer,
                    "materialSlot": slot,
                    "property": property_name,
                    "asset": f"{asset_root}/{filename}",
                    "type": "Texture2D",
                })

    replacement = {
        "source": primary_geo_name,
        "part": kind,
        "priority": 0,
        "bundle": f"template_{asset_id}.bundle",
        "asset": f"{asset_root}/{primary_geo_name}.prefab",
        "skeleton": f"{asset_root}/{primary_geo_name}_bones.json.txt",
        "type": "GameObject",
        "renderers": renderers,
        "replaceMaterials": False,
        "textures": textures,
    }
    write_json(package_dir / "mod.json", {
        "schemaVersion": 2,
        "id": f"p3_{asset_id}",
        "name": f"Phase 3 template {asset_id}",
        "version": "0.1.0",
        "author": "bundle-route Phase 3",
        "priority": 0,
        "enabled": True,
        "replacements": [replacement],
    })


def build_chunk(
    chunk: list[tuple[str, str, Path, Path]],
    index: int,
    total: int,
    timeout: int,
    clear_library: bool,
    unity: Path,
    unity_project: Path,
) -> list[Path]:
    stage_root = unity_project / "Assets" / "Mods" / "p3_templates"
    library_root = unity_project / "Library"
    if clear_library and library_root.exists():
        safe_remove(library_root, unity_project)
    if stage_root.exists():
        safe_remove(stage_root, unity_project / "Assets" / "Mods")
    stage_root.mkdir(parents=True, exist_ok=True)
    list_path = ROOT / ".local" / "p3-mod-list.txt"
    staged = []
    for kind, asset_id, source_dir, _bundle in chunk:
        package_dir = stage_root / asset_id
        package_dir.mkdir(parents=True, exist_ok=True)
        stage_item(kind, asset_id, source_dir, package_dir)
        staged.append(f"Assets/Mods/p3_templates/{asset_id}")
    list_path.write_text("\n".join(staged) + "\n", encoding="utf-8")
    log_path = ROOT / ".local" / f"p3-unity-{index:03d}.log"
    command = [
        str(unity), "-batchmode", "-quit", "-nographics",
        "-projectPath", str(unity_project),
        "-executeMethod", "BuildGakumasTemplateBundles.BuildAllFromArg",
        "-modList", str(list_path), "-logFile", str(log_path),
        "-bundleOutput", str(unity_project / "GakumasTemplateBuild" / "Windows"),
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        log_tail = ""
        if log_path.is_file():
            log_tail = log_path.read_text(encoding="utf-8", errors="ignore")[-4000:]
        if result.returncode != 0:
            print(log_tail or result.stdout[-4000:])
            raise RuntimeError(f"Unity batch {index}/{total} failed: {result.returncode}")
    except subprocess.TimeoutExpired:
        if log_path.is_file():
            print(log_path.read_text(encoding="utf-8", errors="ignore")[-4000:])
        raise
    finally:
        unlink_with_retry(log_path)
    outputs = []
    for _kind, asset_id, _source_dir, _bundle in chunk:
        bundle = unity_project / "GakumasTemplateBuild" / "Windows" / f"template_{asset_id}.bundle"
        if not bundle.is_file():
            raise FileNotFoundError(f"Unity did not produce {bundle}")
        outputs.append(bundle)
    print(f"[{index}/{total}] built {len(outputs)} templates")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--other", type=Path, required=True, help="decrypted asset_bundle/other directory")
    parser.add_argument("--assetstudio", type=Path, help="AssetStudio.CLI.exe; required unless --skip-textures")
    parser.add_argument("--unity", type=Path, required=True, help="Unity executable")
    parser.add_argument("--unity-project", type=Path, default=DEFAULT_UNITY_PROJECT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_TEMPLATE_LIBRARY,
        help="stable template bundle library used by the Blender add-on",
    )
    parser.add_argument("--chunk-size", type=int, default=24)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--kind", choices=("body", "hair"), default="")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--skip-textures", action="store_true")
    parser.add_argument("--force-textures", action="store_true")
    parser.add_argument("--clear-library", action="store_true", help="clear generated Unity Library before each batch")
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="keep p3-textures and Unity generated directories for debugging; default is to clean them",
    )
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if not args.other.is_dir(): raise SystemExit(f"bundle directory not found: {args.other}")
    if not args.skip_textures and (args.assetstudio is None or not args.assetstudio.is_file()):
        raise SystemExit(f"AssetStudio not found: {args.assetstudio}")
    if not args.unity.is_file(): raise SystemExit(f"Unity not found: {args.unity}")
    if not args.unity_project.is_dir(): raise SystemExit(f"Unity project not found: {args.unity_project}")
    unity_project = args.unity_project.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir == unity_project or unity_project in output_dir.parents:
        raise SystemExit("--output-dir must be outside the generated Unity project")
    output_dir.mkdir(parents=True, exist_ok=True)
    items = asset_ids(args.other)
    if args.kind:
        items = [item for item in items if item[0] == args.kind]
    if args.start > 0:
        items = items[args.start:]
    if args.limit > 0: items = items[:args.limit]
    built_sources = []
    outputs = []
    list_path = ROOT / ".local" / "p3-mod-list.txt"
    try:
        if not args.skip_textures:
            prepare_texture_inputs(items, args.force_textures, args.assetstudio)
        chunks = [items[i:i + args.chunk_size] for i in range(0, len(items), args.chunk_size)]
        for index, chunk in enumerate(chunks, 1):
            built_sources.extend(
                build_chunk(
                    chunk,
                    index,
                    len(chunks),
                    args.timeout,
                    args.clear_library,
                    args.unity,
                    unity_project,
                )
            )
        # Do not mutate the stable plug-in library until every Unity batch has
        # completed.  A failed later batch therefore cannot leave mixed
        # generations in templates/unity.
        for source in built_sources:
            target = output_dir / source.name
            temporary = output_dir / f".{source.name}.tmp"
            try:
                shutil.copy2(source, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            outputs.append(target)
    finally:
        if not args.keep_work:
            cleanup_unity_work(
                unity_project,
                clean_project_cache=unity_project == DEFAULT_UNITY_PROJECT.resolve(),
            )
            safe_remove(TEXTURE_ROOT, ROOT / ".local")
            list_path.unlink(missing_ok=True)
    print(f"Phase 3 complete: {len(outputs)} templates -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
