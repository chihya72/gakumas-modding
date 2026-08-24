import json

import bpy
from bpy.types import Panel

from . import core


_STATE_ICONS = {"reject": "CANCEL", "undecided": "ERROR"}

_STAGE_INFO = {
    "TARGET": ("1 · 目标与参照", "告诉插件要替换谁，并把原版参考网格与骨架带进场景。"),
    "MODEL": ("2 · 作者模型", "明确指定成品网格；后续不再依赖碰巧激活的对象。"),
    "MATERIAL": ("3 · 材质与贴图", "先整理材质槽，再由 t0 派生游戏使用的遮罩、暗面和描边。"),
    "RIG": ("4 · 骨架与物理", "身体骨映射到游戏骨；装饰骨明确选择合并、跟随或自建物理。"),
    "EXPORT": ("5 · 检查与导出", "把所有阻断项集中到一个地方，确认后生成可安装的 bundle。"),
}


def _is_hair_package(scene):
    return scene.gmi_component_id == "hair"


def _active_component(scene, obj):
    return obj.get("gmi_component_id", scene.gmi_component_id) if obj else scene.gmi_component_id


def _author_object(scene, context):
    chosen = getattr(scene, "gmi_author_object", None)
    if chosen is not None and chosen.type == "MESH":
        return chosen
    active = context.active_object
    return (active if active is not None and active.type == "MESH"
            and not active.get("gmi_weighted_reference") else None)


# ---------------------------------------------------------------- 视觉层级
# Blender 侧栏能表达层级的手段就那么几种。这里把它们**绑死成四个角色**，全插件只用这四个
# 画东西 —— 以前标题和正文都是 `box.label()`，屏幕上完全等重，作者分不出哪个是标题、
# 哪句是说明、哪一项非填不可（2026-08-24 作者原话："根本没有主次"）。
#
#   小节标题 `_section()`  真正的可折叠子面板：有三角箭头 + 加粗底，Blender 用户一眼认得
#   必填输入 `_need()`     空着就整行变红，不用读说明也知道非填不可
#   主操作   `_go()`       放大的按钮，一个小节最多一个
#   说明正文 `_note()`     变灰（`active=False`），永远比上面三样轻

def _section(layout, key, title, *, closed=True, alert=False):
    """**可折叠的次要区**：诊断、可选、高级。必经之路不要用它，直接铺在面板上。

    只在 `alert` 时把标题整行变红 —— 颜色是 Blender 里唯一不会和折叠箭头混淆的信号。
    2026-08-24 试过给"完成"画 ✔：每行都有标记等于没有标记，而且 `CHECKMARK` 和折叠
    箭头同色同粗细，并排看不出区别（作者原话："完全分不清"）。**只标异常，不标正常。**
    """
    header, body = layout.panel(key, default_closed=closed)
    header.alert = alert
    header.label(text=title)
    return body


def _group(layout, title):
    """**必经之路的一段**：不可折叠。标题用一行分隔 + 文字，重量介于面板标题和正文之间。"""
    layout.separator()
    row = layout.row()
    row.label(text=title)
    return layout.column(align=True)


def _need(layout, scene, prop, **kwargs):
    """必填项：值为空就把这一行标红。"""
    row = layout.row()
    row.alert = not str(getattr(scene, prop, "") or "").strip()
    row.prop(scene, prop, **kwargs)


def _go(layout, operator, text, icon="PLAY", enabled=True):
    """这一小节的主操作。放大 = "该点的就是我"。"""
    row = layout.row()
    row.scale_y = 1.5
    row.enabled = enabled
    return row.operator(operator, text=text, icon=icon)


def _note(layout, text, icon="NONE"):
    """说明文字：一律变灰。它是"看不懂时才读"的东西，不该和标题抢注意力。"""
    column = layout.column()
    column.active = False
    column.label(text=text, icon=icon)


