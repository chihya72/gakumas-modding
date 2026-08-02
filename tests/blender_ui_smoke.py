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
        # 真 layout 返回算子属性对象，面板会往上写 op.xxx = ...
        return type("FakeOperatorProps", (), {})()

    def prop_search(self, data, name, _src, _coll, **_kwargs):
        assert hasattr(data, name), name
        self.properties.append(name)

    def template_list(self, *_args, **_kwargs):
        return None

    def column(self, **_kwargs):
        return self


gakumas_mi.register()
try:
    component = bpy.types.Scene.bl_rna.properties["gmi_component_id"]
    assert [item.identifier for item in component.enum_items] == ["body", "hair"]
    strategy = operators.GMI_bone_map_item.bl_rna.properties["strategy"]
    assert [item.identifier for item in strategy.enum_items] == [
        "auto", "rigid", "integrate", "follow_skirt", "follow_nearest",
    ]
    legacy_strategy = bpy.context.scene.gmi_bone_map.add()
    legacy_strategy["strategy"] = 3
    assert legacy_strategy.strategy == "follow_skirt"
    bpy.context.scene.gmi_bone_map.clear()
    assert "panel" in bpy.types.UILayout.bl_rna.functions

    ui_source = (ROOT / "gakumas_mi" / "ui.py").read_text(encoding="utf-8")
    icons = set(re.findall(r'icon="([A-Z0-9_]+)"', ui_source))
    valid_icons = set(
        bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
    )
    assert not (icons - valid_icons), sorted(icons - valid_icons)

    scene = bpy.context.scene
    scene.gmi_component_id = "hair"
    scene.gmi_capture_dir = str(ROOT)
    scene.gmi_body_json_library_dir = str(ROOT)
    scene.gmi_extract_output_dir = str(ROOT / ".local" / "test-output" / "blender-ui-smoke")
    scene.gmi_body_resource = "mdl_chr_test-hair-0001_hair"

    # 工作流三步 = 三个常驻子面板,全部挂在 GMI_PT_main 下（AB 路线没有传权那一步）
    step_panels = (ui.GMI_PT_step_profile, ui.GMI_PT_step_texture, ui.GMI_PT_step_export)
    for panel_cls in step_panels:
        assert panel_cls.bl_parent_id == "GMI_PT_main", panel_cls
        assert panel_cls.is_registered, panel_cls
    # 收三步时漏改过步骤号文案,这里钉死:面板按 ①②③ 排,且没有任何一处还写 ④
    assert [cls.bl_label[0] for cls in step_panels] == ["①", "②", "③"]
    init_source = (ROOT / "gakumas_mi" / "__init__.py").read_text(encoding="utf-8")
    assert "④" not in ui_source and "④" not in init_source
    # t0 在步骤②「准备材质」里填,引用它的提示不能再说步骤③
    assert "步骤③已填 t0" not in ui_source and "步骤③已填 t0" not in init_source

    hair_layout = FakeLayout()
    ui.draw_profile_step(hair_layout, scene)
    ui.draw_texture_step(hair_layout, scene, bpy.context)
    ui.draw_export_step(hair_layout, scene, bpy.context)
    # 3Dmigoto 的传权/导出入口必须一个都不剩
    for dead in ("transfer_profile_weights", "transfer_hairprop", "bind_hairprop_rigid",
                 "select_high_risk", "validate_mesh", "export_mesh_mod",
                 "export_inverse_skin_mod", "export_validated_mod", "export_texture_mod"):
        assert not any(dead in op for op in hair_layout.operators), dead
    assert "gmi.export_bundle_source" in hair_layout.operators
    assert "gmi.build_bone_map" in hair_layout.operators
    assert "gmi_hairprop_base_color_file" in hair_layout.properties
    assert "gmi_hair_use_base_alpha" in hair_layout.properties
    assert "gmi_opacity_texture_file" not in hair_layout.properties

    scene.gmi_component_id = "body"
    body_layout = FakeLayout()
    ui.draw_texture_step(body_layout, scene, bpy.context)
    assert "gmi_opacity_texture_file" in body_layout.properties
    assert "gmi_alpha_mode" in body_layout.properties

    # hair 安全模式使用常量色档，不显示 body 的逐顶点基础色合成选项。
    scene.gmi_component_id = "hair"
    hair_only_layout = FakeLayout()
    ui.draw_texture_step(hair_only_layout, scene, bpy.context)
    ui.draw_export_step(hair_only_layout, scene, bpy.context)
    assert "gmi_hair_outline_tier" in hair_only_layout.properties
    assert "gmi_vertex_color_mode" not in hair_only_layout.properties

    # Outline VS 只读 COLOR.B 低 nibble；关闭宽度不能破坏 B高或其它 packed 字段。
    packed = tuple(value / 255.0 for value in (0x12, 0x34, 0xAB, 0x9F))
    cleared = tuple(round(value * 255.0) for value in operators._clear_outline_width(packed))
    assert cleared == (0x12, 0x34, 0xA0, 0x9F), cleared

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
        assert hints.call_args.kwargs["mesh_name"] == "Geo_Hair"

    print("GMI_UI_SMOKE_OK", bpy.app.version_string, sorted(icons))
finally:
    gakumas_mi.unregister()
