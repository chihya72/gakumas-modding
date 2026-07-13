import bpy
from bpy.types import Panel


class GMI_PT_main(Panel):
    bl_label = "GakumasMI 工具"
    bl_idname = "GMI_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"

    def draw_header(self, context):
        self.layout.label(text="v0.7.4")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        workflow = layout.box()
        workflow.label(text="先选目标，再按 ① → ④ 完成", icon="INFO")
        workflow.prop(scene, "gmi_component_id")
        workflow.prop(scene, "gmi_tool_mode")

        if scene.gmi_tool_mode == "EXTRACT":
            self.draw_extract(layout, scene)
        elif scene.gmi_tool_mode == "SKINNING":
            self.draw_skinning(layout, scene)
        elif scene.gmi_tool_mode == "EXPORT":
            self.draw_export(layout, scene, context)
        elif scene.gmi_tool_mode == "TEXTURE":
            self.draw_texture(layout, scene, context)

    def draw_extract(self, layout, scene):
        is_hairprop = scene.gmi_component_id == "hairprop"
        is_hair = scene.gmi_component_id == "hair"
        target_name = "发饰" if is_hairprop else "发型" if is_hair else "身体"
        mesh_name = "Geo_HairProp" if is_hairprop else "Geo_Hair" if is_hair else "Geo_Body"

        box = layout.box()
        box.label(text="步骤 1/4 · 生成完整配置档", icon="FILE_NEW")
        box.label(text=f"需要含 {mesh_name}.json 的{target_name}资源库")
        box.prop(scene, "gmi_capture_dir")
        box.prop(scene, "gmi_body_json_library_dir", text=f"{target_name} JSON 资源库")
        box.prop(
            scene,
            "gmi_body_resource",
            text="目标 hair 资源（可选）" if (is_hairprop or is_hair) else "目标 body 资源（可选）",
        )
        row = box.row()
        row.scale_y = 1.5
        row.operator("gmi.build_full_profile", text="生成完整配置档", icon="AUTO")
        box.label(text="完成后会自动填写下方配置档目录", icon="CHECKMARK")

        reference = layout.box()
        reference.label(text="步骤 1/4 · 导入参考", icon="ARMATURE_DATA")
        reference.prop(scene, "gmi_profile_dir")
        row = reference.row()
        row.scale_y = 1.3
        row.operator("gmi.import_weighted_reference", text="导入参考模型与骨架", icon="ARMATURE_DATA")
        reference.label(text="已有完整配置档可直接从这里开始")
        reference.label(text="导入完成后进入 ② 绑定模型", icon="TRIA_RIGHT")

        header, advanced = layout.panel("GMI_extract_advanced", default_closed=True)
        header.label(text="高级 / 分步 / 排错", icon="PREFERENCES")
        if advanced:
            advanced.prop(scene, "gmi_extract_output_dir")
            advanced.prop(scene, "gmi_extract_draw")
            advanced.operator("gmi.extract_profile_from_frame_dump", text="仅生成注入信息（runtime-only）", icon="FILE_NEW")
            advanced.operator("gmi.resolve_body_json_library", text="匹配网格 JSON 资源库", icon="VIEWZOOM")
            advanced.operator("gmi.update_profile_from_frame_dump", text="更新配置档抓帧源", icon="FILE_REFRESH")
            advanced.operator("gmi.import_profile_object", text="导入配置档对象（完整排错）", icon="OUTLINER_OB_ARMATURE")
            advanced.operator("gmi.import_reference", text="只导入抓帧参考模型", icon="IMPORT")

    def draw_skinning(self, layout, scene):
        box = layout.box()
        box.label(text="步骤 2/4 · 绑定作者模型", icon="MOD_ARMATURE")
        box.label(text="先在 3D 视图中只激活作者网格", icon="RESTRICT_SELECT_OFF")

        if scene.gmi_component_id == "hairprop":
            rigid = box.box()
            rigid.label(text="A · 硬质发饰（推荐）", icon="BONE_DATA")
            rigid.label(text="全部顶点 → Head_Hair；不摆动、不形变")
            rigid.label(text="会清除旧权重；不要再执行传权", icon="ERROR")
            row = rigid.row()
            row.scale_y = 1.5
            row.operator("gmi.bind_hairprop_rigid", text="刚体绑定到 Head_Hair", icon="CONSTRAINT_BONE")

            header, weighted = layout.panel("GMI_hairprop_weighted", default_closed=True)
            header.label(text="B · 需要摆动 / 形变：传递权重", icon="MOD_DATA_TRANSFER")
            if weighted:
                weighted.label(text="与刚体绑定二选一；传权后需复核")
                weighted.prop(scene, "gmi_transfer_risk_distance")
                weighted.operator("gmi.transfer_profile_weights", text="从参考模型传递权重", icon="MOD_DATA_TRANSFER")
                weighted.operator("gmi.transfer_profile_weights_smart", text="实验：智能传递权重", icon="MOD_DATA_TRANSFER")
                weighted.operator("gmi.select_high_risk_vertices", text="选择高风险顶点", icon="RESTRICT_SELECT_OFF")
        else:
            box.prop(scene, "gmi_transfer_risk_distance")
            row = box.row()
            row.scale_y = 1.5
            row.operator("gmi.transfer_profile_weights", text="从参考模型传递权重", icon="MOD_DATA_TRANSFER")

            review = layout.box()
            review.label(text="传权后复核", icon="RESTRICT_SELECT_OFF")
            review.operator("gmi.select_high_risk_vertices", text="选择高风险顶点", icon="RESTRICT_SELECT_OFF")
            review.label(text="风险顶点可 Weight Paint 修正")
            review.label(text="也可在导出时关闭其描边")

            header, advanced = layout.panel("GMI_body_smart_transfer", default_closed=True)
            header.label(text="实验：薄缝 / 多层模型智能传权", icon="EXPERIMENTAL")
            if advanced:
                advanced.operator("gmi.transfer_profile_weights_smart", text="实验：智能传递权重", icon="MOD_DATA_TRANSFER")
        layout.label(text="完成后进入 ③ 准备材质", icon="TRIA_RIGHT")

    def draw_export(self, layout, scene, context):
        package = layout.box()
        package.label(text="步骤 4/4 · 模组信息", icon="PACKAGE")
        package.prop(scene, "gmi_output_dir")
        package.prop(scene, "gmi_package_id")
        package.prop(scene, "gmi_package_name")
        package.prop(scene, "gmi_author")
        package.prop(scene, "gmi_cover_image", text="预览图（必填）")

        mesh = layout.box()
        mesh.label(text="步骤 4/4 · 校验并导出", icon="EXPORT")
        if scene.gmi_component_id == "hair":
            mesh.prop(scene, "gmi_hair_outline_tier")
            mesh.label(text="hair 描边色为常量档;宽度/高光从参考网格拷贝", icon="INFO")
        else:
            mesh.prop(scene, "gmi_vertex_color_mode")
            if scene.gmi_vertex_color_mode == "BASECOLOR":
                mesh.label(text="取自基础色需要在步骤③填写 t0", icon="INFO")
        mesh.prop(scene, "gmi_outline_width_mode")
        obj = context.active_object
        ready = False
        if obj and obj.type == "MESH" and obj.get("gmi_component_id") == scene.gmi_component_id:
            ready = bool(obj.get("gmi_profile_weights") or obj.get("gmi_source_vertex_count"))
            if obj.get("gmi_rigid_head_follow"):
                mesh.label(text="已识别：Head_Hair 刚体发饰", icon="CHECKMARK")
            elif obj.get("gmi_profile_weights"):
                mesh.label(text="已识别：配置档权重网格", icon="CHECKMARK")
            else:
                mesh.label(text="已识别：原拓扑参考网格", icon="CHECKMARK")
        else:
            target_name = (
                "作者发饰" if scene.gmi_component_id == "hairprop"
                else "作者发型" if scene.gmi_component_id == "hair"
                else "作者身体"
            )
            mesh.label(text=f"请激活已绑定的{target_name}网格", icon="ERROR")
        row = mesh.row()
        row.scale_y = 1.6
        row.enabled = ready
        row.operator("gmi.export_validated_mod", text="校验并导出模组", icon="EXPORT")

        header, advanced = layout.panel("GMI_export_advanced", default_closed=True)
        header.label(text="高级 / 分步导出", icon="PREFERENCES")
        if advanced:
            advanced.operator("gmi.validate_mesh", text="仅校验当前网格", icon="CHECKMARK")
            advanced.operator("gmi.export_inverse_skin_mod", text="直接导出带权重 GPU 模组", icon="ARMATURE_DATA")

    def draw_texture(self, layout, scene, context):
        is_hairprop = scene.gmi_component_id == "hairprop"
        is_hair = scene.gmi_component_id == "hair"
        target_name = "发饰 hairprop" if is_hairprop else "发型 hair" if is_hair else "身体 body"

        material = layout.box()
        material.label(text="步骤 3/4 · 指定导出贴图", icon="MATERIAL")
        material.label(text=f"当前目标：{target_name}")
        material.prop(scene, "gmi_base_color_file", text="基础色 t0")
        material.prop(scene, "gmi_packed_mask_file", text="混合遮罩 t1")
        material.prop(scene, "gmi_shade_color_file", text="暗面材质 t4 / sdw")
        material.prop(scene, "gmi_neutral_material")
        if is_hair:
            material.label(text="hair t1：R 阴影 / G 光滑 / B 金属 / A 必须 0(非 AO)", icon="INFO")
            material.label(text="hair t4：base×冷阴影乘数 / A=0")
        else:
            material.label(text="t1：R 阴影 / G 光滑 / B 金属 / A AO", icon="INFO")
            material.label(text="t4：RGB 暗色版 / A 材质遮罩")

        preview = layout.box()
        preview.label(text="可选 · Blender 预览")
        preview.operator("gmi.create_body_material_template", text="创建预览材质模板", icon="MATERIAL")

        if scene.gmi_component_id == "body":
            header, co = layout.panel("GMI_native_co_material", default_closed=True)
            header.label(text="可选 · 原生 co 透明 / 镂空", icon="SHADING_RENDERED")
            if co:
                co.prop(scene, "gmi_opacity_texture_file")
                co.prop(scene, "gmi_opacity_packed_mask_file")
                co.prop(scene, "gmi_opacity_shade_color_file")
                co.label(text="仅供设为「原生co」的材质槽使用", icon="INFO")
                co.label(text="不会回退或共用不透明贴图")

        header, generate = layout.panel("GMI_generate_material_maps", default_closed=True)
        header.label(text="可选 · 没有 t1/t4：按材质生成", icon="NODE_MATERIAL")
        if generate:
            obj = context.active_object
            if obj and obj.type == "MESH" and obj.material_slots:
                for slot in obj.material_slots:
                    if slot.material is not None:
                        row = generate.row(align=True)
                        row.prop(slot.material, "gmi_material_class", text=slot.material.name)
                        if scene.gmi_component_id == "body":
                            row.prop(slot.material, "gmi_alpha_mode", text="")
                        row.prop(slot.material, "gmi_material_toon", text="明暗")
            else:
                generate.label(text="先激活已分材质的作者网格", icon="INFO")
            generate.label(text="明暗：-1 用预设；低=阴影多，高=受光多")
            generate.prop(scene, "gmi_form_shading")
            if scene.gmi_form_shading:
                generate.prop(scene, "gmi_form_strength")
            channels = generate.box()
            channels.label(text="t1 通道覆盖（可选）")
            channels.prop(scene, "gmi_t1_r_file")
            channels.prop(scene, "gmi_t1_g_file")
            channels.prop(scene, "gmi_t1_b_file")
            channels.prop(scene, "gmi_t1_a_file")
            channels.label(text="填四张=整图合成；部分填写=覆盖对应通道")
            generate.operator("gmi.bake_material_maps", text="按材质生成 t1 / t4", icon="NODE_MATERIAL")

        material.label(text="贴图就绪后进入 ④ 导出模组", icon="TRIA_RIGHT")

        header, texture = layout.panel("GMI_single_texture_export", default_closed=True)
        header.label(text="替代流程 · 只导出一张贴图", icon="TEXTURE")
        if texture:
            texture.prop(scene, "gmi_texture_key")
            texture.prop(scene, "gmi_texture_file")
            if is_hairprop:
                texture.label(text="键示例：hairprop.baseColor")
            elif is_hair:
                texture.label(text="键示例：hair.baseColor")
            texture.operator("gmi.export_texture_mod", text="导出单贴图替换", icon="TEXTURE")


CLASSES = (GMI_PT_main,)
