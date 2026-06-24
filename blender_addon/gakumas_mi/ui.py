import bpy
from bpy.types import Panel


class GMI_PT_main(Panel):
    bl_label = "GakumasMI 工具"
    bl_idname = "GMI_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GakumasMI"

    def draw_header(self, context):
        self.layout.label(text="v0.4.6")

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
        box.label(text="① 抓帧 + ② 资源库 → 完整配置档")
        box.prop(scene, "gmi_capture_dir")             # 选项1：抓帧文件夹
        box.prop(scene, "gmi_body_json_library_dir")   # 选项2：Body JSON 资源库
        row = box.row()
        row.scale_y = 1.5
        row.operator("gmi.build_full_profile", text="一键生成完整配置档（注入+结构+逆算子）", icon="AUTO")
        box.label(text="只需填这两个目录，点上面一个按钮，自动生成 ①②③", icon="INFO")

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

    def draw_import(self, layout, scene):
        box = layout.box()
        box.label(text="导入原模型 / 权重参考")
        box.prop(scene, "gmi_body_json_library_dir")
        box.operator("gmi.resolve_body_json_library", text="匹配 Body JSON资源库", icon="VIEWZOOM")
        box.operator("gmi.import_weighted_reference", text="导入带权重参考模型", icon="ARMATURE_DATA")
        box.label(text="必须先匹配 Body JSON资源库；不支持散文件模式", icon="INFO")

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
