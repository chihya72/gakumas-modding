import json

import bpy
from bpy.types import Panel

from . import core


def _is_hair_package(scene):
    return scene.gmi_component_id == "hair"


def _active_component(scene, obj):
    return obj.get("gmi_component_id", scene.gmi_component_id) if obj else scene.gmi_component_id


def draw_profile_step(layout, scene):
    is_hair = _is_hair_package(scene)
    target_name = "发型" if is_hair else "身体"

    box = layout.box()
    box.label(text="A · 从抓帧生成配置档", icon="FILE_NEW")
    box.label(text="输入：游戏抓帧 + 网格 JSON 资源库")
    box.label(text=("发型资源库需含 Geo_Hair.json 和 Geo_HairProp.json" if is_hair
                    else "身体资源库需含 Geo_Body.json"))
    if is_hair:
        box.label(text="发型与配套发饰会自动并入同一个配置档", icon="LINKED")
    box.prop(scene, "gmi_capture_dir")
    box.prop(scene, "gmi_body_json_library_dir", text=f"{target_name} JSON 资源库")
    box.prop(
        scene,
        "gmi_body_resource",
        text="目标 hair 资源（可选）" if is_hair else "目标 body 资源（可选）",
    )
    row = box.row()
    row.scale_y = 1.5
    row.operator("gmi.build_full_profile", text="生成完整配置档", icon="AUTO")
    box.label(text="成功后自动填写下方配置档目录", icon="CHECKMARK")

    reference = layout.box()
    reference.label(text="B · 导入参考模型与骨架", icon="ARMATURE_DATA")
    reference.label(text="已有配置档可直接从这里开始，跳过 A")
    reference.prop(scene, "gmi_profile_dir")
    row = reference.row()
    row.scale_y = 1.3
    row.operator("gmi.import_weighted_reference", text="导入参考模型与骨架", icon="ARMATURE_DATA")
    reference.label(text="参考模型是发型描边取色和绑定体检的数据来源，导出前别删", icon="ERROR")

    header, advanced = layout.panel("GMI_extract_advanced", default_closed=True)
    header.label(text="高级 / 分步 / 排错", icon="PREFERENCES")
    if advanced:
        advanced.prop(scene, "gmi_extract_output_dir")
        advanced.prop(scene, "gmi_extract_draw")
        advanced.operator("gmi.extract_profile_from_frame_dump", text="仅生成注入信息（不补权重骨架）", icon="FILE_NEW")
        advanced.operator("gmi.resolve_body_json_library", text="仅匹配资源库（查匹配结果）", icon="VIEWZOOM")
        advanced.operator("gmi.update_profile_from_frame_dump", text="换新抓帧校验并更新配置档", icon="FILE_REFRESH")
        advanced.operator("gmi.import_profile_object", text="导入配置档全部对象（排错）", icon="OUTLINER_OB_ARMATURE")
        advanced.operator("gmi.import_reference", text="只导入抓帧参考模型（无权重）", icon="IMPORT")