def _model_problems(obj):
    if obj is None:
        return ["还没有选择作者模型：在下面选择网格，或先在 3D 视图激活它。"]
    problems = []
    if not obj.vertex_groups:
        problems.append("作者模型没有顶点组：先完成骨架绑定与权重。")
    if obj.data.uv_layers.active is None:
        problems.append("作者模型没有活动 UV0：整理图集并把导出 UV 设为活动层。")
    if not obj.material_slots or all(slot.material is None for slot in obj.material_slots):
        problems.append("作者模型没有有效材质槽：先按皮肤、布料、金属等用途分材质。")
    armature = next((modifier.object for modifier in obj.modifiers
                     if modifier.type == "ARMATURE" and modifier.object), None)
    if armature is None:
        problems.append("作者模型没有 Armature 修改器：先绑定到作者骨架。")
    if any(abs(float(value) - 1.0) > 1e-4 for value in obj.scale):
        problems.append("对象缩放尚未应用：确认尺寸后执行 Ctrl+A → 缩放。")
    if any(abs(float(value)) > 1e-4 for value in obj.rotation_euler):
        problems.append("对象旋转尚未应用：确认朝向后执行 Ctrl+A → 旋转。")
    return problems


def _bone_problem(item):
    state = _row_state(item)
    if state == "undecided":
        return "这组骨还没决定：映射到游戏骨，或选择一种装饰骨处理。"
    if state == "reject":
        return "这组骨被标记为拒绝导出：删除相关权重或改成可执行的处理方式。"
    if not item.target and item.strategy == "integrate" and item.anchor_only and not item.swing_anchor:
        return "权重全在链根但链根不会摆：打开“链根参与摆动”，否则游戏里不会动。"
    if not item.target and item.strategy == "native_driver":
        resolved = item.swing_category if item.swing_category != "auto" else core.swing_category(item.source)
        if resolved not in core.DRIVER_CATEGORIES:
            return "所选部件类型没有原版布料驱动器：改为裙、披挂或袖，或换一种处理。"
    return ""


def _stage_problems(scene, context, stage):
    obj = _author_object(scene, context)
    if stage == "TARGET":
        if scene.gmi_target_source == "PROFILE":
            return [] if str(scene.gmi_profile_dir or "").strip() else [
                "没有配置档目录：选择已有 profile 后再导入参照。"]
        problems = []
        if not str(scene.gmi_capture_dir or "").strip():
            problems.append("没有抓帧目录：选择 3DMigoto 的 FrameAnalysis 文件夹。")
        if not str(scene.gmi_body_json_library_dir or "").strip():
            problems.append("没有网格 JSON 资源库：选择 AssetStudio 批量导出的目录。")
        return problems
    if stage == "MODEL":
        return _model_problems(obj)
    if stage == "MATERIAL":
        problems = []
        if obj is None:
            problems.append("没有作者模型：回到阶段 2 选择网格。")
        elif not obj.material_slots or all(slot.material is None for slot in obj.material_slots):
            problems.append("作者模型没有有效材质槽：回到模型准备阶段分好材质。")
        if not str(scene.gmi_base_color_file or "").strip():
            problems.append("没有基础色 t0：游戏会沿用原贴图并导致颜色错乱。")
        if obj and not _is_hair_package(scene) and any(
                slot.material and getattr(slot.material, "gmi_alpha_mode", "") == "NATIVE_CO"
                for slot in obj.material_slots) and not str(scene.gmi_opacity_texture_file or "").strip():
            problems.append("存在“原生co”材质，但没有填写它自己的基础色贴图。")
        return problems
    if stage == "RIG":
        problems = []
        if obj is None or not obj.vertex_groups:
            problems.append("没有可处理的作者权重：回到阶段 2 选择已绑定网格。")
        if not scene.gmi_bone_map:
            problems.append("还没有扫描源骨骼：用本页主按钮建立处理队列。")
        else:
            problems.extend(filter(None, (_bone_problem(item) for item in scene.gmi_bone_map)))
            if not scene.gmi_rig_report:
                problems.append("尚未量对齐和跨关节权重带：处理完队列后运行体检。")
        return problems
    problems = []
    if not str(scene.gmi_profile_dir or "").strip():
        problems.append("缺少目标配置档：回到阶段 1 准备目标参照。")
    problems.extend(_model_problems(obj))
    if not str(scene.gmi_base_color_file or "").strip():
        problems.append("缺少基础色 t0：回到阶段 3 准备贴图。")
    if not str(scene.gmi_output_dir or "").strip():
        problems.append("没有输出目录：选择成品 mod 包的写入位置。")
    if not str(scene.gmi_package_id or "").strip():
        problems.append("没有模组标识：填写只含字母、数字、点和横线的唯一 ID。")
    if not str(scene.gmi_bundle_template or "").strip():
        problems.append("没有 R32 模板 bundle：选择与目标资源对应的模板。")
    for item in scene.gmi_bone_map:
        problem = _bone_problem(item)
        if problem and not (scene.gmi_allow_undecided and _row_state(item) == "undecided"):
            problems.append(problem)
    pending_bake = any(item.strategy == "bake" for item in scene.gmi_bone_map)
    if pending_bake and obj and not obj.get("gmi_baked_rest_offset"):
        problems.append("存在“烘焙形变”骨但尚未烘焙：回到阶段 4 执行烘焙。")
    return problems


