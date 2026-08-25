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
import shutil
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
    gitignored working data — e.g. profiles/*/Reference/Geo_Body*.json,
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


# 打包器随插件走：Blender 自带的就是标准 CPython（4.2 / 4.5 都是 3.11），所以 PyPI 上的
# cp311 wheel 直接能用，不需要自己编。作者因此不用装 Python、不用配 PATH、不用 pip。
#
# 版本**钉死**：`patch_unity_bundle.py` 按 UnityPy 1.10.x 的 API 写（1.25 把 `TextAsset.text`
# 换掉了）。让作者自己 pip install 就是版本轮盘赌，这也正是内置的理由之一。
UNITYPY_PIN = "UnityPy==1.10.18"
VENDOR_REQUIREMENTS = (UNITYPY_PIN, "Pillow")


def vendor_unitypy(python_exe: str, vendor_dir: Path) -> None:
    """用**目标 Blender 自带的 python** 把打包器依赖装进 addon 的 vendor/。

    必须用那一个解释器：wheel 是按 ABI（cp311 / win_amd64）选的，用别的版本装出来的东西
    在 Blender 里 import 不了。`--only-binary` 是故意的 —— 要源码编译就说明这台机器上
    选不到合适的 wheel，那就该直接失败，而不是打出一个装上才炸的 zip。
    """
    if vendor_dir.exists():
        shutil.rmtree(vendor_dir)
    subprocess.run(
        [python_exe, "-m", "pip", "install", "--target", str(vendor_dir),
         "--only-binary", ":all:", "--no-warn-script-location", *VENDOR_REQUIREMENTS],
        check=True,
    )
    if not (vendor_dir / "UnityPy").is_dir() or not (vendor_dir / "PIL").is_dir():
        raise FileNotFoundError(f"vendor 目录里没装出 UnityPy / PIL：{vendor_dir}")


def package(output: Path | None = None, include_body_lib: bool = False,
            vendor_python: str | None = None) -> Path:
    if not ADDON_DIR.is_dir():
        raise FileNotFoundError(f"找不到插件目录：{ADDON_DIR}")

    # Body JSON 资源库默认作为单独资源包发布，不打进插件 zip（513 套约数 GB）。
    # 它本身 gitignored，_iter_files（只取 git 跟踪）天然排除；--with-body-lib 时显式加。
    body_lib = ADDON_DIR / "resources" / "assetstudio-body-json"
    if include_body_lib and not body_lib.is_dir():
        raise FileNotFoundError(
            f"指定了 --with-body-lib，但找不到内置 Body JSON资源库：{body_lib}"
        )

    vendor_dir = ADDON_DIR / "vendor"
    if vendor_python:
        vendor_unitypy(vendor_python, vendor_dir)

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
        addon_files = list(_iter_files(ADDON_DIR))
        for path in addon_files:
            _add(path, Path("gakumas_mi") / path.relative_to(ADDON_DIR))
        # Required runtime data may be locally generated/untracked; it still
        # must ship with the add-on or Blender falls back to the user add-on
        # directory and raises FileNotFoundError.
        # 这些是运行时**无条件读取**的数据文件，缺一个就在作者点导出时炸
        # FileNotFoundError。以前只在"存在时"添加 —— 干净 checkout 或漏 git add 会打出一个
        # "成功"的 ZIP，装上才发现功能没了。缺就直接失败。
        for name in ("bone_remap_presets.json", "swing_presets.json", "driver_presets.json"):
            path = ADDON_DIR / name
            if not path.is_file():
                raise FileNotFoundError(
                    f"缺少必需的数据文件 {name}（{path}）——它由 tools/ 下的扫描脚本生成，"
                    "必须随插件一起打包，且必须入库")
            if path not in addon_files:
                _add(path, Path("gakumas_mi") / name)
        # `__init__.py` 顶层 import 的每个模块都必须真的进 zip。漏一个的表现是**插件整个
        # 装不上**（`ImportError: cannot import name ... from partially initialized module`），
        # 而 `_iter_files` 只收 git 跟踪的文件 —— 忘了 git add 就会打出一个"成功"的 zip。
        # 实际发生过：unity_route.py / topology_map.py 未入库，打出的 zip 一装就报错。
        packaged = {arc for arc in zf.namelist()}
        missing_modules = [
            name for name in re.findall(
                r"^from \. import (.+)$", (ADDON_DIR / "__init__.py").read_text(encoding="utf-8"),
                re.MULTILINE)
            for name in (part.strip() for part in name.split(","))
            if name and f"gakumas_mi/{name}.py" not in packaged
        ]
        if missing_modules:
            raise FileNotFoundError(
                "以下模块被 __init__.py 顶层 import，但没有进 zip："
                + "、".join(f"{name}.py" for name in missing_modules)
                + "。打出去插件会整个装不上。多半是忘了 `git add`（打包只收 git 跟踪的文件）")
        # vendor 模板补丁脚本进 addon：一键打包时插件 subprocess 调它（跑在作者的外部
        # Python 上，不是 Blender 自带 Python）。单一 git 源在 tools/，此处只做打包拷贝。
        patch_script = ROOT / "tools" / "patch_unity_bundle.py"
        if patch_script.is_file():
            _add(patch_script, Path("gakumas_mi") / "patch_unity_bundle.py")
        # 同理 vendor 绑定体检（导出前跑 AB 蒙皮姿势模拟）；它在 Blender 内被 import 执行。
        sanity_script = ROOT / "tools" / "simulate_ab_skinning.py"
        if sanity_script.is_file():
            _add(sanity_script, Path("gakumas_mi") / "simulate_ab_skinning.py")
        if PROFILE_DIR.is_dir():
            for path in _iter_files(PROFILE_DIR):
                if path.name == "extraction-report.json":
                    continue
                _add(path, Path("gakumas_mi") / "profiles" / path.relative_to(PROFILE_DIR))
        if include_body_lib:
            for path in _iter_glob(body_lib):
                _add(path, Path("gakumas_mi") / path.relative_to(ADDON_DIR))
        # 自带打包器（vendor/）：只有这次显式要了才打进去。目录是 gitignored 的，
        # 上一次 --with-unitypy 留在盘上的残留不能悄悄混进"纯代码版"的 zip。
        if vendor_python:
            for path in _iter_glob(vendor_dir):
                _add(path, Path("gakumas_mi") / path.relative_to(ADDON_DIR))
        elif vendor_dir.is_dir():
            print(f"提示：{vendor_dir} 是上次 --with-unitypy 的残留，这次没打进 zip")

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
    parser.add_argument(
        "--with-unitypy", metavar="BLENDER_PYTHON",
        help="把打包器（UnityPy+Pillow 的 wheel）装进 zip，作者就不用装 Python 了。"
             "参数是**目标 Blender 自带的** python.exe，"
             r"例如 C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe"
             "（wheel 按 ABI 选，用别的解释器装出来的在 Blender 里 import 不了）")
    args = parser.parse_args(argv)
    package(args.output, include_body_lib=args.with_body_lib,
            vendor_python=args.with_unitypy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