def draw_texture_step(layout, scene, context):
    is_hair = _is_hair_package(scene)

    material = layout.box()
    material.label(text="指定三张导出贴图（正方形）", icon="MATERIAL")
    material.label(text="t0 必填；t1/t4 没有现成的就留空，用下方按材质生成")
    material.prop(scene, "gmi_base_color_file", text="基础色 t0")
    if is_hair:
        material.prop(scene, "gmi_hair_use_base_alpha")
    material.prop(scene, "gmi_packed_mask_file", text="混合遮罩 t1")
    material.prop(scene, "gmi_shade_color_file", text="暗面材质 t4 / sdw")
    material.prop(scene, "gmi_neutral_material")
    if is_hair:
        material.label(text="Hair：默认保留 t0.A；t1.A 默认安全归零；自动 t4 是缺图 fallback", icon="INFO")
        prop = material.box()
        prop.label(text="发饰贴图（只在制作发饰时填写）", icon="LINKED")
        prop.prop(scene, "gmi_hairprop_base_color_file")
        prop.prop(scene, "gmi_hairprop_packed_mask_file")
        prop.prop(scene, "gmi_hairprop_shade_color_file")
    else:
        material.label(text="t1：R 阴影阈值 / G 光滑 / B 金属 / A AO（线性空间）", icon="INFO")
        material.label(text="t4：RGB=暗化基础色 / A=皮肤遮罩（非透明度）")

    slots = layout.box()
    slots.label(text="给材质槽标类型（生成 t1/t4 和描边预设的依据）", icon="MATERIAL")
    obj = context.active_object
    if is_hair:
        component_name = "发饰 hairprop" if _active_component(scene, obj) == "hairprop" else "发型 hair"
        slots.label(text=f"当前激活的作者网格：{component_name}", icon="LINKED")
    if obj and obj.type == "MESH" and obj.material_slots:
        if not is_hair:
            slots.label(text="透明/镂空部件把「渲染材质」改为原生co；其余保持不透明", icon="INFO")
        slots.label(text="金属件务必标 metal；明暗 -1=用预设，偏暗调高", icon="INFO")
        for slot in obj.material_slots:
            if slot.material is None:
                continue
            row = slots.row(align=True)
            row.prop(slot.material, "gmi_material_class", text=slot.material.name)
            if not is_hair:
                row.prop(slot.material, "gmi_alpha_mode", text="渲染材质")
            row.prop(slot.material, "gmi_material_toon", text="明暗")
    else:
        slots.label(text="先在 3D 视图激活已分好材质的作者网格", icon="INFO")

    if not is_hair:
        co = layout.box()
        co.label(text="原生 co 贴图（有材质槽设为原生co时必填）", icon="SHADING_RENDERED")
        co.prop(scene, "gmi_opacity_texture_file")
        co.prop(scene, "gmi_opacity_packed_mask_file")
        co.prop(scene, "gmi_opacity_shade_color_file")
        co.label(text="co 部件用自己的贴图与 UV，不共用身体那套", icon="INFO")

    generate = layout.box()
    generate.label(text="按材质槽类型处理贴图", icon="NODE_MATERIAL")
    generate.label(text="需要先填 t0 并标好上方材质类型；结果自动填进贴图栏")
    generate.label(text="生成 t1/t4；开肤色对齐时另存一份校准过的 t0，不改你的原文件")
    generate.prop(scene, "gmi_skin_calibrate")
    generate.prop(scene, "gmi_form_shading")
    if scene.gmi_form_shading:
        generate.prop(scene, "gmi_form_strength")
    generate.operator(
        "gmi.bake_material_maps", text="按材质生成 t1/t4 并校准肤色", icon="NODE_MATERIAL")

    preview = layout.box()
    preview.label(text="可选：在 Blender 里近似预览游戏材质")
    preview.operator("gmi.create_body_material_template", text="创建预览材质模板", icon="MATERIAL")

    header, advanced = layout.panel("GMI_generate_material_advanced", default_closed=True)
    header.label(text="高级：t1 单通道覆盖", icon="PREFERENCES")
    if advanced:
        advanced.prop(scene, "gmi_t1_r_file")
        advanced.prop(scene, "gmi_t1_g_file")
        advanced.prop(scene, "gmi_t1_b_file")
        active_component = _active_component(scene, context.active_object)
        a_label = (
            "t1.A HHL / 镜面可见性" if active_component == "hair"
            else "t1.A 材质可见性（通常 0）" if active_component == "hairprop"
            else "t1.A AO / 间接光"
        )
        advanced.prop(scene, "gmi_t1_a_file", text=a_label)
        advanced.label(text="填四张=整图合成；只填部分=生成后覆盖对应通道")