def _draw_stage_header(layout, scene, context, stage):
    title, description = _STAGE_INFO[stage]
    problems = _stage_problems(scene, context, stage)
    box = layout.box()
    row = box.row()
    row.label(text=title)
    if problems:
        row.alert = True
        row.label(text=f"{len(problems)} 处待处理", icon="ERROR")
    _note(box, description)
    return problems


def _draw_problems(layout, problems):
    for message in problems:
        row = layout.row()
        row.alert = True
        row.label(text=message, icon="ERROR")


def draw_profile_step(layout, scene):
    is_hair = _is_hair_package(scene)
    target_name = "发型" if is_hair else "身体"
    column = _group(layout, "目标来源")
    column.prop(scene, "gmi_target_source", expand=True)
    if scene.gmi_target_source == "CAPTURE":
        _note(layout, "第一次替换这个资源时选这里；配置档建好后可以长期复用")
        column = _group(layout, "抓帧与原版资源")
        _need(column, scene, "gmi_capture_dir")
        _need(column, scene, "gmi_body_json_library_dir", text=f"{target_name} JSON 资源库")
        column.prop(scene, "gmi_body_resource",
                    text="目标 hair 资源（可选）" if is_hair else "目标 body 资源（可选）")
        _go(layout, "gmi.prepare_target", "生成配置档并导入目标参照", icon="ARMATURE_DATA")
    else:
        column = _group(layout, "已有配置档")
        _need(column, scene, "gmi_profile_dir")
        _go(layout, "gmi.prepare_target", "导入目标参照", icon="ARMATURE_DATA")
    _note(layout, "完成后场景里会出现原版参考网格与骨架；它们用于取色、对齐和导出体检，请保留")

    body = _section(layout, "GMI_extract_advanced", "高级 / 分步 / 排错")
    if body:
        body.prop(scene, "gmi_profile_dir")
        body.prop(scene, "gmi_capture_dir")
        body.prop(scene, "gmi_body_json_library_dir", text=f"{target_name} JSON 资源库")
        body.operator("gmi.build_full_profile", text="只生成 / 重新生成完整配置档", icon="AUTO")
        body.prop(scene, "gmi_extract_output_dir")
        body.prop(scene, "gmi_extract_draw")
        body.operator("gmi.extract_profile_from_frame_dump", text="仅生成注入信息（不补权重骨架）", icon="FILE_NEW")
        body.operator("gmi.resolve_body_json_library", text="仅匹配资源库（查匹配结果）", icon="VIEWZOOM")
        body.operator("gmi.update_profile_from_frame_dump", text="换新抓帧校验并更新配置档", icon="FILE_REFRESH")
        body.operator("gmi.import_profile_object", text="导入配置档全部对象（排错）", icon="OUTLINER_OB_ARMATURE")
        body.operator("gmi.import_reference", text="只导入抓帧参考模型（无权重）", icon="IMPORT")


