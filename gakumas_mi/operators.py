import json
import traceback
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bpy
from bpy.types import Operator


_BUNDLE_PATCH_TIMEOUT_SECONDS = 10 * 60


def _resolve_patch_script():
    """定位 patch_unity_bundle.py：装好的插件里打包脚本把它 vendor 进了 addon 目录；
    开发仓 checkout 里它只在 ../tools。找不到就报错，别静默。"""
    here = Path(__file__).resolve().parent
    for candidate in (here / "patch_unity_bundle.py",
                      here.parent / "tools" / "patch_unity_bundle.py"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 patch_unity_bundle.py（addon 内或 ../tools 均无）")


# mmd_tools 导入会带这两个记账用顶点组,它们不是骨:权重是每顶点 1.0,
# 当成骨会导出报错;若按提示填兜底骨 Hips,整个模型会塌成刚体。直接忽略。
NON_BONE_GROUPS = frozenset({"mmd_edge_scale", "mmd_vertex_order"})

def _is_bone_group(name):
    return bool(name) and not name.startswith("GMI_") and name not in NON_BONE_GROUPS


def _dominant_group_tip_offsets(obj):
    """{骨名: 合成链尾该放的位置（该骨**局部** Unity 坐标）}。

    链尾定义"这一节朝哪儿"，解算就按它把这一段拽过去。以前链尾是硬写的
    `[0, 0, -骨长]`（Blender 骨的局部 -Z + 默认骨长 55mm），而源骨的局部轴是任意的 ——
    实测 chs-sucu：三片前裙板的链尾世界方向是 `(-1,0,0)` 正侧向、左右翅膀一个朝下一个朝上，
    画面上就是裙片整体偏向一侧。源模型自己的链尾在局部 -X（`CenterBackTail5_S_End`
    实测 -0.221m），也不是 -Z —— 所以这个轴不能猜，要按几何定。

    这里把链尾放到该骨**主导顶点的质心**：那是这块几何真正的去向，任何源都成立。
    没有主导顶点（纯配角骨/空骨）就返回不了值，调用方退回旧的骨长兜底。
    """
    armature = next(
        (modifier.object for modifier in obj.modifiers
         if modifier.type == "ARMATURE" and modifier.object), None
    )
    if armature is None:
        return {}
    names = {group.index: group.name for group in obj.vertex_groups}
    sums, counts = {}, {}
    world = obj.matrix_world
    for vertex in obj.data.vertices:
        best_name, best_weight = None, 0.0
        for item in vertex.groups:
            name = names.get(item.group)
            if not _is_bone_group(name) or item.weight <= best_weight:
                continue
            best_name, best_weight = name, item.weight
        if best_name is None:
            continue
        position = world @ vertex.co
        sums[best_name] = sums.get(best_name, Vector((0.0, 0.0, 0.0))) + position
        counts[best_name] = counts.get(best_name, 0) + 1
    offsets = {}
    for name, total in sums.items():
        bone = armature.data.bones.get(name)
        if bone is None:
            continue
        centroid = total / counts[name]
        local = (armature.matrix_world @ bone.matrix_local).inverted() @ centroid
        if local.length < 1e-6:
            continue
        offsets[name] = list(core._to_unity(local))
    return offsets


def _dominant_group_counts(obj):
    """每根骨"主导"多少个顶点（在该顶点上权重最大）。

    判"这块几何属于谁"只能用主导，不能用总权重：实测 `Spine_Bow_L_A0` 在 613 个顶点上有权重
    却一个都不主导 —— 那些顶点属于后裙和大蝴蝶结。把这种纯配角骨当成"持有几何"去改它的
    求解器，改坏的是**别人的形状**，症状离被改的骨很远（2026-08-19 把花边拖出锯齿就是这么来的）。
    """
    names = {group.index: group.name for group in obj.vertex_groups}
    counts = {}
    for vertex in obj.data.vertices:
        best_name, best_weight = None, 0.0
        for item in vertex.groups:
            name = names.get(item.group)
            if not _is_bone_group(name) or item.weight <= best_weight:
                continue
            best_name, best_weight = name, item.weight
        if best_name is not None:
            counts[best_name] = counts.get(best_name, 0) + 1
    return counts

def _weighted_group_mass(obj):
    """每个骨顶点组的权重占比(%),按占比降序返回。"""
    mass, total = {}, 0.0
    names = {group.index: group.name for group in obj.vertex_groups}
    for vertex in obj.data.vertices:
        for item in vertex.groups:
            name = names.get(item.group)
            if item.weight <= 0.0 or not _is_bone_group(name):
                continue
            mass[name] = mass.get(name, 0.0) + item.weight
            total += item.weight
    scale = 100.0 / total if total else 0.0
    return sorted(((name, value * scale) for name, value in mass.items()),
                  key=lambda pair: -pair[1])


def _bind_sanity_report(obj, remap):
    """跑 AB 蒙皮姿势模拟，返回 (失败区, 未测区, 明细) —— 拿不到就返回 None 跳过。

    静止永远看着对（rest 时 `游戏骨·bindpose` = 恒等），所以坏绑定/错权重只有骨头转起来才暴露；
    dress_2219 就是这样一路混到游戏里才炸手指。这里在导出前按游戏骨架摆一次手指，用场景里的
    GMI 参考体（游戏原生身体+原生权重）当已知正确基线做比值。结构性绝对阈值已实测不可用
    （捻骨/`_1` 双链干扰），所以只用这个功能性判据，细节见
    docs/wiki 的「外部模型转换实战规范」§2 步骤 6。
    """
    here = Path(__file__).resolve().parent
    for candidate in (here / "simulate_ab_skinning.py",
                      here.parent / "tools" / "simulate_ab_skinning.py"):
        if candidate.is_file():
            break
    else:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("gmi_ab_sim", candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        _mod, reference, game = module.find_objects()
    except SystemExit:
        return None  # 场景里没有参考体，作者没走带权重参考流程，不拦
    report = module.measure(obj, reference, game, remap)
    failed, unmeasured = [], []
    for region in ("fingers", "forearm"):
        ratio = report.get(region, {}).get("ratio")
        if ratio is None:
            unmeasured.append(region)
        elif ratio > module.FAIL_RATIO:
            failed.append(f"{region} {ratio:.2f}x")
    return failed, unmeasured, report


def vendored_unitypy():
    """插件自带的 UnityPy（随 zip 一起装的 wheel）能 import 就返回它的版本，否则 None。

    Blender 自带的就是标准 CPython（4.2 / 4.5 都是 3.11），所以 PyPI 上的 cp311 wheel 直接能用，
    不需要自己编。装在插件目录的 `vendor/` 下，作者不用装 Python、不用配 PATH、不用 pip。
    版本是**钉死**的：`patch_unity_bundle.py` 按 1.10.x 的 API 写，1.25 把 `TextAsset.text`
    改成别的了，装什么版本靠作者自己撞运气不行。
    """
    vendor = Path(__file__).resolve().parent / "vendor"
    if not vendor.is_dir():
        return None
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    try:
        import UnityPy                                    # noqa: PLC0415
        from PIL import Image                             # noqa: PLC0415,F401
    except Exception:
        return None
    return getattr(UnityPy, "__version__", "unknown")


def _run_bundle_patch_in_process(template, mod_root, output_bundle):
    """在 Blender 自带 Python 里直接跑模板补丁（零子进程、零 PATH）。"""
    import importlib.util
    script = _resolve_patch_script()
    spec = importlib.util.spec_from_file_location("gmi_patch_unity_bundle", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main(["--template", str(template), "--mod-root", str(mod_root),
                 "--output", str(output_bundle)])
    return output_bundle


def _run_bundle_patch(scene, mod_root, output_bundle):
    """把 bundle 源灌进 R32 模板：优先用插件自带的 UnityPy，没有才起外部 Python。"""
    template = bpy.path.abspath(scene.gmi_bundle_template)
    if not template or not Path(template).is_file():
        raise ValueError("请先选择有效的 R32 模板 bundle")
    if vendored_unitypy():
        return _run_bundle_patch_in_process(template, mod_root, output_bundle)
    python_exe = (scene.gmi_bundle_python or "python").strip()
    script = _resolve_patch_script()
    cmd = [python_exe, "-X", "utf8", str(script),
           "--template", template,
           "--mod-root", str(mod_root),
           "--output", str(output_bundle)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_BUNDLE_PATCH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"找不到 Python 可执行文件：{python_exe}\n"
            "在「外部 Python」栏填绝对路径，例如 C:\\Program Files\\Python\\Python312\\python.exe；"
            "查路径：命令行跑 python -c \"import sys;print(sys.executable)\"")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"模板补丁超过 {_BUNDLE_PATCH_TIMEOUT_SECONDS // 60} 分钟，已终止外部 Python；"
            "请检查模板、磁盘空间和补丁输入，确认没有卡死后再试") from exc
    if proc.returncode != 0:
        output = "\n".join(
            stream.strip() for stream in (proc.stdout or "", proc.stderr or "") if stream.strip()
        )
        tail = output.splitlines()[-12:] if output else ["外部 Python 没有输出；请检查 Python 路径和启动权限"]
        # 缺依赖只是众多可能之一。子进程给了真实报错就先亮它，别拿装包提示盖住数据问题。
        missing_module = "ModuleNotFoundError" in output or "ImportError" in output
        hint = (f"外部 Python 缺依赖，装上再试：{python_exe} -m pip install UnityPy Pillow"
                if missing_module else
                "这是模板补丁自己的报错，不是缺依赖；按上面最后一行的异常处理")
        raise RuntimeError(
            f"模板补丁失败（外部 Python：{python_exe}，returncode={proc.returncode}）\n"
            + "\n".join(tail) + f"\n\n{hint}")
    return output_bundle


def _publish_runtime_manifest(mod_root, output_bundle):
    """打包成功后把游戏要读取的 mod.json 放到成品 bundle 同级。"""
    source = Path(mod_root) / "mod.json"
    if not source.is_file():
        raise FileNotFoundError(f"bundle 源缺少 mod.json：{source}")
    destination = Path(output_bundle).parent / "mod.json"
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return destination


def _scene_component_id(scene):
    return scene.gmi_component_id


def _object_component_id(obj, scene=None):
    return str(obj.get("gmi_component_id")) if obj and obj.get("gmi_component_id") else (
        scene.gmi_component_id if scene else "body"
    )


def _author_mesh(context):
    """Return the explicitly chosen author mesh, with active-object fallback for old .blend files."""
    scene = context.scene
    chosen = getattr(scene, "gmi_author_object", None)
    return chosen if chosen is not None else context.active_object


def _scene_texture_path(scene, component_id, semantic):
    if component_id == "hairprop":
        value = getattr(scene, f"gmi_hairprop_{semantic}_file", "")
        if value:
            return value
    return getattr(scene, f"gmi_{semantic}_file", "")


def _png_to_dds(image_path, srgb=True, alpha_override=None):
    """把 PNG/其它图像转成未压缩 RGBA8 的 DDS（DX10 头），返回临时 DDS 路径。

    用 Blender 自带图像 API 读取(无需外部工具);设为 Non-Color，让存储的字节原样
    写入 DDS。t0/t4 原版是 BC7_UNORM_SRGB → srgb=True;t1 PackedMask 原版是
    BC7_UNORM 线性 → 必须 srgb=False,否则 shader 自动 sRGB 解码,阈值被压暗。
    """
    import numpy as np

    image = bpy.data.images.load(image_path, check_existing=False)
    try:
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            raise ValueError(f"无法读取图像尺寸：{image_path}")
        buffer = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(buffer)
        buffer = np.nan_to_num(buffer, nan=0.0, posinf=1.0, neginf=0.0)
        rgba = buffer.reshape(height, width, 4)[::-1]  # Blender 自下而上 → DDS 自上而下
        if alpha_override is not None:
            rgba[..., 3] = max(0.0, min(1.0, float(alpha_override)))
        rgba8 = np.clip(rgba * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
        suffix = "" if srgb else "_unorm"
        output = Path(tempfile.gettempdir()) / f"gmi_{Path(image_path).stem}{suffix}.dds"
        core.write_rgba8_dds(output, width, height, rgba8.tobytes(), srgb=srgb)
        return str(output)
    finally:
        bpy.data.images.remove(image)


def _neutral_material_dds(semantic, component_id="body"):
    """生成临时的中性 t1/t4 DDS，盖掉游戏原版遮罩/阴影对新贴图的干扰。"""
    if semantic == "packedMask":
        # 当前不替换 hair t6 HHL；A=0 屏蔽原图，避免自定义 UV 采到旧高光。
        rgba = core.HAIR_NEUTRAL_PACKED_MASK if component_id in {"hair", "hairprop"} else core.NEUTRAL_PACKED_MASK
    else:
        rgba = core.NEUTRAL_SHADE_COLOR
    output = Path(tempfile.gettempdir()) / f"gmi_neutral_{component_id}_{semantic}.dds"
    core.write_solid_rgba8_dds(output, rgba)
    return str(output)
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import core


# COLOR.b low nibble drives outline extrusion width. 0xFF keeps the neutral
# packed material class from 0.5.9 while restoring full outline width.
GMI_CLOTH_COLOR_RGBA8 = (0, 0, 255, 0)
GMI_CLOTH_COLOR_FLOAT = tuple(channel / 255.0 for channel in GMI_CLOTH_COLOR_RGBA8)


def _load_image_rgba8_top_down(image_path):
    """Load an image through Blender and return top-down RGBA8 plus dimensions."""
    import numpy as np

    image = bpy.data.images.load(image_path, check_existing=False)
    try:
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            raise ValueError(f"无法读取图像尺寸：{image_path}")
        buffer = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(buffer)
        buffer = np.nan_to_num(buffer, nan=0.0, posinf=1.0, neginf=0.0)
        rgba8 = np.clip(
            buffer.reshape(height, width, 4)[::-1] * 255.0 + 0.5, 0, 255
        ).astype(np.uint8)
        return rgba8, width, height
    finally:
        bpy.data.images.remove(image)


def _rgba8_to_mask_channel(rgba8):
    """Convert RGB to a single 8-bit mask channel."""
    import numpy as np

    rgb = rgba8[..., :3].astype(np.float32)
    channel = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return np.clip(channel + 0.5, 0, 255).astype(np.uint8)


def _scene_paths(scene):
    profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
    capture_dir = bpy.path.abspath(scene.gmi_capture_dir) if scene.gmi_capture_dir else None
    output_dir = bpy.path.abspath(scene.gmi_output_dir)
    return profile_dir, capture_dir, output_dir


def _resolve_body_json_library(scene, component_id=None):
    component_id = component_id or _scene_component_id(scene)
    profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
    # 已补全的配置档自带 Reference（真实或合成骨架），优先用它，与资源库解耦。
    if profile_dir:
        ref = core.resolve_profile_reference(profile_dir, component_id)
        if ref:
            scene.gmi_source_mesh_json = ref["meshJson"]
            scene.gmi_skeleton_json = ref["skeletonJson"]
            return ref
    library_dir = bpy.path.abspath(scene.gmi_body_json_library_dir)
    if not library_dir:
        raise ValueError("请先选择网格 JSON 资源库目录")
    result = core.resolve_body_json_resource(profile_dir, library_dir, component_id)
    scene.gmi_source_mesh_json = result["meshJson"]
    scene.gmi_skeleton_json = result.get("skeletonJson") or ""
    return result


def _create_mesh(context, name, data):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(data["vertices"], [], data["faces"])
    mesh.update()
    if data.get("uv0"):
        for layer_name, values in (("UV0", data["uv0"]), ("UV1", data["uv1"])):
            layer = mesh.uv_layers.new(name=layer_name)
            flat = [axis for loop in mesh.loops for axis in values[loop.vertex_index]]
            layer.data.foreach_set("uv", flat)
    if data.get("colors"):
        color = mesh.color_attributes.new(name="COLOR", type="FLOAT_COLOR", domain="POINT")
        color.data.foreach_set("color", [value for rgba in data["colors"] for value in rgba])
    if data.get("tangents"):
        tangent = mesh.attributes.new(name="GMI_TANGENT", type="FLOAT_VECTOR", domain="POINT")
        tangent.data.foreach_set("vector", [v for item in data["tangents"] for v in item[:3]])
        tangent_w = mesh.attributes.new(name="GMI_TANGENT_W", type="FLOAT", domain="POINT")
        tangent_w.data.foreach_set("value", [item[3] for item in data["tangents"]])
    if data.get("normals"):
        normal = mesh.attributes.new(name="GMI_NORMAL", type="FLOAT_VECTOR", domain="POINT")
        normal.data.foreach_set("vector", [v for item in data["normals"] for v in item])
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        if hasattr(mesh, "normals_split_custom_set_from_vertices"):
            mesh.normals_split_custom_set_from_vertices(data["normals"])
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _collection(context, name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        context.scene.collection.children.link(collection)
    return collection


def _link_only_to_collection(obj, collection):
    if obj.name not in collection.objects.keys():
        collection.objects.link(obj)
    for existing in list(obj.users_collection):
        if existing != collection:
            existing.objects.unlink(obj)


def _sync_object_mesh_data(context, obj):
    if not obj or obj.type != "MESH":
        return
    if context.mode != "OBJECT":
        try:
            obj.update_from_editmode()
        except Exception:
            pass
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    obj.data.update()
    context.view_layer.objects.active = obj
    obj.select_set(True)
    context.view_layer.update()
    try:
        context.evaluated_depsgraph_get().update()
    except Exception:
        pass
    removed_uv_layers = _cleanup_invalid_uv_layers(obj.data)
    if removed_uv_layers:
        obj["gmi_removed_invalid_uv_layers"] = json.dumps(removed_uv_layers, separators=(",", ":"))
    return removed_uv_layers


def _bind_pose_matrix(values):
    # AssetStudio JSON stores Unity's column-major fields with translation in M30..M32.
    return Matrix((
        (values["M00"], values["M10"], values["M20"], values["M30"]),
        (values["M01"], values["M11"], values["M21"], values["M31"]),
        (values["M02"], values["M12"], values["M22"], values["M32"]),
        (values["M03"], values["M13"], values["M23"], values["M33"]),
    ))


def _barycentric(point, a, b, c):
    v0, v1, v2 = b - a, c - a, point - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) < 1e-20:
        return (1.0, 0.0, 0.0)
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    return (1.0 - v - w, v, w)


def _vertex_uv(mesh, name):
    layer = mesh.uv_layers.get(name)
    values = [(0.0, 0.0)] * len(mesh.vertices)
    assigned = [False] * len(mesh.vertices)
    if layer:
        for loop in mesh.loops:
            index = loop.vertex_index
            if not assigned[index]:
                values[index] = tuple(layer.data[loop.index].uv)
                assigned[index] = True
    return values


def _uv_layer_stats(layer):
    if layer is None or len(layer.data) <= 0:
        return {"score": 0.0, "seen": 0, "validRatio": 0.0, "coverage": 0.0, "maxAbs": 0.0}
    non_zero = 0
    valid = 0
    lo_u = lo_v = float("inf")
    hi_u = hi_v = float("-inf")
    max_abs = 0.0
    sample_count = min(len(layer.data), 4096)
    step = max(1, len(layer.data) // sample_count)
    seen = 0
    for index in range(0, len(layer.data), step):
        item = layer.data[index]
        uv = item.uv
        u = core._safe_float(uv[0], 0.0)
        v = core._safe_float(uv[1], 0.0)
        max_abs = max(max_abs, abs(u), abs(v))
        if abs(u) > 8.0 or abs(v) > 8.0:
            seen += 1
            continue
        valid += 1
        if abs(u) > 1e-7 or abs(v) > 1e-7:
            non_zero += 1
        lo_u = min(lo_u, u); hi_u = max(hi_u, u)
        lo_v = min(lo_v, v); hi_v = max(hi_v, v)
        seen += 1
    if seen <= 0 or valid <= 0:
        return {"score": 0.0, "seen": seen, "validRatio": 0.0, "coverage": 0.0, "maxAbs": max_abs}
    if valid / seen < 0.95:
        return {
            "score": 0.0, "seen": seen, "validRatio": valid / seen,
            "coverage": 0.0, "maxAbs": max_abs,
        }
    coverage = max(0.0, hi_u - lo_u) + max(0.0, hi_v - lo_v)
    if coverage < 1e-5 or coverage > 16.0:
        return {
            "score": 0.0, "seen": seen, "validRatio": valid / seen,
            "coverage": coverage, "maxAbs": max_abs,
        }
    score = (non_zero / valid) + min(coverage, 4.0)
    return {
        "score": score, "seen": seen, "validRatio": valid / seen,
        "coverage": coverage, "maxAbs": max_abs,
    }


def _uv_layer_score(layer):
    return _uv_layer_stats(layer)["score"]


def _cleanup_invalid_uv_layers(mesh):
    if mesh is None or getattr(mesh, "uv_layers", None) is None:
        return []
    removed = []
    for layer in list(mesh.uv_layers):
        stats = _uv_layer_stats(layer)
        name = layer.name or ""
        # Empty-name UV layers are never created intentionally by this add-on.
        # They also caused first-click exports to read garbage coordinates
        # clamped to fp16 max (65504), so remove them before any export path.
        invalid_empty_name = not name.strip()
        invalid_range = stats["seen"] > 0 and stats["validRatio"] < 0.95 and stats["maxAbs"] > 8.0
        if invalid_empty_name or invalid_range:
            removed.append({
                "name": name,
                "reason": "empty_name" if invalid_empty_name else "out_of_range",
                **stats,
            })
            mesh.uv_layers.remove(layer)
    if removed:
        mesh.update()
    return removed


def _best_uv_layer(mesh, preferred_name=None, fallback=None):
    layers = list(mesh.uv_layers)
    if not layers:
        return None
    preferred = mesh.uv_layers.get(preferred_name) if preferred_name else None
    candidates = []
    if preferred is not None:
        candidates.append(preferred)
    if fallback is not None and fallback not in candidates:
        candidates.append(fallback)
    active = mesh.uv_layers.active
    if active is not None and active not in candidates:
        candidates.append(active)
    for layer in layers:
        if layer not in candidates:
            candidates.append(layer)
    scored = [(layer, _uv_layer_score(layer)) for layer in candidates]
    best, best_score = max(scored, key=lambda item: item[1])
    if preferred is not None and _uv_layer_score(preferred) >= max(0.02, best_score * 0.25):
        return preferred
    if best_score <= 0.02:
        return None
    return best


def _uv_layer_candidates_report(mesh):
    return [
        {
            "name": layer.name,
            "score": _uv_layer_score(layer),
        }
        for layer in mesh.uv_layers
    ]


def _vertex_colors(mesh):
    attribute = mesh.color_attributes.get("COLOR")
    values = [(1.0, 1.0, 1.0, 1.0)] * len(mesh.vertices)
    if not attribute:
        return values
    if attribute.domain == "POINT":
        return [tuple(item.color) for item in attribute.data]
    assigned = [False] * len(mesh.vertices)
    for loop in mesh.loops:
        index = loop.vertex_index
        if not assigned[index]:
            values[index] = tuple(attribute.data[loop.index].color)
            assigned[index] = True
    return values


def _profile_weight_reference(context, component_id=None):
    if component_id is None:
        component_id = _object_component_id(_author_mesh(context), context.scene)
    references = [
        obj for obj in context.scene.objects
        if obj.type == "MESH" and obj.get("gmi_weighted_reference")
        and (component_id is None or obj.get("gmi_component_id") == component_id)
    ]
    if not references:
        raise ValueError("场景里没有带权重参考模型；请先在步骤①点「导入参考模型与骨架」")
    if len(references) > 1:
        raise ValueError("场景中存在多个带权重参考模型，请只保留一个")
    return references[0]


def _source_bone_parents(obj):
    armature = next(
        (modifier.object for modifier in obj.modifiers
         if modifier.type == "ARMATURE" and modifier.object), None
    )
    if not armature:
        return {}
    return {
        bone.name: bone.parent.name if bone.parent else None
        for bone in armature.data.bones
    }


def _source_bone_positions(obj):
    armature = next(
        (modifier.object for modifier in obj.modifiers
         if modifier.type == "ARMATURE" and modifier.object), None
    )
    if not armature:
        return {}
    return {
        bone.name: core._to_unity(armature.matrix_world @ bone.head_local)
        for bone in armature.data.bones
    }


# Blender(Z-up, -Y forward) → Unity(Y-up, Z forward)
C_UNITY = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


def _quaternion_xyzw(quaternion):
    """Unity 的 Quaternion 序列化顺序是 (x,y,z,w)；mathutils 迭代是 (w,x,y,z)。"""
    return [quaternion.x, quaternion.y, quaternion.z, quaternion.w]


def _matrix_json(matrix):
    """按 AssetStudio 的键序写 bindPose：`M<列><行>`，平移落在 M30..M32。

    这是 `_bind_pose_matrix()` 和 `patch_unity_bundle` 读取时用的同一套约定。曾经写成
    `M<行><列>`（转置），游戏原始 156 根骨的 bindPose 来自 Mesh JSON 不受影响，只有插件
    自己新增的源专属骨中招——dress-2219 上表现为胸口/背后蝴蝶结、缎带、鞋花整片炸成黑刺。
    """
    return {
        f"M{column}{row}": float(matrix[row][column])
        for row in range(4) for column in range(4)
    }


def _source_bone_sidecar_records(obj):
    armature = next(
        (modifier.object for modifier in obj.modifiers
         if modifier.type == "ARMATURE" and modifier.object), None
    )
    if not armature:
        return []
    conversion = C_UNITY
    inverse_conversion = conversion.inverted()
    result = []
    for bone in armature.data.bones:
        parent_matrix = bone.parent.matrix_local if bone.parent else Matrix.Identity(4)
        local = parent_matrix.inverted() @ bone.matrix_local
        unity = conversion @ local @ inverse_conversion
        bone_world = armature.matrix_world @ bone.matrix_local
        bind_pose = conversion @ bone_world.inverted() @ obj.matrix_world @ inverse_conversion
        result.append({
            "name": bone.name,
            "localPosition": list(unity.translation),
            # Unity 的 Quaternion 是 (x,y,z,w)，mathutils 迭代出来是 (w,x,y,z)——
            # 直接 list() 会把 w 写到第一位，运行时按 x 读，新骨的朝向整个错掉。
            "localRotation": _quaternion_xyzw(unity.to_quaternion()),
            "localScale": list(unity.to_scale()),
            "length": float(bone.length),
            "bindPose": _matrix_json(bind_pose),
            # 供新骨链根节点按游戏骨架静止姿势重算 local 用（见 _retarget_new_bone_roots）
            "worldMatrix": C_UNITY @ bone_world @ C_UNITY.inverted(),
        })
    return result


# 驱动器系数是从原版量的，而原版链有多长得看**目标那套服装自己的骨架**，不能写死一个数。
# 这里按名字把游戏侧的衣物骨归到驱动器类型上，数出最长的一条链有几节。
_DRIVER_KIND_TOKENS = {"Skirt": ("skirt",), "Frill": ("frill",),
                       "HumanoidSleeve": ("sleeve",)}


def _driver_reference_links(skeleton):
    """{驱动器类型: 原版这类链最长几节} —— 给 core.scale_driver_coefficients 当基准。"""
    nodes = skeleton.get("nodes") or []
    names = [str(node.get("name") or "") for node in nodes]
    parent_of = {}
    for index, node in enumerate(nodes):
        parent = int(node.get("parent", -1))
        parent_of[names[index]] = names[parent] if 0 <= parent < len(names) else None
    result = {}
    for kind, tokens in _DRIVER_KIND_TOKENS.items():
        members = {name for name in names
                   if name.endswith("_S") and any(t in name.lower() for t in tokens)}
        if not members:
            continue
        best = 0
        for name in members:
            depth, current, guard = 1, name, 0
            while parent_of.get(current) in members and guard < 512:
                current = parent_of[current]; depth += 1; guard += 1
            best = max(best, depth)
        result[kind] = best
    return result


def _target_bone_positions(skeleton):
    positions = {}
    for node in skeleton.get("nodes", []):
        bind_pose = node.get("bindPose")
        if node.get("name") and bind_pose:
            positions[node["name"]] = tuple(_bind_pose_matrix(bind_pose).inverted().translation)
    return positions


def _extend_bundle_skeleton(skeleton, bone_map, source_bind, sidecar_report):
    extra = sidecar_report.get("newBones") or []
    if not extra:
        return [], []
    nodes = skeleton.setdefault("nodes", [])
    node_by_name = {str(node.get("name")): index for index, node in enumerate(nodes)}
    next_index = max((int(index) for index in bone_map.values()), default=-1) + 1
    added_nodes, added_bind_poses = [], []
    for item in extra:
        name = str(item.get("name") or "")
        bind_pose = item.get("bindPose")
        if not name or bind_pose is None or name in bone_map:
            continue
        parent_name = str(item.get("parentName") or "Hips")
        parent_index = node_by_name.get(parent_name, node_by_name.get("Hips", -1))
        node = {
            "name": name,
            "parent": parent_index,
            "weightedIndex": next_index,
            "bindPose": bind_pose,
            "localPosition": item.get("localPosition") or [0.0, 0.0, 0.0],
            "localRotation": item.get("localRotation") or [0.0, 0.0, 0.0, 1.0],
            "localScale": item.get("localScale") or [1.0, 1.0, 1.0],
        }
        nodes.append(node)
        node_by_name[name] = len(nodes) - 1
        bone_map[name] = next_index
        source_bind[name] = _bind_pose_matrix(bind_pose).inverted()
        added_nodes.append(node)
        added_bind_poses.append(bind_pose)
        next_index += 1
    return added_nodes, added_bind_poses


def _target_rest_world(skeleton):
    """游戏骨架每根骨的静止世界矩阵（Unity 空间），由 sidecar 的 local 链逐级合成。"""
    nodes = skeleton.get("nodes") or []
    world, result = {}, {}

    def compose(index):
        if index in world:
            return world[index]
        node = nodes[index]
        position = node.get("localPosition") or [0.0, 0.0, 0.0]
        x, y, z, w = node.get("localRotation") or [0.0, 0.0, 0.0, 1.0]
        scale = node.get("localScale") or [1.0, 1.0, 1.0]
        local = Matrix.LocRotScale(Vector(position), Quaternion((w, x, y, z)), Vector(scale))
        parent = int(node.get("parent", -1))
        world[index] = local if parent < 0 else compose(parent) @ local
        return world[index]

    for index, node in enumerate(nodes):
        name = str(node.get("name") or "")
        if name and name not in result:
            result[name] = compose(index)
    return result


def _retarget_new_bone_roots(new_bones, records, skeleton):
    """把挂在游戏骨下的新骨链根，按游戏骨架的静止姿势重算 local 变换。

    作者骨架和游戏骨架的静止姿势并不相同（dress-2219 实测 Hips 差 38mm、Spine 差 83mm）。
    直接沿用作者骨架里的相对变换，运行时会把新骨挂到别的位置，而 bindPose 记的是作者
    世界位置——两边对不上，装饰件就被拉变形（蝴蝶结坍缩成一片）。

    链内部（父也是新骨）不用动：那一段父子都按作者世界摆放，相对关系本来就自洽。
    """
    if not new_bones or not skeleton:
        return 0
    target_world = _target_rest_world(skeleton)
    by_name = {str(item.get("name")): item for item in records if item.get("name")}
    created = {str(item.get("name")) for item in new_bones}
    retargeted = 0
    for item in new_bones:
        parent_name = str(item.get("parentName") or "")
        if parent_name in created:
            continue
        source = by_name.get(str(item.get("name")))
        parent_world = target_world.get(parent_name)
        if source is None or parent_world is None or source.get("worldMatrix") is None:
            continue
        local = parent_world.inverted() @ source["worldMatrix"]
        position, rotation, scale = local.decompose()
        item["localPosition"] = list(position)
        item["localRotation"] = _quaternion_xyzw(rotation)
        item["localScale"] = list(scale)
        retargeted += 1
    return retargeted


def row_bones(item):
    """一行覆盖的源骨。一行 = 一组（`members` 换行分隔），单根骨的行退化成 [source]。"""
    members = [name for name in str(item.members or "").split("\n") if name]
    return members or ([item.source] if item.source else [])


def _row_state(item):
    """一行（= 一组）的五档状态。一组多根骨指同一根目标骨 = 合并，不是 direct。"""
    return core.row_state(item.target, item.strategy,
                          shared_target=len(row_bones(item)) > 1)


def _row_label(item):
    """报错里指得出是哪一组：用组里第一根骨的名字，多根就带个计数。"""
    members = row_bones(item)
    if not members:
        return "(空组)"
    return members[0] if len(members) == 1 else f"{members[0]} 等 {len(members)} 根"


def _form_bone_map(scene):
    """骨骼映射表单里作者填过的行。空目标=不干预,交给自动判断。"""
    return {name: item.target.strip()
            for item in getattr(scene, "gmi_bone_map", ())
            if item.target.strip()
            for name in row_bones(item)}


def _form_physics_overrides(scene):
    """表单里选过装饰物理策略的行(填了目标骨的行不算,那已经是确定映射)。

    `bake` / `reject` 不是物理策略，是五档决定 —— 对下游一律按 `rigid`（并到父骨、无物理）解析。
    不翻译的话它们会掉进"按位置蹭最近摇物骨"那条兜底路径，静态装饰骨反而被绑上物理。
    """
    physical = {"bake": "rigid", "reject": "rigid"}
    return {name: physical.get(item.strategy, item.strategy)
            for item in getattr(scene, "gmi_bone_map", ())
            if item.strategy != "auto" and not item.target.strip()
            for name in row_bones(item)}


def _form_swing_categories(scene):
    """表单里点名过部件类型的行。只对自建摇物链有意义,别的策略不新建骨。"""
    return {name: item.swing_category
            for item in getattr(scene, "gmi_bone_map", ())
            if item.swing_category != "auto"
            and item.strategy == "integrate" and not item.target.strip()
            for name in row_bones(item)}


def _form_swing_anchor_bones(scene):
    """勾了「链根自己摆」的那些行覆盖的骨名。空集 = 全按默认（链根是惰性锚）。"""
    return {name for item in getattr(scene, "gmi_bone_map", ())
            if getattr(item, "swing_anchor", False)
            for name in row_bones(item)}

def _form_driver_bones(scene):
    """{骨名: 部件类型} —— 点名走「原版布料驱动器」的**那几根骨**。

    空 dict = 完全不走这条路径，导出结果与以前逐字节一样。以前这里收的是"类别集合"，
    core 再按类别去套 —— 作者在一行上选了 skirt，全模型每一根 skirt 类别的新骨都跟着改，
    点一条链等于改整件衣服。现在按骨名限定作用域（一行=一组=一条链，正好是作者的本意）。

    只收运行时真的实现了的三类（Skirt / Frill / HumanoidSleeve）。ribbon 没有对应驱动器，
    收进来只会得到"既没驱动器也没摇物"的哑骨 —— 那种静默洞正是这一版要消灭的。
    """
    bones = {}
    for item in getattr(scene, "gmi_bone_map", ()):
        if item.strategy != "native_driver" or item.target.strip():
            continue
        for name in row_bones(item):
            category = (item.swing_category if item.swing_category != "auto"
                        else core.swing_category(name))
            if category in core.DRIVER_CATEGORIES:
                bones[name] = category
    return bones


def _form_driver_gaps(scene):
    """选了「原版布料驱动器」却落在没有驱动器的类别上的行 → [(骨名, 类别)]。

    运行时只实现三类（Skirt / Frill / HumanoidSleeve）；ribbon 没有对应驱动器。这种组合
    导出后那几根骨**既没驱动器也没摇物** = 不会动的哑骨，而日志全绿。宁可导出前拦下，
    也不要静默把它换成摇物 —— 偷偷换求解器等于给作者一个"能动但不是他配的"结果。
    """
    gaps = []
    for item in getattr(scene, "gmi_bone_map", ()):
        if item.strategy != "native_driver" or item.target.strip():
            continue
        for name in row_bones(item):
            category = (item.swing_category if item.swing_category != "auto"
                        else core.swing_category(name))
            if category not in core.DRIVER_CATEGORIES:
                gaps.append((name, category))
    return gaps


def _resolve_source_bone_remap(obj, bone_map, scene, skeleton=None):
    explicit = {}
    if scene.gmi_bone_remap_file:
        remap_data = core.load_json(Path(bpy.path.abspath(scene.gmi_bone_remap_file)))
        explicit = dict(remap_data.get("bones", remap_data))
    # 面板表单比外部 JSON 更"手边",冲突时以表单为准
    explicit.update(_form_bone_map(scene))
    source_names = [
        group.name for group in obj.vertex_groups if _is_bone_group(group.name)
    ]
    report = core.build_bone_remap(
        source_names,
        bone_map,
        parent_by_name=_source_bone_parents(obj),
        preset_name=getattr(scene, "gmi_source_rig", "auto"),
    )
    remap = dict(report["bones"])
    remap.update(explicit)
    if skeleton is not None:
        physics_overrides, override_data = {}, {}
        if getattr(scene, "gmi_physics_override_file", ""):
            override_data = core.load_json(
                Path(bpy.path.abspath(scene.gmi_physics_override_file)))
            physics_overrides = dict(override_data.get("physics", override_data))
        # 同上:面板表单比外部 JSON 更"手边",冲突时以表单为准
        physics_overrides.update(_form_physics_overrides(scene))
        # 作者给了物理策略、又没填目标骨 = 他明确说这根骨不走目标骨。以前这种骨如果**名字**
        # 恰好也在目标骨架里（`build_bone_remap` 的 direct 命中），名字仍然赢，作者的
        # 「自建摇物链」被静默吞掉 —— 违反「作者覆盖 > 内置规则」。实测代价：IP 源的
        # `*Skirt*_S` 与目标服装同名但位置差 221mm，包臀裙会被拉成目标那条裙子的形状。
        # 只认全名（前缀匹配留给 build_accessory_physics_remap 的策略解析，不用来解绑映射）。
        forced_helpers = [name for name, strategy in physics_overrides.items()
                          if name in remap and name not in explicit and strategy != "rigid"]
        for name in forced_helpers:
            remap.pop(name, None)
            report["bones"].pop(name, None)
            report["bodyBones"] = [bone for bone in report["bodyBones"] if bone != name]
            if name not in report["accessoryBones"]:
                report["accessoryBones"].append(name)
        # 分组按结构（锚点+链+链长），不读骨名——外语/乱码骨名下正则剥 left/right 全废。
        parents = _source_bone_parents(obj)
        groups = core.structural_bone_groups(
            report["accessoryBones"], parents, report["bodyBones"])
        physics_report = core.build_accessory_physics_remap(
            [{"name": name, "position": position}
             for name, position in _source_bone_positions(obj).items()],
            [{"name": name, "position": position}
             for name, position in _target_bone_positions(skeleton).items()
             if name in bone_map],
            report["accessoryBones"],
            parent_by_name=parents,
            body_remap=remap,
            group_by_name={name: group["key"]
                           for group in groups for name in group["members"]},
            overrides=physics_overrides,
        )
        remap = core.merge_accessory_bone_remap(
            remap, physics_report["bones"], physics_report["rigidParent"]
        )
        # 部件类型决定摆动参数取原版哪一档、要不要建链；同样表单优先于外部 JSON
        # 部件类型：**先按几何判**（锚点 / 同锚点链数 / 垂向，一个骨名不读），再让外部 JSON
        # 和表单依次覆盖。按名字判只对恰好用本作命名习惯的源有效 —— 原神 rip 的 `Bone_HemA01_L`、
        # MMD 的 `スカート` 词表都不认，整条裙摆会拿到最保守的飘带档（不建链），
        # 环形碰撞和限位全丢。作者显式点过的行永远优先。
        swing_categories = core.geometric_swing_categories(
            physics_report["newBones"], parents, _source_bone_positions(obj), body_remap=remap)
        swing_categories.update(override_data.get("swingCategories") or {})
        swing_categories.update(_form_swing_categories(scene))
        records = _source_bone_sidecar_records(obj)
        # 权重进来是为了「链根扛着几何就让它自己摆」以及闸门①，见 core 里的注释
        report["newBones"] = core.build_source_extra_bones(
            records, physics_report["newBones"],
            parent_by_name=_source_bone_parents(obj), body_remap=remap,
            categories=swing_categories,
            driver_bones=_form_driver_bones(scene),
            weight_by_name=dict(_weighted_group_mass(obj)),
            dominant_by_name=_dominant_group_counts(obj),
            swing_anchor_bones=_form_swing_anchor_bones(scene),
            tip_offset_by_name=_dominant_group_tip_offsets(obj),
            driver_reference_links=_driver_reference_links(skeleton),
        )
        # 新骨链的根挂在游戏骨下，local 必须按游戏骨架的静止姿势重算
        _retarget_new_bone_roots(report["newBones"]["newBones"], records, skeleton)
        # 闸门：点名走原版布料驱动器、却一根都没真的挂上 = 静默退回摇物。build_driver_block
        # 判不出左右或表里没这型驱动器时返回 None，此前只是无声地留着 swing —— 作者选了
        # 驱动器、拿到摇物、日志全绿。实测 192 根 MMD 裙骨一根都没挂上就是这么过去的。
        wanted_drivers = set(_form_driver_bones(scene))
        if wanted_drivers:
            got = {item["name"] for item in report["newBones"]["newBones"]
                   if item.get("driver")}
            missed = sorted(wanted_drivers - got)
            if missed:
                raise ValueError(
                    f"{len(missed)} 根骨点名走「原版布料驱动器」，但一根都没挂上："
                    + "、".join(missed[:12]) + ("…" if len(missed) > 12 else "")
                    + "。它们会静默退回摇物物理 —— 日志全绿、画面却不是你配的那套解算器。"
                      "常见原因：这型驱动器不在 driver_presets.json 里，或者骨的左右判不出来"
                      "（参考骨 Left/RightUpLeg 分左右）。")
        report["physicsInheritance"] = physics_report
    report["explicitBones"] = explicit
    report["bones"] = remap
    report["unmapped"] = [name for name in source_names if name not in remap]
    return remap, report


def _semantic_bone_names(group_names):
    tokens = ("HandThumb", "HandIndex", "HandMiddle", "HandRing", "HandPinky")
    return {name for name in group_names if any(token in name for token in tokens)} | {
        name for name in group_names if name == "Neck"
    }


def _normalize_profile_weights(obj, maximum=4):
    """Limit to the strongest Profile influences and normalize without context operators."""
    groups = {group.index: group for group in obj.vertex_groups}
    truncated_total = 0.0
    zero_vertices = []
    for vertex in obj.data.vertices:
        weighted = sorted(
            ((item.group, float(item.weight)) for item in vertex.groups if item.weight > 0.0),
            key=lambda item: item[1], reverse=True,
        )
        if not weighted:
            zero_vertices.append(vertex.index)
            continue
        kept = weighted[:maximum]
        truncated_total += sum(weight for _, weight in weighted[maximum:])
        total = sum(weight for _, weight in kept)
        for group_index, _ in weighted:
            groups[group_index].remove([vertex.index])
        for group_index, weight in kept:
            groups[group_index].add([vertex.index], weight / total, "REPLACE")
    return zero_vertices, truncated_total


def _vertex_group_indices(obj, name):
    group = obj.vertex_groups.get(name)
    if not group:
        return set()
    return {
        vertex.index
        for vertex in obj.data.vertices
        for item in vertex.groups
        if item.group == group.index and item.weight > 0.0
    }


def _clear_outline_width(color):
    rgba = [core._safe_unorm8(channel) for channel in color]
    # Outline VS decodes the low nibble of COLOR.b as extrusion width.
    rgba[2] &= 0xF0
    return tuple(channel / 255.0 for channel in rgba)


def _black_outline_colors(colors):
    """黑色常量描边:R=0、G高位=0(描边色黑),保留 g低(ramp行)/b(宽度)/a(光照)。"""
    out = []
    for r, g, b, a in colors:
        g8 = core._safe_unorm8(g)
        out.append((0.0, (g8 & 0x0F) / 255.0, b, a))
    return out


def _set_constant_color_attribute(target, color=GMI_CLOTH_COLOR_FLOAT):
    dst = target.data.color_attributes.get("COLOR")
    if dst is not None and dst.domain != "POINT":
        target.data.color_attributes.remove(dst)
        dst = None
    if dst is None:
        dst = target.data.color_attributes.new(name="COLOR", type="FLOAT_COLOR", domain="POINT")
    dst.data.foreach_set("color", [value for _ in target.data.vertices for value in color])
    return True


def _preset_color_float(preset):
    rgba = (preset or {}).get("color", {}).get("rgba", GMI_CLOTH_COLOR_RGBA8)
    if len(rgba) != 4:
        rgba = GMI_CLOTH_COLOR_RGBA8
    return tuple(
        max(0, min(255, int(core._safe_float(channel, 0.0)))) / 255.0
        for channel in rgba
    )


def _material_slot_color_map(obj):
    presets = core.load_material_presets()
    result = {}
    for index, slot in enumerate(obj.material_slots):
        key = getattr(slot.material, "gmi_material_class", "cloth") if slot.material else "cloth"
        result[index] = _preset_color_float(presets.get(key) or presets.get("cloth"))
    return result


def _material_slot_alpha_modes(obj):
    result = {}
    for index, slot in enumerate(obj.material_slots):
        material = slot.material
        if material is None:
            continue
        mode = getattr(material, "gmi_alpha_mode", "OPAQUE")
        # 两条透明路径：原生co(NATIVE_CO)走游戏原生第二材质段(m_bdyco)，只有镂空；
        # GMI_TRANSPARENT 走插件自带的 Gmi/Transparent，是真半透明，由 runtime 新建材质段。
        # 更早的自建镂空/半透明 pass 已移除，旧工程里的那些值统一回退到不透明。
        if mode in {"NATIVE_CO", "NATIVE_SECTION", "CO"}:
            result[index] = "NATIVE_CO"
        elif mode in {"GMI_TRANSPARENT", "ALPHA_BLEND_GMI"}:
            result[index] = "GMI_TRANSPARENT"
    return result


def _load_rgba_sampler(image_path):
    if not image_path:
        return None
    path = bpy.path.abspath(image_path)
    if not path:
        return None
    import numpy as np

    image = bpy.data.images.load(path, check_existing=False)
    try:
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            return None
        buffer = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(buffer)
        buffer = np.nan_to_num(buffer, nan=0.0, posinf=1.0, neginf=0.0)
        # Blender exposes image pixels bottom-to-top; DDS/PIL and GPU UV sampling
        # for the frame dumps are top-to-bottom. Flip here so the native COLOR
        # synthesis sees the same top-to-bottom texel order as DDS/PIL and the GPU frame dump.
        pixels = np.clip(
            buffer.reshape(height, width, 4)[::-1] * 255.0 + 0.5, 0, 255
        ).astype(np.uint8)
    finally:
        bpy.data.images.remove(image)

    def sample(uv):
        u = core._safe_float(uv[0], 0.0) % 1.0
        v = core._safe_float(uv[1], 0.0) % 1.0
        x = min(width - 1, max(0, int(u * width)))
        y = min(height - 1, max(0, int((1.0 - v) * height)))
        r, g, b, a = pixels[y, x]
        return int(r), int(g), int(b), int(a)

    return sample


def _color_feature(uv, rgba):
    r, g, b, _ = rgba or (128, 128, 128, 255)
    luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return (core._safe_float(uv[0], 0.0) * 2.0, core._safe_float(uv[1], 0.0) * 2.0, luma)


def _object_vertex_arrays(obj):
    import numpy as np

    world = obj.matrix_world
    normal_matrix = world.to_3x3().inverted().transposed()
    positions, normals = [], []
    for vertex in obj.data.vertices:
        position = world @ vertex.co
        normal = (normal_matrix @ vertex.normal).normalized()
        positions.append((float(position.x), float(position.y), float(position.z)))
        normals.append((float(normal.x), float(normal.y), float(normal.z)))
    return np.asarray(positions, dtype=np.float32), np.asarray(normals, dtype=np.float32)


def _mesh_triangles(mesh):
    faces = []
    for poly in mesh.polygons:
        vertices = list(poly.vertices)
        if len(vertices) == 3:
            faces.append(vertices)
        elif len(vertices) > 3:
            for index in range(1, len(vertices) - 1):
                faces.append([vertices[0], vertices[index], vertices[index + 1]])
    return faces


def _source_weight_matrix(reference):
    import numpy as np

    groups = list(reference.vertex_groups)
    slots = {group.index: index for index, group in enumerate(groups)}
    weights = np.zeros((len(reference.data.vertices), len(groups)), dtype=np.float64)
    for vertex in reference.data.vertices:
        for item in vertex.groups:
            slot = slots.get(item.group)
            if slot is not None and item.weight > 0.0:
                weights[vertex.index, slot] = float(item.weight)
    return groups, weights


def _write_weight_matrix(target, groups, weights, threshold=1e-8):
    for group in groups:
        target.vertex_groups.new(name=group.name)
    target_groups = list(target.vertex_groups)
    for vertex_index, row in enumerate(weights):
        for group_index, value in enumerate(row):
            if value > threshold:
                target_groups[group_index].add([vertex_index], float(value), "REPLACE")


def _normalize_numpy_vectors(values):
    import numpy as np

    length = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(length, 1e-8)


def _sample_vertex_rgb(sampler, uvs):
    import numpy as np

    if not sampler:
        return np.full((len(uvs), 3), 0.5, dtype=np.float32)
    colors = []
    for uv in uvs:
        r, g, b, _ = sampler(uv)
        colors.append((r / 255.0, g / 255.0, b / 255.0))
    return np.asarray(colors, dtype=np.float32)


def _synthesize_export_native_colors(profile_dir, component_id, data, target_base_color_file, color_per_slot=None):
    import numpy as np

    texture_notes = []
    try:
        tgt_sampler = _load_rgba_sampler(target_base_color_file)
    except Exception as exc:
        tgt_sampler = None
        texture_notes.append(f"target baseColor unavailable: {exc}")
    tgt_uv = np.nan_to_num(np.asarray(data["uv0"], dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    tgt_rgb = _sample_vertex_rgb(tgt_sampler, tgt_uv)

    # 复刻原版描边色:逐顶点把【该点基础色】编码进 COLOR 的 nibble。
    # 实测原版编码系数(saki body draw227, o1=(R高,R低,G高)/15 与基础色相关 0.94/0.77/0.24):
    #   R高4位 ≈ 4.08×baseR, R低4位 ≈ 1.03×baseG, G高4位 ≈ 0.63×baseB
    # 描边 VS 解出 o1≈基础色,×全局常量 → 衣服自身颜色的暗化描边(贴合衣服、不死黑)。
    # ramp行(g低4位)/宽度(b)/光照(a) 仍按材质预设(防色块、对称)。
    # 曲线与暗部塌绿的处理都在 core.outline_nibbles_from_base。
    OUTLINE_GAIN = 1.0   # 整体微调:实机整体偏弱调>1,偏强调<1
    colors = []
    for index in range(len(tgt_uv)):
        r_high, r_low, g_high = core.outline_nibbles_from_base(
            tgt_rgb[index][0], tgt_rgb[index][1], tgt_rgb[index][2], OUTLINE_GAIN
        )
        # 保留 gather 已写好的 ramp行(g低)/宽度(b,已按「描边宽度」处理)/光照(a);只改描边色 R/G高位
        existing = data["colors"][index] if index < len(data["colors"]) else (0.0, 0.0, 1.0, 0.0)
        g8 = core._safe_unorm8(existing[1])
        r_byte = r_high * 16 + r_low
        g_byte = g_high * 16 + (g8 & 0x0F)
        colors.append((r_byte / 255.0, g_byte / 255.0, existing[2], existing[3]))

    return colors, {
        "method": "export_outline_color_from_basecolor",
        "encodeFactors": {"rHigh": 4.08, "rLow": 1.03, "gHigh": 0.63},
        "encodedVertices": len(colors),
        "totalVertices": len(colors),
        "textureNotes": texture_notes,
    }


# 原版 hair 可按顶点/发片改变描边色；任意新拓扑无法可靠复刻区域映射，故安全作者模式使用
# 全网格常量档。描边色 nibble=(R高,R低,G高)/15，宁小勿大，避免暗部量化塌绿。
HAIR_OUTLINE_TIERS = {
    "DARK": (0, 0, 1),
    "PINK": (1, 0, 0),
    "BLONDE": (4, 2, 1),
    "BLACK": (0, 0, 0),
}


def _hair_export_colors(reference, data, tier, outline_width_mode, no_outline_vertices):
    """安全 hair COLOR：写常量描边 RGB，参考拷贝 G低 LUT 行、B低宽度及 A高 rim 等字段。"""
    if reference.data.color_attributes.get("COLOR") is None:
        raise ValueError("参考网格没有 COLOR 属性,无法拷贝 hair 的 LUT 行/描边宽度/rim mask(请重新导入带权重参考模型)")
    ref_colors = _vertex_colors(reference.data)
    tree = KDTree(len(reference.data.vertices))
    for index, vertex in enumerate(reference.data.vertices):
        tree.insert(core._to_unity(reference.matrix_world @ vertex.co), index)
    tree.balance()
    r_high, r_low, g_high = HAIR_OUTLINE_TIERS[tier]
    r_byte = r_high * 16 + r_low
    colors = []
    for index, position in enumerate(data["vertices"]):
        _, nearest, _ = tree.find(position)
        _, ref_g, ref_b, ref_a = ref_colors[nearest]
        b8 = core._safe_unorm8(ref_b)
        if outline_width_mode == "DISABLE_ALL" or data["vertexIndices"][index] in no_outline_vertices:
            b8 &= 0xF0
        colors.append((
            r_byte / 255.0,
            (g_high * 16 + (core._safe_unorm8(ref_g) & 0x0F)) / 255.0,
            b8 / 255.0,
            core._safe_unorm8(ref_a) / 255.0,
        ))
    return colors, {
        "method": "hair_outline_constant_plus_reference_nn",
        "outlineTier": tier,
        "outlineNibbles": [r_high, r_low, g_high],
        "referenceVertices": len(reference.data.vertices),
        "totalVertices": len(colors),
    }


# hairprop 的原版 section/COLOR 可不同；任意新拓扑的安全 fallback 按材质槽写常量：
# metal=(3,3,3)+A高9/15，布件=(0,0,0)+A高0，B低=8。A高控制 rim/backlight，
# B低控制 outline；这里的整字节 144/8 只是所选编码，不是 shader 的二值字段定义。
HAIRPROP_OUTLINE_BY_CLASS = {
    "metal": ((3, 3, 3), 144),
    "skin": ((1, 0, 0), 0),
}
HAIRPROP_OUTLINE_DEFAULT = ((0, 0, 0), 0)
HAIRPROP_OUTLINE_WIDTH = 8


def _hairprop_export_colors(obj, data, outline_width_mode, no_outline_vertices):
    """hairprop 安全 COLOR：逐材质槽写描边 RGB、B低宽度和 A高 rim mask。"""
    per_slot = {}
    for index, slot in enumerate(obj.material_slots):
        key = getattr(slot.material, "gmi_material_class", "cloth") if slot.material else "cloth"
        (r_high, r_low, g_high), a8 = HAIRPROP_OUTLINE_BY_CLASS.get(key, HAIRPROP_OUTLINE_DEFAULT)
        per_slot[index] = (r_high * 16 + r_low, g_high * 16, a8)
    default = (0, 0, HAIRPROP_OUTLINE_DEFAULT[1])
    colors = []
    class_counts = {}
    for index, slot_index in enumerate(data["materials"]):
        r8, g8, a8 = per_slot.get(int(slot_index), default)
        b8 = HAIRPROP_OUTLINE_WIDTH
        if outline_width_mode == "DISABLE_ALL" or data["vertexIndices"][index] in no_outline_vertices:
            b8 = 0
        colors.append((r8 / 255.0, g8 / 255.0, b8 / 255.0, a8 / 255.0))
        class_counts[int(slot_index)] = class_counts.get(int(slot_index), 0) + 1
    return colors, {
        "method": "hairprop_outline_constant_per_slot",
        "slotOutlineBytes": {str(k): list(v) for k, v in per_slot.items()},
        "slotVertexCounts": {str(k): v for k, v in class_counts.items()},
        "totalVertices": len(colors),
    }


def _apply_semantic_weight_correction(target, reference, old_dominant):
    reference_groups = {group.index: group.name for group in reference.vertex_groups}
    semantic_names = _semantic_bone_names(reference_groups.values())
    reference_weights = []
    candidates = {name: [] for name in semantic_names}
    for vertex in reference.data.vertices:
        weights = {
            reference_groups[item.group]: float(item.weight)
            for item in vertex.groups if item.weight > 0.0
        }
        reference_weights.append(weights)
        for name in semantic_names:
            if weights.get(name, 0.0) > 0.05:
                candidates[name].append(vertex.index)
    trees = {}
    for name, indices in candidates.items():
        if not indices:
            continue
        tree = KDTree(len(indices))
        for slot, vertex_index in enumerate(indices):
            tree.insert(reference.matrix_world @ reference.data.vertices[vertex_index].co, slot)
        tree.balance()
        trees[name] = (tree, indices)
    target_groups = {group.name: group for group in target.vertex_groups}
    corrected = {}
    for vertex in target.data.vertices:
        semantic = old_dominant[vertex.index]
        if semantic not in trees:
            continue
        tree, indices = trees[semantic]
        _, slot, _ = tree.find(target.matrix_world @ vertex.co)
        source_weights = reference_weights[indices[slot]]
        for item in list(vertex.groups):
            target.vertex_groups[item.group].remove([vertex.index])
        for name, weight in source_weights.items():
            target_groups[name].add([vertex.index], weight, "REPLACE")
        corrected[semantic] = corrected.get(semantic, 0) + 1
    return corrected


def _write_weight_risk_attributes(target, reference, risk_distance, old_dominant):
    vertices = [reference.matrix_world @ vertex.co for vertex in reference.data.vertices]
    faces = [tuple(poly.vertices) for poly in reference.data.polygons]
    tree = BVHTree.FromPolygons(vertices, faces, all_triangles=True)
    semantic_names = _semantic_bone_names(old_dominant)
    distances, risks = [], []
    for vertex, dominant in zip(target.data.vertices, old_dominant):
        _, _, _, distance = tree.find_nearest(target.matrix_world @ vertex.co)
        distance = float(distance or 0.0)
        risk = min(1.0, distance / risk_distance)
        if dominant in semantic_names:
            risk = max(risk, 0.75)
        distances.append(distance)
        risks.append(risk)
    attribute = target.data.color_attributes.get("GMI_WEIGHT_RISK")
    if attribute:
        target.data.color_attributes.remove(attribute)
    attribute = target.data.color_attributes.new(
        name="GMI_WEIGHT_RISK", type="FLOAT_COLOR", domain="POINT"
    )
    attribute.data.foreach_set(
        "color", [value for risk in risks for value in (risk, 1.0 - risk, 0.0, 1.0)]
    )
    review = target.vertex_groups.get("GMI_REVIEW_HIGH_RISK")
    if review:
        target.vertex_groups.remove(review)
    review = target.vertex_groups.new(name="GMI_REVIEW_HIGH_RISK")
    indices = [index for index, risk in enumerate(risks) if risk >= 0.75]
    if indices:
        review.add(indices, 1.0, "REPLACE")
    ordered = sorted(distances)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else 0.0
    return {
        "maxDistance": max(distances, default=0.0),
        "meanDistance": sum(distances) / len(distances) if distances else 0.0,
        "p95Distance": p95,
        "reviewVertices": len(indices),
    }


def _inverse_skin_export_data(
    obj, bone_map, source_bind, remap=None, fallback_bone="", source_rig_weights=False,
    outline_width_mode="DISABLE_ALL", vertex_color_mode="MATERIAL_PRESET",
    color_per_slot=None,
):
    """Expand triangle loops, resolve groups and generate target->source bind corrections."""
    mesh = obj.data
    if any(len(poly.vertices) != 3 for poly in mesh.polygons):
        raise ValueError("带权重 GPU 导出前请先三角化网格")
    remap = remap or {}
    if fallback_bone and fallback_bone not in bone_map:
        raise ValueError(f"兜底骨骼不在配置档中：{fallback_bone}")
    group_names = {group.index: group.name for group in obj.vertex_groups}
    weighted_group_indices = {
        item.group
        for vertex in mesh.vertices
        for item in vertex.groups
        if item.weight > 0.0
    }
    armature_obj = next(
        (modifier.object for modifier in obj.modifiers
         if modifier.type == "ARMATURE" and modifier.object), None
    )
    if not armature_obj and not source_rig_weights:
            raise ValueError("带权重 GPU 导出需要 Armature 修改器")
    automatic_remap = {}
    for group_name in group_names.values() if armature_obj and not source_rig_weights else ():
        if remap.get(group_name, group_name) in bone_map:
            continue
        bone = armature_obj.data.bones.get(group_name)
        while bone and bone.parent:
            bone = bone.parent
            candidate = remap.get(bone.name, bone.name)
            if candidate in bone_map:
                automatic_remap[group_name] = candidate
                break

    conversion = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    group_binding = {}
    identity_correction = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, 0.0),
    )
    corrections = [identity_correction] if source_rig_weights else []
    unresolved = set()
    for group_index, group_name in group_names.items():
        if not _is_bone_group(group_name):
            continue
        mapped_name = remap.get(group_name, automatic_remap.get(group_name, group_name))
        if mapped_name not in bone_map:
            if group_index in weighted_group_indices:
                unresolved.add(group_name)
            if not fallback_bone:
                continue
            mapped_name = fallback_bone
        if source_rig_weights:
            group_binding[group_index] = (bone_map[mapped_name], 0)
            continue
        target_bone = armature_obj.data.bones.get(group_name)
        if not target_bone:
            raise ValueError(f"顶点组没有匹配的骨架骨骼：{group_name}")
        target_bind_blender = armature_obj.matrix_world @ target_bone.matrix_local
        target_bind_unity = conversion.inverted() @ target_bind_blender @ conversion
        correction = source_bind[mapped_name] @ target_bind_unity.inverted()
        rows = tuple(
            tuple(float(correction[column][row]) for column in range(3))
            for row in range(4)
        )
        correction_index = len(corrections)
        corrections.append(rows)
        group_binding[group_index] = (bone_map[mapped_name], correction_index)

    uv_layers = list(mesh.uv_layers)
    uv0_layer = _best_uv_layer(mesh, "UV0", uv_layers[0] if uv_layers else None)
    uv1_layer = _best_uv_layer(
        mesh,
        "UV1",
        uv_layers[1] if len(uv_layers) > 1 else uv0_layer,
    )
    if uv0_layer is None:
        names = ", ".join(
            f"{layer.name or '<空名>'}:{_uv_layer_score(layer):.3f}"
            for layer in uv_layers
        ) or "无"
        raise ValueError(f"没有可用 UV 层，已停止导出（候选：{names}）")
    if uv1_layer is None:
        uv1_layer = uv0_layer
    uv0_layer_name = uv0_layer.name
    uv1_layer_name = uv1_layer.name
    color_layer = mesh.color_attributes.get("COLOR")
    # 「沿用源模型顶点色」：逐顶点原样用网格自带的 COLOR。别的模式按**材质槽**写常量，而
    # IP 源一个 m_bdy 槽里同时装着皮肤和布料——常量会把皮肤按布料的 ramp 行渲染（实测
    # chs-sucu：脖子/大腿发黑）。源已经处理好描边语义时（process_ip_geo_body.py），
    # 逐顶点保留才是对的。
    source_colors = None
    if vertex_color_mode == "SOURCE":
        if color_layer is None or color_layer.domain != "POINT":
            raise ValueError(
                "描边颜色选了「沿用源模型顶点色」，但网格没有逐顶点的 COLOR 属性。"
                "换个描边模式，或者先把源的顶点色导进来（IP 源见 tools/process_ip_geo_body.py）")
        source_colors = [tuple(item.color) for item in color_layer.data]
    no_outline_vertices = set()
    if outline_width_mode == "RISK_ONLY":
        no_outline_vertices = (
            _vertex_group_indices(obj, "GMI_NO_OUTLINE")
            | _vertex_group_indices(obj, "GMI_REVIEW_HIGH_RISK")
        )
    world = obj.matrix_world
    normal_matrix = world.to_3x3().inverted().transposed()
    tangent_matrix = world.to_3x3()
    tangents_ready = False
    if uv0_layer is not None:
        try:
            mesh.calc_tangents(uvmap=uv0_layer_name)
            tangents_ready = True
        except RuntimeError:
            tangents_ready = False
    # calc_tangents can rebuild loop custom data on the first run and invalidate
    # previously held MeshUVLoopLayer RNA wrappers. Re-fetch by name so the
    # export never falls back to zero UVs after tangent calculation.
    uv0_layer = mesh.uv_layers.get(uv0_layer_name)
    uv1_layer = mesh.uv_layers.get(uv1_layer_name) or uv0_layer
    if uv0_layer is None:
        raise ValueError(f"切线计算后 UV 层丢失：{uv0_layer_name}")
    vertices, normals, tangents, uv0, uv1, colors, skin, faces, materials = ([] for _ in range(9))
    vertex_indices = []
    tangent_groups = {}
    color_per_slot = color_per_slot or {}
    truncated_weight = 0.0
    for polygon in mesh.polygons:
        face = []
        for loop_index in polygon.loop_indices:
            loop = mesh.loops[loop_index]
            source_vertex = mesh.vertices[loop.vertex_index]
            position = core._to_unity(world @ source_vertex.co)
            normal = core._to_unity((normal_matrix @ loop.normal).normalized())
            if tangents_ready:
                tangent_xyz = core._to_unity((tangent_matrix @ loop.tangent).normalized())
                tangent = (*tangent_xyz, float(loop.bitangent_sign))
            else:
                tangent = (1.0, 0.0, 0.0, 1.0)
            if uv0_layer is not None:
                value = uv0_layer.data[loop_index].uv
                tex0 = (core._safe_float(value[0], 0.0), core._safe_float(value[1], 0.0))
            else:
                raise ValueError("没有可用 UV0，已停止导出")
            if uv1_layer is not None:
                value = uv1_layer.data[loop_index].uv
                tex1 = (core._safe_float(value[0], 0.0), core._safe_float(value[1], 0.0))
            else:
                tex1 = tex0
            color = (source_colors[loop.vertex_index] if source_colors is not None
                     else color_per_slot.get(int(polygon.material_index), GMI_CLOTH_COLOR_FLOAT))
            if outline_width_mode == "DISABLE_ALL" or loop.vertex_index in no_outline_vertices:
                color = _clear_outline_width(color)
            resolved = {}
            for item in source_vertex.groups:
                if item.weight <= 0.0 or item.group not in group_binding:
                    continue
                source_bone_index, correction_index = group_binding[item.group]
                key = (source_bone_index, correction_index)
                resolved[key] = resolved.get(key, 0.0) + float(item.weight)
            ordered = sorted(
                ((bone, correction, weight) for (bone, correction), weight in resolved.items()),
                key=lambda value: value[2], reverse=True,
            )
            if len(ordered) > 4:
                truncated_weight += sum(value[2] for value in ordered[4:])
                ordered = ordered[:4]
            if not ordered:
                raise ValueError(f"顶点 {loop.vertex_index} 没有可导出的配置档兼容权重")
            expanded_index = len(vertices)
            face.append(expanded_index)
            vertices.append(position); normals.append(normal); tangents.append(tangent)
            uv0.append(tex0); uv1.append(tex1); colors.append(color); skin.append(ordered)
            materials.append(int(polygon.material_index))
            vertex_indices.append(int(loop.vertex_index))
            key = (
                round(position[0], 5), round(position[1], 5), round(position[2], 5),
                int(polygon.material_index),
            )
            tangent_groups.setdefault(key, []).append(expanded_index)
        faces.append(tuple(face))
    if unresolved and not fallback_bone:
        # P4 闸门 2/10：带权重的源骨没有对应的游戏骨。两条出路都要给（见
        # core.critical_coverage_error 里的同一段理由）。
        sample = "、".join(sorted(unresolved)[:12])
        raise ValueError(
            f"{len(unresolved)} 根带权重的源骨没有对应的游戏骨：{sample}"
            + ("…" if len(unresolved) > 12 else "")
            + "。这些骨上的权重进不了包。三条出路：\n"
              "  · 骨名没认出来 → 「骨骼映射表」里指定目标骨；\n"
              "  · 是装饰/物理骨 → 在表里给它选装饰物理策略（刚性/自建摇物链/跟裙摆）；\n"
              "  · 承重关节源模型压根没有 → 点「从相邻骨劈权重」")
    # 学马仕描边 VS(e0ceaa85)沿 TANGENT.xyz 挤出描边(NORMAL 通道不参与描边),
    # 且原版 TANGENT 并非 UV 切线,而是逐顶点"平滑法线"(同坐标顶点法线平均,cos≈0.6)。
    # 自定义网格若把 UV 切线写进 TANGENT,描边会沿表面方向挤出 → 整圈不可见。
    # 故这里按位置+材质合并法线得到平滑法线,写入 TANGENT.xyz(w=1,与原版一致),让描边外扩。
    if vertices:
        smoothed_tangents = list(tangents)
        for indices in tangent_groups.values():
            if len(indices) == 1:
                n = normals[indices[0]]
                smoothed_tangents[indices[0]] = (n[0], n[1], n[2], 1.0)
                continue
            for i in indices:
                ni = normals[i]
                sx = sy = sz = 0.0
                for j in indices:
                    nj = normals[j]
                    # 只平均与本顶点同朝向(点积>0)的法线。裙褶/薄壳/双面处同坐标的正反面
                    # 法线相反,若一起平均会相消成乱向 → 描边沿错向挤出 → 凸起毛刺(橙色破边)。
                    if ni[0] * nj[0] + ni[1] * nj[1] + ni[2] * nj[2] > 0.35:
                        sx += nj[0]; sy += nj[1]; sz += nj[2]
                length = (sx * sx + sy * sy + sz * sz) ** 0.5
                if length > 1e-8:
                    smoothed_tangents[i] = (sx / length, sy / length, sz / length, 1.0)
                else:
                    smoothed_tangents[i] = (ni[0], ni[1], ni[2], 1.0)
        tangents = smoothed_tangents
    return {
        "vertices": vertices, "normals": normals, "tangents": tangents,
        "uv0": uv0, "uv1": uv1, "colors": colors, "skin": skin, "faces": faces,
        "materials": materials, "vertexIndices": vertex_indices,
        "uvLayers": {
            "uv0": uv0_layer.name if uv0_layer is not None else "",
            "uv1": uv1_layer.name if uv1_layer is not None else "",
            "uv0Score": _uv_layer_score(uv0_layer),
            "uv1Score": _uv_layer_score(uv1_layer),
            "candidates": _uv_layer_candidates_report(mesh),
        },
        "corrections": corrections, "unresolved": sorted(unresolved),
        "automatic_remap": automatic_remap, "truncated_weight": truncated_weight,
    }


def _prepare_bundle_export_data(context, obj, scene, component_id=None):
    component_id = component_id or _object_component_id(obj, scene)
    _sync_object_mesh_data(context, obj)
    profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
    resolved = _resolve_body_json_library(scene, component_id)
    skeleton_path = Path(resolved.get("skeletonJson") or "")
    if not skeleton_path.is_file():
        raise ValueError("缺少带骨架的 Mesh JSON；请先完成配置档或重新导入带骨架资源")
    bone_map = core.inverse_skin_bone_map(profile_dir, skeleton_path, component_id)
    skeleton = core.load_json(skeleton_path)
    source_bind = {
        node["name"]: _bind_pose_matrix(node["bindPose"]).inverted()
        for node in skeleton["nodes"] if node.get("weightedIndex") is not None
    }
    # 闸门 0：面朝里。几何事实，最先查——它一错，画面上什么都对不上，而所有数据尺子全绿。
    inverted = core.inverted_mesh_error(_mesh_signed_volume(obj))
    if inverted:
        raise ValueError(inverted)
    # 闸门 0.5：一行横跨多个骨族还下了物理指令 —— 结构组装得下两件衣服，误伤看不见。
    mixed = core.mixed_family_directive_error(core.mixed_family_directive_rows(
        [(_row_label(item), item.strategy, row_bones(item))
         for item in getattr(scene, "gmi_bone_map", ())]))
    if mixed:
        raise ValueError(mixed)
    remap, remap_report = _resolve_source_bone_remap(obj, bone_map, scene, skeleton)
    # 闸门 0.8：并进游戏衣物骨、子骨却还留在 mod 骨架里 → 整支子树被外来物理拽走。
    orphans = core.orphaned_subtree_error(core.orphaned_subtree_merges(
        (remap_report.get("physicsInheritance") or {}).get("bones") or {},
        [item["name"] for item
         in ((remap_report.get("newBones") or {}).get("newBones") or [])],
        _source_bone_parents(obj)))
    if orphans:
        raise ValueError(orphans)
    # 闸门 6.5:左右反了。排在下面两道之前——脚尖劈不出权重、朝向整片 177°,都是它的症状。
    if component_id == "body":
        mirror_error = _mirrored_side_error(obj, skeleton, remap, remap_report)
        if mirror_error:
            raise ValueError(mirror_error)
    # 硬闸门:承重关节零权重就别导了。这类错误静止完全看不出、进游戏才炸,
    # 而位置匹配永远能返回一个骨名,所以不拦就是静默出废品。
    weighted_names = [name for name, _mass in _weighted_group_mass(obj)]
    coverage_error = core.critical_coverage_error(weighted_names, remap, bone_map)
    if coverage_error:
        raise ValueError(coverage_error)
    # Head / 脚尖只提醒不拦：body 网格通常没有几何要跟它们（见 core.CRITICAL_SOFT_BONES）
    _coverage_soft_note[0] = core.critical_coverage_note(weighted_names, remap, bone_map)
    # 闸门 9（五档）：`reject` = 作者说这根骨处理不了 → 禁止导出；`bake` 没烘就导出等于
    # 把"会跳位"的几何原样出包，所以也拦。两条都点名具体的骨，不给"哪里错了自己找"。
    rejected = [name for item in getattr(scene, "gmi_bone_map", ())
                if item.strategy == "reject" for name in row_bones(item)]
    if rejected:
        raise ValueError(
            f"{len(rejected)} 根骨被标成「拒绝导出」：" + "、".join(rejected[:12])
            + ("…" if len(rejected) > 12 else "")
            + "。这是显式决定，不是漏配：想导出就把它们改成别的处理（映射到目标骨 / 刚性跟父骨 /"
              "自建摇物链 / 烘焙），或者先从网格里删掉这些骨的权重")
    # 闸门 9（B 档：默认拦，留一个显式放行开关，且放行必须留痕）。
    undecided_rows = [(_row_label(item), _row_state(item))
                      for item in getattr(scene, "gmi_bone_map", ())]
    allow_undecided = bool(getattr(scene, "gmi_allow_undecided", False))
    undecided_error = core.undecided_export_error(undecided_rows, allow_undecided)
    if undecided_error:
        raise ValueError(undecided_error)
    undecided_record = core.undecided_export_record(undecided_rows, allow_undecided)
    # 闸门：自建骨与目标骨架重名（契约 §4.1）
    collision = core.new_bone_name_collision_error(
        [bone.get("name") for bone in
         ((remap_report.get("newBones") or {}).get("newBones") or [])
         if isinstance(bone, dict)],
        [node.get("name") for node in (skeleton.get("nodes") or ())] if skeleton else (),
    )
    if collision:
        raise ValueError(collision)
    # 闸门①：自建摇物链上没有任何带权重的骨 —— 建了也没人看得见，日志却全绿。
    new_bone_report = (remap_report.get("newBones") or {}) if isinstance(remap_report, dict) else {}
    empty_error = core.empty_swing_chain_error(new_bone_report.get("emptyChains"))
    if empty_error:
        raise ValueError(empty_error)
    pending_bake = [name for item in getattr(scene, "gmi_bone_map", ())
                    if item.strategy == "bake" for name in row_bones(item)]
    if pending_bake and not obj.get("gmi_baked_rest_offset"):
        raise ValueError(
            f"{len(pending_bake)} 根骨标了「烘焙形变+并到父骨」，但还没烘："
            + "、".join(pending_bake[:12]) + ("…" if len(pending_bake) > 12 else "")
            + "。点「烘焙静止形变」跑一次（它会先量形变有多大，小于阈值就不动网格），再导出")
    # 闸门：作者点了原版布料驱动器，但那个类别没有驱动器可用 —— 拦下，别出哑骨。
    driver_gaps = _form_driver_gaps(scene)
    if driver_gaps:
        sample = "、".join(f"{name}（{category}）" for name, category in driver_gaps[:8])
        raise ValueError(
            f"{len(driver_gaps)} 根骨选了「原版布料驱动器」，但它们的部件类型没有对应的驱动器："
            + sample + ("…" if len(driver_gaps) > 8 else "")
            + f"。运行时只实现了 {'/'.join(core.DRIVER_CATEGORIES)} 三类"
              "（裙→Skirt、披挂→Frill、袖→HumanoidSleeve）。"
              "把「部件类型」改成这三类之一，或把策略换成「自建摇物链」——"
              "照现在这样导出，这几根骨既没有驱动器也没有摇物，在游戏里根本不会动")
    # 闸门 7：静止朝向。会 1:1 显示在游戏里，而位置差被重定向吸收，所以只拦朝向。
    # body 之外没有人形骨，量不了也没意义。
    if component_id == "body":
        orientation_error = _rest_orientation_error(obj, skeleton, remap, remap_report)
        if orientation_error:
            raise ValueError(orientation_error)
    extra_nodes, extra_bind_poses = _extend_bundle_skeleton(
        skeleton, bone_map, source_bind, remap_report.get("newBones") or {}
    )
    data = _inverse_skin_export_data(
        obj, bone_map, source_bind, remap, scene.gmi_unmapped_bone_fallback.strip(),
        source_rig_weights=True,
        outline_width_mode=scene.gmi_outline_width_mode,
        vertex_color_mode=scene.gmi_vertex_color_mode,
        color_per_slot=_material_slot_color_map(obj),
    )
    # 尺子：衣物链的跨节权重过渡带。这次撕裙子的唯一真凶，而 CROSS_JOINT_BANDS 只覆盖
    # 肩肘腕膝，衣物链一根都没有。有场景里的原版参考体就现算基线，没有就用常数门槛。
    new_bone_list = (remap_report.get("newBones") or {}).get("newBones") or []
    if new_bone_list:
        try:
            reference = _profile_weight_reference(context)
        except Exception:
            reference = None
        vanilla_ratios = None
        if reference is not None:
            vanilla_arm = next((m.object for m in reference.modifiers
                                if m.type == "ARMATURE" and m.object), None)
            vanilla_ratios = core.chain_blend_ratio(
                _vertex_influences(reference), _vanilla_chain_node_map(vanilla_arm))
        data["chain_blend_note"] = core.chain_blend_note(core.chain_blend_findings(
            # 不传 remap：新骨用的就是源骨名，而 remap 里新骨的值是 None，
            # `.get(name, name)` 会把它们全折成 None 这一个键。
            core.chain_blend_ratio(_vertex_influences(obj),
                                   _chain_node_map(new_bone_list)),
            vanilla_ratios))
    data["bundle_extra_skeleton_nodes"] = extra_nodes
    data["bundle_extra_bind_poses"] = extra_bind_poses
    # 这里是模块级函数，报警交给算子统一发（见 export_bundle_source 里的 anchor_only_note）
    anchor_note = core.anchor_only_chain_note(
        new_bone_report.get("anchorOnlyChains"),
        applied=new_bone_report.get("anchorSwingApplied"))
    remap_report["undecided"] = undecided_record
    data["source_rig_report"] = remap_report
    if anchor_note:
        data["anchor_only_note"] = anchor_note
    # 体检量的是 fingers/forearm，只有 body 有这些区域；hair/hairprop 上跑必然“无法评估”，
    # 那条警告会被当成骨名没映射的假警报。
    if component_id == "body":
        sanity = _bind_sanity_report(obj, remap)
        if sanity:
            failed, unmeasured, report = sanity
            data["bind_sanity"] = {"failed": failed, "unmeasured": unmeasured, "detail": report}
    if component_id == "hair":
        reference = _profile_weight_reference(context, "hair")
        if reference.get("gmi_component_id") != "hair":
            raise ValueError("场景中的带权重参考模型不是 hair,无法拷贝 hair 顶点色语义")
        no_outline = set()
        if scene.gmi_outline_width_mode == "RISK_ONLY":
            no_outline = (
                _vertex_group_indices(obj, "GMI_NO_OUTLINE")
                | _vertex_group_indices(obj, "GMI_REVIEW_HIGH_RISK")
            )
        data["colors"], _ = _hair_export_colors(
            reference, data, scene.gmi_hair_outline_tier,
            scene.gmi_outline_width_mode, no_outline,
        )
    elif component_id == "hairprop":
        no_outline = set()
        if scene.gmi_outline_width_mode == "RISK_ONLY":
            no_outline = (
                _vertex_group_indices(obj, "GMI_NO_OUTLINE")
                | _vertex_group_indices(obj, "GMI_REVIEW_HIGH_RISK")
            )
        data["colors"], _ = _hairprop_export_colors(
            obj, data, scene.gmi_outline_width_mode, no_outline,
        )
    elif scene.gmi_vertex_color_mode == "BASECOLOR":
        data["colors"], _ = _synthesize_export_native_colors(
            profile_dir, component_id, data,
            _scene_texture_path(scene, component_id, "base_color"),
            _material_slot_color_map(obj),
        )
    elif scene.gmi_vertex_color_mode == "CONSTANT_BLACK":
        data["colors"] = _black_outline_colors(data["colors"])
    return component_id, resolved, data


def _resolve_target_scheme(resolved):
    """目标 body 的材质段数(1=bdy，2=bdy+bdyco)，用来把作者网格材质归并到位。"""
    target = core.load_json(Path(resolved["meshJson"]))
    return max(1, len(target.get("m_SubMeshes") or []))


def _bundle_texture_sources(obj, scene, component_id, group_alpha=None):
    main = {
        "baseColor": _scene_texture_path(scene, component_id, "base_color"),
        "packedMask": _scene_texture_path(scene, component_id, "packed_mask"),
        "shadeColor": _scene_texture_path(scene, component_id, "shade_color"),
    }
    native = {
        "baseColor": scene.gmi_opacity_texture_file,
        "packedMask": scene.gmi_opacity_packed_mask_file,
        "shadeColor": scene.gmi_opacity_shade_color_file,
    }
    properties = (("_BaseMap", "baseColor", "t0"), ("_DefMap", "packedMask", "t1"),
                  ("_ShadeMap", "shadeColor", "t4"))
    # group_alpha 给定时按【归并后的目标段】导出(每段一套贴图)，否则按原始材质槽。
    if group_alpha is not None:
        slot_alpha = {int(g): mode for g, mode in dict(group_alpha).items()}
    else:
        modes = _material_slot_alpha_modes(obj)
        slot_alpha = {slot: modes.get(slot) for slot in range(max(1, len(obj.material_slots)))}
    result = []
    for slot in sorted(slot_alpha):
        use_native = slot_alpha.get(slot) == "NATIVE_CO"
        sources = native if use_native else main
        for prop, semantic, suffix in properties:
            source = sources[semantic]
            if not source:
                if semantic == "baseColor":
                    raise ValueError(f"材质槽 {slot} 缺少 {suffix} 基础色贴图")
                if not scene.gmi_neutral_material:
                    raise ValueError(f"材质槽 {slot} 缺少 {suffix}，且未启用中性贴图")
                source = _neutral_material_dds(semantic, "body" if use_native else component_id)
            result.append({
                "materialSlot": slot,
                "property": prop,
                "semantic": semantic,
                "source": source,
                "filename": f"{component_id}_slot{slot}_{suffix}.png",
            })
    return result


def _export_bundle_png(source, destination):
    source = Path(bpy.path.abspath(source)).resolve()
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f"贴图不存在：{source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        shutil.copy2(source, destination)
        return
    def non_color(image):
        # 必须在写像素之前设。给 colorspace_settings.name 赋值会重建图像缓冲、丢掉
        # 已写入的像素——赋同一个值也一样——存盘就是纯黑。t0 走 copy2 所以看不出来,
        # t1/t4 从烘焙的 DDS 转 PNG 就会整张黑 → 游戏里 ShadeColor=黑,整身发暗。
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        return image

    try:
        if source.suffix.lower() == ".dds":
            width, height, rgba = core.read_rgba8_dds(source)
            image = non_color(bpy.data.images.new(
                source.stem, width=width, height=height, alpha=True
            ))
            # 必须走 numpy。列表推导会给每个通道造一个 Python float 对象：8192² RGBA
            # = 2.68 亿个，约 8.6 GB → MemoryError，而且异常本身没有消息，作者只看到
            # 一个空的红叉。4096² 也要 2.1 GB，本来就在悬崖边上。
            # numpy 版同一张图只占 1.07 GB（float32），且没有逐元素的 Python 开销。
            import numpy as np
            rows = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width * 4)
            flat = rows[::-1].reshape(-1)          # DDS 顶行在前，Blender 底行在前
            image.pixels.foreach_set(flat.astype(np.float32) / np.float32(255.0))
        else:
            image = non_color(bpy.data.images.load(str(source), check_existing=False))
    except RuntimeError as exc:
        raise ValueError(f"无法读取贴图：{source}: {exc}") from exc
    try:
        image.filepath_raw = str(destination)
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)
    if not destination.is_file():
        raise IOError(f"PNG 导出失败：{destination}")


# 参考骨的显示长度。Unity 没有"骨长"这个概念，所以这个数纯粹是为了在视图里看得见，
# 不参与任何判据（`tests/blender_reference_rig_smoke.py` 只查位置、朝向、层级）。
REFERENCE_BONE_LENGTH = 0.05


def reference_rest_world(nodes):
    """{节点下标: 静止世界矩阵（Blender 空间）}。

    带权重的骨用 `bindPose` 求逆 —— 精确，且不碰四元数手性。没权重的节点（`Reference`、
    `Pelvis`、动态链锚点 `*_A`/`*_O`、摇物链根 `*_S`）没有 bindPose，只能从最近的带权重
    祖先按**完整 local 矩阵**往下合成；只累加 `localPosition` 会让任何带旋转的关节以下全错
    （151 个节点里 57 个带非单位 localRotation）。
    """
    cache = {}

    def world(index):
        if index in cache:
            return cache[index]
        node = nodes[index]
        bind = node.get("bindPose")
        if bind:
            matrix = (C_UNITY.inverted() @ _bind_pose_matrix(bind).inverted() @ C_UNITY)
        else:
            x, y, z, w = node.get("localRotation") or [0.0, 0.0, 0.0, 1.0]
            local = Matrix.LocRotScale(
                Vector(node.get("localPosition") or (0.0, 0.0, 0.0)),
                Quaternion((w, x, y, z)),
                Vector(node.get("localScale") or (1.0, 1.0, 1.0)))
            matrix = C_UNITY.inverted() @ local @ C_UNITY
            parent = int(node.get("parent", -1))
            if parent >= 0:
                matrix = world(parent) @ matrix
        cache[index] = matrix
        return matrix

    return {index: world(index) for index in range(len(nodes))}


def _create_armature(context, mesh_obj, data):
    skeleton = data["skeleton"]
    nodes = skeleton["nodes"]
    weighted = {node["weightedIndex"]: node for node in nodes if node["weightedIndex"] is not None}
    world_by_index = reference_rest_world(nodes)
    armature = bpy.data.armatures.new(f"{data['name']}_Armature")
    armature_obj = bpy.data.objects.new(armature.name, armature)
    context.collection.objects.link(armature_obj)
    context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    # 没权重的节点也要建骨：动态链锚点与链根决定"自建链的根该落哪"，作者在 Blender 里
    # 对齐时看得到它们才有参考。唯一跳过的是没有父节点又没有 bindPose 的那个——
    # 它是模型根对象，不是骨。
    edit_by_index = {}
    for index, node in enumerate(nodes):
        if int(node.get("parent", -1)) < 0 and not node.get("bindPose"):
            continue
        world = world_by_index[index]
        bone = armature.edit_bones.new(node["name"])
        bone.head = (0.0, 0.0, 0.0)
        bone.tail = (0.0, REFERENCE_BONE_LENGTH, 0.0)
        # 朝向必须照搬游戏骨的静止坐标系。旧版只按 head→tail 摆、roll 留默认值，实测
        # 104 根里 69 根（镜像那一侧）与原版差整整 180° —— 作者拿这副骨架对齐时看到的
        # 轴向是错的。写 EditBone.matrix 一次把 head / 方向 / roll 都定下来；缩放归一，
        # 别把节点上的非单位 localScale 带进骨架。
        bone.matrix = Matrix.LocRotScale(
            world.translation, world.to_quaternion(), Vector((1.0, 1.0, 1.0)))
        edit_by_index[index] = bone
    for index, bone in edit_by_index.items():
        parent = int(nodes[index].get("parent", -1))
        while parent >= 0:
            if parent in edit_by_index:
                bone.parent = edit_by_index[parent]
                break
            parent = int(nodes[parent].get("parent", -1))
    bpy.ops.object.mode_set(mode="OBJECT")
    for weighted_index in sorted(weighted):
        mesh_obj.vertex_groups.new(name=weighted[weighted_index]["name"])
    for vertex_index, influence in enumerate(data["skin"]):
        for bone_index, weight in zip(influence["boneIndex"], influence["weight"]):
            if weight > 0.0:
                mesh_obj.vertex_groups[weighted[bone_index]["name"]].add(
                    [vertex_index], float(weight), "REPLACE"
                )
    modifier = mesh_obj.modifiers.new(name="GakumasMI Armature", type="ARMATURE")
    modifier.object = armature_obj
    mesh_obj.parent = armature_obj
    context.view_layer.objects.active = mesh_obj
    armature_obj.select_set(False)
    mesh_obj.select_set(True)
    return armature_obj


class GMI_OT_import_profile_object(Operator):
    bl_idname = "gmi.import_profile_object"
    bl_label = "导入配置档全部对象（排错）"
    bl_description = "一次导入抓帧参考、带权重参考和复核顶点组，用于排查配置档问题；正常流程用「导入参考模型与骨架」即可"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        profile_dir, capture_dir, _ = _scene_paths(scene)
        try:
            profile_set = core.load_profile_set(profile_dir)
            profile = profile_set["profile"]
            component = core.component_by_id(profile, _scene_component_id(scene))
            resolved = _resolve_body_json_library(scene)
            mesh_path = Path(resolved["meshJson"])
            skeleton_path = Path(resolved["skeletonJson"])

            reference_collection = _collection(context, "GMI_配置档参考")
            author_collection = _collection(context, "GMI_作者模型")
            export_collection = _collection(context, "GMI_导出对象")
            export_collection["gmi_profile_id"] = profile["id"]
            export_collection["gmi_component_id"] = _scene_component_id(scene)

            reference_data = core.read_reference(profile_dir, _scene_component_id(scene), capture_dir)
            reference_obj = _create_mesh(context, f"GMI_{_scene_component_id(scene)}_抓帧参考", reference_data)
            reference_obj["gmi_profile_id"] = profile["id"]
            reference_obj["gmi_profile_dir"] = str(profile_set["root"])
            reference_obj["gmi_component_id"] = _scene_component_id(scene)
            reference_obj["gmi_source_vertex_count"] = component["vertices"]
            reference_obj["gmi_source_index_count"] = component["indices"]
            reference_obj["gmi_source_ib_hash"] = component["ibHash"]
            reference_obj["gmi_reference_only"] = True
            reference_obj.display_type = "WIRE"
            reference_obj.hide_render = True
            _link_only_to_collection(reference_obj, reference_collection)

            weighted_data = core.read_weighted_reference(mesh_path, skeleton_path)
            weighted_obj = _create_mesh(context, f"GMI_{weighted_data['name']}_带权重参考", weighted_data)
            armature = _create_armature(context, weighted_obj, weighted_data)
            weighted_obj["gmi_profile_id"] = profile["id"]
            weighted_obj["gmi_profile_dir"] = str(profile_set["root"])
            weighted_obj["gmi_component_id"] = _scene_component_id(scene)
            weighted_obj["gmi_source_vertex_count"] = component["vertices"]
            weighted_obj["gmi_source_index_count"] = component["indices"]
            weighted_obj["gmi_source_ib_hash"] = component["ibHash"]
            weighted_obj["gmi_weighted_reference"] = True
            weighted_obj["gmi_blend_shape_data_present"] = bool(weighted_data.get("shapes"))
            _link_only_to_collection(weighted_obj, reference_collection)
            _link_only_to_collection(armature, reference_collection)

            context.view_layer.objects.active = weighted_obj
            weighted_obj.select_set(True)
            self.report(
                {"INFO"},
                f"已导入配置档对象：参考 {len(reference_data['vertices'])} 顶点，"
                f"权重 {weighted_data['vertex_count']} 顶点",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_resolve_body_json_library(Operator):
    bl_idname = "gmi.resolve_body_json_library"
    bl_label = "仅匹配资源库"
    bl_description = "只做资源库匹配：按制作目标找到原模型 JSON 与骨架 JSON 并填入字段，不生成配置档；用于确认匹配到的是不是目标网格"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = _resolve_body_json_library(context.scene)
            vc = result.get("vertexCount")
            detail = f"，{vc} 顶点 / {result.get('indexCount')} 索引" if vc else ""
            self.report(
                {"INFO"},
                f"已匹配 {result['body']}（{result['match']}{detail}）",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_extract_profile_from_frame_dump(Operator):
    bl_idname = "gmi.extract_profile_from_frame_dump"
    bl_label = "仅生成注入信息"
    bl_description = "只扫描抓帧生成注入信息（Draw/VB/IB/贴图 hash），不补权重与逆算子；正常流程用「生成完整配置档」一步到位"

    def execute(self, context):
        scene = context.scene
        capture_dir = bpy.path.abspath(scene.gmi_capture_dir)
        output_dir = bpy.path.abspath(scene.gmi_extract_output_dir)
        if not capture_dir:
            self.report({"ERROR"}, "请先选择 FrameAnalysis 抓帧目录")
            return {"CANCELLED"}
        if not scene.gmi_body_json_library_dir:
            self.report({"ERROR"}, "请先选择网格 JSON 资源库目录")
            return {"CANCELLED"}
        try:
            if not output_dir:
                output_dir = str(Path(capture_dir) / "GakumasMI-profile")
            expected_vertex_count = None
            expected_vertex_counts = []
            if scene.gmi_body_json_library_dir and scene.gmi_body_resource:
                hints = core.body_json_vertex_hints(
                    bpy.path.abspath(scene.gmi_body_json_library_dir),
                    scene.gmi_body_resource,
                    mesh_name=core.component_mesh_name(_scene_component_id(scene)),
                )
                expected_vertex_counts = hints["vertexCounts"]
                entry = hints["exact"]
                if entry:
                    expected_vertex_count = entry.get("vertexCount")
            report = core.extract_profile_from_frame_dump(
                capture_dir,
                output_dir,
                component_id=_scene_component_id(scene),
                main_draw=scene.gmi_extract_draw or None,
                expected_vertex_count=expected_vertex_count,
                expected_vertex_counts=expected_vertex_counts,
                body_resource=(scene.gmi_body_resource or None),
            )
            scene.gmi_profile_dir = output_dir
            selected = report["selected"]
            resource = _resolve_body_json_library(scene)
            self.report(
                {"INFO"},
                f"已生成配置档：Draw {selected['draw']:06d}，"
                f"{selected['vertices']} 顶点 / {selected['indices']} 索引"
                f"，已匹配 {resource['body']}"
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_build_full_profile(Operator):
    bl_idname = "gmi.build_full_profile"
    bl_label = "生成完整配置档"
    bl_description = "一键完成：扫描抓帧 → 匹配资源库 → 生成注入信息、参考网格、骨架与逆蒙皮算子。制作目标为发型时自动把配套发饰并入同一配置档"

    def execute(self, context):
        scene = context.scene
        capture_dir = bpy.path.abspath(scene.gmi_capture_dir)
        library_dir = bpy.path.abspath(scene.gmi_body_json_library_dir)
        if not capture_dir:
            self.report({"ERROR"}, "请先填写抓帧目录")
            return {"CANCELLED"}
        if not library_dir:
            self.report({"ERROR"}, "请先填写网格 JSON 资源库目录")
            return {"CANCELLED"}
        try:
            output_dir = bpy.path.abspath(scene.gmi_extract_output_dir)
            if not output_dir:
                output_dir = str(Path(capture_dir) / "GakumasMI-profile")
            component_id = scene.gmi_component_id
            expected_vertex_count = None
            expected_vertex_counts = []
            if scene.gmi_body_resource:
                hints = core.body_json_vertex_hints(
                    library_dir,
                    scene.gmi_body_resource,
                    mesh_name=core.component_mesh_name(component_id),
                )
                expected_vertex_counts = hints["vertexCounts"]
                entry = hints["exact"]
                if entry:
                    expected_vertex_count = entry.get("vertexCount")
            # ① 注入信息
            core.extract_profile_from_frame_dump(
                capture_dir, output_dir,
                component_id=component_id,
                main_draw=scene.gmi_extract_draw or None,
                expected_vertex_count=expected_vertex_count,
                expected_vertex_counts=expected_vertex_counts,
                body_resource=(scene.gmi_body_resource or None),
            )
            # ②结构数据 + ③逆算子（可选指定目标资源以消歧）
            report = core.complete_inverse_skin_profile(
                output_dir, library_dir, component_id,
                body_resource=(scene.gmi_body_resource or None),
            )
            if component_id == "hair":
                prop_resource = scene.gmi_body_resource or report["body"]
                prop_hints = core.body_json_vertex_hints(
                    library_dir, prop_resource,
                    mesh_name=core.component_mesh_name("hairprop"),
                )
                with tempfile.TemporaryDirectory(prefix="gmi-hairprop-") as prop_dir:
                    core.extract_profile_from_frame_dump(
                        capture_dir, prop_dir, component_id="hairprop",
                        expected_vertex_count=(prop_hints.get("exact") or {}).get("vertexCount"),
                        expected_vertex_counts=prop_hints["vertexCounts"],
                        body_resource=prop_resource,
                    )
                    core.complete_inverse_skin_profile(
                        prop_dir, library_dir, "hairprop",
                        body_resource=prop_resource,
                    )
                    core.merge_profile_component(output_dir, prop_dir, "hairprop")
            scene.gmi_profile_dir = output_dir
            naming = "骨架名" if report["boneNaming"] == "skeleton" else "骨骼hash(合成骨架)"
            self.report(
                {"INFO"},
                f"完整配置档已生成 → {output_dir}；匹配 {report['body']}（{report['match']}，{naming}），"
                f"{report['vertexCount']} 顶点 / {report['weightedBoneCount']} 骨骼，"
                f"不可观测骨 {len(report['unobservableBones'])} 根",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_update_profile_from_frame_dump(Operator):
    bl_idname = "gmi.update_profile_from_frame_dump"
    bl_label = "换新抓帧更新配置档"
    bl_description = "用新的 FrameAnalysis 重新校验 VB/IB/贴图 hash 并写回配置档；游戏更新导致 hash 变化时用这个，不必重做配置档"

    def execute(self, context):
        scene = context.scene
        profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
        capture_dir = bpy.path.abspath(scene.gmi_capture_dir)
        if not capture_dir:
            self.report({"ERROR"}, "请先选择 FrameAnalysis 抓帧目录")
            return {"CANCELLED"}
        try:
            report = core.update_profile_capture_from_frame_dump(profile_dir, capture_dir)
            if report["ok"]:
                self.report(
                    {"INFO"},
                    f"配置档已更新：{report['fileCount']} 个文件，资源匹配完整"
                )
            else:
                preview = ", ".join(report["missing"][:4])
                suffix = " ..." if len(report["missing"]) > 4 else ""
                self.report(
                    {"WARNING"},
                    f"配置档已更新，但缺 {len(report['missing'])} 项资源：{preview}{suffix}"
                )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_import_reference(Operator):
    bl_idname = "gmi.import_reference"
    bl_label = "只导入抓帧参考模型"
    bl_description = "导入抓帧里的原始网格（保留顶点编号、无权重无骨架），用于排错比对；正常流程用「导入参考模型与骨架」"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        profile_dir, capture_dir, _ = _scene_paths(scene)
        try:
            data = core.read_reference(profile_dir, _scene_component_id(scene), capture_dir)
            component = data["component"]
            obj = _create_mesh(context, f"GMI_{_scene_component_id(scene)}_参考", data)
            obj["gmi_profile_id"] = data["profile_set"]["profile"]["id"]
            obj["gmi_profile_dir"] = str(data["profile_set"]["root"])
            obj["gmi_component_id"] = _scene_component_id(scene)
            obj["gmi_source_vertex_count"] = component["vertices"]
            obj["gmi_source_index_count"] = component.get("indices", len(data["faces"]) * 3)
            obj["gmi_source_ib_hash"] = component["ibHash"]
            obj["gmi_reference_only"] = True
            self.report({"INFO"}, f"已导入 {len(data['vertices'])} 个顶点 / {len(data['faces'])} 个三角面")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


def _import_weighted_reference_component(context, component_id):
    scene = context.scene
    profile_set = core.load_profile_set(bpy.path.abspath(scene.gmi_profile_dir))
    resolved = _resolve_body_json_library(scene, component_id)
    data = core.read_weighted_reference(Path(resolved["meshJson"]), Path(resolved["skeletonJson"]))
    obj = _create_mesh(context, f"GMI_{data['name']}_{component_id}_带权重参考", data)
    armature = _create_armature(context, obj, data)
    profile = profile_set["profile"]
    component = core.component_by_id(profile, component_id)
    obj["gmi_profile_id"] = profile["id"]
    obj["gmi_profile_dir"] = bpy.path.abspath(scene.gmi_profile_dir)
    obj["gmi_component_id"] = component_id
    obj["gmi_source_vertex_count"] = component["vertices"]
    obj["gmi_source_index_count"] = component["indices"]
    obj["gmi_source_ib_hash"] = component["ibHash"]
    obj["gmi_weighted_reference"] = True
    obj["gmi_blend_shape_data_present"] = bool(data.get("shapes"))
    return obj


class GMI_OT_import_weighted_reference(Operator):
    bl_idname = "gmi.import_weighted_reference"
    bl_label = "导入参考模型与骨架"
    bl_description = "导入被替换网格的带权重参考与骨架。它是发型描边取色和导出前绑定体检的数据源，导出前别删；制作目标为发型时同时导入发型和发饰两个参考"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            components = [_scene_component_id(scene)]
            if scene.gmi_component_id == "hair":
                components.append("hairprop")
            imported = [_import_weighted_reference_component(context, component_id) for component_id in components]
            primary = next(obj for obj in imported if obj.get("gmi_component_id") == scene.gmi_component_id)
            context.view_layer.objects.active = primary
            primary.select_set(True)
            self.report(
                {"INFO"},
                "；".join(
                    f"{obj.get('gmi_component_id')} {obj['gmi_source_vertex_count']} 顶点"
                    for obj in imported
                ) + "；已导入到同一发型 profile",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_prepare_target(Operator):
    bl_idname = "gmi.prepare_target"
    bl_label = "准备目标参照"
    bl_description = "按当前目标来源建立或读取配置档，然后把带权重参考模型与骨架导入场景"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if scene.gmi_target_source == "CAPTURE":
            result = bpy.ops.gmi.build_full_profile()
            if "FINISHED" not in result:
                return result
        if not str(scene.gmi_profile_dir or "").strip():
            self.report({"ERROR"}, "请先选择已有配置档目录")
            return {"CANCELLED"}
        result = bpy.ops.gmi.import_weighted_reference()
        if "FINISHED" in result:
            scene.gmi_workflow_stage = "MODEL"
            self.report({"INFO"}, "目标配置档、参考模型与骨架已准备好")
        return result


class GMI_OT_activate_author_object(Operator):
    bl_idname = "gmi.activate_author_object"
    bl_label = "使用这个作者模型"
    bl_description = "把显式选择的作者网格设为当前对象；未选择时采用 3D 视图里当前激活的网格"

    def execute(self, context):
        scene = context.scene
        obj = getattr(scene, "gmi_author_object", None)
        if (obj is None and context.active_object and context.active_object.type == "MESH"
                and not context.active_object.get("gmi_weighted_reference")):
            obj = context.active_object
            scene.gmi_author_object = obj
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "请在「作者模型」选择一个网格，或先在 3D 视图激活网格")
            return {"CANCELLED"}
        if obj.name not in context.view_layer.objects:
            self.report({"ERROR"}, "作者模型不在当前视图层，无法激活")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        scene.gmi_workflow_stage = "MATERIAL"
        self.report({"INFO"}, f"后续阶段将使用作者模型：{obj.name}")
        return {"FINISHED"}


class GMI_OT_export_bundle_source(Operator):
    bl_idname = "gmi.export_bundle_source"
    bl_label = "导出 bundle 源"
    bl_description = "导出 geojson、骨骼 sidecar、PNG 和 mod.json，供 Unity/UnityPy 打包"

    also_patch: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    def execute(self, context):
        obj = _author_mesh(context)
        scene = context.scene
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请激活带顶点组权重的作者网格")
            return {"CANCELLED"}
        try:
            component_id, resolved, data = _prepare_bundle_export_data(
                context, obj, scene
            )
            # 只带 Geo_HairProp 的包实测装上去毫无反应（发型发饰都不变）。发型+发饰是同一件
            # 头饰的两个 renderer，必须从发型这边一次导成一个包。
            if component_id == "hairprop":
                raise ValueError(
                    "发饰不能单独导出成包：请激活【发型】网格，再在「发饰对象」里选上发饰，"
                    "一次导出会把两个 renderer 打进同一个包")
            # 把作者网格的材质槽归并到目标资源的段数，并校验匹配。body 是 bdy(+bdyco)；
            # hair/hairprop 的目标只有 1 段，作者模型常带 m_FrontHair/m_BackHair 之类的
            # 多槽切分，不归并就会带着 3 个 submesh 撞进模板补丁，报一句看不懂的
            # “submesh count changed”。co 只对 body 有意义。
            target_n = _resolve_target_scheme(resolved)
            slot_modes = _material_slot_alpha_modes(obj) if component_id == "body" else {}
            co_slots = {slot for slot, mode in slot_modes.items() if mode == "NATIVE_CO"}
            transparent_slots = {slot for slot, mode in slot_modes.items()
                                 if mode == "GMI_TRANSPARENT"}
            data["materials"] = core.merge_material_groups(
                co_slots, target_n, data.get("materials") or [], transparent_slots
            )
            # 自建半透明段：原版 renderer 没有这些槽，runtime 按 mod.json 的
            # transparentMaterials 扩容 sharedMaterials 并新建 Gmi/Transparent 材质。
            transparent_groups = core.transparent_group_map(co_slots, target_n, transparent_slots)
            used_material_groups = set(data["materials"])
            transparent_materials = []
            for slot, group in sorted(transparent_groups.items(), key=lambda item: item[1]):
                if group not in used_material_groups:
                    continue  # 标了半透明但没有面用到这个槽
                material = obj.material_slots[slot].material
                # 贴图不另出一张：半透明段的 UV 就落在已有的 body/co 图集里，直接引用
                # 那两张已经导出的 t0。（模板里没有多余的 Texture2D 对象，UnityPy 现造
                # 对象是已知的 Unity6 加载崩溃源，别碰。）
                co_atlas = bool(getattr(material, "gmi_transparent_co_atlas", False))
                atlas = 1 if co_atlas else 0
                is_proxy = bool(getattr(material, "gmi_transparent_proxy", False))
                # 代理段进不透明区间末尾（原生角色 MRT 那一趟只收 <=2500），颜色段留在透明队列；
                # 两段共用同一个 shader，靠开关分工。
                transparent_materials.append({
                    "rendererName": core.RENDERER_NAMES[component_id],
                    "materialSlot": group,
                    "filename": f"{component_id}_slot{atlas}_t0.png",
                    # toon 用同一套图集的 t1/t4（r=阴影阈值、a=AO；rgb=暗面色、a=分支）
                    "defMap": f"{component_id}_slot{atlas}_t1.png",
                    "shadeMap": f"{component_id}_slot{atlas}_t4.png",
                    "alpha": float(getattr(material, "gmi_transparent_alpha", 0.5)),
                    "toonStrength": float(getattr(material, "gmi_transparent_toon", 1.0)),
                    "cull": 0.0,
                    "zwrite": 1.0 if is_proxy else 0.0,
                    "renderQueue": 2500 if is_proxy else 3000,
                    "props": {
                        "_ProxyEnable": 1.0 if is_proxy else 0.0,
                        "_ForwardEnable": 0.0 if is_proxy else 1.0,
                        "_MaterialId": 256.0,
                        # 代理段跨两个图集，别按贴图 alpha 裁：几何在哪就认领到哪
                        "_AlphaFromTexture": 0.0 if is_proxy else 1.0,
                    },
                })
            # 贴图只出【作者网格真的用到的段】。目标资源的段数可能多于用到的段——
            # cstm-0119 全系列原版就是 3 段(主体 + 腰上一圈 128 顶点 + 胸前 179 顶点的
            # 小件)。空段照样会被 _bundle_submeshes 造出来，但 0 面片、不可见，贴图给
            # 什么都无所谓;不出条目就保留原版材质。按 range(target_n) 出的话，没做 co
            # 部件的工程会被段 1 拽去要「原生 co 基础色」，空着就报“缺少 t0”。
            # 半透明段不进贴图导出：它复用 body/co 已有的那两张 t0（同一套 UV），
            # 模板里也没有多余的 Texture2D 对象可以承载新图。
            transparent_group_ids = {item["materialSlot"] for item in transparent_materials}
            used_groups = sorted((set(data["materials"]) - transparent_group_ids) or {0})
            group_alpha = {group: ("NATIVE_CO" if (component_id == "body" and group == 1) else None)
                           for group in used_groups}
            material_slot_count = target_n
            output_root = bpy.path.abspath(scene.gmi_output_dir)
            if not output_root:
                raise ValueError("请先选择输出目录")
            package_id = core._sanitize_package_id(scene.gmi_package_id)
            bundle_dir = Path(output_root) / package_id / "bundle-src"
            textures = _bundle_texture_sources(obj, scene, component_id, group_alpha)
            # 发型和发饰是同一件头饰的两个 renderer，必须进同一个包：只导发型的话
            # 发饰仍是原版，只导发饰则整包 part 对不上，两种都等于没换。
            extra_components = []
            prop_obj = scene.gmi_hairprop_object if component_id == "hair" else None
            if prop_obj is not None and prop_obj.type == "MESH":
                _, prop_resolved, prop_data = _prepare_bundle_export_data(
                    context, prop_obj, scene, "hairprop"
                )
                prop_slots = _resolve_target_scheme(prop_resolved)
                prop_data["materials"] = core.merge_material_groups(
                    set(), prop_slots, prop_data.get("materials") or []
                )
                prop_textures = _bundle_texture_sources(
                    prop_obj, scene, "hairprop",
                    {group: None for group in sorted(set(prop_data["materials"]) or {0})}
                )
                for item in prop_textures:
                    item["rendererName"] = core.RENDERER_NAMES["hairprop"]
                textures = list(textures) + prop_textures
                extra_components.append({
                    "component_id": "hairprop", "data": prop_data,
                    "mesh_json": prop_resolved["meshJson"],
                    "skeleton_json": prop_resolved["skeletonJson"],
                    "material_slot_count": prop_slots,
                })
            for item in textures:
                _export_bundle_png(item["source"], bundle_dir / item["filename"])
            source = resolved.get("body") or Path(resolved["meshJson"]).parent.name
            package = core.write_bundle_source(
                output_root, package_id, source, component_id,
                scene.gmi_package_name, scene.gmi_author, data,
                resolved["meshJson"], resolved["skeletonJson"], textures,
                material_slot_count=material_slot_count,
                extra_components=extra_components,
                transparent_materials=transparent_materials,
            )
            if component_id == "hair" and not extra_components:
                self.report({"WARNING"}, "只导出了发型：没指定发饰对象，游戏里发饰还是原版。"
                                         "在「发饰对象」里选上发饰再导一次")
            # Unity 每顶点只能带 4 个影响，第 5 个起被丢掉再归一化 —— 丢多少以前只在
            # 内部变量里，作者看不到。这是 §8.2 「哪些顶点影响变化较大」的可量化那一半。
            truncated = float(data.get("truncated_weight") or 0.0)
            # 每顶点权重和为 1，所以顶点数就是总权重。旧阈值 1% 太松：这个量级的丢失
            # 已经能让相邻顶点绑到不同骨上、接缝张口。收到 0.1%。
            total_weight = max(1, len(data.get("skin") or []))
            if truncated > 0.001 * total_weight:
                self.report({"WARNING"},
                            f"有顶点的影响骨超过 4 个，被截掉的权重合计 {truncated:.1f}"
                            f"（占总权重 {truncated / total_weight:.2%}，"
                            f"顶点 {len(data['skin'])} 个，截掉后会重新归一化）："
                            "那些顶点的形变与你在 Blender 里看到的不完全一致，"
                            "介意就回去把这些顶点的影响骨减到 4 个以内")
            # 坏绑定导出侧补不了，所以只能大声警告并让作者回上游重做 prep。
            if data.get("anchor_only_note"):
                self.report({"WARNING"}, data["anchor_only_note"])
            if _coverage_soft_note[0]:
                self.report({"WARNING"}, _coverage_soft_note[0])
            if _orientation_soft_note[0]:
                self.report({"WARNING"}, _orientation_soft_note[0])
            if data.get("chain_blend_note"):
                self.report({"WARNING"}, data["chain_blend_note"])
            sanity = data.get("bind_sanity") or {}
            if sanity.get("failed"):
                self.report({"WARNING"}, "绑定体检未通过（"
                            + "、".join(sanity["failed"])
                            + "）：该区域动起来会变形，需回 prep 阶段重做，导出侧补不了")
            elif sanity.get("unmeasured"):
                self.report({"WARNING"}, "绑定体检无法评估（"
                            + "、".join(sanity["unmeasured"])
                            + " 没有可测顶点）：作者骨名可能没映射到游戏骨名，别当通过")
            if not self.also_patch:
                self.report({"INFO"}, f"已导出 bundle 源 {package}")
                return {"FINISHED"}
            output_bundle = Path(output_root) / package_id / f"{package_id}.bundle"
            _run_bundle_patch(scene, bundle_dir, output_bundle)
            output_manifest = _publish_runtime_manifest(bundle_dir, output_bundle)
            self.report(
                {"INFO"},
                f"已导出并打包 bundle {output_bundle}；mod.json {output_manifest}",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}


class GMI_OT_create_body_material_template(Operator):
    bl_idname = "gmi.create_body_material_template"
    bl_label = "创建预览材质模板"
    bl_description = "给激活网格创建一个近似游戏渲染的 Blender 材质（挂上 t0/t1/t4 并标注语义），只用于在 Blender 里预览，不影响导出"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _author_mesh(context)
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择要添加材质模板的网格")
            return {"CANCELLED"}
        scene = context.scene
        component_id = _object_component_id(obj, scene)
        target_name = "发饰" if component_id == "hairprop" else "发型" if component_id == "hair" else "身体"
        material = bpy.data.materials.new(f"GMI_{target_name}材质模板")
        material.use_nodes = True
        material["gmi_material_profile"] = component_id
        base_color = _scene_texture_path(scene, component_id, "base_color")
        packed_mask = _scene_texture_path(scene, component_id, "packed_mask")
        shade_color = _scene_texture_path(scene, component_id, "shade_color")
        material["gmi_t0_base_color"] = bpy.path.abspath(base_color) if base_color else ""
        material["gmi_t1_packed_mask"] = bpy.path.abspath(packed_mask) if packed_mask else ""
        material["gmi_t4_shade_color"] = bpy.path.abspath(shade_color) if shade_color else ""
        if component_id == "body":
            material["gmi_co_t0_base_color"] = bpy.path.abspath(scene.gmi_opacity_texture_file) if scene.gmi_opacity_texture_file else ""
            material["gmi_co_t1_packed_mask"] = bpy.path.abspath(scene.gmi_opacity_packed_mask_file) if scene.gmi_opacity_packed_mask_file else ""
            material["gmi_co_t4_shade_color"] = bpy.path.abspath(scene.gmi_opacity_shade_color_file) if scene.gmi_opacity_shade_color_file else ""
        material["gmi_t1_channels"] = (
            "R=阴影阈值, G=光滑度, B=金属度, A=镜面/间接/HHL门控(当前无t6时用0)"
            if component_id in {"hair", "hairprop"}
            else "R=阴影阈值, G=光滑度, B=金属度, A=AO/镜面/间接光门控"
        )
        material["gmi_t4_channels"] = "RGB=基础色暗色版, A=原生sdw二值遮罩"

        nodes = material.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        if principled:
            principled.label = f"游戏{target_name}主材质近似预览"
        textures = [
            (f"{component_id} t0 基础色 / BaseColor", _scene_texture_path(scene, component_id, "base_color"), (-600, 200)),
            (f"{component_id} t1 混合遮罩", _scene_texture_path(scene, component_id, "packed_mask"), (-600, 0)),
            (f"{component_id} t4 暗面材质 / ShadeMap", _scene_texture_path(scene, component_id, "shade_color"), (-600, -200)),
        ]
        if component_id == "body":
            textures.extend((
                ("co t0 基础色 / m_bdyco", scene.gmi_opacity_texture_file, (-950, 200)),
                ("co t1 混合遮罩", scene.gmi_opacity_packed_mask_file, (-950, 0)),
                ("co t4 暗面材质 / ShadeMap", scene.gmi_opacity_shade_color_file, (-950, -200)),
            ))
        for label, path, location in textures:
            node = nodes.new(type="ShaderNodeTexImage")
            node.label = label
            node.name = f"GMI_{label.split()[0]}"
            node.location = location
            if path:
                absolute = bpy.path.abspath(path)
                if Path(absolute).is_file():
                    try:
                        node.image = bpy.data.images.load(absolute, check_existing=True)
                    except RuntimeError:
                        pass
        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)
        self.report({"INFO"}, f"已创建{target_name}预览材质；游戏绑定仍以导出时 t0/t1/t4 为准")
        return {"FINISHED"}


def _compute_vertex_ao(obj, samples=20):
    """对网格逐顶点算几何 AO(BVHTree 半球射线遮蔽),返回 0..1 数组并做百分位拉伸。

    用来重建游戏皮肤那种随形体的柔和光影渐变,替代 flat toon 阈值,避免圆柱体
    (如腿/裤袜)上出现硬光影分界。
    """
    import numpy as np

    deps = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, deps)
    mesh = obj.data
    mw = obj.matrix_world
    nrm = mw.to_3x3().inverted_safe().transposed()
    max_dist = max(obj.dimensions) * 0.12 or 0.2
    eps = max_dist * 0.002

    # 斐波那契半球方向(切空间 +Z)
    ga = np.pi * (3 - np.sqrt(5))
    dirs = []
    for i in range(samples):
        z = (i + 0.5) / samples
        r = np.sqrt(max(0.0, 1 - z * z))
        th = ga * i
        dirs.append((r * np.cos(th), r * np.sin(th), z))

    ao = np.empty(len(mesh.vertices), dtype=np.float32)
    for vi, v in enumerate(mesh.vertices):
        co = mw @ v.co
        n = (nrm @ v.normal).normalized()
        up = Vector((0, 0, 1)) if abs(n.z) < 0.99 else Vector((1, 0, 0))
        t = n.cross(up).normalized()
        b = n.cross(t)
        origin = co + n * eps
        hits = 0
        for dx, dy, dz in dirs:
            wd = t * dx + b * dy + n * dz
            loc, _, _, _ = bvh.ray_cast(origin, wd, max_dist)
            if loc is not None:
                hits += 1
        ao[vi] = 1.0 - hits / samples
    # 百分位拉伸到 [0,1],让渐变用满量程(强度由 form_strength 控制)
    lo, hi = np.percentile(ao, 5), np.percentile(ao, 95)
    if hi - lo > 1e-4:
        ao = np.clip((ao - lo) / (hi - lo), 0.0, 1.0)
    return ao


class GMI_OT_bake_material_maps(Operator):
    bl_idname = "gmi.bake_material_maps"
    bl_label = "按材质生成 t1/t4 并校准肤色"
    bl_description = (
        "按各材质槽标注的「材质类型」实测预设，从基础色 t0 派生 t1/t4 并自动填入导出贴图栏。"
        "需要先填 t0 并给材质槽标好类型；对激活的发饰网格执行会写入发饰贴图栏"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        import numpy as np

        scene = context.scene
        obj = _author_mesh(context)
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择网格")
            return {"CANCELLED"}
        component_id = _object_component_id(obj, scene)
        target_name = "发饰" if component_id == "hairprop" else "发型" if component_id == "hair" else "身体"
        _sync_object_mesh_data(context, obj)
        base_color_file = _scene_texture_path(scene, component_id, "base_color")
        if not base_color_file:
            self.report({"ERROR"}, "需要先指定基础色 t0（t4 从它派生）")
            return {"CANCELLED"}
        mesh = obj.data
        if mesh.uv_layers.active is None:
            self.report({"ERROR"}, "网格缺少 UV，无法按 UV 烘焙")
            return {"CANCELLED"}
        if not obj.material_slots or all(s.material is None for s in obj.material_slots):
            self.report({"ERROR"}, "网格没有材质槽，请先分材质并设置每个材质的「材质类型」")
            return {"CANCELLED"}

        def _load_base_texture(file_path, label):
            path = bpy.path.abspath(file_path)
            if path.lower().endswith(".dds"):
                raise ValueError(f"{label} 请用 PNG（DDS 无法在 Blender 内读像素派生 t4）")
            image = bpy.data.images.load(path, check_existing=False)
            try:
                try:
                    image.colorspace_settings.name = "Non-Color"
                except Exception:
                    pass
                w, h = int(image.size[0]), int(image.size[1])
                if w != h:
                    raise ValueError(f"{label} 需为正方形（当前 {w}x{h}）")
                buffer = np.empty(w * h * 4, dtype=np.float32)
                image.pixels.foreach_get(buffer)
                buffer = np.nan_to_num(buffer, nan=0.0, posinf=1.0, neginf=0.0)
                rgba8 = np.clip(
                    buffer.reshape(h, w, 4)[::-1] * 255.0 + 0.5, 0, 255
                ).astype(np.uint8)  # top-down，与 DDS / UV(1-v) 一致
                return rgba8, w, h
            finally:
                bpy.data.images.remove(image)

        try:
            base8, width, height = _load_base_texture(base_color_file, f"{target_name}基础色 t0")
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}

        mesh.calc_loop_triangles()
        uv = mesh.uv_layers.active.data
        count = len(mesh.loop_triangles)
        tris = np.empty((count, 3, 2), dtype=np.float32)
        mat_ids = np.empty(count, dtype=np.int32)
        vert_tris = np.empty((count, 3), dtype=np.int32)
        for i, lt in enumerate(mesh.loop_triangles):
            for j, loop in enumerate(lt.loops):
                tris[i, j] = uv[loop].uv
            mat_ids[i] = lt.material_index
            vert_tris[i] = lt.vertices

        presets = core.load_material_presets()
        class_per_slot = {
            idx: slot.material.gmi_material_class
            for idx, slot in enumerate(obj.material_slots)
            if slot.material is not None
        }
        toon_per_slot = {
            idx: slot.material.gmi_material_toon
            for idx, slot in enumerate(obj.material_slots)
            if slot.material is not None and slot.material.gmi_material_toon >= 0
        }
        alpha_modes = _material_slot_alpha_modes(obj)
        opaque_slots = [
            idx for idx, slot in enumerate(obj.material_slots)
            if slot.material is not None and alpha_modes.get(idx) != "NATIVE_CO"
        ]
        native_co_slots = sorted(alpha_modes)

        def _slot_triangle_mask(slots):
            if not slots:
                return np.zeros(count, dtype=bool)
            return np.isin(mat_ids, np.asarray(slots, dtype=np.int32))

        def _slot_id_map(slots, size):
            mask = _slot_triangle_mask(slots)
            if not mask.any():
                return np.full((size, size), -1, dtype=np.int16)
            return core.rasterize_material_ids(tris[mask], mat_ids[mask], size, dilate=8)

        def _slot_form_map(slots, size, ao_values):
            mask = _slot_triangle_mask(slots)
            if not mask.any():
                return np.full((size, size), np.nan, dtype=np.float32)
            return core.rasterize_vertex_scalar(tris[mask], ao_values[vert_tris[mask]], size, dilate=8)

        id_map = _slot_id_map(opaque_slots, width)

        # 肤色校准：作者模型的皮肤底色几乎不会正好等于原版，脸/头发用的是原版贴图，
        # 不对齐脖子上就有一道断层。取样按网格 UV（与 core.VANILLA_SKIN_TONE 的测法同
        # 口径），改的是光栅化皮肤区。t4 在下面从 base8 派生，所以会自动跟着修正。
        skin_note = ""
        skin_slots = [idx for idx, cls in class_per_slot.items() if cls == "skin"]
        if scene.gmi_skin_calibrate and skin_slots:
            skin_tris = _slot_triangle_mask(skin_slots)
            skin_area = np.isin(id_map, np.asarray(skin_slots, dtype=np.int16))
            if skin_tris.any() and skin_area.any():
                skin_uv = tris[skin_tris].reshape(-1, 2)
                sy = np.clip(((1.0 - skin_uv[:, 1]) * height).astype(int), 0, height - 1)
                sx = np.clip((skin_uv[:, 0] * width).astype(int), 0, width - 1)
                base8, skin_report = core.calibrate_skin_tone(
                    base8, skin_area, base8[sy, sx, :3])
                if skin_report["calibrated"]:
                    skin_note = (f"；肤色 {skin_report['before']} → {skin_report['after']}"
                                 f"（原版 {skin_report['target']}）")
                else:
                    skin_note = f"；肤色未校准（{skin_report['reason']}）"
            else:
                skin_note = "；肤色未校准（皮肤材质没有 UV 覆盖）"

        form_map = None
        ao = None
        if scene.gmi_form_shading:
            ao = _compute_vertex_ao(obj)
            form_map = _slot_form_map(opaque_slots, width, ao)
        # hair/hairprop 未覆盖区用 A=0 的安全预设，避免原 t6 HHL/间接光从 atlas 空白区漏出。
        neutral_key = "hair" if component_id in {"hair", "hairprop"} else "neutral"
        t1, t4 = core.bake_material_maps(
            id_map, base8, class_per_slot, presets,
            form_map=form_map, form_strength=scene.gmi_form_strength,
            toon_per_slot=toon_per_slot, neutral_key=neutral_key,
        )
        channel_files = {
            0: scene.gmi_t1_r_file,
            1: scene.gmi_t1_g_file,
            2: scene.gmi_t1_b_file,
            3: scene.gmi_t1_a_file,
        }
        channel_maps = {}
        for channel, file_path in channel_files.items():
            if not file_path:
                continue
            resolved = bpy.path.abspath(file_path)
            rgba8, cw, ch = _load_image_rgba8_top_down(resolved)
            if cw != width or ch != height:
                label = core.packed_mask_channel_label(channel)
                self.report(
                    {"ERROR"},
                    f"t1.{label} 通道图尺寸必须等于基础色 atlas（{width}x{height}），当前 {cw}x{ch}",
                )
                return {"CANCELLED"}
            channel_maps[channel] = _rgba8_to_mask_channel(rgba8)
        channel_summary = core.apply_packed_mask_channel_overrides(t1, id_map, channel_maps)

        out = Path(tempfile.gettempdir())
        # Hair 与 HairProp 会在同一场景依次烘焙；固定文件名会让后者覆盖前者。
        bake_prefix = f"gmi_baked_{component_id}"
        t1_path = out / f"{bake_prefix}_packedMask.dds"
        t4_path = out / f"{bake_prefix}_shadeColor.dds"
        co_t1 = co_t4 = None
        co_t1_path = co_t4_path = None
        co_note = ""
        if native_co_slots:
            if not scene.gmi_opacity_texture_file:
                self.report({"ERROR"}, "检测到原生co材质槽，需要先填写 co 基础色 t0 / m_bdyco")
                return {"CANCELLED"}
            try:
                co_base8, co_width, co_height = _load_base_texture(
                    scene.gmi_opacity_texture_file, "co 基础色 t0 / m_bdyco"
                )
            except Exception as exc:
                self.report({"ERROR"}, _error_text(exc))
                return {"CANCELLED"}
            co_id_map = _slot_id_map(native_co_slots, co_width)
            co_form_map = None
            if scene.gmi_form_shading:
                co_form_map = _slot_form_map(native_co_slots, co_width, ao)
            co_t1, co_t4 = core.bake_material_maps(
                co_id_map, co_base8, class_per_slot, presets,
                form_map=co_form_map, form_strength=scene.gmi_form_strength,
                toon_per_slot=toon_per_slot, neutral_key=neutral_key,
            )
            co_t1_path = out / f"{bake_prefix}_co_packedMask.dds"
            co_t4_path = out / f"{bake_prefix}_co_shadeColor.dds"
            co_covered = int((co_id_map >= 0).sum()) * 100 // (co_width * co_height)
            co_note = f"；co {co_covered}% UV 覆盖"

        core.write_rgba8_dds(t1_path, width, height, t1.tobytes(), srgb=False)
        core.write_rgba8_dds(t4_path, width, height, t4.tobytes(), srgb=True)
        if skin_note.startswith("；肤色 "):
            # 校准后的 t0 必须落盘并回填，否则导出仍然用作者原图，只有 t4 被修正。
            # 写 PNG 不写 DDS：_load_base_texture 读不了 DDS 像素。
            t0_path = out / f"{bake_prefix}_baseColor.png"
            image = bpy.data.images.new(
                t0_path.stem, width=width, height=height, alpha=True)
            try:
                # 先设 colorspace 再写像素：赋值会重建缓冲、丢掉已写入的像素（赋同值也一样）。
                try:
                    image.colorspace_settings.name = "sRGB"
                except Exception:
                    pass
                image.pixels.foreach_set(
                    (base8[::-1].astype(np.float32) / 255.0).ravel())  # Blender 像素自下而上
                image.filepath_raw = str(t0_path)
                image.file_format = "PNG"
                image.save()
            finally:
                bpy.data.images.remove(image)
            if component_id == "hairprop":
                scene.gmi_hairprop_base_color_file = str(t0_path)
            else:
                scene.gmi_base_color_file = str(t0_path)
        if component_id == "hairprop":
            scene.gmi_hairprop_packed_mask_file = str(t1_path)
            scene.gmi_hairprop_shade_color_file = str(t4_path)
        else:
            scene.gmi_packed_mask_file = str(t1_path)
            scene.gmi_shade_color_file = str(t4_path)
        if co_t1 is not None and co_t4 is not None:
            core.write_rgba8_dds(co_t1_path, co_width, co_height, co_t1.tobytes(), srgb=False)
            core.write_rgba8_dds(co_t4_path, co_width, co_height, co_t4.tobytes(), srgb=True)
            scene.gmi_opacity_packed_mask_file = str(co_t1_path)
            scene.gmi_opacity_shade_color_file = str(co_t4_path)

        covered = int((id_map >= 0).sum()) * 100 // (width * height)
        used = sorted({presets[c]["label"] for c in class_per_slot.values() if c in presets})
        form_note = "；几何AO软化阴影" if form_map is not None else ""
        channel_note = ""
        if channel_summary["mode"] != "none":
            parts = []
            for label, slots in channel_summary["applied"].items():
                if slots == ["global"]:
                    parts.append(f"{label}=整图")
                elif slots:
                    parts.append(f"{label}=材质{','.join(str(s) for s in slots)}")
                else:
                    parts.append(f"{label}=未覆盖")
            channel_note = f"；通道覆盖：{' / '.join(parts)}"
        self.report(
            {"INFO"},
            f"已生成{target_name} t1/t4（{covered}% UV 覆盖{co_note}；材质：{'、'.join(used)}"
            f"{form_note}{channel_note}{skin_note}）；"
            f"已设为导出 {'t0/t1/t4' if skin_note.startswith('；肤色 ') else 't1/t4'}，可直接校验导出",
        )
        return {"FINISHED"}


# ------------------------------------------------------------------ 骨映射表单
# 作者直接说"哪根源骨对应哪根游戏骨"。preset 退化成预填,认不出来的骨架由作者点选,
# 覆盖率因此不再取决于我们认识多少种命名规范。出口沿用已有的 explicit 通路,
# 所以后端零改动。


class GMI_bone_name(bpy.types.PropertyGroup):
    """prop_search 的候选容器：目标骨架的骨名。"""
    name: bpy.props.StringProperty()


class GMI_bone_map_item(bpy.types.PropertyGroup):
    source: bpy.props.StringProperty(name="源骨")
    # 一行 = 一组（结构分组的成员，换行分隔）。留空 = 这行只管 source 那一根骨。
    # 作者在一行上做的决定落到这一组的每一根骨；要逐根不同就按「拆开这一组」。
    members: bpy.props.StringProperty(options={"HIDDEN"})
    target: bpy.props.StringProperty(
        name="目标骨",
        description="填了就以此为准（优先级最高）；留空=交给自动判断（预设/装饰骨物理）",
    )
    origin: bpy.props.StringProperty()          # preset / auto / ""
    mass: bpy.props.FloatProperty()             # 该骨的权重占比 %
    # 几何全绑在链根、子骨是空的那种链（实测 Lace_R_A0 主导 97 顶点、Lace_R_Aend 0 个）：
    # 链根按原版是惰性锚，照拓扑出参数 = 装了摇物也不会动。勾上让链根按链中段的参数自己摆。
    # **逐行**而不是全局开关：同一个模型里，靴口花边要摆、腰侧挂坠要焊死，是两个决定。
    # 「几何全在链根」是**几何事实**（与策略无关），生成表单时算一次存在行上，
    # UI 就能一直标黄，而不是等到导出后在状态栏闪一句 WARNING。
    anchor_only: bpy.props.BoolProperty(default=False, options={"HIDDEN"})
    swing_anchor: bpy.props.BoolProperty(
        name="链根自己摆",
        description="只对「自建摇物链」有意义。这一组的几何全在链根上时，"
                    "不勾=链根是惰性锚、这条链在游戏里不会动；勾上=链根自己摆",
        default=False)
    strategy: bpy.props.EnumProperty(
        name="装饰物理",
        description="只对没填目标骨的装饰骨有效。自动=跟源父骨（胸/Bust 按 Bust*_S）；"
                    "刚性=跟最近的已映射身体父骨，不摆，最安全；"
                    "自建摇物=新建骨+自己的摆动链（飘带/蝴蝶结）；"
                    "跟裙摆=蹭最近的裙摆摇物骨（裙边花边）；"
                    "跟随最近骨骼=跟最近的目标摇物骨，过远则安全回退到父骨",
        items=[
            ("auto", "自动", "跟源父骨；胸/Bust 名称按 Bust*_S，异常件用覆盖策略"),
            ("rigid", "刚性跟父骨", "无物理，跟最近的已映射身体父骨——不确定时选它"),
            ("integrate", "自建摇物链", "新建骨 + 自己的摆动物理；飘带/蝴蝶结用这个。2026-08-11 已实机确认可用，手感（幅度）仍在调"),
            ("follow_skirt", "跟裙摆", "蹭最近的裙摆摇物骨（裙边花边），无视距离"),
            ("follow_nearest", "跟随最近骨骼",
             "跟随最近的目标摇物骨；超过安全距离时改为刚性跟父骨"),
            ("native_driver", "原版布料驱动器",
             "新建骨 + 挂学马自己的布料驱动器（裙→Skirt、披挂→Frill、袖→HumanoidSleeve），"
             "不用摇物物理。参数取自 530 套原版；只支持这三类——Waist/Furisode/Poncho 的参考骨"
             "是每套服装自己的 *_O 偏移骨，装到别的服装上只会得到空引用"),
            # bake / reject 只能**追加在末尾**：EnumProperty 不写数字时按顺序编号，
            # 已存盘的 .blend 里存的是那个整数，插在中间会把老文件的策略整排错位
            # （blender_ui_smoke 里那条 legacy 断言就是为这个立的）。
            ("bake", "烘焙形变+并到父骨",
             "静态装饰骨用这个：先把它造成的**静止形变**烘进网格，再像刚性一样并到父骨。"
             "破坏性操作，要点「烘焙静止形变」按钮才真的改网格；改前自动存一份 "
             "GMI_PRE_BAKE 形态键，随时能退回去。没烘就导出会被拦下"),
            ("reject", "拒绝导出",
             "这根骨处理不了，**禁止导出**：点导出会被拦下并点名它。"
             "用在「还没想清楚怎么办、但绝不能静默出包」的骨上"),
        ],
        default="auto",
    )
    swing_category: bpy.props.EnumProperty(
        name="部件类型",
        description="只对「自建摇物链」的骨有效。决定摆动参数取原版哪一档，以及要不要建 "
                    "ActorSwingChain——530 套原版实测：裙类 94% 挂链、飘带绳结类只有 2.6%。"
                    "自动=按骨名猜（认不出来按飘带处理，最保守）。"
                    "选中链上任意一根即对整条链生效",
        items=[
            ("auto", "自动", "按骨名猜；认不出来按飘带（自由悬垂、不建链）"),
            ("ribbon", "飘带 / 蝴蝶结", "自由悬垂，不建链——原版的飘带绳结就是这样"),
            ("cloth", "披风 / 褶边 / 领腰", "建链，比裙摆轻"),
            ("sleeve", "袖口", "原版用 Slide 型，限位很紧"),
            ("skirt", "裙 / 裤 / 外套下摆", "建链 + 环形碰撞，最重"),
        ],
        default="auto",
    )


def _bone_map_context(context):
    """表单要用的三样：作者网格、目标骨名表、预设映射结果。"""
    obj = _author_mesh(context)
    scene = context.scene
    if not obj or obj.type != "MESH" or not obj.vertex_groups:
        raise ValueError("请先激活带顶点组权重的作者网格")
    component_id = _object_component_id(obj, scene)
    resolved = _resolve_body_json_library(scene, component_id)
    skeleton_path = Path(resolved.get("skeletonJson") or "")
    if not skeleton_path.is_file():
        raise ValueError("缺少带骨架的 Mesh JSON；请先完成步骤①的配置档")
    bone_map = core.inverse_skin_bone_map(
        bpy.path.abspath(scene.gmi_profile_dir), skeleton_path, component_id)
    source_names = [g.name for g in obj.vertex_groups if _is_bone_group(g.name)]
    preset = core.build_bone_remap(
        source_names, bone_map, parent_by_name=_source_bone_parents(obj),
        preset_name=getattr(scene, "gmi_source_rig", "auto"),
    )
    return obj, bone_map, preset


class GMI_OT_build_bone_map(Operator):
    bl_idname = "gmi.build_bone_map"
    bl_label = "扫描源骨骼"
    bl_description = ("列出作者网格上带权重的骨。预设认出来的自动预填目标骨，"
                      "认不出来的留空等你指定。已填写的行不会被覆盖")

    only_unmapped: bpy.props.BoolProperty(default=True, options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        try:
            obj, bone_map, preset = _bone_map_context(context)
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}
        kept = dict(_form_bone_map(scene))          # 保住作者已经填过的
        kept_strategy = dict(_form_physics_overrides(scene))
        kept_category = dict(_form_swing_categories(scene))
        scene.gmi_bone_targets.clear()
        for name in sorted(bone_map):
            scene.gmi_bone_targets.add().name = name

        # 装饰骨按结构并成组（一行一组）；身体骨仍然一行一根 —— 它们本来就被预设填好了，
        # 而且承重关节要能逐根点。分组信号一个骨名都不读，见 core.structural_bone_groups。
        mass_by_name = dict(_weighted_group_mass(obj))
        dominant_counts = _dominant_group_counts(obj)
        weighted = [name for name, _mass in _weighted_group_mass(obj)]
        body = set(preset["bodyBones"]) | set(kept)
        groups = core.structural_bone_groups(weighted, _source_bone_parents(obj), body)
        rows = [[name] for name in weighted if name in body]
        rows += [group["members"] for group in groups]
        rows.sort(key=lambda members: -max(mass_by_name.get(name, 0.0) for name in members)
                  if members else 0.0)

        scene.gmi_bone_map.clear()
        listed = 0
        for members in rows:
            autos = {preset["bones"].get(name) for name in members}
            auto = autos.pop() if len(autos) == 1 else None
            touched = any(name in kept or name in kept_strategy for name in members)
            if self.only_unmapped and auto and not touched:
                continue                            # 预设已认出且作者没改过 → 不占屏
            item = scene.gmi_bone_map.add()
            item.source = max(members, key=lambda name: mass_by_name.get(name, 0.0))
            item.members = "\n".join(members)
            item.target = next((kept[name] for name in members if name in kept), auto or "")
            item.origin = "preset" if auto else ""
            item.mass = sum(mass_by_name.get(name, 0.0) for name in members)
            item.anchor_only = bool(core.anchor_only_roots(
                members, _source_bone_parents(obj), dominant_counts))
            strategy = next((kept_strategy[name] for name in members
                             if name in kept_strategy), None)
            if strategy:
                item.strategy = strategy
            category = next((kept_category[name] for name in members
                             if name in kept_category), None)
            if category:
                item.swing_category = category
            listed += 1
        scene.gmi_bone_map_index = 0
        undecided = sum(1 for item in scene.gmi_bone_map
                        if core.row_state(item.target, item.strategy) == "undecided")
        scope = "未被预设识别的" if self.only_unmapped else "全部"
        self.report({"INFO"}, f"已列出 {listed} 行{scope}骨（{len(weighted)} 根骨并成 "
                              f"{len(rows)} 行；预设识别 {len(preset['bones'])} 根，"
                              f"待决定 {undecided} 行）")
        return {"FINISHED"}


class GMI_OT_split_bone_group(Operator):
    bl_idname = "gmi.split_bone_group"
    bl_label = "拆开这一组"
    bl_description = "把这一行（一组骨）拆成一行一根骨，逐根单独指定；组里的决定原样带过去"

    index: bpy.props.IntProperty(default=-1, options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        index = self.index if self.index >= 0 else scene.gmi_bone_map_index
        if not 0 <= index < len(scene.gmi_bone_map):
            self.report({"ERROR"}, "没有选中的行")
            return {"CANCELLED"}
        item = scene.gmi_bone_map[index]
        members = row_bones(item)
        if len(members) < 2:
            self.report({"INFO"}, "这行只有一根骨，不用拆")
            return {"CANCELLED"}
        kept = (item.target, item.strategy, item.swing_category, item.origin)
        kept_anchor = bool(item.swing_anchor)
        # remove() 之后 item 是野指针，用到的值必须先取出来
        fallback_mass = item.mass / len(members)
        obj = _author_mesh(context)
        mass_by_name = (dict(_weighted_group_mass(obj))
                        if obj and obj.type == "MESH" and obj.vertex_groups else {})
        # 「几何全在链根」是逐根的事实：拆开后只有真正的链根该继续标黄，中段骨不标。
        anchor_only_roots = set()
        if obj and obj.type == "MESH" and obj.vertex_groups:
            anchor_only_roots = set(core.anchor_only_roots(
                members, _source_bone_parents(obj), _dominant_group_counts(obj)))
        scene.gmi_bone_map.remove(index)
        for offset, name in enumerate(members):
            new = scene.gmi_bone_map.add()
            new.source = name
            new.members = name
            new.target, new.strategy, new.swing_category, new.origin = kept
            new.swing_anchor = kept_anchor
            new.anchor_only = name in anchor_only_roots
            new.mass = mass_by_name.get(name, fallback_mass)
            scene.gmi_bone_map.move(len(scene.gmi_bone_map) - 1, index + offset)
        scene.gmi_bone_map_index = index
        self.report({"INFO"}, f"已拆成 {len(members)} 行")
        return {"FINISHED"}


def _vertex_influences(obj, remap=None):
    """逐顶点 {目标骨名: 权重}。`remap` 给了就按映射折算，不给就当顶点组名已是目标骨名。"""
    names = {group.index: group.name for group in obj.vertex_groups}
    for vertex in obj.data.vertices:
        row = {}
        for item in vertex.groups:
            name = names.get(item.group)
            if item.weight <= 0.0 or not _is_bone_group(name):
                continue
            target = (remap or {}).get(name, name)
            row[target] = row.get(target, 0.0) + item.weight
        yield row


def _target_parent_names(skeleton):
    nodes = skeleton.get("nodes") or []
    return {str(node.get("name")): (str(nodes[int(node.get("parent", -1))].get("name"))
                                    if 0 <= int(node.get("parent", -1)) < len(nodes) else None)
            for node in nodes if node.get("name")}


def _collect_rest_alignment(obj, armature, skeleton, remap, body_bones):
    """(source_positions, target_positions, children, lengths) —— 尺子和导出闸门共用同一份。

    全部换算到**目标骨名 + Unity 空间**；游戏骨位置用 `bindPose` 求逆，不按层级累加。
    朝向的子骨关系取**游戏骨架**的，且只取同样被 direct 映射到的骨 —— 把衣物骨算进去会
    把方向拽反（事实文档 §6.2 坑 4）。
    """
    target_positions = _target_bone_positions(skeleton)
    source_positions, lengths = {}, {}
    for name in body_bones:
        target = remap.get(name)
        bone = armature.data.bones.get(name) if armature else None
        if bone is None or target not in target_positions:
            continue
        source_positions[target] = core._to_unity(armature.matrix_world @ bone.head_local)
        lengths[target] = bone.length
    children = {}
    for name, parent in _target_parent_names(skeleton).items():
        if name in source_positions and parent in source_positions:
            children.setdefault(parent, []).append(name)
    return source_positions, target_positions, children, lengths


# 朝向闸门降黄条之后要有地方把话说出去：raise 那条路没了，作者就什么都看不到。
_orientation_soft_note = [None]
_coverage_soft_note = [None]


def _error_text(exc):
    """给作者看的异常文案。`str(exc)` 可能是空的（`KeyError()`、`IndexError()` 之类），
    直接 report 出去就是一个**空的红叉** —— 作者什么线索都没有，只能来问。
    空的时候退回异常类型名，并把完整 traceback 打到系统控制台。
    """
    traceback.print_exc()
    text = str(exc).strip()
    if text:
        return text
    return (f"{type(exc).__name__}（异常没有附带消息，完整调用栈见系统控制台："
            "Window ▸ Toggle System Console）")


def _mesh_signed_volume(obj):
    """网格的有符号体积（m³）。负 = 面朝里，见 core.inverted_mesh_error。"""
    mesh = obj.data
    total = 0.0
    for polygon in mesh.polygons:
        loops = polygon.vertices
        first = mesh.vertices[loops[0]].co
        for index in range(1, len(loops) - 1):
            second = mesh.vertices[loops[index]].co
            third = mesh.vertices[loops[index + 1]].co
            total += first.dot(second.cross(third))
    return total / 6.0


def _chain_node_map(new_bones):
    """{骨名: (链号, 节号)} —— 链号取链根骨名，节号 = 到链根的深度。"""
    parent_of = {item["name"]: item.get("parentName") for item in new_bones or ()}
    node_of = {}
    for name in parent_of:
        depth, current, guard = 0, name, 0
        while parent_of.get(current) in parent_of and guard < 512:
            current = parent_of[current]; depth += 1; guard += 1
        node_of[name] = (current, depth)
    return node_of


def _vanilla_chain_node_map(armature):
    """原版衣物骨（`*_S`）的 {骨名: (链号, 节号)}，给跨节过渡带当基线。"""
    if armature is None:
        return {}
    members = {bone.name for bone in armature.data.bones if bone.name.endswith("_S")}
    node_of = {}
    for bone in armature.data.bones:
        if bone.name not in members:
            continue
        depth, current = 0, bone
        while current.parent is not None and current.parent.name in members:
            current = current.parent; depth += 1
        node_of[bone.name] = (current.name, depth)
    return node_of


def _mirrored_side_error(obj, skeleton, remap, report):
    """P4 闸门 6.5：左右整个装反了 → 返回报错文案，否则 None。

    必须排在承重关节（闸门 2）和静止朝向（闸门 7）之前：那两道报出来的都是这个的症状，
    先撞上哪道作者就去修哪道，修的全是错的地方。见 core.mirrored_side_error。
    """
    armature = next((modifier.object for modifier in obj.modifiers
                     if modifier.type == "ARMATURE" and modifier.object), None)
    if armature is None:
        return None
    source_positions, target_positions, _children, _lengths = _collect_rest_alignment(
        obj, armature, skeleton, remap, report.get("bodyBones") or [])
    return core.mirrored_side_error(source_positions, target_positions)


def _rest_orientation_error(obj, skeleton, remap, report):
    """P4 闸门 7：任何 direct 映射骨的静止朝向差到红档 → 返回报错文案，否则 None。

    位置差**不拦**（lossless 把它当重定向吸收，"免的是位置"）；朝向差会 1:1 显示在游戏里：
    肩差 172° 的包静止截图完全正常，转身之后手臂转到身后、手指拉成面条。
    """
    armature = next((modifier.object for modifier in obj.modifiers
                     if modifier.type == "ARMATURE" and modifier.object), None)
    if armature is None:
        return None
    rows = core.rest_alignment(*_collect_rest_alignment(
        obj, armature, skeleton, remap, report.get("bodyBones") or []))
    # 只拦有实测背书的那一段（≥45°，坏样本实测 52°~172°）。15°~45° 是 7° 与 52° 之间
    # 那个从没验证过的空档，报黄条 + 留痕，不拦 —— 见 core.ORIENTATION_BLOCK_DEG。
    over = [row for row in rows
            if row["deg"] is not None and row["deg"] >= core.ORIENTATION_FAIL_DEG]
    bad = [row for row in over if row["deg"] >= core.ORIENTATION_BLOCK_DEG]
    soft = [row for row in over if row["deg"] < core.ORIENTATION_BLOCK_DEG]
    if soft:
        _orientation_soft_note[0] = (
            f"{len(soft)} 根骨的静止朝向在 {core.ORIENTATION_FAIL_DEG:.0f}°~"
            f"{core.ORIENTATION_BLOCK_DEG:.0f}° 之间，**没有拦**你导出："
            + "、".join(f"{row['bone']} {row['deg']:.0f}°(对 {row['child']})"
                        for row in soft[:6])
            + ("…" if len(soft) > 6 else "")
            + "。这一段没有实测背书：验过的坏样本是 52°~172°，验过的正常样本是 0°~7°，"
              "中间这段谁也没验过。进游戏转身看看这几处，觉得不对再回来摆。")
    else:
        _orientation_soft_note[0] = None
    if not bad:
        return None
    detail = "、".join(f"{row['bone']} {row['deg']:.0f}°(对 {row['child']})" for row in bad[:6])
    return (f"{len(bad)} 根身体骨的静止朝向和游戏骨差得太多（阈值 "
            f"{core.ORIENTATION_FAIL_DEG:.0f}°）：{detail}"
            + ("…" if len(bad) > 6 else "")
            + "。这个角度会 1:1 显示在游戏里：静止截图看着正常，转身之后那块几何整个转过去"
              "（实机三次坐实，肩差 172° → 手臂到身后、手指拉成面条）。请在 Blender 里把这些骨"
              "摆到游戏骨的朝向上（点「量对齐 / 跨关节带」逐骨看差多少），再导出。")


def mirror_mesh_x(mesh):
    """把一个网格沿 X 镜像：顶点、全部形态键、绕序、自定义拆分法线。

    **自定义法线必须按 `(面号, 顶点号)` 对号，不能按 loop 顺序。** `flip_normals()` 反转
    绕序时会把每个面内部的 loop 顺序也反过来；拿反转前的 loop 顺序写回，等于把每个角的
    法线安到别的角上 —— 静止画面看着"法线还是朝外的"，实际是 90% 的共享顶点法线分裂，
    进游戏就是整片三角面阴影。这个坑实测踩过一次（91092 个共享顶点全裂）。
    """
    pre = None
    if mesh.has_custom_normals:
        pre = {(polygon.index, mesh.loops[loop].vertex_index): tuple(mesh.loops[loop].normal)
               for polygon in mesh.polygons for loop in polygon.loop_indices}
    for vertex in mesh.vertices:
        vertex.co.x = -vertex.co.x
    if mesh.shape_keys:
        for block in mesh.shape_keys.key_blocks:
            for point in block.data:
                point.co.x = -point.co.x
    mesh.flip_normals()          # 镜像翻了面朝向，反转绕序翻回来
    if pre is not None:
        normals = [None] * len(mesh.loops)
        for polygon in mesh.polygons:
            for loop in polygon.loop_indices:
                n = pre[(polygon.index, mesh.loops[loop].vertex_index)]
                normals[loop] = (-n[0], n[1], n[2])
        mesh.normals_split_custom_set(normals)
    mesh.update()


def mirror_armature_x(armature_object):
    """把骨架沿 X 镜像：编辑模式直接改 head/tail/roll，不碰物体变换。

    **不能用「选中物体 → S X -1 → 应用缩放」**：作者网格通常是骨架的子物体，父子变换
    互相抵消，做偶数次等于没做。实测作者手动做了三次，净效果为零。
    """
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for bone in armature_object.data.edit_bones:
            head, tail, roll = bone.head.copy(), bone.tail.copy(), bone.roll
            bone.head = (-head.x, head.y, head.z)
            bone.tail = (-tail.x, tail.y, tail.z)
            bone.roll = -roll
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = previous


class GMI_OT_mirror_model(Operator):
    bl_idname = "gmi.mirror_model"
    bl_label = "沿 X 镜像整个模型"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = ("把作者网格和它的骨架一起沿 X 镜像。走标准导入器进来的源（MMD / FBX /"
                      "各种 rip）左右都和游戏参照骨架相反，必须镜像一次。"
                      "直接改数据，不用物体缩放——网格是骨架的子物体时，"
                      "「选中两个 → S X -1 → 应用缩放」父子会互相抵消，做几次都等于没做")

    def execute(self, context):
        scene = context.scene
        obj = _author_mesh(context)
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请先在阶段 2 选好作者网格")
            return {"CANCELLED"}
        armature = next((modifier.object for modifier in obj.modifiers
                         if modifier.type == "ARMATURE" and modifier.object), None)
        if armature is None:
            self.report({"ERROR"}, "作者网格没有骨架修改器，镜像了骨架也跟不上")
            return {"CANCELLED"}
        # 同一副骨架驱动的网格要一起镜像（发型 + 发饰这种），否则剩下的那个就分家了
        meshes = [item for item in bpy.data.objects
                  if item.type == "MESH" and any(
                      modifier.type == "ARMATURE" and modifier.object is armature
                      for modifier in item.modifiers)]
        try:
            for item in meshes:
                mirror_mesh_x(item.data)
            mirror_armature_x(armature)
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}
        names = "、".join(item.name for item in meshes[:3])
        self.report({"INFO"},
                    f"已沿 X 镜像：骨架 {armature.name}，网格 {len(meshes)} 个（{names}"
                    + ("…" if len(meshes) > 3 else "")
                    + "）。顶点、形态键、绕序、自定义法线都处理了；"
                      "再点一次就镜像回去。回到导出页重跑闸门确认")
        return {"FINISHED"}


class GMI_OT_split_weight_from_neighbours(Operator):
    bl_idname = "gmi.split_weight_from_neighbours"
    bl_label = "从相邻骨劈权重"
    bl_description = ("给源模型没有的承重关节（锁骨/脖子/脚尖等）劈出权重：按原版身体在同一位置"
                      "的权重分布，从旁边那圈骨里分。只动这几根骨，不重绘全身权重；"
                      "要求先把模型对齐到参考骨架")

    # 只在原版有这根骨权重的地方动手，所以搜索半径按"作者顶点离原版表面多远"算。
    # 超过这个距离就不是同一块肉，宁可不动（对齐没做好时整批跳过，日志说清楚）。
    search_radius: bpy.props.FloatProperty(
        name="搜索半径(m)", default=0.03, min=0.001, max=0.2, options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        obj = _author_mesh(context)
        try:
            _obj, bone_map, _preset = _bone_map_context(context)
            reference = _profile_weight_reference(context, "body")
            remap, report = _resolve_source_bone_remap(obj, bone_map, scene)
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}
        weighted = [name for name, _mass in _weighted_group_mass(obj)]
        missing = core.missing_critical_bones(weighted, remap, bone_map)
        if not missing:
            self.report({"INFO"}, "21 根承重关节都已经有权重，不需要劈")
            return {"CANCELLED"}

        from mathutils import kdtree
        vanilla_world = reference.matrix_world
        vanilla = [
            {group_name: item.weight
             for item in vertex.groups
             for group_name in (reference.vertex_groups[item.group].name,)
             if item.weight > 0.0}
            for vertex in reference.data.vertices
        ]
        tree = kdtree.KDTree(len(reference.data.vertices))
        for index, vertex in enumerate(reference.data.vertices):
            tree.insert(vanilla_world @ vertex.co, index)
        tree.balance()

        # 作者顶点 → 目标骨权重（按 remap 合并），以及"这个目标骨的权重是从哪些源组来的"
        source_of = {}
        for group in obj.vertex_groups:
            target = remap.get(group.name)
            if target:
                source_of.setdefault(target, []).append(group)
        world = obj.matrix_world
        distances, moved, touched = [], {}, 0
        for vertex in obj.data.vertices:
            _co, nearest, distance = tree.find(world @ vertex.co)
            distances.append(distance)
            if nearest is None or distance > self.search_radius:
                continue
            reference_weights = vanilla[nearest]
            # 顶点上现有的源组权重取一次就够：`VertexGroup.weight()` 对不在组里的顶点会
            # 抛异常并往日志里刷 "Vertex not in group"，逐顶点查等于刷屏。
            current = {item.group: float(item.weight) for item in vertex.groups}
            author = {}
            for group_index, weight in current.items():
                target = remap.get(obj.vertex_groups[group_index].name)
                if target and weight > 0.0:
                    author[target] = author.get(target, 0.0) + weight
            for bone in missing:
                if bone not in reference_weights:
                    continue
                updated = core.redistribute_family_weight(author, reference_weights, bone)
                if not updated:
                    continue
                touched += 1
                for target, value in updated.items():
                    author[target] = value                      # 同顶点多根缺骨时逐次生效
                    if target == bone:
                        moved[bone] = moved.get(bone, 0.0) + value
                    _write_target_weight(obj, vertex.index, target, value,
                                         source_of, current)
        distances.sort()
        median_mm = distances[len(distances) // 2] * 1000.0 if distances else 0.0
        if not moved:
            self.report({"ERROR"},
                        f"一个顶点都没动：作者网格离参考体中位 {median_mm:.0f}mm，"
                        f"超过搜索半径 {self.search_radius * 1000:.0f}mm 就不是同一块肉了。"
                        "先把模型对齐到参考骨架（步骤①导入的那副），再劈权重")
            return {"CANCELLED"}
        detail = "、".join(f"{bone} {mass:.1f}" for bone, mass in sorted(moved.items()))
        self.report({"INFO"},
                    f"已从相邻骨劈出 {len(moved)} 根骨的权重（{touched} 个顶点被改；"
                    f"劈到的权重总量 {detail}；作者网格离参考体中位 {median_mm:.1f}mm）。"
                    "只动了这几根骨所在的那一族，别的权重原样")
        return {"FINISHED"}


def _write_target_weight(obj, vertex_index, target, value, source_of, current):
    """把"目标骨的新权重"写回作者网格的源顶点组：按源组现有比例分摊；缺骨就新建同名组。

    `current` = 这个顶点上 {顶点组下标: 权重}（调用方已经取好，别再逐组去查）。
    """
    groups = source_of.get(target)
    if not groups:
        group = obj.vertex_groups.get(target) or obj.vertex_groups.new(name=target)
        source_of[target] = [group]
        groups = [group]
    if len(groups) == 1:
        groups[0].add([vertex_index], value, "REPLACE")
        return
    weights = [current.get(group.index, 0.0) for group in groups]
    total = sum(weights)
    for group, weight in zip(groups, weights):
        share = (weight / total) if total > 0.0 else (1.0 / len(groups))
        group.add([vertex_index], value * share, "REPLACE")


# 回退用的原坐标存在对象自定义属性里，**不用形态键**：加了形态键之后网格的显示/求值走的是
# 形态键而不是 `mesh.vertices`，改完 co 反而"看不见变化"，导出读的又是另一份 —— 那是个陷阱。
BAKE_SNAPSHOT_KEY = "gmi_pre_bake"
# 烘焙前后位移小于这个数就当"本来就没形变"，不写网格（对齐好的模型多数属于这一档）。
BAKE_FLOOR_MM = 0.05


def _bake_rest_offsets(obj, armature, bake_bones, remap, target_rest):
    """算 bake 骨造成的静止形变，返回逐顶点修正量 {顶点号: 世界空间向量}。空 = 不需要烘。

    两项相加，都是**实测有意义**的：

    1. **当前姿势**（`pose_matrix · rest⁻¹`）。导出器读的是 `mesh.vertices`（静止），作者在
       视图里看到的是摆过姿势之后的样子 —— 摆了姿势直接导出，出包的是没摆的那个形状，
       画面上完全看不出哪一步丢了。这才是这条路线里真实存在的"静止形变"；
    2. **父目标骨自己的错位**（`G_P · S_P⁻¹`）。bake 骨没有自己的目标骨，权重并到父目标骨 P 之后
       那些顶点按 P 的骨摆出去。**P 对齐好时这一项恒等于零**（2026-08-17 用原版身体量过：
       给装饰骨加 5cm 偏移，这一项仍是 0.000mm —— 装饰骨自己的变换根本不进这条公式）。
       所以它只在 P 本身没对齐时才有值，量级与「对齐体检」里 P 那一行的位置差一致。
    """
    world = obj.matrix_world
    groups = {group.index: group.name for group in obj.vertex_groups}
    offsets = {}
    for name in bake_bones:
        bone = armature.data.bones.get(name)
        group = obj.vertex_groups.get(name)
        if bone is None or group is None:
            continue
        # 父目标骨：沿源父链找第一根映射到游戏骨的
        parent, target = bone.parent, None
        while parent is not None:
            candidate = remap.get(parent.name)
            if candidate in target_rest:
                target = candidate
                break
            parent = parent.parent
        if target is None:
            continue
        # 两边都在 Blender 世界空间：`reference_rest_world` 已经换算过，别再 conjugate 一次
        source_rest = armature.matrix_world @ armature.data.bones[parent.name].matrix_local
        skinning = target_rest[target] @ source_rest.inverted()
        # 当前姿势：作者看到的形状 vs 导出读到的静止形状
        pose_bone = armature.pose.bones.get(name)
        pose = Matrix.Identity(4)
        if pose_bone is not None:
            rest = armature.matrix_world @ bone.matrix_local
            pose = (armature.matrix_world @ pose_bone.matrix) @ rest.inverted()
        for vertex in obj.data.vertices:
            weight = next((item.weight for item in vertex.groups
                           if groups.get(item.group) == name), 0.0)
            if weight <= 0.0:
                continue
            position = world @ vertex.co
            delta = (pose @ position - position) + (position - skinning @ position)
            if delta.length > 0.0:
                offsets[vertex.index] = offsets.get(vertex.index, Vector()) + delta * weight
    return offsets


class GMI_OT_bake_rest_offset(Operator):
    bl_idname = "gmi.bake_rest_offset"
    bl_label = "烘焙静止形变"
    bl_description = ("把标了「烘焙形变+并到父骨」的骨造成的静止形变烘进网格，之后那些骨的权重"
                      "并到父骨也不会让几何跳位。破坏性操作：改网格前会存一份 GMI_PRE_BAKE "
                      "形态键，随时能退回去")

    revert: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        obj = _author_mesh(context)
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请先激活作者网格")
            return {"CANCELLED"}
        snapshot = obj.get(BAKE_SNAPSHOT_KEY)
        if self.revert:
            if not snapshot:
                self.report({"ERROR"}, "这个网格没有烘焙记录，没有可回退的东西")
                return {"CANCELLED"}
            restored = json.loads(snapshot)
            for index, x, y, z in restored:
                obj.data.vertices[int(index)].co = Vector((x, y, z))
            obj.data.update()
            del obj[BAKE_SNAPSHOT_KEY]
            obj["gmi_baked_rest_offset"] = 0
            self.report({"INFO"}, f"已回退 {len(restored)} 个顶点到烘焙前的位置")
            return {"FINISHED"}
        if snapshot:
            self.report({"ERROR"},
                        "这个网格已经烘过一次（回退记录还在）。要重烘先点「回退烘焙」——"
                        "连着烘两次等于把形变叠两遍")
            return {"CANCELLED"}

        bake_bones = [name for item in scene.gmi_bone_map if item.strategy == "bake"
                      for name in row_bones(item)]
        if not bake_bones:
            self.report({"ERROR"}, "没有标成「烘焙形变+并到父骨」的骨；先在骨骼映射表里标")
            return {"CANCELLED"}
        try:
            _obj, bone_map, _preset = _bone_map_context(context)
            resolved = _resolve_body_json_library(scene, _object_component_id(obj, scene))
            skeleton = core.load_json(Path(resolved["skeletonJson"]))
            remap, _report = _resolve_source_bone_remap(obj, bone_map, scene)
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}
        armature = next((modifier.object for modifier in obj.modifiers
                         if modifier.type == "ARMATURE" and modifier.object), None)
        if armature is None:
            self.report({"ERROR"}, "作者网格没有骨架修改器，算不了静止形变")
            return {"CANCELLED"}

        target_rest = {name: matrix for name, matrix
                       in reference_rest_world_by_name(skeleton).items()}
        offsets = _bake_rest_offsets(obj, armature, bake_bones, remap, target_rest)
        moved = [offset.length * 1000.0 for offset in offsets.values()]
        worst = max(moved) if moved else 0.0
        if worst <= BAKE_FLOOR_MM:
            obj["gmi_baked_rest_offset"] = 1                 # 声明过了：形变本来就没有
            self.report({"INFO"},
                        f"{len(bake_bones)} 根 bake 骨造成的静止形变最大只有 {worst:.3f}mm"
                        f"（阈值 {BAKE_FLOOR_MM}mm），网格没有改动 —— 直接并到父骨就行")
            return {"FINISHED"}

        # 破坏性一步（INV-7 可见 / 可关 / 可量化 / 可撤销）：先把要动的顶点原坐标存下来，再改网格
        obj[BAKE_SNAPSHOT_KEY] = json.dumps(
            [[index, *obj.data.vertices[index].co] for index in sorted(offsets)],
            separators=(",", ":"))
        inverse = obj.matrix_world.inverted()
        for index, offset in offsets.items():
            vertex = obj.data.vertices[index]
            vertex.co = inverse @ ((obj.matrix_world @ vertex.co) + offset)
        obj.data.update()
        obj["gmi_baked_rest_offset"] = 1
        average = sum(moved) / len(moved)
        self.report({"INFO"},
                    f"已烘焙 {len(offsets)} 个顶点（{len(bake_bones)} 根 bake 骨）："
                    f"位移最大 {worst:.2f}mm、平均 {average:.2f}mm。"
                    "回退记录已存在对象上，点「回退烘焙」可原样退回")
        return {"FINISHED"}


def reference_rest_world_by_name(skeleton):
    """{骨名: 静止世界矩阵（Blender 空间）} —— `reference_rest_world` 的按名字版。"""
    nodes = skeleton.get("nodes") or []
    world = reference_rest_world(nodes)
    return {str(node.get("name")): world[index]
            for index, node in enumerate(nodes) if node.get("name")}


class GMI_OT_report_rig_alignment(Operator):
    bl_idname = "gmi.report_rig_alignment"
    bl_label = "量对齐 / 跨关节带"
    bl_description = ("只读尺子：逐骨报关节位置差与**静止朝向差**，并把跨关节权重带和原版"
                      "逐关节对比。朝向差是作者唯一自查不到的东西——静止截图完全正常，"
                      "转身之后手臂炸开、手指变面条")

    def execute(self, context):
        scene = context.scene
        obj = _author_mesh(context)
        try:
            _obj, bone_map, _preset = _bone_map_context(context)
            resolved = _resolve_body_json_library(scene, _object_component_id(obj, scene))
            skeleton = core.load_json(Path(resolved["skeletonJson"]))
        except Exception as exc:
            self.report({"ERROR"}, _error_text(exc))
            return {"CANCELLED"}
        armature = next((modifier.object for modifier in obj.modifiers
                         if modifier.type == "ARMATURE" and modifier.object), None)
        if armature is None:
            self.report({"ERROR"}, "作者网格没有骨架修改器，量不了对齐")
            return {"CANCELLED"}
        # 传 skeleton：解析要和导出**同一份**——没解析的源骨（扭转骨、装饰骨）会经装饰物理/
        # 父骨兜底落到某根身体骨上，那些权重照样进跨关节带。只按身体骨映射去量，Claymore 那副
        # rip 的跨肩带会报 0.0%（实际 4.9%）——扭转骨的权重全被漏掉。
        remap, report = _resolve_source_bone_remap(obj, bone_map, scene, skeleton)

        # 对齐尺：只量 direct 映射的身体骨（装饰骨蹭的是摇物骨，位置差按设计就很大）
        collected = _collect_rest_alignment(
            obj, armature, skeleton, remap, report["bodyBones"])
        alignment = core.rest_alignment(*collected)
        mirrored = core.mirrored_side_pairs(collected[0], collected[1])

        # 跨关节带：有参考体就现算原版基线，没有就用扫出来的真值表。
        sides = core.joint_band_sides(_target_parent_names(skeleton))
        bands = core.cross_joint_bands(_vertex_influences(obj, remap), sides)
        try:
            reference = _profile_weight_reference(context)
        except ValueError:
            reference = None
        vanilla = (core.cross_joint_bands(_vertex_influences(reference), sides)
                   if reference is not None else None)
        findings = core.cross_joint_band_findings(bands, vanilla)

        # 权重报告（§8.2）：多少权重是原样保留的、多少并进了别的骨、多少走了新建辅助骨
        states = core.weight_state_summary(
            dict(_weighted_group_mass(obj)), remap,
            new_bones=[item.get("name") for item
                       in (report.get("newBones") or {}).get("newBones") or []],
            unmapped=report.get("unmapped") or [])
        # 档 3：节数不同被塌短的链 —— 每根骨都有目标、权重也归一，闸门永远抓不到，只能标出来
        collapsed = core.collapsed_chains(remap, _source_bone_parents(obj),
                                          dict(_weighted_group_mass(obj)))
        scene.gmi_rig_report = json.dumps({
            "alignment": alignment, "bands": findings, "states": states,
            "collapsed": collapsed, "mirrored": mirrored,
            "measured": len(alignment), "skipped": len(report["bodyBones"]) - len(alignment),
            "baseline": "参考体" if vanilla else "原版真值表",
        }, ensure_ascii=False, separators=(",", ":"))
        worst = alignment[0] if alignment else None
        self.report({"INFO"}, (
            f"已量 {len(alignment)} 根 direct 映射骨"
            + (f"；最差 {worst['bone']} 朝向 {core.format_degrees(worst['deg'])} "
               f"/ 位置 {worst['mm']:.1f}mm" if worst else "")
            + f"；跨关节带 " + "  ".join(
                f"{row['joint']} {row['share']:.1%}(原版 {row['vanilla']:.1%})"
                for row in findings)))
        return {"FINISHED"}


class GMI_OT_show_bone_weights(Operator):
    bl_idname = "gmi.show_bone_weights"
    bl_label = "查看骨骼权重"
    bl_description = "选中源骨骼并在作者模型上高亮它实际影响的权重"

    source: bpy.props.StringProperty(options={"HIDDEN"})

    def execute(self, context):
        obj = _author_mesh(context)
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请先激活作者模型")
            return {"CANCELLED"}
        group = obj.vertex_groups.get(self.source)
        armature = next(
            (modifier.object for modifier in obj.modifiers
             if modifier.type == "ARMATURE" and modifier.object), None
        )
        bone = armature.data.bones.get(self.source) if armature else None
        if not group or not armature or not bone:
            self.report({"ERROR"}, f"找不到源骨骼或顶点组：{self.source}")
            return {"CANCELLED"}
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for selected in context.selected_objects:
            selected.select_set(False)
        for selected_bone in armature.data.bones:
            selected_bone.select = False
        bone.select = True
        armature.data.bones.active = bone
        armature.select_set(True)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj.vertex_groups.active_index = group.index
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        self.report({"INFO"}, f"已高亮 {self.source} 的权重")
        return {"FINISHED"}


class GMI_OT_clear_bone_map(Operator):
    bl_idname = "gmi.clear_bone_map"
    bl_label = "清空映射表"
    bl_description = "清空表单（不影响外部骨骼映射 JSON）"

    def execute(self, context):
        context.scene.gmi_bone_map.clear()
        context.scene.gmi_bone_targets.clear()
        self.report({"INFO"}, "已清空骨骼映射表")
        return {"FINISHED"}


class GMI_OT_save_bone_map(Operator):
    bl_idname = "gmi.save_bone_map"
    bl_label = "存为 JSON"
    bl_description = "把表单里填好的对应关系存成骨骼映射 JSON，换模型/换目标服装时可复用"

    def execute(self, context):
        scene = context.scene
        bones = _form_bone_map(scene)
        physics = _form_physics_overrides(scene)
        categories = _form_swing_categories(scene)
        if not bones and not physics:
            self.report({"ERROR"}, "表单里还没有填写任何目标骨或装饰物理策略")
            return {"CANCELLED"}
        path = bpy.path.abspath(scene.gmi_bone_remap_file) if scene.gmi_bone_remap_file else ""
        if not path:
            output = bpy.path.abspath(scene.gmi_output_dir) or bpy.app.tempdir
            path = str(Path(output) / "bone-remap.json")
            scene.gmi_bone_remap_file = path
        # 骨映射和装饰物理写同一份文件:两个读取入口各取自己的键。"physics" 必须写出来
        # (哪怕是空的),否则物理读取会 fallback 成整个 dict、把 bones 当策略用。
        core._write_json(Path(path), {
            "schemaVersion": 2, "bones": bones, "physics": physics,
            "swingCategories": categories,
        })
        if physics:
            scene.gmi_physics_override_file = path
        self.report({"INFO"}, f"已存 {len(bones)} 条骨映射 + {len(physics)} 条装饰物理 + "
                              f"{len(categories)} 条部件类型到 {path}")
        return {"FINISHED"}


class GMI_OT_load_bone_map(Operator):
    bl_idname = "gmi.load_bone_map"
    bl_label = "从 JSON 读入"
    bl_description = "把骨骼映射 JSON 读进表单，方便核对和微调"

    def execute(self, context):
        scene = context.scene
        path = bpy.path.abspath(scene.gmi_bone_remap_file)
        if not path or not Path(path).is_file():
            self.report({"ERROR"}, "请先在「骨骼映射」里选择 JSON 文件")
            return {"CANCELLED"}
        data = core.load_json(Path(path))
        bones = data.get("bones", data)
        physics = data.get("physics", {}) if isinstance(data, dict) else {}
        categories = data.get("swingCategories", {}) if isinstance(data, dict) else {}
        enum_ids = lambda prop: {item.identifier for item in
                                 GMI_bone_map_item.bl_rna.properties[prop].enum_items}
        valid, valid_categories = enum_ids("strategy"), enum_ids("swing_category")
        hit = 0
        for item in scene.gmi_bone_map:
            # 一行 = 一组：组里任一成员命中就算这一行命中（组内决定本来就是同一个）
            pick = lambda table: next((table[name] for name in row_bones(item)
                                       if name in table), None)
            # 部件类型是策略的附属，两者可以同时命中同一行 —— 别用 elif 把它挤掉
            if pick(categories) in valid_categories:
                item.swing_category = pick(categories)
            if pick(bones) is not None:
                item.target = str(pick(bones))
                hit += 1
            elif pick(physics) in valid:
                item.strategy = pick(physics)
                hit += 1
        self.report({"INFO"}, f"读入 {len(bones)} 条骨映射 + {len(physics)} 条装饰物理 + "
                              f"{len(categories)} 条部件类型，命中表内 {hit} 行")
        return {"FINISHED"}



CLASSES = (
    GMI_bone_name,
    GMI_bone_map_item,
    GMI_OT_build_bone_map,
    GMI_OT_split_bone_group,
    GMI_OT_report_rig_alignment,
    GMI_OT_mirror_model,
    GMI_OT_split_weight_from_neighbours,
    GMI_OT_bake_rest_offset,
    GMI_OT_show_bone_weights,
    GMI_OT_clear_bone_map,
    GMI_OT_save_bone_map,
    GMI_OT_load_bone_map,
    GMI_OT_extract_profile_from_frame_dump,
    GMI_OT_build_full_profile,
    GMI_OT_update_profile_from_frame_dump,
    GMI_OT_resolve_body_json_library,
    GMI_OT_import_profile_object,
    GMI_OT_import_reference,
    GMI_OT_import_weighted_reference,
    GMI_OT_prepare_target,
    GMI_OT_activate_author_object,
    GMI_OT_export_bundle_source,
    GMI_OT_create_body_material_template,
    GMI_OT_bake_material_maps,
)
