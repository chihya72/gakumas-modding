bl_info = {
    "name": "GakumasMI",
    "author": "GakumasMI",
    "version": (0, 7, 6),
    "blender": (4, 2, 0),
    "location": "3D 视图 > 侧边栏 > GakumasMI",
    "description": "学园偶像大师换装/换发 mod 制作：抓帧生成配置档 → 绑定作者模型 → 导出 3DMigoto 逆蒙皮模组",
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
    bpy.types.Scene.gmi_profile_dir = StringProperty(
        name="配置档目录", subtype="DIR_PATH", default=_default_profile_dir(),
        description="配置档（profile）记录被替换目标的注入信息、参考网格与逆蒙皮算子，"
                    "之后每一步都围绕它工作。步骤①生成后自动填写；已有配置档可直接填这里跳过生成",
    )
    bpy.types.Scene.gmi_capture_dir = StringProperty(
        name="抓帧目录", subtype="DIR_PATH",
        description="3DMigoto 帧分析（F8）生成的 FrameAnalysis-* 文件夹。"
                    "抓帧时让目标角色在游戏里穿上要被替换的服装/发型。"
                    "留空时使用配置档中记录的抓帧路径",
    )
    bpy.types.Scene.gmi_extract_output_dir = StringProperty(
        name="新配置档输出", subtype="DIR_PATH",
        description="可选。留空时写入抓帧目录下的 GakumasMI-profile。"
                    "建议生成后把配置档移出游戏目录保存，抓帧文件夹被清理时配置档会一并丢失",
    )
    bpy.types.Scene.gmi_body_json_library_dir = StringProperty(
        name="网格 JSON 资源库", subtype="DIR_PATH", default=_default_body_json_dir(),
        description="AssetStudio 批量导出的游戏网格 JSON 目录（tools/export_all_body_json.py 生成）。"
                    "身体需要 Geo_Body.json；发型需要同一批 _hair 包的 Geo_Hair.json 与 Geo_HairProp.json。"
                    "用于把抓帧数据补全成带权重、骨架和逆算子的完整配置档",
    )
    bpy.types.Scene.gmi_body_resource = StringProperty(
        name="目标资源（可选）", default="",
        description="在资源库里消歧用：填角色代号（如 hski）或完整资源名"
                    "（如 mdl_chr_hski-cstm-0000_body）。留空时按抓帧顶点数自动匹配，"
                    "多个候选撞车时才需要填",
    )
    bpy.types.Scene.gmi_extract_draw = IntProperty(
        name="主 Draw", default=0, min=0,
        description="0 = 按顶点布局自动打分选择。自动选错（生成的参考模型不是目标网格）时，"
                    "填 3DMigoto 左上角显示的 Draw 编号强制指定",
    )
    bpy.types.Scene.gmi_output_dir = StringProperty(
        name="输出目录", subtype="DIR_PATH",
        description="导出的 mod 包写到这里；把整个包文件夹放进游戏 Mods 目录即可安装",
    )
    bpy.types.Scene.gmi_component_id = EnumProperty(
        name="制作目标",
        description="选身体或发型即可，发饰不是独立目标：发型和配套发饰是两个网格对象，"
                    "在步骤②分别绑定，导出时按对象标记自动分包/合并",
        items=[
            ("body", "身体（body）",
             "替换 Geo_Body 整个身体网格；透明/镂空部件在步骤③把对应材质槽设为「原生co」"),
            ("hair", "发型（hair）",
             "替换 Geo_Hair；配套发饰 Geo_HairProp 可选制作——只做发型则保留原发饰，"
             "发型+发饰一起做则导出时自动合并为一个完整包"),
        ],
        default="body",
    )
    bpy.types.Scene.gmi_source_mesh_json = StringProperty(
        name="原模型 JSON", subtype="FILE_PATH",
        description="被替换网格的 AssetStudio JSON；由资源库匹配自动填写，一般不用手动改",
    )
    bpy.types.Scene.gmi_skeleton_json = StringProperty(
        name="骨架 JSON", subtype="FILE_PATH",
        description="被替换网格的骨架 sidecar JSON；由资源库匹配自动填写，一般不用手动改",
    )
    bpy.types.Scene.gmi_bone_remap_file = StringProperty(
        name="骨骼映射", subtype="FILE_PATH",
        description="可选 JSON 映射表 {作者骨名: 配置档骨名}。"
                    "作者模型带配置档没有的辅助骨/物理骨时，把这些骨的权重并到指定主骨",
    )
    bpy.types.Scene.gmi_unmapped_bone_fallback = StringProperty(
        name="未映射骨骼兜底", default="",
        description="可选配置档骨名，一般填 Hips。MMD 等外部模型常有顶点权重残留在控制骨/物理骨上，"
                    "导出报「顶点没有可导出的配置档兼容权重」时启用：未映射的权重归到该骨。"
                    "留空=严格校验，遇到未知骨直接报错；受影响顶点很多时应回去修权重而不是靠兜底",
    )
    bpy.types.Scene.gmi_transfer_risk_distance = FloatProperty(
        name="风险距离", default=0.02, min=0.0001, unit="LENGTH",
        description="传权时距参考模型表面超过该距离的顶点会记入 GMI_REVIEW_HIGH_RISK 顶点组。"
                    "宽袖、裙摆、飘带等远离身体的部件超出属正常现象，传权后人工复核这些顶点即可",
    )
    bpy.types.Scene.gmi_texture_key = StringProperty(
        name="贴图键", default="body.baseColor",
        description="要替换的配置档贴图槽位，格式 <组件>.<语义>，"
                    "如 body.baseColor、hair.packedMask、body.shadeColor",
    )
    bpy.types.Scene.gmi_texture_file = StringProperty(
        name="DDS 文件", subtype="FILE_PATH",
        description="替换用贴图。t0/t4 是 sRGB，t1 是线性；PNG 会自动转 DDS",
    )
    bpy.types.Scene.gmi_base_color_file = StringProperty(
        name="基础色 t0", subtype="FILE_PATH",
        description="必填。角色的固有色贴图，PNG 或 DDS，必须为正方形。"
                    "留空不报错，但 mod.ini 不会生成 ps-t0 → 游戏沿用原贴图，颜色整体错乱",
    )
    bpy.types.Scene.gmi_packed_mask_file = StringProperty(
        name="混合遮罩 t1", subtype="FILE_PATH",
        description="打包遮罩（线性空间）：R=toon 阴影阈值 / G=光滑度 / B=金属度 / A=AO。"
                    "发型语义不同：A 必须为 0。没有现成图就留空，用下方「按材质生成 t1/t4」",
    )
    bpy.types.Scene.gmi_shade_color_file = StringProperty(
        name="暗面材质 t4/sdw", subtype="FILE_PATH",
        description="暗面颜色图：RGB=基础色的暗化版（布料约 ×0.45、皮肤约 ×0.78），"
                    "A=皮肤二值遮罩——是数据不是透明度，看图软件里显示成透明属正常。"
                    "没有现成图就留空，用「按材质生成 t1/t4」",
    )
    bpy.types.Scene.gmi_hairprop_base_color_file = StringProperty(
        name="发饰基础色 t0", subtype="FILE_PATH",
        description="发饰作者网格的固有色贴图；只在同时制作发饰时填写。"
                    "发饰网格已绑定却留空时，发饰会沿用原贴图导致颜色错乱",
    )
    bpy.types.Scene.gmi_hairprop_packed_mask_file = StringProperty(
        name="发饰混合遮罩 t1", subtype="FILE_PATH",
        description="发饰的打包遮罩，语义同发型（A 必须为 0）。"
                    "留空可用「按材质生成 t1/t4」对激活的发饰网格生成",
    )
    bpy.types.Scene.gmi_hairprop_shade_color_file = StringProperty(
        name="发饰暗面材质 t4/sdw", subtype="FILE_PATH",
        description="发饰的暗面颜色图，语义同发型（RGB=基础色×冷阴影乘数、A=0）",
    )
    bpy.types.Scene.gmi_t1_r_file = StringProperty(
        name="t1.R 阴影阈值", subtype="FILE_PATH",
        description="可选通道图，写入 t1.R（toon 阴影阈值：越低阴影越大）。"
                    "只填部分通道时，先按材质预设生成完整 t1，再只覆盖有内容的区域",
    )
    bpy.types.Scene.gmi_t1_g_file = StringProperty(
        name="t1.G 光滑度", subtype="FILE_PATH",
        description="可选通道图，写入 t1.G。四个通道都填时跳过材质预设、整图合成",
    )
    bpy.types.Scene.gmi_t1_b_file = StringProperty(
        name="t1.B 金属度", subtype="FILE_PATH",
        description="可选通道图，写入 t1.B。四个通道都填时跳过材质预设、整图合成",
    )
    bpy.types.Scene.gmi_t1_a_file = StringProperty(
        name="t1.A AO", subtype="FILE_PATH",
        description="可选通道图，写入 t1.A（body=AO/间接光；别搬源游戏的白色 AO 图，会大片白斑）。"
                    "四个通道都填时跳过材质预设、整图合成",
    )
    bpy.types.Scene.gmi_opacity_texture_file = StringProperty(
        name="co 基础色 t0 / m_bdyco", subtype="FILE_PATH",
        description="有材质槽设为「原生co」时必填：透明/镂空部件自己的基础色（RGBA，"
                    "alpha 做镂空；透明区 RGB 记得外扩防黑边）。不会回退共用身体 t0",
    )
    bpy.types.Scene.gmi_opacity_packed_mask_file = StringProperty(
        name="co 混合遮罩 t1", subtype="FILE_PATH",
        description="原生 co 部件自己的打包遮罩；留空时用中性 t1 顶替（部件质感会丢），不共用身体 t1",
    )
    bpy.types.Scene.gmi_opacity_shade_color_file = StringProperty(
        name="co 暗面材质 t4/sdw", subtype="FILE_PATH",
        description="原生 co 部件自己的暗面颜色；留空时用中性 t4 顶替，不共用身体 t4",
    )
    bpy.types.Scene.gmi_neutral_material = BoolProperty(
        name="中性 t1/t4", default=True,
        description="t1/t4 留空时自动绑定中性贴图，防止游戏原版遮罩/阴影叠在新贴图上"
                    "（身体与发型使用不同的中性常量）。建议保持开启",
    )
    bpy.types.Scene.gmi_outline_width_mode = EnumProperty(
        name="描边宽度",
        description="描边线条的粗细来源（写进顶点 COLOR，游戏描边 pass 读取）",
        items=[
            ("KEEP", "正常描边", "全网格正常描边"),
            ("RISK_ONLY", "仅安全顶点", "只关闭高风险 / GMI_NO_OUTLINE 顶点的描边，掩盖传权瑕疵"),
            ("DISABLE_ALL", "关闭", "全网格无描边"),
        ],
        default="KEEP",
    )
    bpy.types.Scene.gmi_vertex_color_mode = EnumProperty(
        name="描边颜色",
        description="描边颜色的来源。游戏描边读顶点 COLOR，新网格必须由插件写入——"
                    "缺 COLOR 会被默认白色冲掉，描边直接消失",
        items=[
            ("BASECOLOR", "取自基础色", "逐顶点从 t0 采样生成描边色，复刻原版观感（需要步骤③已填 t0）"),
            ("MATERIAL_PRESET", "按材质预设", "按材质槽类型用预设描边色（布料/皮肤/金属…）"),
            ("CONSTANT_BLACK", "黑色常量", "全部描边统一纯黑，最保守"),
        ],
        default="BASECOLOR",
    )
    bpy.types.Scene.gmi_hair_outline_tier = EnumProperty(
        name="发型描边色档",
        description="发型描边色是全网格常量（不是逐顶点），按发色明度选档；"
                    "进游戏后描边偏亮就换更暗一档，宁小勿大",
        items=[
            ("DARK", "深色发(蓝紫/黑褐)", "nibble (0,0,1)，实测自蓝紫发"),
            ("PINK", "粉/红发", "nibble (1,0,0)，实测自粉发"),
            ("BLONDE", "金/浅色发", "nibble (4,2,1)，实测自金发"),
            ("BLACK", "纯黑描边", "nibble (0,0,0)，最保守"),
        ],
        default="DARK",
    )
    bpy.types.Scene.gmi_form_shading = BoolProperty(
        name="几何AO软化阴影", default=False,
        description="生成 t1 时从网格几何烘 AO，只对凹陷缝隙（腋下/裆部/衣褶内）加深阴影；"
                    "对光滑凸面（腿/裤袜）无效——硬光影分界要靠材质行的「明暗」调",
    )
    bpy.types.Scene.gmi_form_strength = FloatProperty(
        name="软化强度", default=0.6, min=0.0, max=2.0,
        description="几何 AO 对 toon 渐变的影响强度：进游戏偏硬就调高、显脏就调低",
    )
    bpy.types.Material.gmi_material_class = EnumProperty(
        name="材质类型",
        description="该材质槽按哪套实测预设生成 t1/t4（皮肤/布料/金属…）。"
                    "金属发饰务必标 metal（灰描边+高光）；暗场景发乌的小金属件可改用布料参数",
        items=_material_class_items(),
        default="cloth",
    )
    bpy.types.Material.gmi_alpha_mode = EnumProperty(
        name="渲染材质",
        description="该材质槽走不透明身体路径，还是交给游戏原生第二材质段（m_bdyco）画透明/镂空",
        items=[
            ("OPAQUE", "不透明", "普通身体路径；投影/遮挡/描边最稳定，默认选这个"),
            ("NATIVE_CO", "原生co", "borrow 游戏原生 m_bdyco 的 shader/state 画镂空半透明。"
             "判断标准：该材质贴图的实际 UV 足迹里透明像素多才需要；需要配置档含第二材质段"),
        ],
        default="OPAQUE",
    )
    bpy.types.Material.gmi_material_toon = FloatProperty(
        name="明暗(阴影范围)", default=-1.0, min=-1.0, max=1.0,
        description="-1=用预设值。t1 的 toon 阴影阈值：越低阴影铺得越大越暗、越高受光越多越亮；"
                    "只影响这一个材质槽",
    )
    bpy.types.Scene.gmi_package_id = StringProperty(
        name="模组标识", default="author.hski.my-mod",
        description="mod 包的唯一 ID，只能用字母/数字/点/横线；同 ID 的包会互相覆盖",
    )
    bpy.types.Scene.gmi_package_name = StringProperty(
        name="模组名称", default="我的学马仕模组",
        description="显示在 Mod 管理器里的名称",
    )
    bpy.types.Scene.gmi_author = StringProperty(
        name="作者", default="作者",
        description="显示在 Mod 管理器里的作者名",
    )
    bpy.types.Scene.gmi_cover_image = StringProperty(
        name="预览图", subtype="FILE_PATH",
        description="mod 封面（png/jpg/webp），导出必填；过大会自动缩到 ≤1024px、上限 2MB",
    )


def unregister():
    for name in (
        "gmi_profile_dir", "gmi_capture_dir", "gmi_extract_output_dir",
        "gmi_body_json_library_dir", "gmi_body_resource",
        "gmi_extract_draw", "gmi_output_dir", "gmi_component_id",
        "gmi_source_mesh_json", "gmi_skeleton_json", "gmi_bone_remap_file",
        "gmi_unmapped_bone_fallback",
        "gmi_transfer_risk_distance",
        "gmi_texture_key", "gmi_texture_file", "gmi_package_id",
        "gmi_base_color_file", "gmi_packed_mask_file", "gmi_shade_color_file",
        "gmi_hairprop_base_color_file", "gmi_hairprop_packed_mask_file", "gmi_hairprop_shade_color_file",
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
