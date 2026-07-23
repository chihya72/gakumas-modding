import bpy
from bpy.types import Panel


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
    reference.label(text="参考模型是传权和描边的数据来源，导出前别删", icon="ERROR")

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


def draw_binding_step(layout, scene):
    box = layout.box()
    box.label(text="把权重从参考模型转到作者模型", icon="MOD_ARMATURE")
    box.label(text="前提：作者模型已对齐参考模型（T-pose、同比例）")
    box.label(text="操作：3D 视图里只激活作者网格，再点按钮", icon="RESTRICT_SELECT_OFF")

    if _is_hair_package(scene):
        box.prop(scene, "gmi_transfer_risk_distance")
        row = box.row()
        row.scale_y = 1.5
        row.operator("gmi.transfer_profile_weights", text="绑定发型：传递权重", icon="MOD_DATA_TRANSFER")
        prop = layout.box()
        prop.label(text="配套发饰（可选，需要独立的发饰网格对象）", icon="BONE_DATA")
        prop.label(text="不做发饰=保留游戏原发饰；做发饰按软硬二选一：")
        row = prop.row()
        row.scale_y = 1.3
        row.operator("gmi.bind_hairprop_rigid", text="硬质发饰：刚体绑定到 Head_Hair", icon="CONSTRAINT_BONE")
        prop.operator("gmi.transfer_hairprop_weights", text="软质发饰：传递权重（可摆动）", icon="MOD_DATA_TRANSFER")
        prop.operator("gmi.transfer_hairprop_weights_smart", text="实验：智能传递发饰权重", icon="MOD_DATA_TRANSFER")
        prop.label(text="刚体会清掉已有权重，两个按钮别连着点", icon="ERROR")
    else:
        box.prop(scene, "gmi_transfer_risk_distance")
        row = box.row()
        row.scale_y = 1.5
        row.operator("gmi.transfer_profile_weights", text="绑定身体：传递权重", icon="MOD_DATA_TRANSFER")

        header, advanced = layout.panel("GMI_body_smart_transfer", default_closed=True)
        header.label(text="实验：薄缝 / 多层模型智能传权", icon="EXPERIMENTAL")
        if advanced:
            advanced.operator("gmi.transfer_profile_weights_smart", text="实验：智能传递权重", icon="MOD_DATA_TRANSFER")
    review = layout.box()
    review.label(text="传权后复核", icon="RESTRICT_SELECT_OFF")
    review.operator("gmi.select_high_risk_vertices", text="选中高风险顶点", icon="RESTRICT_SELECT_OFF")
    review.label(text="离身体远的顶点权重是猜的：袖口/裙摆重点看")
    review.label(text="问题顶点用 Weight Paint 修，或导出时关它们的描边")


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
    generate.label(text="没有 t1/t4？按材质槽类型生成", icon="NODE_MATERIAL")
    generate.label(text="需要先填 t0 并标好上方材质类型；结果自动填进贴图栏")
    generate.prop(scene, "gmi_form_shading")
    if scene.gmi_form_shading:
        generate.prop(scene, "gmi_form_strength")
    generate.operator("gmi.bake_material_maps", text="按材质生成 t1 / t4", icon="NODE_MATERIAL")

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

    header, texture = layout.panel("GMI_single_texture_export", default_closed=True)
    header.label(text="替代流程：不换网格，只替换一张贴图", icon="TEXTURE")
    if texture:
        texture.prop(scene, "gmi_texture_key")
        texture.prop(scene, "gmi_texture_file")
        texture.label(text="贴图键示例：body.baseColor / hair.baseColor")
        texture.operator("gmi.export_texture_mod", text="导出单贴图替换 mod", icon="TEXTURE")


