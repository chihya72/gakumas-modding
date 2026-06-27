import bpy
from bpy.types import Panel


class GMI_PT_main(Panel):
    bl_label = "GakumasMI 工具"
    bl_idname = "GMI_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"

    def draw_header(self, context):
        self.layout.label(text="v0.5.13")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.prop(scene, "gmi_tool_mode")

        if scene.gmi_tool_mode == "EXTRACT":
            self.draw_extract(layout, scene)
        elif scene.gmi_tool_mode == "SKINNING":
            self.draw_skinning(layout, scene)
        elif scene.gmi_tool_mode == "EXPORT":
            self.draw_export(layout, scene)
        elif scene.gmi_tool_mode == "TEXTURE":
            self.draw_texture(layout, scene)

    def draw_extract(self, layout, scene):
        box = layout.box()
        box.label(text="① 抓帧 + ② 资源库 → 完整配置档")
        box.prop(scene, "gmi_capture_dir")             # 选项1：抓帧文件夹
        box.prop(scene, "gmi_body_json_library_dir")   # 选项2：Body JSON 资源库
        box.prop(scene, "gmi_body_resource")           # 可选：同款多角色时指定 body
        row = box.row()
        row.scale_y = 1.5
        row.operator("gmi.build_full_profile", text="① 一键生成完整配置档（注入+结构+逆算子）", icon="AUTO")
        row2 = box.row()
        row2.scale_y = 1.3
        row2.operator("gmi.import_weighted_reference", text="② 导入带权重参考模型", icon="ARMATURE_DATA")
        box.label(text="先点①生成配置档，再点②导入；然后切到「蒙皮转权」", icon="INFO")

        adv = layout.box()
        adv.label(text="高级 / 分步")
        adv.prop(scene, "gmi_component_id")
        adv.prop(scene, "gmi_extract_output_dir")
        adv.prop(scene, "gmi_extract_draw")
        adv.operator("gmi.extract_profile_from_frame_dump", text="仅生成注入信息(runtime-only)", icon="FILE_NEW")
        adv.operator("gmi.resolve_body_json_library", text="匹配 Body JSON资源库", icon="VIEWZOOM")
        adv.operator("gmi.update_profile_from_frame_dump", text="更新配置档抓帧源", icon="FILE_REFRESH")
        adv.operator("gmi.import_profile_object", text="导入配置档对象", icon="OUTLINER_OB_ARMATURE")
        adv.operator("gmi.import_reference", text="导入抓帧参考模型", icon="IMPORT")

        fallback = layout.box()
        fallback.label(text="已有配置档 / 复核")
        fallback.prop(scene, "gmi_profile_dir")

    def draw_skinning(self, layout, scene):
        box = layout.box()
        box.label(text="作者模型蒙皮 / 转权")
        box.prop(scene, "gmi_transfer_risk_distance")
        box.prop(scene, "gmi_semantic_correction")
        box.prop(scene, "gmi_vertex_color_mode")
        box.operator("gmi.transfer_profile_weights", text="从配置档传递权重 + 颜色", icon="MOD_DATA_TRANSFER")
        box.operator("gmi.select_high_risk_vertices", text="选择高风险顶点", icon="RESTRICT_SELECT_OFF")
        box.label(text="高风险/GMI_NO_OUTLINE 顶点导出时会关闭描边宽度", icon="ERROR")

    def draw_export(self, layout, scene):
        package = layout.box()
        package.label(text="模组信息")
        package.prop(scene, "gmi_output_dir")
        package.prop(scene, "gmi_package_id")
        package.prop(scene, "gmi_package_name")
        package.prop(scene, "gmi_author")

        mesh = layout.box()
        mesh.label(text="网格导出")
        mesh.prop(scene, "gmi_vertex_color_mode")
        mesh.prop(scene, "gmi_outline_width_mode")
        mesh.operator("gmi.export_validated_mod", text="校验并导出模组", icon="EXPORT")
        mesh.operator("gmi.validate_mesh", text="校验网格", icon="CHECKMARK")
        mesh.operator("gmi.export_inverse_skin_mod", text="导出带权重 GPU 模组", icon="ARMATURE_DATA")

    def draw_texture(self, layout, scene):
        material = layout.box()
        material.label(text="身体材质（贴图可填 PNG 或 DDS）")
        material.prop(scene, "gmi_base_color_file")
        material.prop(scene, "gmi_packed_mask_file")
        material.prop(scene, "gmi_shade_color_file")
        material.prop(scene, "gmi_neutral_material")
        material.label(text="只有基础色时勾「中性 t1/t4」：盖掉原版遮罩/阴影，避免叠在新贴图上", icon="INFO")
        material.label(text="遮罩通道：R 阴影 / G 光滑度 / B 金属度 / A 环境光遮蔽")
        material.operator("gmi.create_body_material_template", text="创建身体材质模板", icon="MATERIAL")

        smart = layout.box()
        smart.label(text="分材质烘焙 t1/t4（比中性更接近游戏观感）")
        obj = bpy.context.active_object
        if obj and obj.type == "MESH" and obj.material_slots:
            for slot in obj.material_slots:
                if slot.material is not None:
                    row = smart.row(align=True)
                    row.prop(slot.material, "gmi_material_class", text=slot.material.name)
                    row.prop(slot.material, "gmi_material_toon", text="明暗")
                    row.prop(slot.material, "gmi_material_shade", text="阴影色")
        else:
            smart.label(text="选中已分材质的网格后，逐材质设「材质类型」", icon="INFO")
        smart.label(text="需先填上方「基础色 t0」(PNG)；t4 从它逐材质派生", icon="INFO")
        smart.prop(scene, "gmi_form_shading")
        if scene.gmi_form_shading:
            smart.prop(scene, "gmi_form_strength")
            smart.label(text="圆柱体(腿/裤袜)出硬光影分界时开此项；偏硬调高、偏脏调低", icon="INFO")
        smart.operator("gmi.bake_material_maps", text="按材质烘焙 t1/t4", icon="NODE_MATERIAL")

        texture = layout.box()
        texture.label(text="单贴图替换")
        texture.prop(scene, "gmi_texture_key")
        texture.prop(scene, "gmi_texture_file")
        texture.operator("gmi.export_texture_mod", text="导出贴图模组", icon="TEXTURE")


CLASSES = (GMI_PT_main,)
