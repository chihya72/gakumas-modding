import sys
from pathlib import Path

import bpy
import bmesh


ROOT = Path(r"D:\GIT\gakumas-modding")
sys.path.insert(0, str(ROOT / "blender_addon"))

import gakumas_mi


gakumas_mi.register()
scene = bpy.context.scene
scene.gmi_profile_dir = str(ROOT / "profiles" / "hski-cstm-0000")
scene.gmi_capture_dir = ""
scene.gmi_output_dir = str(ROOT / "build" / "blender-smoke")
scene.gmi_component_id = "body"
scene.gmi_package_id = "test.blender.mesh"
scene.gmi_package_name = "Blender Smoke Mesh"
scene.gmi_author = "GakumasMI"

assert bpy.ops.gmi.import_reference() == {"FINISHED"}
obj = bpy.context.active_object
assert len(obj.data.vertices) == 17615
assert len(obj.data.polygons) == 24888
assert len(obj.data.uv_layers) == 2
assert bpy.ops.gmi.validate_mesh() == {"FINISHED"}
assert bpy.ops.gmi.export_mesh_mod() == {"FINISHED"}

scene.gmi_source_mesh_json = ""
scene.gmi_skeleton_json = ""
assert bpy.ops.gmi.import_weighted_reference() == {"FINISHED"}
weighted_obj = bpy.context.active_object
assert len(weighted_obj.data.vertices) == 17615
assert len(weighted_obj.vertex_groups) == 152
assert weighted_obj.parent.type == "ARMATURE"
assert len(weighted_obj.parent.data.bones) == 152
assert bpy.ops.gmi.validate_mesh() == {"FINISHED"}

# Product workflow: an arbitrary author mesh receives Profile weights, risk
# attributes and can be exported without keeping the foreign armature.
target = weighted_obj.copy()
target.data = weighted_obj.data.copy()
target.name = "AuthorMesh"
bpy.context.collection.objects.link(target)
target.parent = None
# Keep the smoke fixture below the R16 expanded-loop limit. Real author meshes
# are validated against the same limit during export.
bm = bmesh.new()
bm.from_mesh(target.data)
bmesh.ops.delete(bm, geom=list(bm.faces)[10000:], context="FACES_ONLY")
bm.to_mesh(target.data)
bm.free()
if "gmi_weighted_reference" in target:
    del target["gmi_weighted_reference"]
for selected in bpy.context.selected_objects:
    selected.select_set(False)
target.select_set(True)
bpy.context.view_layer.objects.active = target
assert bpy.ops.gmi.transfer_profile_weights() == {"FINISHED"}
assert target["gmi_profile_weights"] is True
assert "GMI_WEIGHT_RISK" in target.data.color_attributes
assert "GMI_REVIEW_HIGH_RISK" in target.vertex_groups
assert bpy.ops.gmi.validate_mesh() == {"FINISHED"}
assert bpy.ops.gmi.create_native_body_sets() == {"FINISHED"}
assert "GMI_NATIVE_HAND" in weighted_obj.vertex_groups
assert "GMI_NATIVE_NECK" in weighted_obj.vertex_groups

scene.gmi_package_id = "test.blender.weighted"
scene.gmi_package_name = "Blender Weighted Mod"
material_root = ROOT / "build" / "inverse-skin-generated" / "test.ttmr-outfit-on-hski" / "Textures"
scene.gmi_base_color_file = str(material_root / "Body.BaseColor.dds")
scene.gmi_packed_mask_file = str(material_root / "Body.PackedMask.dds")
scene.gmi_shade_color_file = str(material_root / "Body.ShadeColor.dds")
bpy.context.view_layer.objects.active = target
target.select_set(True)
weighted_obj.select_set(False)
assert bpy.ops.gmi.export_inverse_skin_mod() == {"FINISHED"}
weighted_root = ROOT / "build" / "blender-smoke" / "test.blender.weighted"
assert (weighted_root / "Buffers" / "Body.BindSkin.R32_UINT.buf").is_file()
assert (weighted_root / "Textures" / "Body.PackedMask.dds").is_file()
ini = (weighted_root / "mod.ini").read_text(encoding="utf-8")
assert "ps-t0 = Resource" in ini and "ps-t1 = Resource" in ini and "ps-t4 = Resource" in ini

scene.gmi_package_id = "test.blender.surface"
scene.gmi_package_name = "Blender Smoke Surface"
assert bpy.ops.gmi.export_surface_mod() == {"FINISHED"}

scene.gmi_package_id = "test.blender.texture"
scene.gmi_package_name = "Blender Smoke Texture"
scene.gmi_texture_key = "body.baseColor"
scene.gmi_texture_file = str(
    ROOT / "mods" / "poc-recolor-hski-body" / "Textures" / "Body.BaseColor.dds"
)
assert bpy.ops.gmi.export_texture_mod() == {"FINISHED"}

mesh_buffer = (
    ROOT / "build" / "blender-smoke" / "test.blender.mesh"
    / "Buffers" / "Body.IB.R16_UINT.buf"
)
texture = (
    ROOT / "build" / "blender-smoke" / "test.blender.texture"
    / "Textures" / "Body.BaseColor.dds"
)
surface_root = ROOT / "build" / "blender-smoke" / "test.blender.surface"
assert mesh_buffer.stat().st_size == 149328
assert texture.stat().st_size == 4194432
assert (surface_root / "Buffers" / "Body.VB0.buf").stat().st_size == 704600
assert (surface_root / "Buffers" / "Body.VB1.buf").stat().st_size == 211380
assert (surface_root / "Buffers" / "Body.IB.R16_UINT.buf").stat().st_size == 149328
assert (surface_root / "Buffers" / "Body.SurfaceMap.buf").stat().st_size == 563680
print("GMI_SMOKE_OK", len(weighted_obj.data.vertices), len(weighted_obj.vertex_groups))

gakumas_mi.unregister()
