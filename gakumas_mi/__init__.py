bl_info = {
    "name": "GakumasMI",
    "author": "GakumasMI",
    "version": (0, 7, 5),
    "blender": (4, 2, 0),
    "location": "3D 视图 > 侧边栏 > GakumasMI",
    "description": "导入学马仕参考模型，并导出绑定配置档的 3DMigoto 模组",
    "category": "Import-Export",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from pathlib import Path

from . import core, operators, ui


CLASSES = operators.CLASSES + ui.CLASSES


def _material_class_items():
    """从预设库生成材质类型下拉项（值=预设键，名=中文标签）。"""
    try:
        presets = core.load_material_presets()
    except Exception:
        return [("neutral", "中性", "")]
    order = ["skin", "cloth", "leather_shoe", "leather_plastic", "metal", "hair", "neutral"]
    keys = [k for k in order if k in presets] + [k for k in presets if k not in order]
    return [(k, presets[k].get("label", k), presets[k].get("confidence", "")) for k in keys]


def _default_profile_dir():
    bundled = Path(__file__).resolve().parent / "profiles" / "atbm-cstm-0140"
    if bundled.is_dir():
        return str(bundled)
    development = Path(__file__).resolve().parents[1] / "profiles" / "atbm-cstm-0140"
    return str(development) if development.is_dir() else ""


def _default_body_json_dir():
    bundled = Path(__file__).resolve().parent / "resources" / "assetstudio-body-json"
    if bundled.is_dir():
        return str(bundled)
    development = Path(__file__).resolve().parents[1] / ".local" / "assetstudio-body-json"
    return str(development) if development.is_dir() else ""


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gmi_tool_mode = EnumProperty(
        name="当前步骤",
        description="按 ① 到 ④ 完成模组制作",
        items=[
            ("EXTRACT", "① 准备配置档", "从抓帧和资源库生成完整配置档并导入参考"),
            ("SKINNING", "② 绑定模型", "为作者模型传递权重或绑定发饰到头部"),
            ("TEXTURE", "③ 准备材质", "指定或生成 t0/t1/t4 贴图"),
            ("EXPORT", "④ 导出模组", "校验并导出可安装模组"),
        ],
        default="EXTRACT",
    )
    bpy.types.Scene.gmi_profile_dir = StringProperty(
        name="配置档目录", subtype="DIR_PATH", default=_default_profile_dir()
    )
    bpy.types.Scene.gmi_capture_dir = StringProperty(
        name="抓帧目录", subtype="DIR_PATH",
        description="可选 FrameAnalysis 抓帧目录；留空时使用配置档中记录的抓帧路径",
    )
    bpy.types.Scene.gmi_extract_output_dir = StringProperty(
        name="新配置档输出", subtype="DIR_PATH",
        description="可选；留空时自动写入 FrameAnalysis 目录下的 GakumasMI-profile",
    )
    bpy.types.Scene.gmi_body_json_library_dir = StringProperty(
        name="网格 JSON 资源库", subtype="DIR_PATH", default=_default_body_json_dir(),
        description="AssetStudio 批量导出的资源库；身体匹配 Geo_Body，发型匹配 Geo_Hair，发饰匹配 Geo_HairProp",
    )
    bpy.types.Scene.gmi_body_resource = StringProperty(
        name="目标资源（可选）", default="",
        description="用于消歧或加速匹配；可填角色代号，或完整的 body / hair 资源名",
    )
    bpy.types.Scene.gmi_extract_draw = IntProperty(
        name="主 Draw", default=0, min=0,
        description="0 表示自动选择；填入 3DMigoto 顶部显示的 Draw 编号可强制指定",
    )
    bpy.types.Scene.gmi_output_dir = StringProperty(name="输出目录", subtype="DIR_PATH")
    bpy.types.Scene.gmi_component_id = EnumProperty(
        name="制作目标",
        description="选择要替换的游戏组件；后续四个步骤共用此目标",
        items=[
            ("body", "身体（body）", "替换 Geo_Body；透明/镂空配饰可选用原生 m_bdyco"),
            ("hair", "发型（hair）", "替换 Geo_Hair；可选同时制作 Geo_HairProp 发饰"),
        ],
        default="body",
    )
    bpy.types.Scene.gmi_hairprop_enabled = BoolProperty(
        name="制作发饰（可选）", default=False,
        description="在当前发型 profile 内切换到 Geo_HairProp；关闭时制作 Geo_Hair",
    )
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
    bpy.types.Scene.gmi_texture_key = StringProperty(name="贴图键", default="body.baseColor")
    bpy.types.Scene.gmi_texture_file = StringProperty(name="DDS 文件", subtype="FILE_PATH")
    bpy.types.Scene.gmi_base_color_file = StringProperty(name="基础色 t0", subtype="FILE_PATH")
    bpy.types.Scene.gmi_packed_mask_file = StringProperty(name="混合遮罩 t1", subtype="FILE_PATH")
    bpy.types.Scene.gmi_shade_color_file = StringProperty(
        name="暗面材质 t4/sdw", subtype="FILE_PATH",
        description="暗面时使用的材质颜色图；RGB 应是基础色 t0 的暗化版，A 是近似二值材质遮罩，不是透明度",
    )
    bpy.types.Scene.gmi_t1_r_file = StringProperty(
        name="t1.R 阴影阈值", subtype="FILE_PATH",
        description="可选通道图；填入后写入 PackedMask.R。只填部分通道时先按材质烘焙，再只覆盖有内容的材质区域",
    )
    bpy.types.Scene.gmi_t1_g_file = StringProperty(
        name="t1.G 光滑度", subtype="FILE_PATH",
        description="可选通道图；填入后写入 PackedMask.G。四个通道都填时会整图合成完整 t1",
    )
    bpy.types.Scene.gmi_t1_b_file = StringProperty(
        name="t1.B 金属度", subtype="FILE_PATH",
        description="可选通道图；填入后写入 PackedMask.B。四个通道都填时会整图合成完整 t1",
    )
    bpy.types.Scene.gmi_t1_a_file = StringProperty(
        name="t1.A AO", subtype="FILE_PATH",
        description="可选通道图；填入后写入 PackedMask.A。四个通道都填时会整图合成完整 t1",
    )
    bpy.types.Scene.gmi_opacity_texture_file = StringProperty(
        name="co 基础色 t0 / m_bdyco", subtype="FILE_PATH",
        description="仅当材质槽设为原生co时填写且必填；使用透明材质自己的 t0/UV，不回退基础色 t0",
    )
    bpy.types.Scene.gmi_opacity_packed_mask_file = StringProperty(
        name="co 混合遮罩 t1", subtype="FILE_PATH",
        description="原生 co / m_bdyco 自己的 PackedMask；留空时导出会使用中性 t1，不再共用 body t1",
    )
    bpy.types.Scene.gmi_opacity_shade_color_file = StringProperty(
        name="co 暗面材质 t4/sdw", subtype="FILE_PATH",
        description="原生 co / m_bdyco 自己的暗面材质；留空时导出会使用中性 t4，不再共用 body t4",
    )
    bpy.types.Scene.gmi_neutral_material = BoolProperty(
        name="中性 t1/t4", default=True,
        description="未提供 t1/t4 时自动绑定中性贴图，盖掉游戏原版遮罩/阴影对新贴图的干扰",
    )
    bpy.types.Scene.gmi_outline_width_mode = EnumProperty(
        name="描边宽度",
        description="控制描边线条的粗细(挤出宽度)",
        items=[
            ("KEEP", "正常描边", "正常显示描边"),
            ("RISK_ONLY", "仅安全顶点", "只在高风险/GMI_NO_OUTLINE 顶点关闭描边"),
            ("DISABLE_ALL", "关闭", "关闭全部描边"),
        ],
        default="KEEP",
    )
    bpy.types.Scene.gmi_vertex_color_mode = EnumProperty(
        name="描边颜色",
        description="描边线条的颜色来源",
        items=[
            ("BASECOLOR", "取自基础色", "逐顶点从基础色 t0 生成描边色(复刻原版,贴合衣服色)"),
            ("MATERIAL_PRESET", "按材质预设", "按材质类型用预设描边色(裙=布料、皮肤=皮肤…)"),
            ("CONSTANT_BLACK", "黑色常量", "所有描边统一黑色"),
        ],
        default="BASECOLOR",
    )
    bpy.types.Scene.gmi_hair_outline_tier = EnumProperty(
        name="发型描边色档",
        description="hair 描边色是全网格常量(非逐顶点);按发色明度选档,实机偏亮可换更暗一档",
        items=[
            ("DARK", "深色发(蓝紫/黑褐)", "nibble (0,0,1),实测自蓝紫发"),
            ("PINK", "粉/红发", "nibble (1,0,0),实测自粉发"),
            ("BLONDE", "金/浅色发", "nibble (4,2,1),实测自金发"),
            ("BLACK", "纯黑描边", "nibble (0,0,0),最保守"),
        ],
        default="DARK",
    )
    bpy.types.Scene.gmi_form_shading = BoolProperty(
        name="几何AO软化阴影", default=False,
        description="从网格几何烘 AO,只对凹陷缝隙(腋下/裆部/衣褶内)加深阴影;对光滑凸面(腿/裤袜)无效——硬光影分界要靠 toon 阈值",
    )
    bpy.types.Scene.gmi_form_strength = FloatProperty(
        name="软化强度", default=0.6, min=0.0, max=2.0,
        description="几何AO对 toon 渐变的影响强度;0=关闭,实机偏硬就调高、偏脏就调低",
    )
    bpy.types.Material.gmi_material_class = EnumProperty(
        name="材质类型",
        description="分材质烘焙 t1/t4 时该材质槽使用的预设（皮肤/布料/金属…）",
        items=_material_class_items(),
        default="cloth",
    )
    bpy.types.Material.gmi_alpha_mode = EnumProperty(
        name="渲染材质",
        description="导出时该材质槽走不透明 body 路径，还是走游戏原生第二材质段(透明/镂空)",
        items=[
            ("OPAQUE", "不透明", "使用普通 body 路径，投影/遮挡/描边最稳定"),
            ("NATIVE_CO", "原生co", "使用游戏原生第二材质段(m_bdyco)绘制，借用原版 shader/state 实现透明/镂空。需要配置档含 secondary material section"),
        ],
        default="OPAQUE",
    )
    bpy.types.Material.gmi_material_toon = FloatProperty(
        name="明暗(阴影范围)", default=-1.0, min=-1.0, max=1.0,
        description="-1=用预设值。即 t1 的 toon 阴影阈值:值越低=阴影越大越暗、值越高=受光越多越亮。控制这个材质明暗分界落在哪、阴影铺多大;只影响这一个材质",
    )
    bpy.types.Scene.gmi_package_id = StringProperty(name="模组标识", default="author.hski.my-mod")
    bpy.types.Scene.gmi_package_name = StringProperty(name="模组名称", default="我的学马仕模组")
    bpy.types.Scene.gmi_author = StringProperty(name="作者", default="作者")
    bpy.types.Scene.gmi_cover_image = StringProperty(
        name="预览图", subtype="FILE_PATH",
        description="mod 封面/预览图（png/jpg/webp，导出必填；过大会自动缩到 ≤1024px、上限 2MB）",
    )


def unregister():
    for name in (
        "gmi_tool_mode",
        "gmi_profile_dir", "gmi_capture_dir", "gmi_extract_output_dir",
        "gmi_body_json_library_dir", "gmi_body_resource",
        "gmi_extract_draw", "gmi_output_dir", "gmi_component_id", "gmi_hairprop_enabled",
        "gmi_source_mesh_json", "gmi_skeleton_json", "gmi_bone_remap_file",
        "gmi_unmapped_bone_fallback",
        "gmi_transfer_risk_distance",
        "gmi_texture_key", "gmi_texture_file", "gmi_package_id",
        "gmi_base_color_file", "gmi_packed_mask_file", "gmi_shade_color_file",
        "gmi_t1_r_file", "gmi_t1_g_file", "gmi_t1_b_file", "gmi_t1_a_file",
        "gmi_opacity_texture_file", "gmi_opacity_packed_mask_file", "gmi_opacity_shade_color_file",
        "gmi_neutral_material", "gmi_outline_width_mode", "gmi_vertex_color_mode",
        "gmi_hair_outline_tier",
        "gmi_form_shading", "gmi_form_strength",
        "gmi_package_name", "gmi_author", "gmi_cover_image",
    ):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    if hasattr(bpy.types.Material, "gmi_material_class"):
        del bpy.types.Material.gmi_material_class
    if hasattr(bpy.types.Material, "gmi_alpha_mode"):
        del bpy.types.Material.gmi_alpha_mode
    if hasattr(bpy.types.Material, "gmi_material_toon"):
        del bpy.types.Material.gmi_material_toon
    if hasattr(bpy.types.Material, "gmi_material_shade"):
        del bpy.types.Material.gmi_material_shade
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
