"""一键打包的接线契约:算子硬编码的 CLI flag 必须仍被 patch 脚本接受,且打包脚本
必须仍把 patch 脚本 vendor 进 addon。三者任一漂移,一键打包就静默断裂。

纯文本级检查——不 import operators(它 import bpy,pytest 环境没有)。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _flags(text):
    return set(re.findall(r'"(--[a-z-]+)"', text))


def test_operator_flags_are_accepted_by_patch_script():
    ops = (ROOT / "gakumas_mi" / "operators.py").read_text(encoding="utf-8")
    patch = (ROOT / "tools" / "patch_unity_bundle.py").read_text(encoding="utf-8")
    # 算子在 _run_bundle_patch 里传的三个 flag
    passed = {"--template", "--mod-root", "--output"}
    assert passed <= _flags(ops), "operators.py 不再传这些 flag，改了要同步"
    accepted = _flags(patch)
    missing = passed - accepted
    assert not missing, f"patch_unity_bundle.py 不再接受: {missing}"


def test_packaging_vendors_patch_script():
    pkg = (ROOT / "tools" / "package_blender_addon.py").read_text(encoding="utf-8")
    assert "patch_unity_bundle.py" in pkg, "打包脚本不再 vendor patch 脚本，一键打包在装好的插件里会找不到它"


if __name__ == "__main__":
    test_operator_flags_are_accepted_by_patch_script()
    test_packaging_vendors_patch_script()
    print("ok")
