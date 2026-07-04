import json
import tempfile
from pathlib import Path

import bpy
from bpy.types import Operator


def _png_to_dds(image_path):
    """把 PNG/其它图像转成未压缩 RGBA8_UNORM_SRGB 的 DDS（DX10 头），返回临时 DDS 路径。

    用 Blender 自带图像 API 读取(无需外部工具);设为 Non-Color，让存储的 sRGB 字节
    原样写入 DDS，再以 _SRGB 格式标记，使游戏采样结果与原 BC7_UNORM_SRGB 一致。
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
        rgba8 = np.clip(rgba * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
        output = Path(tempfile.gettempdir()) / f"gmi_{Path(image_path).stem}.dds"
        core.write_rgba8_dds(output, width, height, rgba8.tobytes(), srgb=True)
        return str(output)
    finally:
        bpy.data.images.remove(image)


def _prepare_cover_image(path, max_dim=1024):
    """预览图过大时用 Blender 缩到 ≤max_dim 边长并存临时 PNG；否则原样返回。"""
    try:
        image = bpy.data.images.load(path, check_existing=False)
    except RuntimeError as exc:
        raise ValueError(f"无法读取预览图：{exc}")
    try:
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            raise ValueError(f"预览图尺寸无效：{path}")
        if max(width, height) <= max_dim:
            return path
        scale = max_dim / max(width, height)
        image.scale(max(1, int(width * scale)), max(1, int(height * scale)))
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix="gmi_cover_")
        handle.close()
        image.filepath_raw = handle.name
        image.file_format = "PNG"
        image.save()
        return handle.name
    finally:
        bpy.data.images.remove(image)


def _neutral_material_dds(semantic):
    """生成临时的中性 t1/t4 DDS，盖掉游戏原版遮罩/阴影对新贴图的干扰。"""
    rgba = core.NEUTRAL_PACKED_MASK if semantic == "packedMask" else core.NEUTRAL_SHADE_COLOR
    output = Path(tempfile.gettempdir()) / f"gmi_neutral_{semantic}.dds"
    core.write_solid_rgba8_dds(output, rgba)
    return str(output)
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import core, weight_transfer


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


def _resolve_body_json_library(scene):
    profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
    # 已补全的配置档自带 Reference（真实或合成骨架），优先用它，与资源库解耦。
    if profile_dir:
        ref = core.resolve_profile_reference(profile_dir)
        if ref:
            scene.gmi_source_mesh_json = ref["meshJson"]
            scene.gmi_skeleton_json = ref["skeletonJson"]
            return ref
    library_dir = bpy.path.abspath(scene.gmi_body_json_library_dir)
    if not library_dir:
        raise ValueError("请先选择 Body JSON资源库目录")
    result = core.resolve_body_json_resource(profile_dir, library_dir, scene.gmi_component_id)
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


def _profile_weight_reference(context):
    references = [
        obj for obj in context.scene.objects
        if obj.type == "MESH" and obj.get("gmi_weighted_reference")
    ]
    if not references:
        raise ValueError("请先导入带权重参考模型")
    if len(references) > 1:
        raise ValueError("场景中存在多个带权重参考模型，请只保留一个")
    return references[0]


def _world_bounds(obj):
    """Return world-space AABB (min, max), center and diagonal length for an object."""
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lo, hi, (lo + hi) * 0.5, (hi - lo).length


def _check_transfer_alignment(target, reference):
    """Guard the one-click weight transfer against a misaligned author mesh.

    The inverse-skin operator and the per-frame recovered matrices live in the
    reference body's bind space. If the author mesh does not overlap the reference
    at a comparable size, both the nearest-surface weights and the exported bind
    positions (export bakes ``matrix_world @ co``) will be wrong. So a clear hard
    error here is far better than silently producing a broken Mod.

    Returns a list of soft warnings; raises ValueError on a hard misalignment.
    """
    ref_lo, ref_hi, ref_center, ref_diag = _world_bounds(reference)
    tgt_lo, tgt_hi, tgt_center, tgt_diag = _world_bounds(target)
    if ref_diag <= 1e-6 or tgt_diag <= 1e-6:
        raise ValueError("参考身体或作者模型的包围盒为空，无法判断对齐情况")

    # 1. Size: HSKI body and the author body should be roughly the same scale.
    ratio = tgt_diag / ref_diag
    if ratio < 0.5 or ratio > 2.0:
        raise ValueError(
            f"作者模型尺寸与参考身体相差过大（比例 {ratio:.2f}，应在 0.5~2.0 之间）。"
            "请把模型缩放到与参考身体接近，并按 Ctrl+A 应用缩放后再传权。"
        )

    # 2. Position: centers must be close and the bounding boxes must overlap.
    center_offset = (tgt_center - ref_center).length
    if center_offset > 0.5 * ref_diag:
        raise ValueError(
            f"作者模型与参考身体未对齐（中心偏移 {center_offset:.3f} m，"
            f"参考身体对角线 {ref_diag:.3f} m）。请把模型移动到与参考身体重合后再传权。"
        )
    if any(tgt_hi[i] < ref_lo[i] or tgt_lo[i] > ref_hi[i] for i in range(3)):
        raise ValueError("作者模型的包围盒与参考身体没有重叠，请先对齐后再传权。")

    # 3. Soft warning: unapplied transform is the most common cause of the above.
    warnings = []
    _, rotation, scale = target.matrix_basis.decompose()
    if any(abs(component - 1.0) > 1e-3 for component in scale) or rotation.angle > 1e-3:
        warnings.append(
            "作者模型存在未应用的缩放/旋转，建议先按 Ctrl+A 应用变换，避免法线翻转和尺寸误差"
        )
    return warnings


def _select_vertex_group(context, obj, group_name):
    group = obj.vertex_groups.get(group_name)
    if not group:
        raise ValueError(f"找不到顶点组：{group_name}")
    group_index = group.index
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    selected_count = 0
    for vertex in obj.data.vertices:
        selected = any(item.group == group_index and item.weight > 0.0 for item in vertex.groups)
        vertex.select = selected
        selected_count += 1 if selected else 0
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="VERT")
    return selected_count


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
        # 唯一的透明路径:原生co(NATIVE_CO)走游戏原生第二材质段(m_bdyco)。
        # 旧的镂空/半透明自建 pass 已移除,旧工程里的这些值统一回退到不透明。
        if mode in {"NATIVE_CO", "NATIVE_SECTION", "CO"}:
            result[index] = "NATIVE_CO"
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
        # synthesis sees the same texels as tools/synthesize_mod_mcolors.py.
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
    def _nib(value):
        return max(0, min(15, int(round(value))))

    # 原版描边色逐通道曲线(实测自两套服装 0628outfit + saki):描边色 = 基础色经一条
    # 「暗化 + 越亮越暖」曲线 —— R 随基础R 明显上升(亮处达 ~4/15),G/B 偏低(~1-2/15)。
    # 效果:暗/中性面→暗灰线;亮/白面→暗线偏暖;肤色→棕。整体偏暗,不是高饱和红。
    # 曲线改陡(实测锚点 saki:灰0.55→R nibble~1、米0.99→~5):R 用 5.0×base^2.7 → 灰面保持
    # 暗(~1/15,和原版灰衣一致、对比足)、亮/米面才提到 ~5/15(暖)。G/B 保持低平(原版亦如此)。
    OUTLINE_GAIN = 1.0   # 整体微调:实机整体偏弱调>1,偏强调<1
    materials = data.get("materials", [])
    color_per_slot = color_per_slot or {}
    colors = []
    encoded = 0
    for index in range(len(tgt_uv)):
        br = min(1.0, max(0.0, float(tgt_rgb[index][0])))
        bg = min(1.0, max(0.0, float(tgt_rgb[index][1])))
        bb = min(1.0, max(0.0, float(tgt_rgb[index][2])))
        r_high = _nib(OUTLINE_GAIN * 5.0 * br ** 2.7)
        r_low = _nib(OUTLINE_GAIN * 1.50 * bg ** 0.41)
        g_high = _nib(OUTLINE_GAIN * 1.50 * bb ** 0.86)
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
        if group_name.startswith("GMI_"):
            continue
        mapped_name = remap.get(group_name, automatic_remap.get(group_name, group_name))
        if mapped_name not in bone_map:
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
            color = color_per_slot.get(int(polygon.material_index), GMI_CLOTH_COLOR_FLOAT)
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
            key = (
                round(position[0], 5), round(position[1], 5), round(position[2], 5),
                int(polygon.material_index),
            )
            tangent_groups.setdefault(key, []).append(expanded_index)
        faces.append(tuple(face))
    if unresolved and not fallback_bone:
        sample = ", ".join(sorted(unresolved)[:12])
        raise ValueError(f"Unmapped weighted bones ({len(unresolved)}): {sample}")
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
        "materials": materials,
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


def _create_armature(context, mesh_obj, data):
    skeleton = data["skeleton"]
    nodes = skeleton["nodes"]
    weighted = {node["weightedIndex"]: node for node in nodes if node["weightedIndex"] is not None}
    conversion = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    armature = bpy.data.armatures.new(f"{data['name']}_Armature")
    armature_obj = bpy.data.objects.new(armature.name, armature)
    context.collection.objects.link(armature_obj)
    context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_by_index = {}
    world_by_index = {}
    for weighted_index in sorted(weighted):
        node = weighted[weighted_index]
        world = conversion @ _bind_pose_matrix(node["bindPose"]).inverted() @ conversion.inverted()
        world_by_index[weighted_index] = world
        bone = armature.edit_bones.new(node["name"])
        bone.head = world.translation
        axis = world.to_3x3() @ Vector((0.0, 0.05, 0.0))
        if axis.length < 1e-5:
            axis = Vector((0.0, 0.05, 0.0))
        bone.tail = bone.head + axis.normalized() * 0.05
        edit_by_index[weighted_index] = bone
    node_by_list_index = {i: node for i, node in enumerate(nodes)}
    for weighted_index, node in weighted.items():
        parent_node_index = node["parent"]
        while parent_node_index >= 0:
            parent_node = node_by_list_index[parent_node_index]
            parent_weighted = parent_node["weightedIndex"]
            if parent_weighted is not None:
                edit_by_index[weighted_index].parent = edit_by_index[parent_weighted]
                break
            parent_node_index = parent_node["parent"]
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
    bl_label = "导入配置档对象"
    bl_description = "按当前配置档一次导入抓帧参考、带权重原模型和基础复核顶点组"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        profile_dir, capture_dir, _ = _scene_paths(scene)
        try:
            profile_set = core.load_profile_set(profile_dir)
            profile = profile_set["profile"]
            component = core.component_by_id(profile, scene.gmi_component_id)
            resolved = _resolve_body_json_library(scene)
            mesh_path = Path(resolved["meshJson"])
            skeleton_path = Path(resolved["skeletonJson"])

            reference_collection = _collection(context, "GMI_配置档参考")
            author_collection = _collection(context, "GMI_作者模型")
            export_collection = _collection(context, "GMI_导出对象")
            export_collection["gmi_profile_id"] = profile["id"]
            export_collection["gmi_component_id"] = scene.gmi_component_id

            reference_data = core.read_reference(profile_dir, scene.gmi_component_id, capture_dir)
            reference_obj = _create_mesh(context, f"GMI_{scene.gmi_component_id}_抓帧参考", reference_data)
            reference_obj["gmi_profile_id"] = profile["id"]
            reference_obj["gmi_profile_dir"] = str(profile_set["root"])
            reference_obj["gmi_component_id"] = scene.gmi_component_id
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
            weighted_obj["gmi_component_id"] = scene.gmi_component_id
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
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_resolve_body_json_library(Operator):
    bl_idname = "gmi.resolve_body_json_library"
    bl_label = "解析 Body JSON资源库"
    bl_description = "根据当前配置档自动匹配 assetstudio-body-json 中的原模型 JSON 和骨架 JSON"
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
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_extract_profile_from_frame_dump(Operator):
    bl_idname = "gmi.extract_profile_from_frame_dump"
    bl_label = "从抓帧生成配置档"
    bl_description = "扫描 FrameAnalysis 抓帧目录，自动识别 Body 的 Draw/VB/IB/贴图绑定并生成 runtime-only 配置档"

    def execute(self, context):
        scene = context.scene
        capture_dir = bpy.path.abspath(scene.gmi_capture_dir)
        output_dir = bpy.path.abspath(scene.gmi_extract_output_dir)
        if not capture_dir:
            self.report({"ERROR"}, "请先选择 FrameAnalysis 抓帧目录")
            return {"CANCELLED"}
        if not scene.gmi_body_json_library_dir:
            self.report({"ERROR"}, "请先选择 Body JSON资源库目录")
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
                )
                expected_vertex_counts = hints["vertexCounts"]
                entry = hints["exact"]
                if entry:
                    expected_vertex_count = entry.get("vertexCount")
            report = core.extract_profile_from_frame_dump(
                capture_dir,
                output_dir,
                component_id=scene.gmi_component_id,
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
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_build_full_profile(Operator):
    bl_idname = "gmi.build_full_profile"
    bl_label = "一键生成完整配置档"
    bl_description = "从抓帧目录 + Body JSON资源库 一次生成 ①注入信息 ②结构数据 ③逆算子 的完整配置档"

    def execute(self, context):
        scene = context.scene
        capture_dir = bpy.path.abspath(scene.gmi_capture_dir)
        library_dir = bpy.path.abspath(scene.gmi_body_json_library_dir)
        if not capture_dir:
            self.report({"ERROR"}, "请先填写抓帧目录")
            return {"CANCELLED"}
        if not library_dir:
            self.report({"ERROR"}, "请先填写 Body JSON资源库目录")
            return {"CANCELLED"}
        try:
            output_dir = bpy.path.abspath(scene.gmi_extract_output_dir)
            if not output_dir:
                output_dir = str(Path(capture_dir) / "GakumasMI-profile")
            component_id = scene.gmi_component_id
            expected_vertex_count = None
            expected_vertex_counts = []
            if scene.gmi_body_resource:
                hints = core.body_json_vertex_hints(library_dir, scene.gmi_body_resource)
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
            # ②结构数据 + ③逆算子（可选指定 Body 以消歧）
            report = core.complete_inverse_skin_profile(
                output_dir, library_dir, component_id,
                body_resource=(scene.gmi_body_resource or None),
            )
            scene.gmi_profile_dir = output_dir
            naming = "骨架名" if report["boneNaming"] == "skeleton" else "骨骼hash(合成骨架)"
            self.report(
                {"INFO"},
                f"完整配置档已生成 → {output_dir}；匹配 {report['body']}（{report['match']}，{naming}），"
                f"{report['vertexCount']} 顶点 / {report['weightedBoneCount']} 骨骼，"
                f"逆算子 {report['operatorBytes'] // 1024} KB，不可观测骨 {len(report['unobservableBones'])} 根",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_update_profile_from_frame_dump(Operator):
    bl_idname = "gmi.update_profile_from_frame_dump"
    bl_label = "更新配置档抓帧源"
    bl_description = "扫描当前 FrameAnalysis 抓帧目录，校验 VB/IB/贴图 hash，并写入配置档"

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
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_import_reference(Operator):
    bl_idname = "gmi.import_reference"
    bl_label = "导入抓帧参考模型"
    bl_description = "导入配置档中的抓帧组件，并保留原始顶点编号"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        profile_dir, capture_dir, _ = _scene_paths(scene)
        try:
            data = core.read_reference(profile_dir, scene.gmi_component_id, capture_dir)
            component = data["component"]
            obj = _create_mesh(context, f"GMI_{scene.gmi_component_id}_参考", data)
            obj["gmi_profile_id"] = data["profile_set"]["profile"]["id"]
            obj["gmi_profile_dir"] = str(data["profile_set"]["root"])
            obj["gmi_component_id"] = scene.gmi_component_id
            obj["gmi_source_vertex_count"] = component["vertices"]
            obj["gmi_source_index_count"] = component.get("indices", len(data["faces"]) * 3)
            obj["gmi_source_ib_hash"] = component["ibHash"]
            obj["gmi_reference_only"] = True
            self.report({"INFO"}, f"已导入 {len(data['vertices'])} 个顶点 / {len(data['faces'])} 个三角面")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_import_weighted_reference(Operator):
    bl_idname = "gmi.import_weighted_reference"
    bl_label = "导入带权重参考模型"
    bl_description = "导入原始 Unity 网格、四权重、绑定姿势和参考骨架"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            profile_set = core.load_profile_set(bpy.path.abspath(scene.gmi_profile_dir))
            resolved = _resolve_body_json_library(scene)
            mesh_path = Path(resolved["meshJson"])
            skeleton_path = Path(resolved["skeletonJson"])
            data = core.read_weighted_reference(
                mesh_path, skeleton_path,
            )
            obj = _create_mesh(context, f"GMI_{data['name']}_带权重参考", data)
            armature = _create_armature(context, obj, data)
            profile = profile_set["profile"]
            component = core.component_by_id(profile, scene.gmi_component_id)
            obj["gmi_profile_id"] = profile["id"]
            obj["gmi_profile_dir"] = bpy.path.abspath(scene.gmi_profile_dir)
            obj["gmi_component_id"] = scene.gmi_component_id
            obj["gmi_source_vertex_count"] = component["vertices"]
            obj["gmi_source_index_count"] = component["indices"]
            obj["gmi_source_ib_hash"] = component["ibHash"]
            obj["gmi_weighted_reference"] = True
            obj["gmi_blend_shape_data_present"] = bool(data.get("shapes"))
            self.report({"INFO"}, f"已导入 {data['vertex_count']} 个顶点 / {len(armature.data.bones)} 个带权重骨骼")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_transfer_profile_weights(Operator):
    bl_idname = "gmi.transfer_profile_weights"
    bl_label = "从配置档传递权重 + 颜色"
    bl_description = "用 HSKI 配置档插值权重，并按顶点 COLOR 策略写入游戏打包材质参数"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            reference = _profile_weight_reference(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        # 优先用"激活对象";若它不是网格(或正好是参考模型本身),退用"唯一选中的非参考网格"。
        target = context.active_object
        if not (target and target.type == "MESH") or target is reference:
            candidates = [obj for obj in context.selected_objects
                          if obj.type == "MESH" and obj is not reference]
            if len(candidates) == 1:
                target = candidates[0]
                context.view_layer.objects.active = target
            elif len(candidates) > 1:
                self.report({"ERROR"}, "选中了多个网格，请只激活作者模型那一个")
                return {"CANCELLED"}
            else:
                self.report({"ERROR"}, "请把作者模型网格设为激活对象（在 3D 视图里点一下模型本体，别选参考模型）")
                return {"CANCELLED"}
        try:
            alignment_warnings = _check_transfer_alignment(target, reference)
            old_names = {group.index: group.name for group in target.vertex_groups}
            old_dominant = []
            for vertex in target.data.vertices:
                values = [
                    (float(item.weight), old_names[item.group])
                    for item in vertex.groups if item.weight > 0.0 and item.group in old_names
                ]
                old_dominant.append(max(values)[1] if values else "")

            for modifier in list(target.modifiers):
                if modifier.type == "ARMATURE":
                    target.modifiers.remove(modifier)
            target.vertex_groups.clear()
            for group in reference.vertex_groups:
                target.vertex_groups.new(name=group.name)
            transfer = target.modifiers.new(name="GMI_传递配置档权重", type="DATA_TRANSFER")
            transfer.object = reference
            transfer.use_vert_data = True
            transfer.data_types_verts = {"VGROUP_WEIGHTS"}
            transfer.vert_mapping = "POLYINTERP_NEAREST"
            transfer.layers_vgroup_select_src = "ALL"
            transfer.layers_vgroup_select_dst = "NAME"
            transfer.mix_mode = "REPLACE"
            transfer.mix_factor = 1.0
            context.view_layer.objects.active = target
            target.select_set(True)
            reference.select_set(False)
            result = bpy.ops.object.modifier_apply(modifier=transfer.name)
            if "FINISHED" not in result:
                raise RuntimeError(f"权重传递修改器执行失败：{result}")

            corrected = {}
            zero, truncated = _normalize_profile_weights(target, maximum=4)
            # 转权时写中性衣物 COLOR 占位;真正的描边色在导出时按基础色生成
            # (勾选「描边色取自基础色」→ _synthesize_export_native_colors 覆盖)。
            color_transferred = _set_constant_color_attribute(target)
            context.view_layer.objects.active = target
            risk = _write_weight_risk_attributes(
                target, reference, context.scene.gmi_transfer_risk_distance, old_dominant
            )
            target["gmi_profile_weights"] = True
            target["gmi_profile_id"] = reference.get("gmi_profile_id", "")
            target["gmi_profile_dir"] = reference.get("gmi_profile_dir", "")
            target["gmi_component_id"] = reference.get("gmi_component_id", "body")
            report = {
                "method": "POLYINTERP_NEAREST",
                "source": reference.name,
                "target": target.name,
                "vertices": len(target.data.vertices),
                "zeroWeightVertices": zero,
                "truncatedWeightTotal": truncated,
                "semanticCorrections": corrected,
                "alignmentWarnings": alignment_warnings,
                "colorTransferred": color_transferred,
                **risk,
            }
            target["gmi_weight_report"] = json.dumps(report, separators=(",", ":"))
            if zero:
                raise ValueError(f"仍有 {len(zero)} 个顶点没有权重")
            messages = [
                f"已传递配置档权重 + COLOR 占位(描边色在导出时按基础色生成)；"
                f"需复核 {risk['reviewVertices']} 个顶点，"
                f"p95 {risk['p95Distance']:.4f} m，最大 {risk['maxDistance']:.4f} m"
            ]
            messages.extend(alignment_warnings)
            level = {"WARNING"} if (risk["reviewVertices"] or alignment_warnings) else {"INFO"}
            self.report(level, "；".join(messages))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_transfer_profile_weights_smart(Operator):
    bl_idname = "gmi.transfer_profile_weights_smart"
    bl_label = "实验：智能传递权重 + 颜色"
    bl_description = "实验性：用法线闸门 + Laplacian inpaint 替代最近面传权，减少薄缝跨面串权重"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            reference = _profile_weight_reference(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        target = context.active_object
        if not (target and target.type == "MESH") or target is reference:
            candidates = [
                obj for obj in context.selected_objects
                if obj.type == "MESH" and obj is not reference
            ]
            if len(candidates) == 1:
                target = candidates[0]
                context.view_layer.objects.active = target
            elif len(candidates) > 1:
                self.report({"ERROR"}, "选中了多个网格，请只激活作者模型那一个")
                return {"CANCELLED"}
            else:
                self.report({"ERROR"}, "请把作者模型网格设为激活对象（在 3D 视图里点一下模型本体，别选参考模型）")
                return {"CANCELLED"}
        try:
            import numpy as np

            _sync_object_mesh_data(context, reference)
            _sync_object_mesh_data(context, target)
            alignment_warnings = _check_transfer_alignment(target, reference)
            old_names = {group.index: group.name for group in target.vertex_groups}
            old_dominant = []
            for vertex in target.data.vertices:
                values = [
                    (float(item.weight), old_names[item.group])
                    for item in vertex.groups if item.weight > 0.0 and item.group in old_names
                ]
                old_dominant.append(max(values)[1] if values else "")

            for modifier in list(target.modifiers):
                if modifier.type == "ARMATURE":
                    target.modifiers.remove(modifier)

            source_pos, source_nrm = _object_vertex_arrays(reference)
            target_pos, target_nrm = _object_vertex_arrays(target)
            target_faces = np.asarray(_mesh_triangles(target.data), dtype=np.int64)
            if target_faces.size == 0:
                raise ValueError("作者模型没有可用于 inpaint 的三角面")
            groups, source_weights = _source_weight_matrix(reference)
            result = weight_transfer.smart_weight_transfer(
                target_pos, target_nrm, target_faces,
                source_pos, source_nrm, source_weights,
                max_distance=context.scene.gmi_transfer_risk_distance,
                normal_cos_threshold=0.0,
                inpaint_iterations=256,
                max_influences=4,
            )

            target.vertex_groups.clear()
            _write_weight_matrix(target, groups, result["weights"])
            zero, truncated = _normalize_profile_weights(target, maximum=4)
            color_transferred = _set_constant_color_attribute(target)
            context.view_layer.objects.active = target
            risk = _write_weight_risk_attributes(
                target, reference, context.scene.gmi_transfer_risk_distance, old_dominant
            )
            target["gmi_profile_weights"] = True
            target["gmi_profile_id"] = reference.get("gmi_profile_id", "")
            target["gmi_profile_dir"] = reference.get("gmi_profile_dir", "")
            target["gmi_component_id"] = reference.get("gmi_component_id", "body")
            smart_stats = result["stats"]
            report = {
                "method": "SMART_NORMAL_GATE_LAPLACIAN_INPAINT",
                "source": reference.name,
                "target": target.name,
                "vertices": len(target.data.vertices),
                "zeroWeightVertices": zero,
                "truncatedWeightTotal": truncated,
                "alignmentWarnings": alignment_warnings,
                "colorTransferred": color_transferred,
                "smartTransfer": smart_stats,
                **risk,
            }
            target["gmi_weight_report"] = json.dumps(report, separators=(",", ":"))
            if zero:
                raise ValueError(f"仍有 {len(zero)} 个顶点没有权重")
            messages = [
                f"实验智能传权完成；置信 {smart_stats['confidentVertices']}/"
                f"{smart_stats['vertices']}，inpaint {smart_stats['inpaintedVertices']}，"
                f"法线改写 {smart_stats['normalRedirected']}；",
                f"需复核 {risk['reviewVertices']} 个顶点，"
                f"p95 {risk['p95Distance']:.4f} m，最大 {risk['maxDistance']:.4f} m",
            ]
            messages.extend(alignment_warnings)
            level = {"WARNING"} if (risk["reviewVertices"] or alignment_warnings) else {"INFO"}
            self.report(level, "；".join(messages))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_select_high_risk_vertices(Operator):
    bl_idname = "gmi.select_high_risk_vertices"
    bl_label = "选择高风险顶点"
    bl_description = "选中当前作者模型中的 GMI_REVIEW_HIGH_RISK 顶点组，方便 Weight Paint 复核"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择已经传权的作者模型")
            return {"CANCELLED"}
        try:
            count = _select_vertex_group(context, obj, "GMI_REVIEW_HIGH_RISK")
            self.report({"WARNING"} if count else {"INFO"}, f"已选择 {count} 个高风险顶点")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_validate_mesh(Operator):
    bl_idname = "gmi.validate_mesh"
    bl_label = "校验模组"
    bl_description = "校验当前网格是否满足安全导出条件"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择一个网格对象")
            return {"CANCELLED"}
        _sync_object_mesh_data(context, obj)
        if obj.get("gmi_profile_weights"):
            try:
                profile_set = core.load_profile_set(obj["gmi_profile_dir"])
                component = core.component_by_id(
                    profile_set["profile"], obj.get("gmi_component_id", "body")
                )
                known = set(core.inverse_skin_bone_map(obj["gmi_profile_dir"]))
                group_names = {group.index: group.name for group in obj.vertex_groups}
                errors, warnings = [], []
                if any(len(poly.vertices) != 3 for poly in obj.data.polygons):
                    errors.append("网格尚未三角化")
                loop_count = sum(len(poly.vertices) for poly in obj.data.polygons)
                if loop_count > 65535:
                    warnings.append(f"{loop_count} 个展开顶点超过 R16 上限 65535，导出将使用 R32 索引缓冲")
                if loop_count > int(component["indices"]):
                    warnings.append(f"{loop_count} 个索引超过原 Draw 容量 {component['indices']}，导出将使用自定义 drawindexed")
                unknown, zero, excessive, non_normalized = set(), 0, 0, 0
                for vertex in obj.data.vertices:
                    influences = [
                        (group_names[item.group], float(item.weight))
                        for item in vertex.groups
                        if item.weight > 0.0 and not group_names[item.group].startswith("GMI_")
                    ]
                    unknown.update(name for name, _ in influences if name not in known)
                    if not influences:
                        zero += 1
                    if len(influences) > 4:
                        excessive += 1
                    if influences and abs(sum(weight for _, weight in influences) - 1.0) > 1e-4:
                        non_normalized += 1
                if unknown:
                    errors.append(f"未知骨骼顶点组：{', '.join(sorted(unknown)[:8])}")
                if zero:
                    errors.append(f"{zero} 个顶点没有权重")
                if excessive:
                    errors.append(f"{excessive} 个顶点超过四权重")
                if non_normalized:
                    errors.append(f"{non_normalized} 个顶点权重未归一化")
                for required_uv in ("UV0", "UV1"):
                    if required_uv not in obj.data.uv_layers:
                        warnings.append(f"缺少 {required_uv}")
                if obj.data.color_attributes.get("COLOR") is None:
                    warnings.append("缺少 COLOR（导出默认白色 → 描边会变白色高光，请先“传递权重 + 颜色”）")
                if errors:
                    self.report({"ERROR"}, "; ".join(errors))
                    return {"CANCELLED"}
                message = f"带权重网格校验通过：{len(obj.data.vertices)} 个顶点 / {loop_count} 个索引"
                self.report({"WARNING"} if warnings else {"INFO"}, message + (f"; {'; '.join(warnings)}" if warnings else ""))
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        if "gmi_source_vertex_count" not in obj:
            self.report({"ERROR"}, "请选择 GakumasMI 导入的网格，或已经转为配置档权重的网格")
            return {"CANCELLED"}
        faces = [tuple(poly.vertices) for poly in obj.data.polygons]
        errors, warnings = core.validate_index_mesh(
            len(obj.data.vertices), faces,
            int(obj["gmi_source_vertex_count"]), int(obj["gmi_source_index_count"]),
        )
        for required_uv in ("UV0", "UV1"):
            if required_uv not in obj.data.uv_layers:
                warnings.append(f"缺少 {required_uv}")
        for required_attribute in ("COLOR", "GMI_NORMAL", "GMI_TANGENT", "GMI_TANGENT_W"):
            if required_attribute not in obj.data.attributes and required_attribute not in obj.data.color_attributes:
                warnings.append(f"缺少 {required_attribute}")
        if errors:
            self.report({"ERROR"}, "; ".join(errors))
            return {"CANCELLED"}
        message = "网格校验通过"
        if warnings:
            message += ": " + "; ".join(warnings)
            self.report({"WARNING"}, message)
        else:
            self.report({"INFO"}, message)
        return {"FINISHED"}


class GMI_OT_export_mesh_mod(Operator):
    bl_idname = "gmi.export_mesh_mod"
    bl_label = "导出原拓扑模组"
    bl_description = "把当前原拓扑网格导出为 R16 索引缓冲模组"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH" or "gmi_profile_dir" not in obj:
            self.report({"ERROR"}, "请选择 GakumasMI 导入的网格")
            return {"CANCELLED"}
        _, _, output_dir = _scene_paths(context.scene)
        faces = [tuple(poly.vertices) for poly in obj.data.polygons]
        try:
            package, warnings = core.write_index_package(
                obj["gmi_profile_dir"], output_dir,
                context.scene.gmi_package_id, context.scene.gmi_package_name,
                context.scene.gmi_author, obj["gmi_component_id"], faces,
                len(obj.data.vertices),
            )
            level = {"WARNING"} if warnings else {"INFO"}
            self.report(level, f"已导出 {package}" + (f"（{'; '.join(warnings)}）" if warnings else ""))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_export_inverse_skin_mod(Operator):
    bl_idname = "gmi.export_inverse_skin_mod"
    bl_label = "导出带权重 GPU 模组"
    bl_description = "使用游戏内恢复的动画矩阵导出任意拓扑和骨骼权重"

    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择要导出的带权重网格")
            return {"CANCELLED"}
        try:
            _sync_object_mesh_data(context, obj)
            profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
            profile_set = core.load_profile_set(profile_dir)
            resolved = _resolve_body_json_library(scene)
            skeleton_path = Path(resolved["skeletonJson"])
            bone_map = core.inverse_skin_bone_map(
                profile_dir, skeleton_path
            )
            skeleton = core.load_json(skeleton_path)
            source_bind = {
                node["name"]: _bind_pose_matrix(node["bindPose"]).inverted()
                for node in skeleton["nodes"] if node.get("weightedIndex") is not None
            }
            remap = {}
            if scene.gmi_bone_remap_file:
                remap_data = core.load_json(Path(bpy.path.abspath(scene.gmi_bone_remap_file)))
                remap = remap_data.get("bones", remap_data)
            data = _inverse_skin_export_data(
                obj, bone_map, source_bind, remap, scene.gmi_unmapped_bone_fallback.strip(),
                source_rig_weights=bool(obj.get("gmi_profile_weights")),
                outline_width_mode=scene.gmi_outline_width_mode,
                vertex_color_mode=scene.gmi_vertex_color_mode,
                color_per_slot=_material_slot_color_map(obj),
            )
            known_textures = profile_set["textures"].get("textures", {})
            material_textures = {}
            for key, value, semantic in (
                ("body.baseColor", scene.gmi_base_color_file, None),
                ("body.packedMask", scene.gmi_packed_mask_file, "packedMask"),
                ("body.shadeColor", scene.gmi_shade_color_file, "shadeColor"),
            ):
                if value:
                    path = bpy.path.abspath(value)
                    if not path.lower().endswith(".dds"):
                        path = _png_to_dds(path)  # PNG/其它图像 → 临时 DDS
                    material_textures[key] = path
                elif semantic and scene.gmi_neutral_material and key in known_textures:
                    # 没提供时用中性贴图盖掉原版 t1/t4（仅当配置档有该槽位）
                    material_textures[key] = _neutral_material_dds(semantic)
            # 描边颜色来源:复选框 或 「描边颜色」=取自基础色 → 基础色曲线;黑色常量 → 黑边;
            # 按材质预设 → 保留 gather 的逐材质预设色。宽度已在 gather 按「描边宽度」处理,这里不动。
            export_color_synthesis = None
            if scene.gmi_enable_native_color_transfer or scene.gmi_vertex_color_mode == "BASECOLOR":
                data["colors"], export_color_synthesis = _synthesize_export_native_colors(
                    profile_dir,
                    scene.gmi_component_id,
                    data,
                    material_textures.get("body.baseColor") or scene.gmi_base_color_file,
                    _material_slot_color_map(obj),
                )
            elif scene.gmi_vertex_color_mode == "CONSTANT_BLACK":
                data["colors"] = _black_outline_colors(data["colors"])
            _, _, output_dir = _scene_paths(scene)
            alpha_modes = _material_slot_alpha_modes(obj)
            opacity_texture = (
                _png_to_dds(bpy.path.abspath(scene.gmi_opacity_texture_file))
                if scene.gmi_opacity_texture_file and not bpy.path.abspath(scene.gmi_opacity_texture_file).lower().endswith(".dds")
                else bpy.path.abspath(scene.gmi_opacity_texture_file) if scene.gmi_opacity_texture_file else None
            )
            native_co_textures = {}
            for semantic, value in (
                ("baseColor", scene.gmi_opacity_texture_file),
                ("packedMask", scene.gmi_opacity_packed_mask_file),
                ("shadeColor", scene.gmi_opacity_shade_color_file),
            ):
                if not value:
                    continue
                path = bpy.path.abspath(value)
                if not path.lower().endswith(".dds"):
                    path = _png_to_dds(path)
                native_co_textures[semantic] = path
            cover_src = bpy.path.abspath(scene.gmi_cover_image) if scene.gmi_cover_image else ""
            if not cover_src:
                self.report({"ERROR"}, "必须提供 mod 预览图：请在导出面板选择「预览图」后再导出。")
                return {"CANCELLED"}
            cover_path = _prepare_cover_image(cover_src)
            package = core.write_inverse_skin_package(
                profile_dir, output_dir, scene.gmi_package_id, scene.gmi_package_name,
                scene.gmi_author, scene.gmi_component_id,
                data["vertices"], data["normals"], data["tangents"], data["uv0"],
                data["uv1"], data["colors"], data["faces"], data["skin"],
                data["corrections"], material_textures=material_textures,
                materials=data.get("materials"),
                alpha_modes=alpha_modes,
                opacity_texture=opacity_texture,
                native_co_textures=native_co_textures,
                cover_image=cover_path,
            )
            core._write_json(Path(package) / "export-report.json", {
                "automaticAncestorRemap": data["automatic_remap"],
                "unresolvedGroups": data["unresolved"],
                "truncatedWeightTotal": data["truncated_weight"],
                "materialTextures": material_textures,
                "opacityTexture": bpy.path.abspath(scene.gmi_opacity_texture_file) if scene.gmi_opacity_texture_file else "",
                "nativeCoTextures": native_co_textures,
                "outlineWidthMode": scene.gmi_outline_width_mode,
                "vertexColorMode": scene.gmi_vertex_color_mode,
                "uvLayers": data.get("uvLayers", {}),
                "invalidUvLayersRemoved": json.loads(obj.get("gmi_removed_invalid_uv_layers", "[]")),
                "exportColorSynthesis": export_color_synthesis,
                "vertexColorByMaterialSlot": {
                    str(slot): [core._safe_unorm8(channel) for channel in color]
                    for slot, color in _material_slot_color_map(obj).items()
                },
                "alphaModesByMaterialSlot": alpha_modes,
            })
            suffix = (
                f"；祖先骨骼自动映射 {len(data['automatic_remap'])}，"
                f"兜底顶点组 {len(data['unresolved'])}"
            )
            self.report({"INFO"}, f"已导出 {package}{suffix}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_export_validated_mod(Operator):
    bl_idname = "gmi.export_validated_mod"
    bl_label = "校验并导出模组"
    bl_description = "先执行网格校验，再按当前对象类型选择合适的导出方式"
    bl_options = {"REGISTER"}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择要导出的网格")
            return {"CANCELLED"}
        if "gmi_removed_invalid_uv_layers" in obj:
            del obj["gmi_removed_invalid_uv_layers"]
        _sync_object_mesh_data(context, obj)
        result = bpy.ops.gmi.validate_mesh()
        if "FINISHED" not in result:
            self.report({"ERROR"}, "校验未通过，已停止导出")
            return {"CANCELLED"}
        if obj.get("gmi_profile_weights"):
            return GMI_OT_export_inverse_skin_mod.execute(self, context)
        if obj.get("gmi_source_vertex_count"):
            return GMI_OT_export_mesh_mod.execute(self, context)
        self.report({"ERROR"}, "当前对象不是可导出的 GakumasMI 网格")
        return {"CANCELLED"}


class GMI_OT_create_body_material_template(Operator):
    bl_idname = "gmi.create_body_material_template"
    bl_label = "创建身体材质模板"
    bl_description = "为当前对象创建带 t0/t1/t4 语义记录的材质模板"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择要添加材质模板的网格")
            return {"CANCELLED"}
        scene = context.scene
        material = bpy.data.materials.new("GMI_身体材质模板")
        material.use_nodes = True
        material["gmi_material_profile"] = "body"
        material["gmi_t0_base_color"] = bpy.path.abspath(scene.gmi_base_color_file) if scene.gmi_base_color_file else ""
        material["gmi_t1_packed_mask"] = bpy.path.abspath(scene.gmi_packed_mask_file) if scene.gmi_packed_mask_file else ""
        material["gmi_t4_shade_color"] = bpy.path.abspath(scene.gmi_shade_color_file) if scene.gmi_shade_color_file else ""
        material["gmi_co_t0_base_color"] = bpy.path.abspath(scene.gmi_opacity_texture_file) if scene.gmi_opacity_texture_file else ""
        material["gmi_co_t1_packed_mask"] = bpy.path.abspath(scene.gmi_opacity_packed_mask_file) if scene.gmi_opacity_packed_mask_file else ""
        material["gmi_co_t4_shade_color"] = bpy.path.abspath(scene.gmi_opacity_shade_color_file) if scene.gmi_opacity_shade_color_file else ""
        material["gmi_t1_channels"] = "R=阴影阈值, G=光滑度, B=金属度, A=AO/间接光"
        material["gmi_t4_channels"] = "RGB=基础色暗色版, A=原生sdw二值遮罩"

        nodes = material.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        if principled:
            principled.label = "游戏身体主材质近似预览"
        for label, path, location in (
            ("body t0 基础色 / BaseColor", scene.gmi_base_color_file, (-600, 200)),
            ("body t1 混合遮罩", scene.gmi_packed_mask_file, (-600, 0)),
            ("body t4 暗面材质 / ShadeMap", scene.gmi_shade_color_file, (-600, -200)),
            ("co t0 基础色 / m_bdyco", scene.gmi_opacity_texture_file, (-950, 200)),
            ("co t1 混合遮罩", scene.gmi_opacity_packed_mask_file, (-950, 0)),
            ("co t4 暗面材质 / ShadeMap", scene.gmi_opacity_shade_color_file, (-950, -200)),
        ):
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
        self.report({"INFO"}, "已创建身体材质模板；真实游戏绑定仍以导出时 t0/t1/t4 DDS 为准")
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
    bl_label = "按材质烘焙 t1/t4"
    bl_description = (
        "按各材质槽的「材质类型」预设，从基础色 t0 派生分材质 t1/t4 并设为导出贴图。"
        "比平铺中性更接近游戏观感"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        import numpy as np

        scene = context.scene
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择网格")
            return {"CANCELLED"}
        _sync_object_mesh_data(context, obj)
        if not scene.gmi_base_color_file:
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
            base8, width, height = _load_base_texture(scene.gmi_base_color_file, "body 基础色 t0")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
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

        form_map = None
        ao = None
        if scene.gmi_form_shading:
            ao = _compute_vertex_ao(obj)
            form_map = _slot_form_map(opaque_slots, width, ao)
        t1, t4 = core.bake_material_maps(
            id_map, base8, class_per_slot, presets,
            form_map=form_map, form_strength=scene.gmi_form_strength,
            toon_per_slot=toon_per_slot,
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
        t1_path = out / "gmi_baked_packedMask.dds"
        t4_path = out / "gmi_baked_shadeColor.dds"
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
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            co_id_map = _slot_id_map(native_co_slots, co_width)
            co_form_map = None
            if scene.gmi_form_shading:
                co_form_map = _slot_form_map(native_co_slots, co_width, ao)
            co_t1, co_t4 = core.bake_material_maps(
                co_id_map, co_base8, class_per_slot, presets,
                form_map=co_form_map, form_strength=scene.gmi_form_strength,
                toon_per_slot=toon_per_slot,
            )
            co_t1_path = out / "gmi_baked_co_packedMask.dds"
            co_t4_path = out / "gmi_baked_co_shadeColor.dds"
            co_covered = int((co_id_map >= 0).sum()) * 100 // (co_width * co_height)
            co_note = f"；co {co_covered}% UV 覆盖"

        core.write_rgba8_dds(t1_path, width, height, t1.tobytes(), srgb=False)
        core.write_rgba8_dds(t4_path, width, height, t4.tobytes(), srgb=True)
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
            f"已烘焙 body t1/t4（{covered}% UV 覆盖{co_note}；材质：{'、'.join(used)}{form_note}{channel_note}）；"
            f"已设为导出 t1/t4，可直接校验导出",
        )
        return {"FINISHED"}


class GMI_OT_export_texture_mod(Operator):
    bl_idname = "gmi.export_texture_mod"
    bl_label = "导出贴图模组"
    bl_description = "按已验证的配置档贴图绑定打包 DDS 替换"

    def execute(self, context):
        scene = context.scene
        profile_dir, _, output_dir = _scene_paths(scene)
        try:
            package = core.write_texture_package(
                profile_dir, output_dir, scene.gmi_package_id,
                scene.gmi_package_name, scene.gmi_author,
                scene.gmi_texture_key, bpy.path.abspath(scene.gmi_texture_file),
            )
            self.report({"INFO"}, f"已导出 {package}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


CLASSES = (
    GMI_OT_extract_profile_from_frame_dump,
    GMI_OT_build_full_profile,
    GMI_OT_update_profile_from_frame_dump,
    GMI_OT_resolve_body_json_library,
    GMI_OT_import_profile_object,
    GMI_OT_import_reference,
    GMI_OT_import_weighted_reference,
    GMI_OT_transfer_profile_weights,
    GMI_OT_transfer_profile_weights_smart,
    GMI_OT_select_high_risk_vertices,
    GMI_OT_validate_mesh,
    GMI_OT_export_mesh_mod,
    GMI_OT_export_inverse_skin_mod,
    GMI_OT_export_validated_mod,
    GMI_OT_create_body_material_template,
    GMI_OT_bake_material_maps,
    GMI_OT_export_texture_mod,
)