def draw_export_step(layout, scene, context):
    package = layout.box()
    package.label(text="模组信息（显示在 Mod 管理器里）", icon="PACKAGE")
    package.prop(scene, "gmi_output_dir")
    package.prop(scene, "gmi_package_id")
    package.prop(scene, "gmi_package_name")
    package.prop(scene, "gmi_author")

    mesh = layout.box()
    mesh.label(text="描边设置", icon="GREASEPENCIL")
    if _is_hair_package(scene):
        mesh.prop(scene, "gmi_hair_outline_tier")
        mesh.label(text="发型描边色是常量档；进游戏偏亮就换更暗一档", icon="INFO")
    else:
        mesh.prop(scene, "gmi_vertex_color_mode")
        if scene.gmi_vertex_color_mode == "BASECOLOR":
            mesh.label(text="「取自基础色」要求步骤②已填 t0", icon="INFO")
    mesh.prop(scene, "gmi_outline_width_mode")

    export = layout.box()
    export.label(text="导出 AB bundle", icon="EXPORT")
    # 漏填 t0 不会报错,颜色会直接沿用游戏原贴图 → 错乱,这里必须显式提醒
    if not scene.gmi_base_color_file:
        export.label(text="未填基础色 t0：游戏会沿用原贴图，颜色错乱", icon="ERROR")
    obj = context.active_object
    component = _active_component(scene, obj)
    accepted = {scene.gmi_component_id}
    if _is_hair_package(scene):
        accepted.add("hairprop")
    has_bundle_weights = bool(
        obj and obj.type == "MESH" and component in accepted and obj.vertex_groups
    )
    if has_bundle_weights:
        export.label(text=f"已识别：{len(obj.vertex_groups)} 个顶点组的作者网格",
                     icon="CHECKMARK")
    else:
        target_name = "发型" if _is_hair_package(scene) else "身体"
        export.label(text=f"请先激活带顶点组权重的{target_name}作者网格", icon="ERROR")
    bundle_row = export.row()
    bundle_row.scale_y = 1.6
    bundle_row.enabled = has_bundle_weights
    bundle_row.operator("gmi.export_bundle_source", text="导出 bundle 源", icon="PACKAGE")
    if not has_bundle_weights:
        export.label(text="bundle 源需要作者模型顶点组权重", icon="INFO")
    if _is_hair_package(scene):
        export.prop(scene, "gmi_hairprop_object")
        if not scene.gmi_hairprop_object:
            export.label(text="未选发饰对象：只换发型，发饰保持原版", icon="INFO")
    if has_bundle_weights:
        export.prop(scene, "gmi_bundle_template")
        # 插件自带打包器时不需要外部 Python：那一栏只在没自带时才有意义，画出来会误导
        from . import operators
        vendored = operators.vendored_unitypy()
        if vendored:
            export.label(text=f"已内置打包器（UnityPy {vendored}）：不需要装 Python",
                         icon="CHECKMARK")
        else:
            export.prop(scene, "gmi_bundle_python")
        patch_row = export.row()
        patch_row.enabled = bool(scene.gmi_bundle_template)
        op = patch_row.operator(
            "gmi.export_bundle_source",
            text="导出并打包 bundle（一键）" if vendored else "导出并打包 bundle（一键，需外部 Python）",
            icon="PACKAGE")
        op.also_patch = True
        if not scene.gmi_bundle_template:
            export.label(text="一键打包需先选 R32 模板 bundle", icon="INFO")

    draw_rig_report(layout, scene, context)

    header, bones = layout.panel("GMI_export_bonemap", default_closed=True)
    header.label(text="骨骼映射表（一行 = 一组源骨 → 游戏骨）", icon="GROUP_BONE")
    if bones:
        bones.label(text="预设认识的骨架预填后无需改动；导出报「承重关节没拿到权重」时用这里",
                    icon="INFO")
        bones.label(text="装饰骨按结构（挂在哪根身体骨上 / 一条链 / 链长）并成一行，"
                         "一行上的决定落到整组；要逐根不同就按行尾的「拆开」")
        bones.label(text="左=目标游戏骨（身体骨填这个）；中=装饰物理策略（飘带/花边选这个）；"
                         "右=部件类型（选了「自建摇物链」才可点）")
        row = bones.row(align=True)
        op = row.operator("gmi.build_bone_map", text="扫描源骨骼", icon="VIEWZOOM")
        op.only_unmapped = True
        op = row.operator("gmi.build_bone_map", text="列出全部", icon="OUTLINER")
        op.only_unmapped = False
        row.operator("gmi.clear_bone_map", text="", icon="X")
        if scene.gmi_bone_map:
            bones.template_list("GMI_UL_bone_map", "", scene, "gmi_bone_map",
                                scene, "gmi_bone_map_index", rows=8)
            # 装饰骨没有目标骨是正常状态（原版的飘带裙摆也没有），所以报的不是"没指定目标"，
            # 而是"这一组还没决定"——五档状态里的 undecided。
            undecided = [item for item in scene.gmi_bone_map
                         if _row_state(item) == "undecided"]
            if undecided:
                bones.label(text=f"还有 {len(undecided)} 组没决定怎么处理"
                                 "（填目标骨 / 选装饰物理策略）", icon="ERROR")
            row = bones.row(align=True)
            row.operator("gmi.save_bone_map", text="存为 JSON", icon="FILE_TICK")
            row.operator("gmi.load_bone_map", text="从 JSON 读入", icon="IMPORT")

    header, advanced = layout.panel("GMI_export_advanced", default_closed=True)
    header.label(text="高级 / 外部模型骨骼", icon="PREFERENCES")
    if advanced:
        advanced.prop(scene, "gmi_source_rig")
        advanced.prop(scene, "gmi_bone_remap_file")
        advanced.prop(scene, "gmi_physics_override_file")
        advanced.label(text="这两个 JSON 与上面的骨骼映射表等价，表里填过的优先", icon="INFO")


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
        workflow.label(text="选好制作目标，按 ① → ③ 依次完成", icon="INFO")
        workflow.prop(scene, "gmi_component_id")
        if _is_hair_package(scene):
            workflow.label(text="发型 mod 可只换发型；发饰是可选的第二个网格对象", icon="INFO")


