bl_info = {
    "name": "GakumasMI",
    "author": "GakumasMI",
    "version": (0, 6, 0),
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
    bundled = Path(__file__).resolve().parent / "profiles" / "hski-cstm-0000"
    if bundled.is_dir():
        return str(bundled)
    development = Path(__file__).resolve().parents[2] / "profiles" / "hski-cstm-0000"
    return str(development) if development.is_dir() else ""


def _default_body_json_dir():
    bundled = Path(__file__).resolve().parent / "resources" / "assetstudio-body-json"
    if bundled.is_dir():
        return str(bundled)
    development = Path(__file__).resolve().parents[2] / "build" / "assetstudio-body-json"
    return str(development) if development.is_dir() else ""


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gmi_tool_mode = EnumProperty(
        name="模式",
        description="选择当前要执行的工作流步骤",
        items=[
            ("EXTRACT", "提取 / 导入", "抓帧+资源库生成完整配置档并导入参考模型"),
            ("SKINNING", "蒙皮转权", "把配置档权重转移给作者模型"),
            ("TEXTURE", "材质模板", "绑定身体多贴图或单贴图替换"),
            ("EXPORT", "导出模组", "校验并导出可安装模组"),
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
        name="Body JSON资源库", subtype="DIR_PATH", default=_default_body_json_dir(),
        description="AssetStudio 批量导出的 assetstudio-body-json 目录；插件会自动匹配 Geo_Body.json 和骨架 JSON",
    )
    bpy.types.Scene.gmi_body_resource = StringProperty(
        name="角色 / Body", default="",
        description="填角色代号即可（如 hmsz）：同款多角色时用于消歧，并只扫描该角色文件夹、显著加速匹配。也可填完整 body 名",
    )
    bpy.types.Scene.gmi_extract_draw = IntProperty(
        name="主 Draw", default=0, min=0,
        description="0 表示自动选择；填入 3DMigoto 顶部显示的 Draw 编号可强制指定",
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
    bpy.types.Scene.gmi_enable_native_color_transfer = BoolProperty(
        name="从基础色提取描边色（复刻原版）", default=False,
        description="导出时逐顶点把该点基础色编码进 COLOR(实测原版系数),描边 VS 解出≈基础色→衣服自身"
                    "颜色的暗化描边,贴合衣服、不死黑;ramp行/宽度/光照仍按材质预设锁定(防色块、对称)。需填基础色 t0",
    )
    bpy.types.Scene.gmi_texture_key = StringProperty(name="贴图键", default="body.baseColor")
    bpy.types.Scene.gmi_texture_file = StringProperty(name="DDS 文件", subtype="FILE_PATH")
    bpy.types.Scene.gmi_base_color_file = StringProperty(name="基础色 t0", subtype="FILE_PATH")
    bpy.types.Scene.gmi_packed_mask_file = StringProperty(name="混合遮罩 t1", subtype="FILE_PATH")
    bpy.types.Scene.gmi_shade_color_file = StringProperty(name="阴影色 t4", subtype="FILE_PATH")
    bpy.types.Scene.gmi_opacity_texture_file = StringProperty(
        name="透明材质 t0（可选）", subtype="FILE_PATH",
        description="留空时透明材质使用基础色 t0；仅当透明材质需要单独 RGBA/alpha 图时填写",
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
        description="导出时该材质槽走不透明 body 路径，还是走透明材质路径",
        items=[
            ("OPAQUE", "不透明", "使用普通 body 路径，投影/遮挡/描边最稳定"),
            ("ALPHA_BLEND", "透明", "使用透明材质路径，读取 RGBA alpha 并保留 A=0 镂空"),
        ],
        default="OPAQUE",
    )
    bpy.types.Material.gmi_material_toon = FloatProperty(
        name="明暗(阴影范围)", default=-1.0, min=-1.0, max=1.0,
        description="-1=用预设值。即 t1 的 toon 阴影阈值:值越低=阴影越大越暗、值越高=受光越多越亮。控制这个材质明暗分界落在哪、阴影铺多大;只影响这一个材质",
    )
    bpy.types.Material.gmi_material_shade = FloatProperty(
        name="阴影色强度", default=-1.0, min=-1.0, max=1.0,
        description="-1=用预设值。即 t4 阴影色(如皮肤珊瑚色)的叠加强度:越高阴影区颜色越浓、越低越淡。配合「明暗」用:明暗决定阴影铺多大,阴影色决定阴影多浓;只影响这一个材质",
    )
    bpy.types.Scene.gmi_package_id = StringProperty(name="模组标识", default="author.hski.my-mod")
    bpy.types.Scene.gmi_package_name = StringProperty(name="模组名称", default="我的学马仕模组")
    bpy.types.Scene.gmi_author = StringProperty(name="作者", default="作者")


def unregister():
    for name in (
        "gmi_tool_mode",
        "gmi_profile_dir", "gmi_capture_dir", "gmi_extract_output_dir",
        "gmi_body_json_library_dir", "gmi_body_resource",
        "gmi_extract_draw", "gmi_output_dir", "gmi_component_id",
        "gmi_source_mesh_json", "gmi_skeleton_json", "gmi_bone_remap_file",
        "gmi_unmapped_bone_fallback",
        "gmi_transfer_risk_distance", "gmi_enable_native_color_transfer",
        "gmi_texture_key", "gmi_texture_file", "gmi_package_id",
        "gmi_base_color_file", "gmi_packed_mask_file", "gmi_shade_color_file",
        "gmi_opacity_texture_file",
        "gmi_neutral_material", "gmi_outline_width_mode", "gmi_vertex_color_mode",
        "gmi_form_shading", "gmi_form_strength",
        "gmi_package_name", "gmi_author",
    ):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    if hasattr(bpy.types.Material, "gmi_material_class"):
        del bpy.types.Material.gmi_material_class
    if hasattr(bpy.types.Material, "gmi_alpha_mode"):
        del bpy.types.Material.gmi_alpha_mode
    if hasattr(bpy.types.Material, "gmi_alpha_cutoff"):
        del bpy.types.Material.gmi_alpha_cutoff
    if hasattr(bpy.types.Material, "gmi_material_toon"):
        del bpy.types.Material.gmi_material_toon
    if hasattr(bpy.types.Material, "gmi_material_shade"):
        del bpy.types.Material.gmi_material_shade
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
