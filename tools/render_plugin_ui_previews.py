# -*- coding: utf-8 -*-
"""Render static previews of the GakumasMI Blender sidebar menus."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "ui-previews"
OUT.mkdir(parents=True, exist_ok=True)
FONT = r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf"
FONT_BOLD = r"C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf"
W, H = 760, 1040

def ft(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)

def base(target, step):
    im = Image.new("RGB", (W, H), "#111214")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 46), fill="#25272b")
    d.rectangle((0, 46, 92, H), fill="#1b1d20")
    d.text((18, 15), "Blender", font=ft(16, True), fill="#d8dbe0")
    for y, label, selected in ((96, "工具", True), (145, "场景", False), (194, "视图", False)):
        d.rounded_rectangle((10, y, 82, y + 32), 6, fill="#3d4148" if selected else "#1b1d20")
        d.text((25, y + 6), label, font=ft(15), fill="#e2e4e8")
    d.rounded_rectangle((112, 60, 738, 1000), 10, fill="#292b30", outline="#464a52")
    d.text((136, 82), "GakumasMI 工具", font=ft(23, True), fill="#f0f2f4")
    d.text((630, 86), "v0.7.3", font=ft(12), fill="#9ca3ad")
    d.rounded_rectangle((136, 122, 714, 206), 6, fill="#33363d", outline="#555b65")
    d.text((154, 134), "先选目标，再按 ① → ④ 完成", font=ft(14), fill="#cbd0d8")
    d.text((154, 168), "制作目标", font=ft(15), fill="#b9bec8")
    d.text((266, 168), target, font=ft(15, True), fill="#f5a54a")
    d.text((436, 168), "当前步骤", font=ft(15), fill="#b9bec8")
    d.text((548, 168), step, font=ft(15, True), fill="#f5a54a")
    return im, d

def panel(d, y, title, height):
    d.rounded_rectangle((136, y, 714, y + height), 7, fill="#33363d", outline="#4a4f58")
    d.text((154, y + 14), title, font=ft(17, True), fill="#eef0f3")

def field(d, y, label, value, width=540):
    d.text((154, y), label, font=ft(15), fill="#c5c9d0")
    d.rounded_rectangle((154, y + 25, 154 + width, y + 61), 5, fill="#202226", outline="#555b65")
    d.text((168, y + 33), value, font=ft(14), fill="#e4e7eb")

def button(d, y, text, accent=False):
    d.rounded_rectangle((154, y, 696, y + 42), 6, fill="#c86e2d" if accent else "#454a53")
    d.text((176, y + 10), text, font=ft(15, accent), fill="#fff7ed" if accent else "#edf0f4")

def checkbox(d, x, y, text, checked=False):
    d.rounded_rectangle((x, y, x + 20, y + 20), 3, fill="#e38b3d" if checked else "#202226", outline="#767d88")
    if checked:
        d.text((x + 2, y - 3), "✓", font=ft(18, True), fill="#1e2024")
    d.text((x + 30, y - 2), text, font=ft(14), fill="#d9dde2")

def extract():
    im, d = base("发饰 hairprop", "① 配置档")
    panel(d, 228, "步骤 1/4 · 生成完整配置档", 386)
    d.text((154, 270), "需要含 Geo_HairProp.json 的发饰资源库", font=ft(14), fill="#cbd0d8")
    field(d, 304, "抓帧目录", "D:/Games/gakumas/FrameAnalysis-2026-07-12-062317")
    field(d, 384, "发饰 JSON 资源库", "D:/GIT/gakumas-modding/build/assetstudio-hairprop-json")
    field(d, 464, "目标 hair 资源（可选）", "mdl_chr_ttmr-hair-0023_hair")
    button(d, 550, "生成完整配置档", True)
    panel(d, 632, "步骤 1/4 · 导入参考", 220)
    field(d, 674, "配置档目录", "profiles/hmsz-hair-0023-hairprop", 520)
    button(d, 760, "导入参考模型与骨架", True)
    d.text((154, 820), "导入完成后进入 ② 绑定模型", font=ft(13), fill="#aeb4bd")
    panel(d, 876, ">  高级 / 分步 / 排错", 58)
    return im

def skinning():
    im, d = base("发饰 hairprop", "② 绑定模型")
    panel(d, 228, "步骤 2/4 · 绑定作者模型", 360)
    d.text((154, 272), "先在 3D 视图中只激活作者发饰网格", font=ft(14), fill="#cbd0d8")
    panel(d, 304, "A · 硬质发饰（推荐）", 242)
    d.text((172, 350), "全部顶点 → Head_Hair", font=ft(17, True), fill="#ffbd70")
    d.text((172, 386), "不摆动、不形变", font=ft(14), fill="#cbd0d8")
    d.text((172, 420), "会清除旧权重；不要再执行传权", font=ft(14), fill="#ef9a9a")
    button(d, 474, "刚体绑定到 Head_Hair", True)
    panel(d, 612, ">  B · 需要摆动 / 形变：传递权重", 66)
    d.text((154, 724), "两条路线二选一；完成后进入 ③ 准备材质", font=ft(14), fill="#aeb4bd")
    return im

def texture():
    im, d = base("发饰 hairprop", "③ 准备材质")
    panel(d, 228, "步骤 3/4 · 指定导出贴图", 360)
    d.text((154, 270), "当前目标：发饰 hairprop", font=ft(14), fill="#ffbd70")
    field(d, 304, "基础色 t0", "T_madoka_hairprop_D.dds")
    field(d, 384, "混合遮罩 t1", "T_madoka_hairprop_MSK.dds")
    field(d, 464, "暗面材质 t4 / sdw", "T_madoka_hairprop_SDW.dds")
    checkbox(d, 154, 548, "缺 t1/t4 时使用中性贴图", True)
    panel(d, 612, "创建预览材质模板", 86)
    button(d, 646, "创建预览材质模板")
    panel(d, 724, ">  可选 · 没有 t1/t4：按材质生成", 66)
    panel(d, 812, ">  替代流程 · 只导出一张贴图", 66)
    d.text((154, 916), "hairprop 不显示 body 专用原生 co", font=ft(13), fill="#aeb4bd")
    return im

def export():
    im, d = base("发饰 hairprop", "④ 导出模组")
    panel(d, 228, "步骤 4/4 · 模组信息", 360)
    field(d, 270, "输出目录", "build/export")
    field(d, 350, "模组标识", "pm.ttmr.madoka-swimsuit-hairprop")
    field(d, 430, "模组名称", "圆香泳装配套发饰")
    field(d, 510, "预览图（必填）", "hairprop_preview.png", 420)
    panel(d, 612, "步骤 4/4 · 校验并导出", 250)
    field(d, 654, "描边颜色 / 宽度", "取自基础色  ·  正常描边", 430)
    d.text((154, 742), "✓ 已识别：Head_Hair 刚体发饰", font=ft(15, True), fill="#8bd49c")
    button(d, 786, "校验并导出模组", True)
    panel(d, 888, ">  高级 / 分步导出", 58)
    return im

pages = {
    "01_extract_import.png": extract(),
    "02_skinning_hairprop.png": skinning(),
    "03_texture_template.png": texture(),
    "04_export_mod.png": export(),
}
for filename, image in pages.items():
    image.save(OUT / filename)
overview = Image.new("RGB", (W * 2, H * 2), "#0f1012")
for index, image in enumerate(pages.values()):
    overview.paste(image, ((index % 2) * W, (index // 2) * H))
overview.save(OUT / "00_overview.png")
print(f"rendered {len(pages)} pages to {OUT}")
