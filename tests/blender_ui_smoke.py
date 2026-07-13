import re
import sys
from pathlib import Path
from unittest.mock import patch

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gakumas_mi
from gakumas_mi import core, operators, ui


class FakeLayout:
    def __init__(self):
        self.properties = []
        self.operators = []

    def box(self):
        return self

    def row(self, **_kwargs):
        return self

    def panel(self, *_args, **_kwargs):
        return self, self

    def label(self, **_kwargs):
        return None

    def prop(self, data, name, **_kwargs):
        assert hasattr(data, name), name
        self.properties.append(name)

    def operator(self, name, **_kwargs):
        self.operators.append(name)
        return None


gakumas_mi.register()
try:
    component = bpy.types.Scene.bl_rna.properties["gmi_component_id"]
    assert [item.identifier for item in component.enum_items] == ["body", "hair"]
    assert "panel" in bpy.types.UILayout.bl_rna.functions

    ui_source = (ROOT / "gakumas_mi" / "ui.py").read_text(encoding="utf-8")
    icons = set(re.findall(r'icon="([A-Z0-9_]+)"', ui_source))
    valid_icons = set(
        bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
    )
    assert not (icons - valid_icons), sorted(icons - valid_icons)

    scene = bpy.context.scene
    scene.gmi_component_id = "hair"
    scene.gmi_hairprop_enabled = True
    scene.gmi_capture_dir = str(ROOT)
    scene.gmi_body_json_library_dir = str(ROOT)
    scene.gmi_extract_output_dir = str(ROOT / ".local" / "test-output" / "blender-ui-smoke")
    scene.gmi_body_resource = "mdl_chr_test-hair-0001_hair"

    hairprop_layout = FakeLayout()
    ui.GMI_PT_main.draw_extract(None, hairprop_layout, scene)
    ui.GMI_PT_main.draw_skinning(None, hairprop_layout, scene)
    ui.GMI_PT_main.draw_texture(None, hairprop_layout, scene, bpy.context)
    ui.GMI_PT_main.draw_export(None, hairprop_layout, scene, bpy.context)
    assert "gmi.bind_hairprop_rigid" in hairprop_layout.operators
    assert "gmi_opacity_texture_file" not in hairprop_layout.properties

    scene.gmi_component_id = "body"
    scene.gmi_hairprop_enabled = False
    body_layout = FakeLayout()
    ui.GMI_PT_main.draw_texture(None, body_layout, scene, bpy.context)
    assert "gmi_opacity_texture_file" in body_layout.properties

    # hair 组件:描边色改为常量档下拉,不再显示 body 的逐顶点描边色来源
    scene.gmi_component_id = "hair"
    scene.gmi_hairprop_enabled = False
    hair_layout = FakeLayout()
    ui.GMI_PT_main.draw_texture(None, hair_layout, scene, bpy.context)
    ui.GMI_PT_main.draw_export(None, hair_layout, scene, bpy.context)
    assert "gmi_hair_outline_tier" in hair_layout.properties
    assert "gmi_vertex_color_mode" not in hair_layout.properties
    scene.gmi_hairprop_enabled = True

    hints_result = {"vertexCounts": [1], "exact": {"vertexCount": 1}}
    completion = {
        "body": scene.gmi_body_resource,
        "match": "exact",
        "boneNaming": "skeleton",
        "vertexCount": 1,
        "weightedBoneCount": 1,
        "operatorBytes": 1024,
        "unobservableBones": [],
    }
    with (
        patch.object(core, "body_json_vertex_hints", return_value=hints_result) as hints,
        patch.object(core, "extract_profile_from_frame_dump"),
        patch.object(core, "complete_inverse_skin_profile", return_value=completion),
        patch.object(core, "merge_profile_component"),
    ):
        assert bpy.ops.gmi.build_full_profile() == {"FINISHED"}
        assert {call.kwargs["mesh_name"] for call in hints.call_args_list} == {"Geo_Hair", "Geo_HairProp"}

    frame_report = {"selected": {"draw": 1, "vertices": 1, "indices": 3}}
    with (
        patch.object(core, "body_json_vertex_hints", return_value=hints_result) as hints,
        patch.object(core, "extract_profile_from_frame_dump", return_value=frame_report),
        patch.object(operators, "_resolve_body_json_library", return_value={"body": scene.gmi_body_resource}),
    ):
        assert bpy.ops.gmi.extract_profile_from_frame_dump() == {"FINISHED"}
        assert hints.call_args.kwargs["mesh_name"] == "Geo_HairProp"

    print("GMI_UI_SMOKE_OK", bpy.app.version_string, sorted(icons))
finally:
    gakumas_mi.unregister()
