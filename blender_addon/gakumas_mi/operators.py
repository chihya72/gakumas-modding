import json
import struct
from pathlib import Path

import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import core


def _scene_paths(scene):
    profile_dir = bpy.path.abspath(scene.gmi_profile_dir)
    capture_dir = bpy.path.abspath(scene.gmi_capture_dir) if scene.gmi_capture_dir else None
    output_dir = bpy.path.abspath(scene.gmi_output_dir)
    return profile_dir, capture_dir, output_dir


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


def _create_native_sets_for_obj(obj):
    profile_root = Path(obj["gmi_profile_dir"])
    profile = core.load_profile_set(profile_root)["profile"]
    region_config = profile["skinning"]["regionMap"]
    schema = core.load_json(profile_root / region_config["schema"])
    vertex_map = (profile_root / region_config["vertexMap"]).read_bytes()
    if len(vertex_map) != len(obj.data.vertices) * 2:
        raise ValueError("配置档顶点区域映射尺寸不正确")
    region_ids = struct.unpack(f"<{len(obj.data.vertices)}H", vertex_map)
    suggestions = {
        "GMI_NATIVE_HAND": {
            region["id"] for region in schema["regions"]
            if "native-hand-candidate" in region.get("suggestions", [])
        },
        "GMI_NATIVE_NECK": {
            region["id"] for region in schema["regions"]
            if "native-neck-candidate" in region.get("suggestions", [])
        },
    }
    counts = {}
    for name, selected_regions in suggestions.items():
        group = obj.vertex_groups.get(name)
        if group:
            obj.vertex_groups.remove(group)
        group = obj.vertex_groups.new(name=name)
        indices = [i for i, region_id in enumerate(region_ids) if region_id in selected_regions]
        if indices:
            group.add(indices, 1.0, "REPLACE")
        counts[name] = len(indices)
    return counts


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
            inverse = profile["skinning"]["inverseSkin"]
            component = core.component_by_id(profile, scene.gmi_component_id)
            mesh_path = (profile_set["root"] / inverse["meshJson"]).resolve()
            skeleton_path = (profile_set["root"] / inverse["skeletonJson"]).resolve()
            scene.gmi_source_mesh_json = str(mesh_path)
            scene.gmi_skeleton_json = str(skeleton_path)

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
            counts = _create_native_sets_for_obj(weighted_obj)
            _link_only_to_collection(weighted_obj, reference_collection)
            _link_only_to_collection(armature, reference_collection)

            context.view_layer.objects.active = weighted_obj
            weighted_obj.select_set(True)
            self.report(
                {"INFO"},
                f"已导入配置档对象：参考 {len(reference_data['vertices'])} 顶点，"
                f"权重 {weighted_data['vertex_count']} 顶点，手部 {counts['GMI_NATIVE_HAND']}，"
                f"颈部 {counts['GMI_NATIVE_NECK']}",
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
        output_dir = bpy.path.abspath(scene.gmi_extract_output_dir or scene.gmi_profile_dir)
        if not capture_dir:
            self.report({"ERROR"}, "请先选择 FrameAnalysis 抓帧目录")
            return {"CANCELLED"}
        if not output_dir:
            self.report({"ERROR"}, "请先选择新配置档输出目录")
            return {"CANCELLED"}
        try:
            report = core.extract_profile_from_frame_dump(
                capture_dir,
                output_dir,
                component_id=scene.gmi_component_id,
                main_draw=scene.gmi_extract_draw or None,
            )
            scene.gmi_profile_dir = output_dir
            selected = report["selected"]
            self.report(
                {"INFO"},
                f"已生成配置档：Draw {selected['draw']:06d}，"
                f"{selected['vertices']} 顶点 / {selected['indices']} 索引"
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
            inverse = profile_set["profile"]["skinning"]["inverseSkin"]
            mesh_path = (
                Path(bpy.path.abspath(scene.gmi_source_mesh_json))
                if scene.gmi_source_mesh_json
                else (profile_set["root"] / inverse["meshJson"]).resolve()
            )
            skeleton_path = (
                Path(bpy.path.abspath(scene.gmi_skeleton_json))
                if scene.gmi_skeleton_json
                else (profile_set["root"] / inverse["skeletonJson"]).resolve()
            )
            scene.gmi_source_mesh_json = str(mesh_path)
            scene.gmi_skeleton_json = str(skeleton_path)
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
    bl_label = "从配置档传递权重"
    bl_description = "用 HSKI 配置档插值权重替换当前选中网格的权重"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        target = context.active_object
        if not target or target.type != "MESH":
            self.report({"ERROR"}, "请选择要转权的作者模型网格")
            return {"CANCELLED"}
        try:
            reference = _profile_weight_reference(context)
            if target == reference:
                raise ValueError("请选择作者模型网格，不要选择配置档参考模型本身")
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
                **risk,
            }
            target["gmi_weight_report"] = json.dumps(report, separators=(",", ":"))
            if zero:
                raise ValueError(f"仍有 {len(zero)} 个顶点没有权重")
            self.report(
                {"WARNING"} if risk["reviewVertices"] else {"INFO"},
                f"已传递配置档权重；需复核 {risk['reviewVertices']} 个顶点，"
                f"p95 {risk['p95Distance']:.4f} m，最大 {risk['maxDistance']:.4f} m",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_create_native_body_sets(Operator):
    bl_idname = "gmi.create_native_body_sets"
    bl_label = "生成原生手/颈选择集"
    bl_description = "根据配置档连通区域映射生成可复核的手部和颈部顶点组"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = _profile_weight_reference(context)
            counts = _create_native_sets_for_obj(obj)
            context.view_layer.objects.active = obj
            obj.select_set(True)
            self.report({"INFO"}, f"已生成复核顶点组：手部 {counts['GMI_NATIVE_HAND']}，颈部 {counts['GMI_NATIVE_NECK']}")
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


class GMI_OT_select_native_hand_vertices(Operator):
    bl_idname = "gmi.select_native_hand_vertices"
    bl_label = "选择原生手部"
    bl_description = "在带权重参考模型上选择候选 HSKI 原生手部顶点"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = _profile_weight_reference(context)
            count = _select_vertex_group(context, obj, "GMI_NATIVE_HAND")
            self.report({"INFO"}, f"已选择 {count} 个原生手部候选顶点")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class GMI_OT_select_native_neck_vertices(Operator):
    bl_idname = "gmi.select_native_neck_vertices"
    bl_label = "选择原生颈部"
    bl_description = "在带权重参考模型上选择候选 HSKI 原生颈部顶点"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = _profile_weight_reference(context)
            count = _select_vertex_group(context, obj, "GMI_NATIVE_NECK")
            self.report({"INFO"}, f"已选择 {count} 个原生颈部候选顶点")
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


class GMI_OT_export_surface_mod(Operator):
    bl_idname = "gmi.export_surface_mod"
    bl_label = "导出表面驱动模组"
    bl_description = "导出由原身体动画表面驱动的任意拓扑模组"

    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "请选择要导出的网格")
            return {"CANCELLED"}
        faces = [tuple(poly.vertices) for poly in obj.data.polygons]
        if any(len(face) != 3 for face in faces):
            self.report({"ERROR"}, "表面驱动导出前请先三角化网格")
            return {"CANCELLED"}
        try:
            source = core.read_weighted_reference(
                bpy.path.abspath(scene.gmi_source_mesh_json),
                bpy.path.abspath(scene.gmi_skeleton_json),
            )
            source_vertices = [Vector(value) for value in source["vertices"]]
            tree = BVHTree.FromPolygons(source_vertices, source["faces"], all_triangles=True)
            reference_obj = next(
                (candidate for candidate in context.scene.objects
                 if candidate.type == "MESH" and candidate.get("gmi_weighted_reference")),
                None,
            )
            reference_world = reference_obj.matrix_world if reference_obj else Matrix.Identity(4)
            to_source = reference_world.inverted() @ obj.matrix_world
            normal_matrix = to_source.to_3x3().inverted().transposed()
            vertices = [tuple(to_source @ vertex.co) for vertex in obj.data.vertices]
            normals = [tuple((normal_matrix @ vertex.normal).normalized()) for vertex in obj.data.vertices]
            mappings = []
            max_distance = 0.0
            identity_source = (
                len(vertices) == len(source_vertices)
                and all((Vector(value) - source_vertices[index]).length < 1e-6
                        for index, value in enumerate(vertices))
            )
            if identity_source:
                # Preserve duplicate/seam vertex identity. Coincident vertices can
                # carry different weights and separate after CPU skinning.
                mappings = [{
                    "indices": (index, index, index),
                    "barycentric": (1.0, 0.0, 0.0),
                    "normal_offset": 0.0,
                } for index in range(len(vertices))]
            else:
                for coordinates in vertices:
                    point = Vector(coordinates)
                    location, surface_normal, triangle_index, distance = tree.find_nearest(point)
                    if triangle_index is None:
                        raise ValueError("有顶点无法映射到原身体表面")
                    indices = source["faces"][triangle_index]
                    a, b, c = (source_vertices[index] for index in indices)
                    weights = _barycentric(location, a, b, c)
                    normal_offset = (point - location).dot(surface_normal.normalized())
                    mappings.append({
                        "indices": indices,
                        "barycentric": weights,
                        "normal_offset": normal_offset,
                    })
                    max_distance = max(max_distance, float(distance))
            _, _, output_dir = _scene_paths(scene)
            package = core.write_surface_package(
                bpy.path.abspath(scene.gmi_profile_dir), output_dir,
                scene.gmi_package_id, scene.gmi_package_name, scene.gmi_author,
                scene.gmi_component_id, vertices, normals,
                _vertex_uv(obj.data, "UV0"), _vertex_uv(obj.data, "UV1"),
                _vertex_colors(obj.data), faces, mappings,
            )
            self.report({"INFO"}, f"已导出 {package}；最大表面距离 {max_distance:.4f} m")
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
            inverse_config = profile_set["profile"]["skinning"]["inverseSkin"]
            skeleton_path = (
                Path(bpy.path.abspath(scene.gmi_skeleton_json))
                if scene.gmi_skeleton_json
                else (profile_set["root"] / inverse_config["skeletonJson"]).resolve()
            )
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
            material_textures = {
                key: bpy.path.abspath(value)
                for key, value in {
                    "body.baseColor": scene.gmi_base_color_file,
                    "body.packedMask": scene.gmi_packed_mask_file,
                    "body.shadeColor": scene.gmi_shade_color_file,
                }.items() if value
            }
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
    GMI_OT_update_profile_from_frame_dump,
    GMI_OT_import_profile_object,
    GMI_OT_import_reference,
    GMI_OT_import_weighted_reference,
    GMI_OT_transfer_profile_weights,
    GMI_OT_create_native_body_sets,
    GMI_OT_select_high_risk_vertices,
    GMI_OT_select_native_hand_vertices,
    GMI_OT_select_native_neck_vertices,
    GMI_OT_validate_mesh,
    GMI_OT_export_mesh_mod,
    GMI_OT_export_surface_mod,
    GMI_OT_export_inverse_skin_mod,
    GMI_OT_export_validated_mod,
    GMI_OT_create_body_material_template,
    GMI_OT_export_texture_mod,
)
