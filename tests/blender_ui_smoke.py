import json
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
        self.lists = []

    def box(self):
        return self

    def row(self, **_kwargs):
        return self

    def separator(self, **_kwargs):
        return None

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

    def template_list(self, _ui_class, list_id, data, _prop, *_args, **_kwargs):
        self.lists.append((list_id, getattr(data, "name", data)))

    def column(self, **_kwargs):
        return self


gakumas_mi.register()
try:
    component = bpy.types.Scene.bl_rna.properties["gmi_component_id"]
    assert [item.identifier for item in component.enum_items] == ["body", "hair"]
    workflow = bpy.types.Scene.bl_rna.properties["gmi_workflow_stage"]
    assert [item.identifier for item in workflow.enum_items] == [
        "TARGET", "MODEL", "MATERIAL", "RIG", "EXPORT"]
    target_source = bpy.types.Scene.bl_rna.properties["gmi_target_source"]
    assert [item.identifier for item in target_source.enum_items] == ["CAPTURE", "PROFILE"]
    strategy = operators.GMI_bone_map_item.bl_rna.properties["strategy"]
    assert [item.identifier for item in strategy.enum_items] == [
        "auto", "rigid", "integrate", "follow_skirt", "follow_nearest", "native_driver",
        # bake / reject 只能追加在末尾：老 .blend 存的是枚举的**整数**下标
        "bake", "reject",
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

    # 五阶段只注册一个主面板；旧版三个巨型折叠子面板不能复活。
    assert ui.GMI_PT_main.is_registered
    assert ui.CLASSES == (ui.GMI_UL_bone_map, ui.GMI_PT_main)
    assert not hasattr(ui, "GMI_PT_step_profile")
    init_source = (ROOT / "gakumas_mi" / "__init__.py").read_text(encoding="utf-8")

    # 构造一个明确的作者网格，验证 UI 不再依赖测试进程碰巧激活了哪个对象。
    mesh = bpy.data.meshes.new("GMI_UI_SmokeMesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.uv_layers.new(name="UVMap")
    author_obj = bpy.data.objects.new("GMI_UI_SmokeAuthor", mesh)
    scene.collection.objects.link(author_obj)
    author_obj.vertex_groups.new(name="Hips").add([0, 1, 2], 1.0, "REPLACE")
    material = bpy.data.materials.new("GMI_UI_SmokeMaterial")
    mesh.materials.append(material)
    scene.gmi_author_object = author_obj

    hair_layout = FakeLayout()
    ui.draw_profile_step(hair_layout, scene)
    ui.draw_model_step(hair_layout, scene, bpy.context)
    ui.draw_texture_step(hair_layout, scene, bpy.context)
    ui.draw_rig_step(hair_layout, scene, bpy.context)
    ui.draw_export_step(hair_layout, scene, bpy.context)
    # 3Dmigoto 的传权/导出入口必须一个都不剩
    for dead in ("transfer_profile_weights", "transfer_hairprop", "bind_hairprop_rigid",
                 "select_high_risk", "validate_mesh", "export_mesh_mod",
                 "export_inverse_skin_mod", "export_validated_mod", "export_texture_mod"):
        assert not any(dead in op for op in hair_layout.operators), dead
    assert "gmi.export_bundle_source" in hair_layout.operators
    assert "gmi.build_bone_map" in hair_layout.operators
    assert "gmi.prepare_target" in hair_layout.operators
    assert "gmi.activate_author_object" in hair_layout.operators
    assert "gmi_hairprop_base_color_file" in hair_layout.properties
    assert "gmi_hair_use_base_alpha" in hair_layout.properties
    assert "gmi_opacity_texture_file" not in hair_layout.properties

    # 发型包第三步：发型和发饰是并排的两栏，各有自己的材质槽列表。
    # 发饰以前只有三个贴图路径、没有材质槽，作者在面板里改不了发饰的材质类型
    # （而它决定发饰描边常量），只能去 Scripting 里切 gmi_author_object。
    prop_mesh = bpy.data.meshes.new("GMI_UI_SmokeProp")
    prop_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    prop_mesh.uv_layers.new(name="UVMap")
    prop_mesh.materials.append(bpy.data.materials.new("GMI_UI_SmokePropMaterial"))
    prop_obj = bpy.data.objects.new("GMI_UI_SmokeProp", prop_mesh)
    scene.collection.objects.link(prop_obj)
    scene.gmi_hairprop_object = prop_obj
    hairprop_layout = FakeLayout()
    ui.draw_texture_step(hairprop_layout, scene, bpy.context)
    list_ids = [list_id for list_id, _data in hairprop_layout.lists]
    assert "GMI_materials" in list_ids, list_ids
    assert "GMI_hairprop_materials" in list_ids, list_ids
    # 发饰那一栏画的必须是发饰对象，不能跟着作者模型走
    assert dict(hairprop_layout.lists)["GMI_hairprop_materials"] == prop_obj.name
    scene.gmi_hairprop_object = None

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
    # 必须与 core.complete_inverse_skin_profile 的真实返回键一致——此前这里多造了一个
    # 已删除的 operatorBytes，算子读它、测试喂它，KeyError 就一路溜到用户面前。
    completion = {
        "body": scene.gmi_body_resource,
        "match": "exact",
        "boneNaming": "skeleton",
        "vertexCount": 1,
        "weightedBoneCount": 1,
        "activeBoneCount": 1,
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

    # 骨骼映射表单的「部件类型」列：它决定新骨的摆动参数取原版哪一档、要不要建
    # ActorSwingChain，所以既要保证读得出来，也要保证只在「自建摇物链」时可点——
    # 别的策略不新建骨，那一列可点就是误导。
    item = scene.gmi_bone_map.add()
    item.source = "帯_01"
    item.strategy = "integrate"
    item.swing_category = "skirt"
    assert operators._form_swing_categories(scene) == {"帯_01": "skirt"}
    item.target = "Hips"                    # 填了目标骨=确定映射，类别失效
    assert operators._form_swing_categories(scene) == {}
    item.target = ""
    item.strategy = "rigid"                 # 不新建骨的策略同样不该产出类别
    assert operators._form_swing_categories(scene) == {}


    # 批次 6：原版布料驱动器只作用在**作者点名的那几根骨**上，且只支持运行时实现的三类。
    scene.gmi_bone_map.clear()
    driver_row = scene.gmi_bone_map.add()
    driver_row.source = "LeftSkirt1_S"
    driver_row.members = "LeftSkirt1_S\nLeftSkirt2_S"
    driver_row.strategy = "native_driver"
    driver_row.swing_category = "skirt"
    other = scene.gmi_bone_map.add()          # 同类别、没点名：不该被带上
    other.source = "RightSkirt1_S"
    other.members = "RightSkirt1_S"
    assert operators._form_driver_bones(scene) == {
        "LeftSkirt1_S": "skirt", "LeftSkirt2_S": "skirt"}
    assert operators._form_driver_gaps(scene) == []
    driver_row.swing_category = "ribbon"      # 没有对应驱动器 → 必须被闸门抓住
    assert operators._form_driver_bones(scene) == {}
    assert [name for name, _category in operators._form_driver_gaps(scene)] == [
        "LeftSkirt1_S", "LeftSkirt2_S"]
    driver_row.target = "Hips"                # 填了目标骨=确定映射，驱动器那一列失效
    assert operators._form_driver_gaps(scene) == []
    scene.gmi_bone_map.clear()

    # 列表行只负责选择和暴露异常，不再横向塞目标骨、策略、类别等 6 列控件。
    queue_item = scene.gmi_bone_map.add()
    queue_item.source = "帯_01"
    queue_item.strategy = "rigid"

    class ListRow:
        def __init__(self, sink):
            self.sink, self.enabled = sink, True
            self.scale_x, self.ui_units_x, self.alignment = 1.0, 0.0, "EXPAND"

        def row(self, **_kwargs):
            return ListRow(self.sink)

        def label(self, **_kwargs):
            return None

        def prop(self, data, name, **_kwargs):
            assert hasattr(data, name), name
            self.sink.append((name, self.enabled))

        def prop_search(self, data, name, *_args, **_kwargs):
            assert hasattr(data, name), name

        def operator(self, *_args, **_kwargs):
            return type("FakeOperatorProps", (), {})()

    def draw_row():
        sink = []
        ui.GMI_UL_bone_map.draw_item(
            None, bpy.context, ListRow(sink), scene, queue_item, None, scene, "", 0)
        return sink

    assert draw_row() == []
    rigid_detail = FakeLayout()
    ui.draw_rig_step(rigid_detail, scene, bpy.context)
    assert "target" in rigid_detail.properties and "strategy" in rigid_detail.properties
    assert "swing_category" not in rigid_detail.properties
    queue_item.strategy = "integrate"
    integrate_detail = FakeLayout()
    ui.draw_rig_step(integrate_detail, scene, bpy.context)
    assert "swing_category" in integrate_detail.properties
    assert "swing_anchor" in integrate_detail.properties

    # 一行 = 一组：表单里的决定必须落到组里每一根骨，否则作者点一次只管到代表骨。
    # 五档状态列的图标不走 icon="..." 字面量，上面那道 icon 校验扫不到，这里单独查。
    assert not (set(ui._STATE_ICONS.values()) - valid_icons)
    scene.gmi_bone_map.clear()
    group = scene.gmi_bone_map.add()
    group.source, group.members = "スカート0", "スカート0\nスカート1\nスカート2"
    group.strategy = "integrate"
    group.swing_category = "skirt"
    assert operators._form_swing_categories(scene) == {
        name: "skirt" for name in ("スカート0", "スカート1", "スカート2")}
    assert operators._form_physics_overrides(scene) == {
        name: "integrate" for name in ("スカート0", "スカート1", "スカート2")}
    assert ui._row_state(group) == "helper"
    group.strategy = "auto"
    assert ui._row_state(group) == "undecided", "装饰骨没目标不是错，是「这一组还没决定」"
    group.target = "Hips"
    assert operators._form_bone_map(scene) == {
        name: "Hips" for name in ("スカート0", "スカート1", "スカート2")}
    assert ui._row_state(group) == "merge", "三根骨指到同一根目标骨 = 多对一"

    # 真树形组：展开只插入子视图，点击/选中不改映射；只有修改子字段才写逐骨覆盖。
    group.member_auto_targets = json.dumps({
        "スカート0": "Hips", "スカート1": "Spine", "スカート2": "Hips"})
    assert bpy.ops.gmi.toggle_bone_group(index=0) == {"FINISHED"}
    assert len(scene.gmi_bone_map) == 4
    assert len(operators._mapping_rows(scene)) == 1
    assert operators.row_bones(scene.gmi_bone_map[0]) == [
        "スカート0", "スカート1", "スカート2"]
    children = list(scene.gmi_bone_map)[1:]
    assert all(child.is_group_child for child in children)
    child = next(child for child in children if child.source == "スカート1")
    scene.gmi_bone_map_index = next(
        index for index, row in enumerate(scene.gmi_bone_map) if row.source == "スカート1")
    selected_layout = FakeLayout()
    ui.draw_rig_step(selected_layout, scene, bpy.context)
    assert not json.loads(scene.gmi_bone_map[0].member_overrides or "{}")
    assert operators._form_bone_map(scene) == {
        name: "Hips" for name in ("スカート0", "スカート1", "スカート2")}

    child.target = "Head"
    assert child.is_group_child and len(operators.row_bones(scene.gmi_bone_map[0])) == 3
    assert operators._form_bone_map(scene) == {
        "スカート0": "Hips", "スカート2": "Hips", "スカート1": "Head"}
    child.target = ""
    assert operators._form_bone_map(scene) == {
        name: "Hips" for name in ("スカート0", "スカート1", "スカート2")}
    assert not json.loads(scene.gmi_bone_map[0].member_overrides or "{}")

    child.strategy = "rigid"
    assert "スカート1" not in operators._form_bone_map(scene)
    assert operators._form_physics_overrides(scene)["スカート1"] == "rigid"
    child.strategy = "auto"
    assert operators._form_bone_map(scene)["スカート1"] == "Hips"
    assert "スカート1" not in operators._form_physics_overrides(scene)

    child.target = "Head"
    assert bpy.ops.gmi.reset_bone_member_override(
        index=scene.gmi_bone_map_index) == {"FINISHED"}
    assert not json.loads(scene.gmi_bone_map[0].member_overrides or "{}")
    assert child.is_group_child
    assert bpy.ops.gmi.toggle_bone_group(index=0) == {"FINISHED"}
    assert len(scene.gmi_bone_map) == 1 and not scene.gmi_bone_map[0].expanded

    # 拆开这一组 → 一行一根骨，组里的决定原样带过去
    assert bpy.ops.gmi.split_bone_group(index=0) == {"FINISHED"}
    assert [row.source for row in scene.gmi_bone_map] == ["スカート0", "スカート1", "スカート2"]
    assert all(row.target == "Hips" for row in scene.gmi_bone_map)
    assert ui._row_state(scene.gmi_bone_map[0]) == "direct"
    scene.gmi_bone_map.clear()

    # 1.7.0：扫描始终保存完整集合；「待处理 / 全部」只是 UI 过滤。手动处理一个折叠组后，
    # 它应从待处理视图消失，但不能丢失，也不能在下一扫炸成一行一根。
    weighted = [
        ("VanillaHips", 25.0), ("VanillaHead", 20.0),
        ("Hip +23", 15.0), ("Hip.001", 5.0), ("Hip.002", 3.0),
        ("Bust_L +8", 12.0), ("Sp_Hi_Skirt0_B_01 +5", 9.0), ("Arm_R +33", 11.0),
    ]
    structural_groups = [
        {"members": ["Hip +23", "Hip.001", "Hip.002"]},
        {"members": ["Bust_L +8"]},
        {"members": ["Sp_Hi_Skirt0_B_01 +5"]},
        {"members": ["Arm_R +33"]},
    ]
    preset = {
        "bones": {"VanillaHips": "Hips", "VanillaHead": "Head"},
        "bodyBones": {"VanillaHips", "VanillaHead"},
        "methods": {"VanillaHips": "preset", "VanillaHead": "preset"},
    }
    auto_targets = {"VanillaHips": "Hips", "VanillaHead": "Head"}

    class FilterProbe:
        bitflag_filter_item = 1
        filter_name = ""

    def visible_count():
        flags, _order = ui.GMI_UL_bone_map.filter_items(
            FilterProbe(), bpy.context, scene, "gmi_bone_map")
        return sum(bool(flag) for flag in flags)

    with (
        patch.object(operators, "_bone_map_context",
                     return_value=(author_obj, {"Hips": 0, "Head": 1}, preset)),
        patch.object(operators, "_weighted_group_mass", return_value=weighted),
        patch.object(operators, "_dominant_group_counts", return_value={}),
        patch.object(operators, "_source_bone_parents", return_value={}),
        patch.object(core, "structural_bone_groups", return_value=structural_groups),
        patch.object(operators, "_resolve_body_json_library", return_value={}),
        patch.object(operators, "_resolve_source_bone_remap",
                     return_value=(auto_targets, None)),
    ):
        assert bpy.ops.gmi.build_bone_map(only_unmapped=True) == {"FINISHED"}
        assert len(scene.gmi_bone_map) == 6
        assert scene.gmi_bone_map_only_undecided
        assert visible_count() == 4

        folded = next(row for row in scene.gmi_bone_map if row.source == "Hip +23")
        folded.target = "Hips"
        assert folded.origin == "manual"
        assert bpy.ops.gmi.build_bone_map(only_unmapped=True) == {"FINISHED"}
        assert len(scene.gmi_bone_map) == 6
        folded = next(row for row in scene.gmi_bone_map if row.source == "Hip +23")
        assert operators.row_bones(folded) == ["Hip +23", "Hip.001", "Hip.002"]
        assert visible_count() == 3

        # 子覆盖始终留在父树内，并能穿过重扫；清空子目标 + auto 后恢复父组。
        folded_index = next(index for index, row in enumerate(scene.gmi_bone_map)
                            if row.source == "Hip +23")
        assert bpy.ops.gmi.toggle_bone_group(index=folded_index) == {"FINISHED"}
        child = next(row for row in scene.gmi_bone_map
                     if row.is_group_child and row.source == "Hip.001")
        child.target = "Head"
        assert len(operators._mapping_rows(scene)) == 6
        assert operators._form_bone_map(scene) == {
            "Hip +23": "Hips", "Hip.001": "Head", "Hip.002": "Hips"}
        assert bpy.ops.gmi.toggle_bone_group(index=folded_index) == {"FINISHED"}
        assert len(scene.gmi_bone_map) == 6
        assert bpy.ops.gmi.build_bone_map(only_unmapped=True) == {"FINISHED"}
        folded = next(row for row in scene.gmi_bone_map if row.source == "Hip +23")
        assert json.loads(folded.member_overrides)["Hip.001"]["target"] == "Head"
        folded_index = next(index for index, row in enumerate(scene.gmi_bone_map)
                            if row.source == "Hip +23")
        assert bpy.ops.gmi.toggle_bone_group(index=folded_index) == {"FINISHED"}
        child = next(row for row in scene.gmi_bone_map
                     if row.is_group_child and row.source == "Hip.001")
        assert child.target == "Head"
        child.target = ""
        assert not json.loads(scene.gmi_bone_map[folded_index].member_overrides or "{}")
        assert operators._form_bone_map(scene) == {
            name: "Hips" for name in ("Hip +23", "Hip.001", "Hip.002")}
        assert bpy.ops.gmi.toggle_bone_group(index=folded_index) == {"FINISHED"}
        assert len(scene.gmi_bone_map) == 6

        assert bpy.ops.gmi.build_bone_map(only_unmapped=False) == {"FINISHED"}
        assert not scene.gmi_bone_map_only_undecided
        assert len(scene.gmi_bone_map) == visible_count() == 6
        all_layout = FakeLayout()
        ui.draw_rig_step(all_layout, scene, bpy.context)
        assert "wm.context_set_boolean" in all_layout.operators
        assert "gmi_bone_map_only_undecided" not in all_layout.properties
        assert bpy.ops.gmi.build_bone_map(only_unmapped=True) == {"FINISHED"}
        assert scene.gmi_bone_map_only_undecided
        assert len(scene.gmi_bone_map) == 6 and visible_count() == 3
        pending_layout = FakeLayout()
        ui.draw_rig_step(pending_layout, scene, bpy.context)
        assert "wm.context_set_boolean" not in pending_layout.operators
        assert "gmi_bone_map_only_undecided" not in pending_layout.properties

    mixed = next(row for row in scene.gmi_bone_map if row.source == "Bust_L +8")
    mixed.auto_target = "逐骨不同"
    assert operators.row_effective_target(mixed) == ""
    assert ui._row_state(mixed) == "undecided"
    assert bpy.ops.gmi.clear_bone_map() == {"FINISHED"}
    assert not scene.gmi_bone_map and not scene.gmi_bone_map_only_undecided

    # 已自动识别的 15 根左手指骨仍折成一棵语义树，但每节保留自己的自动目标；展开不能
    # 凭空写出 15 个“单独设置”，父行标题也不能再冒充成 Ring_01_L。
    finger_names = [f"{finger}_{joint:02d}_L"
                    for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                    for joint in range(1, 4)]
    finger_targets = {
        name: f"LeftHand{name.split('_')[0]}{int(name.split('_')[1])}"
        for name in finger_names
    }
    finger_preset = {
        "bones": finger_targets,
        "bodyBones": set(finger_names),
        "methods": {name: "finger_chain" for name in finger_names},
    }
    finger_weighted = [(name, 1.0 - index * 0.01)
                       for index, name in enumerate(finger_names)]
    finger_parents = {}
    for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        finger_parents[f"{finger}_01_L"] = "Wrist_L"
        finger_parents[f"{finger}_02_L"] = f"{finger}_01_L"
        finger_parents[f"{finger}_03_L"] = f"{finger}_02_L"
    target_map = {name: index for index, name in enumerate(finger_targets.values())}
    with (
        patch.object(operators, "_bone_map_context",
                     return_value=(author_obj, target_map, finger_preset)),
        patch.object(operators, "_weighted_group_mass", return_value=finger_weighted),
        patch.object(operators, "_dominant_group_counts", return_value={}),
        patch.object(operators, "_source_bone_parents", return_value=finger_parents),
        patch.object(core, "structural_bone_groups", return_value=[]),
        patch.object(operators, "_resolve_body_json_library", return_value={}),
        patch.object(operators, "_resolve_source_bone_remap",
                     return_value=(finger_targets, None)),
    ):
        assert bpy.ops.gmi.build_bone_map(only_unmapped=False) == {"FINISHED"}
        assert len(scene.gmi_bone_map) == 1
        hand = scene.gmi_bone_map[0]
        assert hand.group_label == "左手手指"
        assert operators.row_bones(hand) == finger_names
        assert hand.auto_target == "逐骨不同" and ui._row_state(hand) == "direct"
        assert bpy.ops.gmi.toggle_bone_group(index=0) == {"FINISHED"}
        assert len(scene.gmi_bone_map) == 16
        assert not json.loads(scene.gmi_bone_map[0].member_overrides or "{}")
        assert all(not operators._override_active({
            "target": child.target, "strategy": child.strategy,
            "category": child.swing_category, "swing_anchor": child.swing_anchor,
        }) for child in list(scene.gmi_bone_map)[1:])
    assert bpy.ops.gmi.clear_bone_map() == {"FINISHED"}

    # 尺子和会改模型的修复工具属于骨架阶段，导出页不再重复塞整张映射表。
    ruler_layout = FakeLayout()
    ruler_item = scene.gmi_bone_map.add()
    ruler_item.source = "Hips"
    ruler_item.target = "Hips"
    scene.gmi_rig_report = json.dumps({
        "alignment": [{"bone": "LeftShoulder", "mm": 0.2, "deg": 172.0, "grade": "red"}],
        "bands": [{"joint": "肩", "share": 0.049, "vanilla": 0.133, "grade": "red"}],
        "measured": 1, "skipped": 0, "baseline": "参考体",
    })
    ui.draw_rig_step(ruler_layout, scene, bpy.context)
    assert "gmi.report_rig_alignment" in ruler_layout.operators
    assert "gmi.split_weight_from_neighbours" in ruler_layout.operators
    assert "gmi.bake_rest_offset" in ruler_layout.operators
    export_layout = FakeLayout()
    ui.draw_export_step(export_layout, scene, bpy.context)
    assert "gmi.build_bone_map" not in export_layout.operators
    assert "gmi.report_rig_alignment" not in export_layout.operators
    scene.gmi_rig_report = ""
    ui.draw_rig_step(FakeLayout(), scene, bpy.context)     # 没量过也要画得出来

    print("GMI_UI_SMOKE_OK", bpy.app.version_string, sorted(icons))
finally:
    gakumas_mi.unregister()
