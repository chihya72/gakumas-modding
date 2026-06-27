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
        rgba = buffer.reshape(height, width, 4)[::-1]  # Blender 自下而上 → DDS 自上而下
        rgba8 = np.clip(rgba * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
        output = Path(tempfile.gettempdir()) / f"gmi_{Path(image_path).stem}.dds"
        core.write_rgba8_dds(output, width, height, rgba8.tobytes(), srgb=True)
        return str(output)
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

from . import core


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
    uv0_layer = mesh.uv_layers.get("UV0") or (uv_layers[0] if uv_layers else None)
    uv1_layer = mesh.uv_layers.get("UV1") or (uv_layers[1] if len(uv_layers) > 1 else uv0_layer)
    color_layer = mesh.color_attributes.get("COLOR")
    world = obj.matrix_world
    normal_matrix = world.to_3x3().inverted().transposed()
    tangent_matrix = world.to_3x3()
    tangents_ready = False
    if uv0_layer:
        try:
            mesh.calc_tangents(uvmap=uv0_layer.name)
            tangents_ready = True
        except RuntimeError:
            tangents_ready = False
    vertices, normals, tangents, uv0, uv1, colors, skin, faces = ([] for _ in range(8))
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
            if uv0_layer:
                value = uv0_layer.data[loop_index].uv
                tex0 = (float(value[0]), float(value[1]))
            else:
                tex0 = (0.0, 0.0)
            if uv1_layer:
                value = uv1_layer.data[loop_index].uv
                tex1 = (float(value[0]), float(value[1]))
            else:
                tex1 = tex0
            if color_layer:
                color_index = loop.vertex_index if color_layer.domain == "POINT" else loop_index
                value = color_layer.data[color_index].color
                color = tuple(float(value[channel]) for channel in range(4))
            else:
                color = (1.0, 1.0, 1.0, 1.0)
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
            face.append(len(vertices))
            vertices.append(position); normals.append(normal); tangents.append(tangent)
            uv0.append(tex0); uv1.append(tex1); colors.append(color); skin.append(ordered)
        faces.append(tuple(face))
    if unresolved and not fallback_bone:
        sample = ", ".join(sorted(unresolved)[:12])
        raise ValueError(f"Unmapped weighted bones ({len(unresolved)}): {sample}")
    # 学马仕描边 VS(e0ceaa85)沿 TANGENT.xyz 挤出描边(NORMAL 通道不参与描边),
    # 且原版 TANGENT 并非 UV 切线,而是逐顶点"平滑法线"(同坐标顶点法线平均,cos≈0.6)。
    # 自定义网格若把 UV 切线写进 TANGENT,描边会沿表面方向挤出 → 整圈不可见。
    # 故这里按位置合并法线得到平滑法线,写入 TANGENT.xyz(w=1,与原版一致),让描边外扩。
    if vertices:
        from collections import defaultdict
        position_groups = defaultdict(list)
        for index, position in enumerate(vertices):
            key = (round(position[0], 5), round(position[1], 5), round(position[2], 5))
            position_groups[key].append(index)
        smoothed_tangents = list(tangents)
        for indices in position_groups.values():
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
                    if ni[0] * nj[0] + ni[1] * nj[1] + ni[2] * nj[2] > 0.0:
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
            report = core.extract_profile_from_frame_dump(
                capture_dir,
                output_dir,
                component_id=scene.gmi_component_id,
                main_draw=scene.gmi_extract_draw or None,
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
            # ① 注入信息
            core.extract_profile_from_frame_dump(
                capture_dir, output_dir,
                component_id=component_id,
                main_draw=scene.gmi_extract_draw or None,
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


def _transfer_color_attribute(context, target, reference):
    """从参考身体把 COLOR 顶点属性按【最近顶点】拷贝到作者网格。

    Gakumas 的顶点 COLOR 是逐顶点【打包位数据】(描边 VS / 主 VS 都 floor(v5*15.9375)
    解包):它编码描边颜色 + 描边宽度等。这种打包数据【绝不能插值】——插值会把相邻
    打包值混成无意义值,导致主 Pass 解包出错(裙子橙斑)。故用 vert_mapping="NEAREST"
    直接拷贝最近原版顶点的精确打包值,不做任何混合。

    若不传 COLOR(网格无该层),导出默认白 (1,1,1,1) → 描边解包成白色高光。
    返回是否成功传递。
    """
    ref_color = reference.data.color_attributes.get("COLOR")
    if not ref_color:
        return False
    dst = target.data.color_attributes.get("COLOR")
    if dst is not None and dst.domain != "POINT":
        target.data.color_attributes.remove(dst)
        dst = None
    if dst is None:
        target.data.color_attributes.new(name="COLOR", type="FLOAT_COLOR", domain="POINT")

    transfer = target.modifiers.new(name="GMI_传递配置档颜色", type="DATA_TRANSFER")
    transfer.object = reference
    transfer.use_vert_data = True
    transfer.data_types_verts = {"COLOR_VERTEX"}
    # 关键:NEAREST = 拷贝最近顶点的精确打包值，绝不插值（插值会毁掉打包数据）。
    transfer.vert_mapping = "NEAREST"
    transfer.layers_vcol_vert_select_src = "ALL"
    transfer.layers_vcol_vert_select_dst = "NAME"
    transfer.mix_mode = "REPLACE"
    transfer.mix_factor = 1.0
    context.view_layer.objects.active = target
    target.select_set(True)
    reference.select_set(False)
    result = bpy.ops.object.modifier_apply(modifier=transfer.name)
    return "FINISHED" in result


class GMI_OT_transfer_profile_weights(Operator):
    bl_idname = "gmi.transfer_profile_weights"
    bl_label = "从配置档传递权重 + 颜色"
    bl_description = "用 HSKI 配置档插值权重 + 按最近顶点拷贝 COLOR（COLOR 是打包数据，决定描边颜色，不可插值）"
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
            if context.scene.gmi_semantic_correction:
                corrected = _apply_semantic_weight_correction(
                    target, reference, old_dominant
                )
            zero, truncated = _normalize_profile_weights(target, maximum=4)
            # 紧接着按【最近顶点】拷贝原版 COLOR(打包数据,决定描边颜色/宽度,不可插值)。
            color_transferred = False
            try:
                color_transferred = _transfer_color_attribute(context, target, reference)
            except Exception as color_exc:
                self.report({"WARNING"}, f"COLOR 拷贝失败（描边会变白）：{color_exc}")
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
            color_note = "权重+COLOR(最近顶点)" if color_transferred else "权重（COLOR 未拷，描边会变白）"
            messages = [
                f"已传递配置档{color_note}；需复核 {risk['reviewVertices']} 个顶点，"
                f"p95 {risk['p95Distance']:.4f} m，最大 {risk['maxDistance']:.4f} m"
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
                if loop_count > int(component["indices"]):
                    errors.append(f"{loop_count} 个索引超过原 Draw 容量 {component['indices']}")
                if loop_count > 65535:
                    errors.append(f"{loop_count} 个展开顶点超过 R16 上限 65535")
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
            _, _, output_dir = _scene_paths(scene)
            package = core.write_inverse_skin_package(
                profile_dir, output_dir, scene.gmi_package_id, scene.gmi_package_name,
                scene.gmi_author, scene.gmi_component_id,
                data["vertices"], data["normals"], data["tangents"], data["uv0"],
                data["uv1"], data["colors"], data["faces"], data["skin"],
                data["corrections"], material_textures=material_textures,
            )
            core._write_json(Path(package) / "export-report.json", {
                "automaticAncestorRemap": data["automatic_remap"],
                "unresolvedGroups": data["unresolved"],
                "truncatedWeightTotal": data["truncated_weight"],
                "materialTextures": material_textures,
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
        result = bpy.ops.gmi.validate_mesh()
        if "FINISHED" not in result:
            self.report({"ERROR"}, "校验未通过，已停止导出")
            return {"CANCELLED"}
        if obj.get("gmi_profile_weights"):
            return bpy.ops.gmi.export_inverse_skin_mod()
        if obj.get("gmi_source_vertex_count"):
            return bpy.ops.gmi.export_mesh_mod()
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
        material["gmi_t1_channels"] = "R=阴影阈值, G=光滑度, B=金属度, A=AO/间接光"
        material["gmi_t4_channels"] = "RGB=阴影色, A=阴影色混合强度"

        nodes = material.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        if principled:
            principled.label = "游戏身体主材质近似预览"
        for label, path, location in (
            ("t0 基础色 / BaseColor", scene.gmi_base_color_file, (-600, 160)),
            ("t1 混合遮罩", scene.gmi_packed_mask_file, (-600, -60)),
            ("t4 阴影色 / ShadeColor", scene.gmi_shade_color_file, (-600, -280)),
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
        if not scene.gmi_base_color_file:
            self.report({"ERROR"}, "需要先指定基础色 t0（t4 从它派生）")
            return {"CANCELLED"}
        mesh = obj.data
        if not mesh.uv_layers.active:
            self.report({"ERROR"}, "网格缺少 UV，无法按 UV 烘焙")
            return {"CANCELLED"}
        if not obj.material_slots or all(s.material is None for s in obj.material_slots):
            self.report({"ERROR"}, "网格没有材质槽，请先分材质并设置每个材质的「材质类型」")
            return {"CANCELLED"}

        base_path = bpy.path.abspath(scene.gmi_base_color_file)
        if base_path.lower().endswith(".dds"):
            self.report({"ERROR"}, "基础色请用 PNG（DDS 无法在 Blender 内读像素派生 t4）")
            return {"CANCELLED"}
        image = bpy.data.images.load(base_path, check_existing=False)
        try:
            try:
                image.colorspace_settings.name = "Non-Color"
            except Exception:
                pass
            width, height = int(image.size[0]), int(image.size[1])
            if width != height:
                self.report({"ERROR"}, f"基础色需为正方形（当前 {width}x{height}）")
                return {"CANCELLED"}
            buffer = np.empty(width * height * 4, dtype=np.float32)
            image.pixels.foreach_get(buffer)
            base8 = np.clip(
                buffer.reshape(height, width, 4)[::-1] * 255.0 + 0.5, 0, 255
            ).astype(np.uint8)  # top-down，与 DDS / UV(1-v) 一致
        finally:
            bpy.data.images.remove(image)

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
        shade_per_slot = {
            idx: slot.material.gmi_material_shade
            for idx, slot in enumerate(obj.material_slots)
            if slot.material is not None and slot.material.gmi_material_shade >= 0
        }
        id_map = core.rasterize_material_ids(tris, mat_ids, width, dilate=8)

        form_map = None
        if scene.gmi_form_shading:
            ao = _compute_vertex_ao(obj)
            form_map = core.rasterize_vertex_scalar(tris, ao[vert_tris], width, dilate=8)
        t1, t4 = core.bake_material_maps(
            id_map, base8, class_per_slot, presets,
            form_map=form_map, form_strength=scene.gmi_form_strength,
            toon_per_slot=toon_per_slot, shade_per_slot=shade_per_slot,
        )

        out = Path(tempfile.gettempdir())
        t1_path = out / "gmi_baked_packedMask.dds"
        t4_path = out / "gmi_baked_shadeColor.dds"
        core.write_rgba8_dds(t1_path, width, height, t1.tobytes(), srgb=False)
        core.write_rgba8_dds(t4_path, width, height, t4.tobytes(), srgb=True)
        scene.gmi_packed_mask_file = str(t1_path)
        scene.gmi_shade_color_file = str(t4_path)

        covered = int((id_map >= 0).sum()) * 100 // (width * height)
        used = sorted({presets[c]["label"] for c in class_per_slot.values() if c in presets})
        form_note = "；几何AO软化阴影" if form_map is not None else ""
        self.report(
            {"INFO"},
            f"已烘焙 t1/t4（{covered}% UV 覆盖；材质：{'、'.join(used)}{form_note}）；"
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
    GMI_OT_select_high_risk_vertices,
    GMI_OT_validate_mesh,
    GMI_OT_export_mesh_mod,
    GMI_OT_export_inverse_skin_mod,
    GMI_OT_export_validated_mod,
    GMI_OT_create_body_material_template,
    GMI_OT_bake_material_maps,
    GMI_OT_export_texture_mod,
)