class _GMIStepPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"
    bl_parent_id = "GMI_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        self.draw_step(layout, context)


class GMI_PT_step_profile(_GMIStepPanel):
    bl_label = "① 准备配置档"
    bl_idname = "GMI_PT_step_profile"

    def draw_step(self, layout, context):
        draw_profile_step(layout, context.scene)


class GMI_PT_step_texture(_GMIStepPanel):
    bl_label = "② 准备材质"
    bl_idname = "GMI_PT_step_texture"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_step(self, layout, context):
        draw_texture_step(layout, context.scene, context)


class GMI_PT_step_export(_GMIStepPanel):
    bl_label = "③ 导出 AB bundle"
    bl_idname = "GMI_PT_step_export"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_step(self, layout, context):
        draw_export_step(layout, context.scene, context)


# 骨映射表右侧控件的固定宽度(UI 单位,1 单位 ≈ 20px @100% 缩放)。骨名列吃掉剩下的宽度——
# 让四列等分的话骨名会被截成 "RightRi... 0."，而作者恰恰要靠骨名判断这根骨是什么部件。
# 嫌窄嫌宽直接改这五个数。
_MASS_WIDTH, _TARGET_WIDTH, _STRATEGY_WIDTH, _CATEGORY_WIDTH = 3.4, 9.0, 8.0, 8.0
_STATE_WIDTH = 4.6

_STATE_ICONS = {
    "direct": "CHECKMARK", "merge": "AUTOMERGE_ON", "helper": "CONSTRAINT_BONE",
    "bake": "RENDER_STILL", "reject": "CANCEL", "undecided": "ERROR",
}


def _row_bones(item):
    members = [name for name in str(item.members or "").split("\n") if name]
    return members or ([item.source] if item.source else [])


def _row_state(item):
    members = _row_bones(item)
    # 一组多根骨指到同一根目标骨,那就是多对一=合并,不是 direct
    return core.row_state(item.target, item.strategy, shared_target=len(members) > 1)


def draw_rig_report(layout, scene, context=None):
    """P2 的尺子：逐骨关节位置差 / 静止朝向差 + 跨关节权重带。作者自查不到朝向,所以必须逐骨报。"""
    box = layout.box()
    box.label(text="对齐体检（只读，不改模型）", icon="DRIVER_TRANSFORM")
    box.operator("gmi.report_rig_alignment", icon="CHECKMARK")
    # 缺骨补权重是**会改权重**的那一个，所以和只读尺子分开画，且写清它只动那几根骨。
    fix = box.row()
    fix.operator("gmi.split_weight_from_neighbours", icon="MOD_VERTEX_WEIGHT")
    box.label(text="源模型没有锁骨/脖子/脚尖时用上面这个：按原版权重分布从相邻骨劈，"
                   "只动那几根骨所在的一族", icon="INFO")
    # 烘焙是**会改网格**的一步，所以按钮旁边永远摆着回退，且明说改了什么
    obj = context.active_object if context else None
    baked = bool(obj and obj.get("gmi_pre_bake"))
    bake = box.row(align=True)
    bake.operator("gmi.bake_rest_offset", icon="RENDER_STILL")
    revert = bake.operator("gmi.bake_rest_offset", text="回退烘焙", icon="LOOP_BACK")
    revert.revert = True
    if baked:
        box.label(text="这个网格已烘过静止形变（回退记录在对象上，随时能退回）", icon="CHECKMARK")
    else:
        box.label(text="标了「烘焙形变+并到父骨」的骨要先烘一次再导出；形变小于 0.05mm 时"
                       "只声明、不动网格", icon="INFO")
    raw = scene.gmi_rig_report
    if not raw:
        box.label(text="量关节位置差 + 静止朝向差（本骨→人形子骨的方向）：朝向差静止截图"
                       "看不出来，转身之后手臂会转到身后、手指拉成面条", icon="INFO")
        return
    try:
        data = json.loads(raw)
    except ValueError:
        return
    icons = {"green": "CHECKMARK", "yellow": "ERROR", "red": "CANCEL"}
    rows = data.get("alignment") or []
    bad = [row for row in rows if row.get("grade") != "green"]
    box.label(text=f"逐骨对齐：量了 {data.get('measured', 0)} 根，"
                   f"{len(bad)} 根不合格（朝向 {core.ORIENTATION_WARN_DEG:.0f}° 黄 / "
                   f"{core.ORIENTATION_FAIL_DEG:.0f}° 红；位置最高判黄）")
    for row in (bad or rows)[:8]:
        box.label(text=f"{row['bone']}   朝向 {core.format_degrees(row.get('deg'))}"
                       f"（对 {row.get('child') or '-'}）   位置 {row['mm']:.1f}mm",
                  icon=icons.get(row.get("grade"), "DOT"))
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