def draw_model_step(layout, scene, context):
    obj = _author_object(scene, context)

    column = _group(layout, "要导出的作者网格")
    row = column.row()
    row.alert = obj is None
    row.prop(scene, "gmi_author_object", text="作者模型")
    if _is_hair_package(scene):
        column.prop(scene, "gmi_hairprop_object", text="配套发饰（可选）")
    _note(layout, "选择后，材质、骨架、体检和导出都会固定使用它，不再跟随临时激活对象")

    column = _group(layout, "建模准备清单")
    column.label(text="网格：完成镜像，删除不会导出的头部 / 身体内层与重复面")
    column.label(text="贴图：整理到一套正方形图集，导出用的 UV 必须是活动 UV0")
    column.label(text="绑定：全身对齐参考骨架，Armature 修改器与顶点权重都在作者网格上")
    column.label(text="对象：确认单位和朝向后应用旋转与缩放")

    problems = _model_problems(obj)
    if problems:
        column = _group(layout, "现在能检测到的问题")
        _draw_problems(column, problems)

    _go(layout, "gmi.activate_author_object", "确认并使用这个作者模型",
        icon="MESH_DATA", enabled=obj is not None)


def draw_texture_step(layout, scene, context):
    is_hair = _is_hair_package(scene)
    obj = _author_object(scene, context)
    has_slots = bool(obj and obj.type == "MESH" and obj.material_slots)
    needs_co = not is_hair and has_slots and any(
        slot.material and getattr(slot.material, "gmi_alpha_mode", "") == "NATIVE_CO"
        for slot in obj.material_slots)

    column = _group(layout, "游戏贴图（正方形）")
    _need(column, scene, "gmi_base_color_file", text="基础色 t0")
    if is_hair:
        column.prop(scene, "gmi_hair_use_base_alpha")
    column.prop(scene, "gmi_packed_mask_file", text="混合遮罩 t1")
    column.prop(scene, "gmi_shade_color_file", text="暗面材质 t4")
    column.prop(scene, "gmi_neutral_material")
    _note(layout, "t0 必填；t1 / t4 留空时，主按钮会根据下面选定的材质类型生成")

    column = _group(layout, "材质槽")
    if has_slots:
        column.template_list("MATERIAL_UL_matslots", "GMI_materials", obj, "material_slots",
                             obj, "active_material_index", rows=5)
        material = obj.active_material
        if material is not None:
            detail = column.box()
            detail.label(text=material.name)
            detail.prop(material, "gmi_material_class", text="材质类型")
            if not is_hair:
                detail.prop(material, "gmi_alpha_mode", text="渲染方式")
            detail.prop(material, "gmi_material_toon", text="明暗范围")
            if not is_hair and material.gmi_alpha_mode == "GMI_TRANSPARENT":
                detail.prop(material, "gmi_transparent_alpha")
                detail.prop(material, "gmi_transparent_toon")
                detail.prop(material, "gmi_transparent_proxy")
                detail.prop(material, "gmi_transparent_co_atlas")
        else:
            row = column.row()
            row.alert = True
            row.label(text="选中的材质槽为空：先指定 Blender 材质", icon="ERROR")
        _note(layout, "一次只编辑选中的材质；金属件务必标为金属，透明方式只在确实需要时改变")
    else:
        row = column.row()
        row.alert = True
        row.label(text="作者模型没有有效材质槽：回到阶段 2 分好材质", icon="ERROR")

    if needs_co:
        column = _group(layout, "原生 co 贴图")
        _need(column, scene, "gmi_opacity_texture_file")
        column.prop(scene, "gmi_opacity_packed_mask_file")
        column.prop(scene, "gmi_opacity_shade_color_file")
        _note(layout, "上面至少一个材质槽选择了“原生co”，它必须使用独立的 t0")

    column = _group(layout, "生成选项")
    column.prop(scene, "gmi_skin_calibrate")
    column.prop(scene, "gmi_form_shading")
    if scene.gmi_form_shading:
        column.prop(scene, "gmi_form_strength")
    _go(layout, "gmi.bake_material_maps", "生成游戏材质贴图", icon="NODE_MATERIAL",
        enabled=bool(str(scene.gmi_base_color_file or "").strip()) and has_slots)

    column = _group(layout, "描边")
    if is_hair:
        column.prop(scene, "gmi_hair_outline_tier")
        _note(layout, "发型描边使用常量档；进游戏偏亮就换更暗一档")
    else:
        column.prop(scene, "gmi_vertex_color_mode")
        if scene.gmi_vertex_color_mode == "BASECOLOR":
            _note(layout, "“取自基础色”会在导出时从本页 t0 采样")
    column.prop(scene, "gmi_outline_width_mode")

    if is_hair:
        body = _section(layout, "GMI_step3_hairprop", "发饰贴图（只在制作发饰时填）")
        if body:
            body.prop(scene, "gmi_hairprop_base_color_file")
            body.prop(scene, "gmi_hairprop_packed_mask_file")
            body.prop(scene, "gmi_hairprop_shade_color_file")

    if not is_hair and not needs_co:
        body = _section(layout, "GMI_step3_co", "原生 co 贴图")
        if body:
            body.prop(scene, "gmi_opacity_texture_file")
            body.prop(scene, "gmi_opacity_packed_mask_file")
            body.prop(scene, "gmi_opacity_shade_color_file")
            _note(body, "只有材质槽设成「原生co」时才需要")

    body = _section(layout, "GMI_step3_preview", "在 Blender 里预览游戏材质")
    if body:
        body.operator("gmi.create_body_material_template", text="创建预览材质模板", icon="MATERIAL")

    body = _section(layout, "GMI_generate_material_advanced", "高级：t1 单通道覆盖")
    if body:
        body.prop(scene, "gmi_t1_r_file")
        body.prop(scene, "gmi_t1_g_file")
        body.prop(scene, "gmi_t1_b_file")
        active_component = _active_component(scene, _author_object(scene, context))
        a_label = (
            "t1.A HHL / 镜面可见性" if active_component == "hair"
            else "t1.A 材质可见性（通常 0）" if active_component == "hairprop"
            else "t1.A AO / 间接光"
        )
        body.prop(scene, "gmi_t1_a_file", text=a_label)
        _note(body, "填四张=整图合成；只填部分=生成后覆盖对应通道")


