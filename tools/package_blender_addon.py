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
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "gakumas_mi"
PROFILE_DIR = ROOT / "profiles"
DIST_DIR = ROOT / "dist"

_IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _read_version() -> str:
    init_py = ADDON_DIR / "__init__.py"
    text = init_py.read_text(encoding="utf-8")
    match = re.search(r'"version"\s*:\s*\(([^)]*)\)', text)
    if not match:
        return "0.0.0"
    nums = [part.strip() for part in match.group(1).split(",") if part.strip()]
    return ".".join(nums)


def _keep(path: Path) -> bool:
    return (
        path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in _IGNORED_SUFFIXES
    )


def _iter_files(root: Path):
    """git-tracked files under root only.

    Packaging must mirror a clean checkout (what the release CI ships), so local
    gitignored working data — e.g. profiles/*/Buffers/*.buf, Reference/Geo_Body*.json,
    the multi-GB Body JSON library — never leaks into the zip. Without this a local
    build ballooned to 35 MB vs the CI build's ~90 KB.
    """
    rel_root = root.relative_to(ROOT).as_posix()
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", rel_root],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    for rel in out.split("\0"):
        if not rel:
            continue
        path = ROOT / rel
        if _keep(path):
            yield path


def _iter_glob(root: Path):
    """Every file under root regardless of git status (for --with-body-lib, whose
    Body JSON library is intentionally gitignored)."""
    for path in sorted(root.rglob("*")):
        if _keep(path):
            yield path


def package(output: Path | None = None, include_body_lib: bool = False) -> Path:
    if not ADDON_DIR.is_dir():
        raise FileNotFoundError(f"找不到插件目录：{ADDON_DIR}")

    # Body JSON 资源库默认作为单独资源包发布，不打进插件 zip（513 套约数 GB）。
    # 它本身 gitignored，_iter_files（只取 git 跟踪）天然排除；--with-body-lib 时显式加。
    body_lib = ADDON_DIR / "resources" / "assetstudio-body-json"
    if include_body_lib and not body_lib.is_dir():
        raise FileNotFoundError(
            f"指定了 --with-body-lib，但找不到内置 Body JSON资源库：{body_lib}"
        )

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
    def _add(path: Path, arcname: Path) -> None:
        nonlocal file_count, total_bytes
        zf.write(path, arcname.as_posix())
        file_count += 1
        total_bytes += path.stat().st_size

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in _iter_files(ADDON_DIR):
            _add(path, Path("gakumas_mi") / path.relative_to(ADDON_DIR))
        # vendor 模板补丁脚本进 addon：一键打包时插件 subprocess 调它（跑在作者的外部
        # Python 上，不是 Blender 自带 Python）。单一 git 源在 tools/，此处只做打包拷贝。
        patch_script = ROOT / "tools" / "patch_unity_bundle.py"
        if patch_script.is_file():
            _add(patch_script, Path("gakumas_mi") / "patch_unity_bundle.py")
        if PROFILE_DIR.is_dir():
            for path in _iter_files(PROFILE_DIR):
                _add(path, Path("gakumas_mi") / "profiles" / path.relative_to(PROFILE_DIR))
        if include_body_lib:
            for path in _iter_glob(body_lib):
                _add(path, Path("gakumas_mi") / path.relative_to(ADDON_DIR))

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