class GMI_UL_bone_map(bpy.types.UIList):
    """一行 = 一组结构上同类的源骨（锚点 + 链 + 链长）。左边代表骨名 + 组内根数 + 权重占比。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        filled = bool(item.target.strip())
        members = _row_bones(item)
        state = _row_state(item)
        label = item.source + (f"  +{len(members) - 1}" if len(members) > 1 else "")
        row.label(text=label, icon=_STATE_ICONS.get(state, "DOT"))
        if len(members) > 1:
            split = row.operator("gmi.split_bone_group", text="", icon="MOD_EXPLODE")
            split.index = index
        state_column = row.row()
        state_column.ui_units_x = _STATE_WIDTH
        state_column.alignment = "RIGHT"
        state_column.label(text=core.ROW_STATE_LABELS.get(state, state))
        mass = row.row()
        mass.ui_units_x = _MASS_WIDTH
        mass.alignment = "RIGHT"
        mass.label(text=f"{item.mass:.2f}%")
        inspect = row.operator("gmi.show_bone_weights", text="", icon="BRUSH_DATA")
        inspect.source = item.source
        target = row.row(align=True)
        target.ui_units_x = _TARGET_WIDTH
        target.prop_search(item, "target", context.scene, "gmi_bone_targets",
                           text="", icon="BONE_DATA")
        # 填了目标骨就是确定映射,装饰物理策略对它没意义,不画
        strategy = row.row(align=True)
        strategy.ui_units_x = _STRATEGY_WIDTH
        strategy.enabled = not filled
        strategy.prop(item, "strategy", text="")
        # 部件类型只对**会新建骨**的两个策略有意义：自建摇物链取哪一档摆动参数，
        # 原版布料驱动器取哪一种驱动器（裙→Skirt、披挂→Frill、袖→HumanoidSleeve）。
        # 别的策略不新建骨，没有参数可选。
        category = row.row(align=True)
        category.ui_units_x = _CATEGORY_WIDTH
        category.enabled = not filled and item.strategy in {"integrate", "native_driver"}
        category.prop(item, "swing_category", text="")
        # 运行时只实现了三类驱动器（Skirt / Frill / HumanoidSleeve）。选了「原版布料驱动器」
        # 又落在别的类别（ribbon，或"自动"猜成 ribbon）时，导出后这几根骨**既没有驱动器也
        # 没有摇物** —— 一个不会动的哑骨，日志还全绿。所以当场标出来，不让它静默过去。
        if not filled and item.strategy == "native_driver":
            resolved = (item.swing_category if item.swing_category != "auto"
                        else core.swing_category(item.source))
            if resolved not in core.DRIVER_CATEGORIES:
                row.label(text="", icon="ERROR")


class GMI_PT_unity_route(bpy.types.Panel):
    """两个按钮的那条路：作者只开 Blender，Unity 在后台跑。"""

    bl_label = "Unity 路线（两下点击）"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        import json
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "gmi_unity_kind")
        layout.prop(scene, "gmi_unity_target")
        layout.prop(scene, "gmi_unity_sdk_dir")
        layout.prop(scene, "gmi_unity_editor")

        column = layout.column(align=True)
        column.scale_y = 1.4
        column.operator("gmi.pose_t_pose", icon="ARMATURE_DATA")
        column.operator("gmi.check_adapt", icon="CHECKMARK")
        column.operator("gmi.export_unity_mod", icon="EXPORT")

        from . import unity_route
        if unity_route.PREVIEW_KEYS:
            row = layout.row()
            for key in unity_route.PREVIEW_KEYS:
                row.template_icon(icon_value=unity_route.preview_icon(key), scale=8.0)

        raw = scene.gmi_unity_report
        if not raw:
            return
        try:
            findings = json.loads(raw)
        except Exception:
            return
        box = layout.box()
        icons = {"ok": "CHECKMARK", "warn": "ERROR", "fail": "CANCEL"}
        for item in findings:
            row = box.row()
            row.label(text=item.get("message", ""), icon=icons.get(item.get("level"), "DOT"))
            action = item.get("action")
            if action:
                box.label(text=f"    → {action}")


CLASSES = (
    GMI_UL_bone_map,
    GMI_PT_unity_route,
    GMI_PT_main,
    GMI_PT_step_profile,
    GMI_PT_step_texture,
    GMI_PT_step_export,
)
