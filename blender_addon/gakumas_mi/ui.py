import bpy
from bpy.types import Panel


class GMI_PT_main(Panel):
    bl_label = "GakumasMI 工具"
    bl_idname = "GMI_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"

    def draw_header(self, context):
        self.layout.label(text="v0.3.5")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.prop(scene, "gmi_tool_mode")

        if scene.gmi_tool_mode == "EXTRACT":
            self.draw_extract(layout, scene)
        elif scene.gmi_tool_mode == "IMPORT":
            self.draw_import(layout, scene)
        elif scene.gmi_tool_mode == "SKINNING":
            self.draw_skinning(layout, scene)
        elif scene.gmi_tool_mode == "EXPORT":
            self.draw_export(layout, scene)
        elif scene.gmi_tool_mode == "TEXTURE":
            self.draw_texture(layout, scene)

    def draw_extract(self, layout, scene):
        box = layout.box()
        box.label(text="从抓帧提取对象")
        box.prop(scene, "gmi_profile_dir")
        box.prop(scene, "gmi_capture_dir")
        box.prop(scene, "gmi_component_id")
        box.prop(scene, "gmi_extract_output_dir")
        box.prop(scene, "gmi_extract_draw")
        box.operator("gmi.extract_profile_from_frame_dump", text="从抓帧生成配置档", icon="FILE_NEW")
        box.operator("gmi.update_profile_from_frame_dump", text="更新配置档抓帧源", icon="FILE_REFRESH")
        box.operator("gmi.import_profile_object", text="导入配置档对象", icon="OUTLINER_OB_ARMATURE")
        box.operator("gmi.import_reference", text="导入抓帧参考模型", icon="IMPORT")
        box.label(text="可先从 FrameAnalysis 自动生成 runtime-only 配置档，再导入参考模型", icon="INFO")

    def draw_import(self, layout, scene):
        box = layout.box()
        box.label(text="导入原模型 / 权重参考")
        box.prop(scene, "gmi_source_mesh_json")
        box.prop(scene, "gmi_skeleton_json")
        box.operator("gmi.import_weighted_reference", text="导入带权重参考模型", icon="ARMATURE_DATA")
        box.operator("gmi.create_native_body_sets", text="生成原生手部 / 颈部选择集", icon="GROUP_VERTEX")
        row = box.row(align=True)
        row.operator("gmi.select_native_hand_vertices", text="选择原生手部", icon="VIEW_PAN")
        row.operator("gmi.select_native_neck_vertices", text="选择原生颈部", icon="MOD_SKIN")
        box.label(text="通常先导入权重参考，再处理作者模型", icon="INFO")

    def draw_skinning(self, layout, scene):
        box = layout.box()
        box.label(text="作者模型蒙皮 / 转权")
        box.prop(scene, "gmi_transfer_risk_distance")
        box.prop(scene, "gmi_semantic_correction")
        box.operator("gmi.transfer_profile_weights", text="从配置档传递权重", icon="MOD_DATA_TRANSFER")
        box.operator("gmi.select_high_risk_vertices", text="选择高风险顶点", icon="RESTRICT_SELECT_OFF")
        box.label(text="传权后检查高风险顶点组：GMI_REVIEW_HIGH_RISK", icon="ERROR")

    def draw_export(self, layout, scene):
        package = layout.box()
        package.label(text="模组信息")
        package.prop(scene, "gmi_output_dir")
        package.prop(scene, "gmi_package_id")
        package.prop(scene, "gmi_package_name")
        package.prop(scene, "gmi_author")

        mesh = layout.box()
        mesh.label(text="网格导出")
        mesh.operator("gmi.export_validated_mod", text="校验并导出模组", icon="EXPORT")
        mesh.operator("gmi.validate_mesh", text="校验网格", icon="CHECKMARK")
        mesh.operator("gmi.export_inverse_skin_mod", text="导出带权重 GPU 模组", icon="ARMATURE_DATA")

    def draw_texture(self, layout, scene):
        material = layout.box()
        material.label(text="身体材质模板（可选 DDS）")
        material.prop(scene, "gmi_base_color_file")
        material.prop(scene, "gmi_packed_mask_file")
        material.prop(scene, "gmi_shade_color_file")
        material.label(text="遮罩通道：R 阴影 / G 光滑度 / B 金属度 / A 环境光遮蔽")
        material.operator("gmi.create_body_material_template", text="创建身体材质模板", icon="MATERIAL")

        texture = layout.box()
        texture.label(text="单贴图替换")
        texture.prop(scene, "gmi_texture_key")
        texture.prop(scene, "gmi_texture_file")
        texture.operator("gmi.export_texture_mod", text="导出贴图模组", icon="TEXTURE")


CLASSES = (GMI_PT_main,)