def draw_rig_step(layout, scene, context):
    obj = _author_object(scene, context)
    undecided = [item for item in scene.gmi_bone_map if _row_state(item) == "undecided"]

    column = _group(layout, "骨骼处理队列")
    if not scene.gmi_bone_map:
        _note(column, "扫描会先套用已知骨架预设；只把无法自动决定的身体骨和装饰骨列出来")
        op = _go(layout, "gmi.build_bone_map", "扫描源骨骼", icon="VIEWZOOM",
                 enabled=bool(obj and obj.vertex_groups))
        op.only_unmapped = True
    else:
        row = column.row(align=True)
        op = row.operator("gmi.build_bone_map", text="重新扫描待处理", icon="FILE_REFRESH")
        op.only_unmapped = True
        op = row.operator("gmi.build_bone_map", text="列出全部", icon="OUTLINER")
        op.only_unmapped = False
        row.operator("gmi.clear_bone_map", text="清空", icon="X")
        if undecided:
            todo = column.row(align=True)
            todo.alert = True
            todo.label(text=f"{len(undecided)} 组还没决定处理方式", icon="ERROR")
            todo.prop(scene, "gmi_bone_map_only_undecided", text="只看这些", toggle=True)
        column.template_list("GMI_UL_bone_map", "GMI_bones", scene, "gmi_bone_map",
                             scene, "gmi_bone_map_index", rows=7)

        index = min(max(scene.gmi_bone_map_index, 0), len(scene.gmi_bone_map) - 1)
        item = scene.gmi_bone_map[index]
        detail = _group(layout, "选中骨组的处理方式")
        members = _row_bones(item)
        detail.label(text=item.source + (f"（同组 {len(members)} 根）" if len(members) > 1 else ""))
        problem = _bone_problem(item)
        if problem:
            _draw_problems(detail, [problem])
        detail.prop_search(item, "target", scene, "gmi_bone_targets", text="映射到游戏骨")
        if item.target:
            _note(detail, "已映射到身体骨；装饰处理选项已隐藏")
        else:
            _note(detail, "不属于身体骨时，在下面选择一种装饰骨处理")
            detail.prop(item, "strategy", text="装饰处理")
            if item.strategy in {"integrate", "native_driver"}:
                detail.prop(item, "swing_category", text="部件类型")
            if item.strategy == "integrate":
                detail.prop(item, "swing_anchor")
        row = detail.row(align=True)
        inspect = row.operator("gmi.show_bone_weights", text="查看这组权重", icon="BRUSH_DATA")
        inspect.source = item.source
        if len(members) > 1:
            split = row.operator("gmi.split_bone_group", text="拆成逐根处理", icon="MOD_EXPLODE")
            split.index = index

        _go(layout, "gmi.report_rig_alignment", "量对齐与跨关节权重带", icon="DRIVER_DISTANCE")
        draw_rig_report(layout, scene, context, show_action=False)

    body = _section(layout, "GMI_rig_repairs", "修复工具（会改模型）")
    if body:
        body.operator("gmi.split_weight_from_neighbours", text="从相邻骨劈权重",
                      icon="MOD_VERTEX_WEIGHT")
        _note(body, "只在源模型缺少锁骨、脖子、脚尖等承重关节时使用")
        row = body.row(align=True)
        row.operator("gmi.bake_rest_offset", text="烘焙静止形变", icon="RENDER_STILL")
        revert = row.operator("gmi.bake_rest_offset", text="回退烘焙", icon="LOOP_BACK")
        revert.revert = True
        _note(body, "烘焙会改网格坐标，但会把原坐标存在对象上供回退")

    body = _section(layout, "GMI_rig_files", "高级 / 映射文件与骨架预设")
    if body:
        body.prop(scene, "gmi_source_rig")
        body.prop(scene, "gmi_bone_remap_file")
        body.prop(scene, "gmi_physics_override_file")
        row = body.row(align=True)
        row.operator("gmi.save_bone_map", text="存为 JSON", icon="FILE_TICK")
        row.operator("gmi.load_bone_map", text="从 JSON 读入", icon="IMPORT")
        _note(body, "外部 JSON 与上面的处理队列等价；队列里手动填写的内容优先")