def draw_export_step(layout, scene, context):
    package = layout.box()
    package.label(text="模组信息（显示在 Mod 管理器里）", icon="PACKAGE")
    package.prop(scene, "gmi_output_dir")
    package.prop(scene, "gmi_package_id")
    package.prop(scene, "gmi_package_name")
    package.prop(scene, "gmi_author")
    package.prop(scene, "gmi_cover_image", text="预览图（必填）")

    mesh = layout.box()
    mesh.label(text="描边设置", icon="GREASEPENCIL")
    if _is_hair_package(scene):
        mesh.prop(scene, "gmi_hair_outline_tier")
        mesh.label(text="发型描边色是常量档；进游戏偏亮就换更暗一档", icon="INFO")
    else:
        mesh.prop(scene, "gmi_vertex_color_mode")
        if scene.gmi_vertex_color_mode == "BASECOLOR":
            mesh.label(text="「取自基础色」要求步骤③已填 t0", icon="INFO")
    mesh.prop(scene, "gmi_outline_width_mode")

    export = layout.box()
    export.label(text="校验并导出", icon="EXPORT")
    # 漏填 t0 不会报错,而是 mod.ini 静默不生成 ps-t0 → 游戏内颜色错乱,这里必须显式提醒
    if not scene.gmi_base_color_file:
        export.label(text="未填基础色 t0：游戏会沿用原贴图，颜色错乱", icon="ERROR")
    obj = context.active_object
    component = _active_component(scene, obj)
    accepted = {scene.gmi_component_id}
    if _is_hair_package(scene):
        accepted.add("hairprop")
    ready = False
    if obj and obj.type == "MESH" and component in accepted:
        ready = bool(obj.get("gmi_profile_weights") or obj.get("gmi_source_vertex_count"))
        if obj.get("gmi_rigid_head_follow"):
            export.label(text="已识别：Head_Hair 刚体发饰", icon="CHECKMARK")
        elif obj.get("gmi_profile_weights"):
            export.label(text="已识别：已传权的作者网格", icon="CHECKMARK")
        else:
            export.label(text="已识别：原拓扑参考网格", icon="CHECKMARK")
    else:
        target_name = "发型" if _is_hair_package(scene) else "身体"
        export.label(text=f"请先激活已在②绑定过的{target_name}作者网格", icon="ERROR")
    if _is_hair_package(scene):
        hair_objects = [
            obj for obj in context.scene.objects
            if obj.type == "MESH" and obj.get("gmi_profile_weights")
            and obj.get("gmi_component_id") == "hair"
        ]
        prop_objects = [
            obj for obj in context.scene.objects
            if obj.type == "MESH" and obj.get("gmi_profile_weights")
            and obj.get("gmi_component_id") == "hairprop"
        ]
        ready = ready and len(hair_objects) == 1 and len(prop_objects) <= 1
        if prop_objects and not scene.gmi_hairprop_base_color_file:
            export.label(text="发饰已绑定但未填发饰 t0，发饰颜色会错乱", icon="ERROR")
        if ready:
            export.label(
                text=("将导出完整包：发型 + 发饰" if prop_objects
                      else "将只替换发型，保留游戏原发饰"),
                icon="CHECKMARK",
            )
        else:
            export.label(text="需要恰好 1 个已绑定发型网格、至多 1 个发饰网格", icon="INFO")
    row = export.row()
    row.scale_y = 1.6
    row.enabled = ready
    row.operator("gmi.export_validated_mod", text="校验并导出模组", icon="EXPORT")
    export.label(text="导出后把包文件夹放进游戏 Mods 目录，进游戏换装验证")
    has_weights = ready and bool(obj and obj.get("gmi_profile_weights"))
    bundle_row = export.row()
    bundle_row.enabled = has_weights
    bundle_row.operator("gmi.export_bundle_source", text="导出 bundle 源", icon="PACKAGE")
    if ready and not has_weights:
        export.label(text="bundle 源要求已传递配置档权重", icon="INFO")
    if has_weights:
        export.prop(scene, "gmi_bundle_template")
        export.prop(scene, "gmi_bundle_python")
        patch_row = export.row()
        patch_row.enabled = bool(scene.gmi_bundle_template)
        op = patch_row.operator("gmi.export_bundle_source",
                                text="导出并打包 bundle（一键，需外部 Python）", icon="PACKAGE")
        op.also_patch = True
        if not scene.gmi_bundle_template:
            export.label(text="一键打包需先选 R32 模板 bundle", icon="INFO")

    header, advanced = layout.panel("GMI_export_advanced", default_closed=True)
    header.label(text="高级 / 外部模型骨骼 / 分步导出", icon="PREFERENCES")
    if advanced:
        # MMD 等外部模型常有顶点残留在控制/物理骨上,导出报"没有可导出的配置档兼容权重"
        # 时在这里填兜底骨(一般填 Hips)或提供骨骼映射 JSON
        advanced.prop(scene, "gmi_bone_remap_file")
        advanced.prop(scene, "gmi_unmapped_bone_fallback")
        advanced.label(text="导出报「顶点没有兼容权重」→ 兜底骨填 Hips", icon="INFO")
        advanced.operator("gmi.validate_mesh", text="仅校验，不导出", icon="CHECKMARK")
        advanced.operator("gmi.export_inverse_skin_mod", text="跳过校验直接导出（不推荐）", icon="ARMATURE_DATA")


class GMI_PT_main(Panel):
    bl_label = "GakumasMI 工具"
    bl_idname = "GMI_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"

    def draw_header(self, context):
        self.layout.label(text="v0.7.8")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        workflow = layout.box()
        workflow.label(text="选好制作目标，按 ① → ④ 依次完成", icon="INFO")
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


class GMI_PT_step_binding(_GMIStepPanel):
    bl_label = "② 绑定模型"
    bl_idname = "GMI_PT_step_binding"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_step(self, layout, context):
        draw_binding_step(layout, context.scene)


class GMI_PT_step_texture(_GMIStepPanel):
    bl_label = "③ 准备材质"
    bl_idname = "GMI_PT_step_texture"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_step(self, layout, context):
        draw_texture_step(layout, context.scene, context)


class GMI_PT_step_export(_GMIStepPanel):
    bl_label = "④ 导出模组"
    bl_idname = "GMI_PT_step_export"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_step(self, layout, context):
        draw_export_step(layout, context.scene, context)


CLASSES = (
    GMI_PT_main,
    GMI_PT_step_profile,
    GMI_PT_step_binding,
    GMI_PT_step_texture,
    GMI_PT_step_export,
)
