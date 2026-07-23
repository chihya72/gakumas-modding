"""Upgrade template bundle meshes from 16-bit (R16) to 32-bit (R32) index format.

R16 index buffers cap an in-place patched mesh at 65535 vertices, so
tools/patch_unity_bundle.py (2B) rejects high-poly mods against R16 templates.
Upgrading the template's Mesh to R32 lifts that cap. 2B already honours whatever
index format the template carries, so no change to 2B is needed.

Only the index buffer changes: vertices, bindpose, textures, skeleton stay put.
Idempotent — meshes already R32 are skipped. In-place by default.

    # 模板现在就地留在 Unity 输出目录（构建脚本已让新模板恒 R32）；
    # 本工具用于补救存量/外来的 R16 模板：
    python tools/upgrade_template_r32.py <AssetBundles/Windows 目录>   # whole dir
    python tools/upgrade_template_r32.py path/to/one.bundle
    python tools/upgrade_template_r32.py <目录> --dry-run             # report only

ponytail: patch existing bundles, don't rebuild 908 from Unity.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import UnityPy


def _triangles(raw: bytes, width: int, submeshes) -> list:
    """Decode each submesh's index run at its byte offset — used to prove the
    R16->R32 rewrite preserves geometry."""
    fmt = "H" if width == 2 else "I"
    out = []
    for sub in submeshes:
        first_byte = int(sub.get("firstByte", 0))
        count = int(sub.get("indexCount", 0))
        out.append(struct.unpack_from(f"<{count}{fmt}", raw, first_byte))
    return out


def _upgrade_mesh_tree(tree: dict) -> bool:
    """Return True if the mesh was R16 and got rewritten to R32."""
    if int(tree.get("m_IndexFormat", 0)) != 0:
        return False  # already R32 (1), leave alone

    raw16 = bytes(tree["m_IndexBuffer"])
    submeshes = tree.get("m_SubMeshes") or []
    before = _triangles(raw16, 2, submeshes)

    count = len(raw16) // 2
    indices = struct.unpack(f"<{count}H", raw16[: count * 2])
    tree["m_IndexBuffer"] = struct.pack(f"<{count}I", *indices)
    tree["m_IndexFormat"] = 1
    for sub in submeshes:
        sub["firstByte"] = int(sub.get("firstByte", 0)) * 2  # 2-byte -> 4-byte offsets

    after = _triangles(bytes(tree["m_IndexBuffer"]), 4, submeshes)
    if before != after:
        raise AssertionError("R16->R32 rewrite changed triangle indices")
    return True


def upgrade_bundle(path: Path, dry_run: bool) -> int:
    env = UnityPy.load(str(path))
    changed = 0
    for obj in env.objects:
        if obj.type.name != "Mesh":
            continue
        tree = obj.read_typetree()
        if _upgrade_mesh_tree(tree):
            changed += 1
            if not dry_run:
                obj.save_typetree(tree)
            n_idx = len(bytes(tree["m_IndexBuffer"])) // 4
            print(f"  {path.name}: {tree.get('m_Name', '?')} R16->R32 ({n_idx} indices)")
    if changed and not dry_run:
        path.write_bytes(env.file.save("original"))
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="a .bundle file or a directory of them")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    files = sorted(args.target.glob("*.bundle")) if args.target.is_dir() else [args.target]
    if not files:
        raise SystemExit(f"no .bundle found at {args.target}")

    touched_files = touched_meshes = 0
    for bundle in files:
        n = upgrade_bundle(bundle, args.dry_run)
        if n:
            touched_files += 1
            touched_meshes += n
    verb = "would upgrade" if args.dry_run else "upgraded"
    print(f"{verb} {touched_meshes} mesh(es) across {touched_files}/{len(files)} bundle(s)")


if __name__ == "__main__":
    main()