def draw_export_step(layout, scene, context):
    obj = _author_object(scene, context)
    has_bundle_weights = bool(obj and obj.vertex_groups)
    problems = _stage_problems(scene, context, "EXPORT")

    column = _group(layout, "模组信息")
    _need(column, scene, "gmi_package_id")
    column.prop(scene, "gmi_package_name")
    column.prop(scene, "gmi_author")

    column = _group(layout, "成品位置与模板")
    _need(column, scene, "gmi_output_dir")
    _need(column, scene, "gmi_bundle_template", text="R32 模板 bundle")
    if _is_hair_package(scene):
        column.prop(scene, "gmi_hairprop_object")
    from . import operators
    vendored = operators.vendored_unitypy()
    if not vendored:
        column.prop(scene, "gmi_bundle_python")
    if scene.gmi_output_dir and scene.gmi_package_id:
        _note(layout, f"成品将写入：{scene.gmi_package_id} / {scene.gmi_package_id}.bundle")

    column = _group(layout, "导出前检查")
    if problems:
        _draw_problems(column, problems)
    else:
        _note(column, "界面未发现明显阻断；点击导出后仍会运行完整的骨架、权重和模板闸门")

    row = layout.row()
    row.scale_y = 2.0
    row.enabled = not problems
    op = row.operator("gmi.export_bundle_source", text="导出并打包 bundle", icon="PACKAGE")
    op.also_patch = True

    body = _section(layout, "GMI_export_source_only", "只导出 bundle 源（诊断）")
    if body:
        row = body.row()
        row.enabled = has_bundle_weights
        row.operator("gmi.export_bundle_source", text="导出 bundle 源", icon="PACKAGE")
        if vendored:
            _note(body, f"已内置打包器（UnityPy {vendored}），正常制作不需要外部 Python")

    body = _section(layout, "GMI_export_risk", "高级 / 风险放行")
    if body:
        body.prop(scene, "gmi_allow_undecided")
        body.prop(scene, "gmi_unmapped_bone_fallback")
        _note(body, "风险放行只用于定位问题；成品应回阶段 4 把每组骨处理清楚")


