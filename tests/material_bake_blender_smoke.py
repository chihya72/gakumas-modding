"""在 Blender 内实测 gmi.bake_material_maps 操作器。

    blender --background --factory-startup --python-exit-code 1 --python tests/material_bake_blender_smoke.py
"""
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gakumas_mi
from gakumas_mi import core, operators

gakumas_mi.register()

# 1) 造一张 64x64 基础色 PNG：左红右蓝
size = 64
base = np.zeros((size, size, 4), np.float32)
base[..., 3] = 1.0
base[:, :32, 0] = 0.78
base[:, 32:, 2] = 0.78
img = bpy.data.images.new("base", size, size, alpha=True)
img.colorspace_settings.name = "Non-Color"
img.pixels.foreach_set(base[::-1].reshape(-1))  # 底向上
png_path = Path(tempfile.gettempdir()) / "gmi_test_base.png"
img.filepath_raw = str(png_path)
img.file_format = "PNG"
img.save()
co_size = 32
co_base = np.zeros((co_size, co_size, 4), np.float32)
co_base[..., 1] = 0.78
co_base[..., 3] = 1.0
co_img = bpy.data.images.new("co_base", co_size, co_size, alpha=True)
co_img.colorspace_settings.name = "Non-Color"
co_img.pixels.foreach_set(co_base[::-1].reshape(-1))
co_png_path = Path(tempfile.gettempdir()) / "gmi_test_co_base.png"
co_img.filepath_raw = str(co_png_path)
co_img.file_format = "PNG"
co_img.save()

# 2) 平面网格，UV 铺满，两材质各占一半
bpy.ops.mesh.primitive_plane_add(size=2)
obj = bpy.context.active_object
mesh = obj.data
mesh.uv_layers.new(name="UVMap")
m_skin = bpy.data.materials.new("skin_mat")
m_metal = bpy.data.materials.new("metal_mat")
m_skin.gmi_material_class = "skin"
m_metal.gmi_material_class = "metal"
m_metal.gmi_alpha_mode = "NATIVE_CO"
mesh.materials.append(m_skin)
mesh.materials.append(m_metal)
# 平面 1 个 quad，赋 slot0；细分出第二材质区
import bmesh
bm = bmesh.new(); bm.from_mesh(mesh)
bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1, use_grid_fill=True)
bm.to_mesh(mesh); bm.free()
uv = mesh.uv_layers.active.data
for poly in mesh.polygons:
    cu = sum(uv[l].uv[0] for l in poly.loop_indices) / poly.loop_total
    poly.material_index = 0 if cu < 0.5 else 1

scene = bpy.context.scene
scene.gmi_base_color_file = str(png_path)
scene.gmi_opacity_texture_file = str(co_png_path)

# 3) 烘焙
result = bpy.ops.gmi.bake_material_maps()
assert result == {"FINISHED"}, result
assert scene.gmi_packed_mask_file and scene.gmi_shade_color_file
assert scene.gmi_opacity_packed_mask_file and scene.gmi_opacity_shade_color_file
t1_path, t4_path = scene.gmi_packed_mask_file, scene.gmi_shade_color_file
co_t1_path, co_t4_path = scene.gmi_opacity_packed_mask_file, scene.gmi_opacity_shade_color_file
d1 = core.inspect_dds(t1_path)
assert (d1["width"], d1["height"]) == (size, size), d1
assert d1["format"] == "DXGI_28", f"t1 应为 R8G8B8A8_UNORM(28)，实际 {d1['format']}"  # linear
d4 = core.inspect_dds(t4_path)
assert d4["format"] == "DXGI_29", f"t4 应为 R8G8B8A8_UNORM_SRGB(29)，实际 {d4['format']}"
co_d1 = core.inspect_dds(co_t1_path)
co_d4 = core.inspect_dds(co_t4_path)
assert (co_d1["width"], co_d1["height"]) == (co_size, co_size), co_d1
assert co_d1["format"] == "DXGI_28", co_d1
assert co_d4["format"] == "DXGI_29", co_d4

# body/hair/hairprop 必须写不同临时文件；否则完整发型包中后烘焙的发饰会覆盖 Hair t1/t4。
assert Path(t1_path).name == "gmi_baked_body_packedMask.dds", t1_path
assert Path(co_t1_path).name == "gmi_baked_body_co_packedMask.dds", co_t1_path
obj["gmi_component_id"] = "hair"
m_skin.gmi_material_class = "hair"
m_metal.gmi_material_class = "hair"
m_metal.gmi_alpha_mode = "OPAQUE"
assert bpy.ops.gmi.bake_material_maps() == {"FINISHED"}
hair_t1 = Path(scene.gmi_packed_mask_file)
hair_t4 = Path(scene.gmi_shade_color_file)
hair_bytes = hair_t1.read_bytes()
assert hair_t1.name == "gmi_baked_hair_packedMask.dds"
assert set(hair_bytes[151::4]) == {0}, "安全 hair t1.A 必须为 0"

obj["gmi_component_id"] = "hairprop"
scene.gmi_hairprop_base_color_file = str(co_png_path)
assert bpy.ops.gmi.bake_material_maps() == {"FINISHED"}
prop_t1 = Path(scene.gmi_hairprop_packed_mask_file)
prop_t4 = Path(scene.gmi_hairprop_shade_color_file)
assert prop_t1.name == "gmi_baked_hairprop_packedMask.dds"
assert prop_t4.name == "gmi_baked_hairprop_shadeColor.dds"
assert hair_t1.read_bytes() == hair_bytes, "HairProp 烘焙覆盖了 Hair t1"
assert hair_t1 != prop_t1 and hair_t4 != prop_t4

# 普通 PNG 默认 A=255；hair 安全转换必须能强制 t0.A=0。
forced_t0 = Path(operators._png_to_dds(str(png_path), alpha_override=0))
assert set(forced_t0.read_bytes()[151::4]) == {0}

print("material_bake_blender_smoke OK:", t1_path, t4_path, co_t1_path, co_t4_path)
