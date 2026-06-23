bl_info = {
    "name": "GakumasMI",
    "author": "GakumasMI",
    "version": (0, 3, 4),
    "blender": (4, 2, 0),
    "location": "3D 视图 > 侧边栏 > GakumasMI",
    "description": "导入学马仕参考模型，并导出绑定配置档的 3DMigoto 模组",
    "category": "Import-Export",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from pathlib import Path

from . import operators, ui


CLASSES = operators.CLASSES + ui.CLASSES


def _default_profile_dir():
    bundled = Path(__file__).resolve().parent / "profiles" / "hski-cstm-0000"
    if bundled.is_dir():
        return str(bundled)
    development = Path(__file__).resolve().parents[2] / "profiles" / "hski-cstm-0000"
    return str(development) if development.is_dir() else ""


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gmi_tool_mode = EnumProperty(
        name="模式",
        description="选择当前要执行的工作流步骤",
        items=[
            ("EXTRACT", "提取对象", "从抓帧数据 / 配置档准备游戏对象数据"),
            ("IMPORT", "导入对象", "导入原模型、骨架与权重参考"),
            ("SKINNING", "蒙皮转权", "把配置档权重转移给作者模型"),
            ("EXPORT", "导出模组", "校验并导出可安装模组"),
            ("TEXTURE", "材质模板", "绑定身体多贴图或单贴图替换"),
        ],
        default="IMPORT",
    )
    bpy.types.Scene.gmi_profile_dir = StringProperty(
        name="配置档目录", subtype="DIR_PATH", default=_default_profile_dir()
    )
    bpy.types.Scene.gmi_capture_dir = StringProperty(
        name="抓帧目录", subtype="DIR_PATH",
        description="可选 FrameAnalysis 抓帧目录；留空时使用配置档中记录的抓帧路径",
    )
    bpy.types.Scene.gmi_output_dir = StringProperty(name="输出目录", subtype="DIR_PATH")
    bpy.types.Scene.gmi_component_id = StringProperty(name="组件", default="body")
    bpy.types.Scene.gmi_source_mesh_json = StringProperty(name="原模型 JSON", subtype="FILE_PATH")
    bpy.types.Scene.gmi_skeleton_json = StringProperty(name="骨架 JSON", subtype="FILE_PATH")
    bpy.types.Scene.gmi_bone_remap_file = StringProperty(name="骨骼映射", subtype="FILE_PATH")
    bpy.types.Scene.gmi_unmapped_bone_fallback = StringProperty(
        name="未映射骨骼兜底", default="",
        description="可选配置档骨骼名；未映射权重会落到该骨骼。留空表示严格校验",
    )
    bpy.types.Scene.gmi_transfer_risk_distance = FloatProperty(
        name="风险距离", default=0.02, min=0.0001, unit="LENGTH",
        description="距离参考身体表面超过该值的顶点会标记为高风险",
    )
    bpy.types.Scene.gmi_semantic_correction = BoolProperty(
        name="修正手指/颈部", default=True,
        description="使用目标模型旧主导骨组来辅助区分相邻手指和颈部",
    )
    bpy.types.Scene.gmi_texture_key = StringProperty(name="贴图键", default="body.baseColor")
    bpy.types.Scene.gmi_texture_file = StringProperty(name="DDS 文件", subtype="FILE_PATH")
    bpy.types.Scene.gmi_base_color_file = StringProperty(name="基础色 t0", subtype="FILE_PATH")
    bpy.types.Scene.gmi_packed_mask_file = StringProperty(name="混合遮罩 t1", subtype="FILE_PATH")
    bpy.types.Scene.gmi_shade_color_file = StringProperty(name="阴影色 t4", subtype="FILE_PATH")
    bpy.types.Scene.gmi_package_id = StringProperty(name="模组标识", default="author.hski.my-mod")
    bpy.types.Scene.gmi_package_name = StringProperty(name="模组名称", default="我的学马仕模组")
    bpy.types.Scene.gmi_author = StringProperty(name="作者", default="作者")


def unregister():
    for name in (
        "gmi_tool_mode",
        "gmi_profile_dir", "gmi_capture_dir", "gmi_output_dir", "gmi_component_id",
        "gmi_source_mesh_json", "gmi_skeleton_json", "gmi_bone_remap_file",
        "gmi_unmapped_bone_fallback",
        "gmi_transfer_risk_distance", "gmi_semantic_correction",
        "gmi_texture_key", "gmi_texture_file", "gmi_package_id",
        "gmi_base_color_file", "gmi_packed_mask_file", "gmi_shade_color_file",
        "gmi_package_name", "gmi_author",
    ):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