def _row_bones(item):
    members = [name for name in str(item.members or "").split("\n") if name]
    return members or ([item.source] if item.source else [])


def _row_state(item):
    members = _row_bones(item)
    # 一组多根骨指到同一根目标骨,那就是多对一=合并,不是 direct
    return core.row_state(item.target, item.strategy, shared_target=len(members) > 1)


def draw_rig_report(layout, scene, context=None, show_action=True):
    """P2 的尺子：逐骨关节位置差 / 静止朝向差 + 跨关节权重带。作者自查不到朝向,所以必须逐骨报。"""
    raw = scene.gmi_rig_report
    box = _section(layout, "GMI_rig_report", "对齐体检结果（只读）", closed=not bool(raw))
    if box is None:
        return
    if show_action:
        _go(box, "gmi.report_rig_alignment", "量对齐与跨关节权重带", icon="DRIVER_DISTANCE")
    if not raw:
        _note(box, "朝向差静止截图看不出来：转身之后手臂会转到身后、手指拉成面条")
        return
    try:
        data = json.loads(raw)
    except ValueError:
        return
    icons = {"yellow": "ERROR", "red": "CANCEL"}
    rows = data.get("alignment") or []
    bad = [row for row in rows if row.get("grade") != "green"]
    box.label(text=f"逐骨对齐：量了 {data.get('measured', 0)} 根，"
                   f"{len(bad)} 根不合格（朝向 {core.ORIENTATION_WARN_DEG:.0f}° 黄 / "
                   f"{core.ORIENTATION_FAIL_DEG:.0f}° 红；位置最高判黄）")
    for row in bad[:8]:
        box.label(text=f"{row['bone']}   朝向 {core.format_degrees(row.get('deg'))}"
                       f"（对 {row.get('child') or '-'}）   位置 {row['mm']:.1f}mm",
                  icon=icons.get(row.get("grade"), "ERROR"))
    if len(bad) > 8:
        box.label(text=f"…还有 {len(bad) - 8} 根，看操作日志", icon="INFO")
    if not rows:
        box.label(text="没有可量的 direct 映射骨：先在骨骼映射表里指定身体骨", icon="ERROR")
    states = data.get("states") or {}
    if states:
        total = sum(states.values()) or 1.0
        box.label(text="权重去处：" + "  ".join(
            f"{core.ROW_STATE_LABELS.get(state, state)} {mass / total:.0%}"
            for state, mass in sorted(states.items(), key=lambda item: -item[1])))
        if states.get("undecided"):
            box.label(text="「未决定」= 这些骨还没有目标骨也没选策略，导出会被拦下",
                      icon="ERROR")
    collapsed = data.get("collapsed") or []
    if collapsed:
        box.label(text=f"节数不同、被塌进同一根目标骨的链 {len(collapsed)} 处"
                       "（塌是安全的，塌错是「有值但错」，闸门抓不到——请人眼核一下）",
                  icon="ERROR")
        for row in collapsed[:5]:
            box.label(text=f"  {row['target']} ← {'、'.join(row['sources'][:4])}"
                           f"（{row['mass']:.1f}% 权重）")
    bands = data.get("bands") or []
    if bands:
        box.label(text=f"跨关节权重带（基线：{data.get('baseline', '')}）——"
                       "唯一能预判「肩膀会不会崩」的数字")
        for band in bands:
            box.label(text=f"{band['joint']}   {band['share']:.1%}   "
                           f"（原版 {band['vanilla']:.1%}）",
                      icon=icons.get(band.get("grade"), "DOT"))
        box.label(text="肩明显低于原版 = A→T 之后肩膀会崩；只能在 Blender 里补权重", icon="INFO")


