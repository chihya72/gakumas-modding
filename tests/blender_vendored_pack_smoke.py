"""批次 4 验收：装好的插件**自带打包器**，在 Blender 里直接把 bundle 打出来。

作者侧不该再要求装 Python / 装 UnityPy / 配 PATH。Blender 自带的就是标准 CPython
（4.2 与 4.5 都是 3.11），所以 PyPI 的 cp311 wheel 直接能用，随插件 zip 一起装即可。

判据不是"跑通了"，是**产物内容与已发布的那份 bundle 一致**（容器字节会因 lz4 版本不同而不同，
所以比对象不比字节）：网格几何 / bindpose / 蒙皮、sidecar 文本、贴图尺寸格式、renderer 骨数。

跑法（需要资源库里的模板和一份已发布的 mod，CI 上没有这两样，会自动跳过）：
  blender --background --factory-startup --python-exit-code 1 \
      --python tests/blender_vendored_pack_smoke.py -- <addon-with-vendor.zip>
"""
import hashlib
import sys
import tempfile
from pathlib import Path

import bpy

WORKSPACE = Path(r"D:/GIT/gakumas-modding/mod-workspace")
TEMPLATE = WORKSPACE / "libraries" / "templates" / "template_mdl_chr_atbm-cstm-0140_body.bundle"
RELEASED = WORKSPACE / "mods" / "release" / "chisaki-swimsuit"

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
assert len(args) == 1, "usage: ... --python tests/blender_vendored_pack_smoke.py -- <addon.zip>"
archive = Path(args[0]).resolve()
assert archive.is_file(), archive

if not TEMPLATE.is_file() or not (RELEASED / "bundle-src" / "mod.json").is_file():
    print("GMI_VENDORED_PACK_SKIPPED 本机没有模板或已发布的 mod，跳过")
    raise SystemExit(0)

assert bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True) == {"FINISHED"}
assert bpy.ops.preferences.addon_enable(module="gakumas_mi") == {"FINISHED"}
import gakumas_mi                                                    # noqa: E402
from gakumas_mi import operators                                     # noqa: E402

installed = Path(gakumas_mi.__file__).resolve().parent
version = operators.vendored_unitypy()
assert version, f"装好的插件里没有可用的自带打包器（{installed / 'vendor'}）"
print(f"  自带 UnityPy {version}（{installed / 'vendor'}）")


def digest(path):
    """按对象比内容。容器字节不比 —— 不同 lz4 版本压出来的大小本来就不一样。"""
    import UnityPy
    result = {}
    for obj in UnityPy.load(str(path)).objects:
        data = obj.read()
        key = f"{obj.type.name}/{getattr(data, 'name', '') or obj.type.name}"
        if obj.type.name == "Mesh":
            blob = hashlib.sha256(
                (",".join(f"{value:.5f}" for value in (data.m_Vertices or []))
                 + "|" + ",".join(str(value) for value in (data.m_Indices or []))
                 + "|" + str(len(data.m_BindPose or []))
                 + "|" + str(len(data.m_Skin or []))).encode()).hexdigest()[:16]
            result[key] = f"geo={blob}"
        elif obj.type.name == "TextAsset":
            text = data.text if isinstance(data.text, str) else str(data.text)
            result[key] = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]
        elif obj.type.name == "Texture2D":
            result[key] = f"{data.m_Width}x{data.m_Height}/{int(data.m_TextureFormat)}"
        elif obj.type.name == "SkinnedMeshRenderer":
            result[key] = f"bones={len(data.m_Bones or [])}"
    return result


with tempfile.TemporaryDirectory(prefix="gmi-vendored-pack-") as tmp:
    output = Path(tmp) / "out.bundle"
    scene = bpy.context.scene
    scene.gmi_bundle_template = str(TEMPLATE)
    scene.gmi_bundle_python = "definitely-not-a-python"   # 自带打包器时这一栏不该被用到
    operators._run_bundle_patch(scene, RELEASED / "bundle-src", output)
    assert output.is_file() and output.stat().st_size > 1_000_000, output

    ours, shipped = digest(output), digest(RELEASED / "chisaki-swimsuit.bundle")
    assert set(ours) == set(shipped), sorted(set(ours) ^ set(shipped))
    different = {key: (ours[key], shipped[key]) for key in ours if ours[key] != shipped[key]}
    assert not different, different
    print(f"GMI_VENDORED_PACK_OK {bpy.app.version_string} "
          f"{len(ours)} 个对象与已发布的 bundle 逐项一致；产物 "
          f"{output.stat().st_size / 1024 / 1024:.1f} MiB")
