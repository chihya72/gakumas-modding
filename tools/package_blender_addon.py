#!/usr/bin/env python3
"""Package the GakumasMI Blender add-on as an installable zip.

The AssetStudio body JSON library is intentionally ignored by git because it is
derived game data, but local release zips must include it so normal users do not
have to select a separate JSON directory.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "blender_addon" / "gakumas_mi"
DIST_DIR = ROOT / "dist"


def _read_version() -> str:
    init_py = ADDON_DIR / "__init__.py"
    text = init_py.read_text(encoding="utf-8")
    match = re.search(r'"version"\s*:\s*\(([^)]*)\)', text)
    if not match:
        return "0.0.0"
    nums = [part.strip() for part in match.group(1).split(",") if part.strip()]
    return ".".join(nums)


def _iter_files(root: Path, skip_dirs=()):
    ignored_dirs = {"__pycache__"}
    ignored_suffixes = {".pyc", ".pyo"}
    skip = set(skip_dirs)
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in ignored_dirs for part in path.parts):
            continue
        if any(part in skip for part in rel_parts):
            continue
        if path.suffix in ignored_suffixes:
            continue
        yield path


def package(output: Path | None = None, include_body_lib: bool = False) -> Path:
    if not ADDON_DIR.is_dir():
        raise FileNotFoundError(f"找不到插件目录：{ADDON_DIR}")

    # Body JSON 资源库默认作为单独资源包发布，不打进插件 zip（513 套约数 GB）。
    # 需要随插件分发时加 --with-body-lib。
    skip_dirs: tuple[str, ...] = ()
    if include_body_lib:
        body_lib = ADDON_DIR / "resources" / "assetstudio-body-json"
        if not body_lib.is_dir():
            raise FileNotFoundError(
                "指定了 --with-body-lib，但找不到内置 Body JSON资源库："
                f"{body_lib}"
            )
    else:
        skip_dirs = ("assetstudio-body-json",)

    version = _read_version()
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if output is None:
        suffix = "bodylib" if include_body_lib else "code"
        output = DIST_DIR / f"gakumas_mi-{version}-{suffix}-{stamp}.zip"
    else:
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in _iter_files(ADDON_DIR, skip_dirs):
            arcname = Path("gakumas_mi") / path.relative_to(ADDON_DIR)
            zf.write(path, arcname.as_posix())
            file_count += 1
            total_bytes += path.stat().st_size

    print(f"已生成：{output}")
    print(f"文件数：{file_count}")
    print(f"原始大小：{total_bytes / 1024 / 1024:.1f} MiB")
    print(f"压缩大小：{output.stat().st_size / 1024 / 1024:.1f} MiB")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打包 GakumasMI Blender 插件 zip。")
    parser.add_argument("-o", "--output", type=Path, help="输出 zip 路径。默认写入 dist/")
    parser.add_argument("--with-body-lib", action="store_true",
                        help="把内置 Body JSON资源库一并打进 zip（体积很大；默认作为单独资源包发布）")
    args = parser.parse_args(argv)
    package(args.output, include_body_lib=args.with_body_lib)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