class GMI_PT_main(Panel):
    bl_label = "GakumasMI 工具"
    bl_idname = "GMI_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"

    def draw_header(self, context):
        from . import bl_info
        self.layout.label(text="v%d.%d.%d" % bl_info["version"])

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        workflow = layout.box()
        workflow.prop(scene, "gmi_component_id", text="当前制作目标")
        if _is_hair_package(scene):
            _note(workflow, "发型与可选发饰会在同一个包里导出")

        navigation = layout.row(align=True)
        navigation.scale_y = 1.25
        navigation.prop(scene, "gmi_workflow_stage", expand=True)
        stage = scene.gmi_workflow_stage
        _draw_stage_header(layout, scene, context, stage)
        if stage == "TARGET":
            draw_profile_step(layout, scene)
        elif stage == "MODEL":
            draw_model_step(layout, scene, context)
        elif stage == "MATERIAL":
            draw_texture_step(layout, scene, context)
        elif stage == "RIG":
            draw_rig_step(layout, scene, context)
        else:
            draw_export_step(layout, scene, context)


_MASS_WIDTH = 2.2


class GMI_UL_bone_map(bpy.types.UIList):
    """一行 = 一组结构上同类的源骨（锚点 + 链 + 链长）。左边代表骨名 + 组内根数 + 权重占比。"""

    def filter_items(self, context, data, propname):
        """「只看未决定」过滤：未决定的组通常散在几十行里，靠搜索框手打骨名找不现实。"""
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item] * len(items)
        if getattr(context.scene, "gmi_bone_map_only_undecided", False):
            for index, item in enumerate(items):
                if _row_state(item) != "undecided":
                    flags[index] = 0
        if self.filter_name:
            needle = self.filter_name.lower()
            for index, item in enumerate(items):
                if needle not in item.source.lower() and needle not in (item.members or "").lower():
                    flags[index] = 0
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        members = _row_bones(item)
        state = _row_state(item)
        problem = _bone_problem(item)
        label = item.source + (f"  +{len(members) - 1}" if len(members) > 1 else "")
        row.alert = bool(problem)
        row.label(text=label, icon=_STATE_ICONS.get(state, "NONE") if problem else "NONE")
        if problem:
            row.label(text="未决定" if state == "undecided" else "异常")
        mass = row.row()
        mass.ui_units_x = _MASS_WIDTH
        mass.alignment = "RIGHT"
        mass.label(text=f"{item.mass:.0f}%" if item.mass >= 0.5 else "")


CLASSES = (
    GMI_UL_bone_map,
    GMI_PT_main,
)
