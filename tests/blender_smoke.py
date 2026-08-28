"""Blender 内的最小 AB bundle 导出闭环，不依赖游戏抓帧或 gitignored 资产。"""

import json
import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gakumas_mi
from gakumas_mi import operators


IDENTITY_BIND = {
    "M00": 1.0, "M01": 0.0, "M02": 0.0, "M03": 0.0,
    "M10": 0.0, "M11": 1.0, "M12": 0.0, "M13": 0.0,
    "M20": 0.0, "M21": 0.0, "M22": 1.0, "M23": 0.0,
    "M30": 0.0, "M31": 0.0, "M32": 0.0, "M33": 1.0,
}


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_profile(root, name="profile", nodes=None):
    nodes = nodes or [{"name": "Bone", "weightedIndex": 0, "bindPose": IDENTITY_BIND}]
    profile = root / name
    (profile / "Reference").mkdir(parents=True)
    inverse = {
        "sourceVertexCount": 1,
        "weightedBoneCount": len(nodes),
        "coefficientCount": 4,
        "posedVertexStride": 40,
        "meshJson": "Reference/Geo_Body.json",
        "skeletonJson": "Reference/Geo_Body.skeleton.json",
        "unobservableBones": [],
    }
    _write_json(profile / "profile.json", {
        "schemaVersion": 1,
        "id": "blender-e2e",
        "target": {
            "actorId": "test",
            "costumeId": "cstm-0000",
            "bodyResource": "mdl_chr_test-cstm-0000_body",
        },
        "components": [{
            "id": "body", "ibHash": "4d5dfe7b", "indices": 3,
            "mainFirstIndex": 0, "inverseSkin": inverse,
        }],
    })
    _write_json(profile / "drawcall_map.json", {
        "components": {"body": {"passBindings": {
            "main": {"draw": 1, "vertexShader": "aaaa1111"},
        }}},
    })
    _write_json(profile / "texture_map.json", {"textures": {}})
    _write_json(profile / "material_map.json", {"materials": {}})
    _write_json(profile / "Reference" / "Geo_Body.json", {
        "m_VertexCount": 3,
        "m_BindPose": [IDENTITY_BIND],
        "m_Name": "mdl_chr_test-cstm-0000_body",
    })
    _write_json(profile / "Reference" / "Geo_Body.skeleton.json", {
        "weightedBoneCount": len(nodes), "nodes": nodes,
    })
    return profile


def _create_mesh():
    mesh = bpy.data.meshes.new("AuthorMesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    uv = mesh.uv_layers.new(name="UV0")
    for loop in mesh.loops:
        uv.data[loop.index].uv = ((0, 0), (1, 0), (0, 1))[loop.vertex_index]
    obj = bpy.data.objects.new("AuthorMesh", mesh)
    bpy.context.collection.objects.link(obj)
    group = obj.vertex_groups.new(name="Bone")
    group.add([0, 1, 2], 1.0, "REPLACE")
    obj["gmi_component_id"] = "body"
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _create_rigged_mesh(roll=0.0, forearm=(0.70, 0.0, 1.40)):
    """带骨架修改器的作者网格：三根身体骨（Hips → LeftArm → LeftForeArm）。

    `roll`    绕骨自身轴的滚转 —— Blender 侧根本没保留它（原版自己的参考骨架 104 根里
              69 根 roll 差 180°），所以尺子必须对它免疫。
    `forearm` 小臂的位置 —— 改它就改了「大臂 → 小臂」的**方向**，那才是会炸的那一种。
    """
    data = bpy.data.armatures.new("Rig")
    rig = bpy.data.objects.new("Rig", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    hips = data.edit_bones.new("Hips")
    hips.head, hips.tail = (0.0, 0.0, 1.00), (0.0, 0.0, 1.12)
    arm = data.edit_bones.new("LeftArm")
    arm.head, arm.tail = (0.15, 0.0, 1.40), (0.45, 0.0, 1.40)
    arm.roll, arm.parent = roll, hips
    fore = data.edit_bones.new("LeftForeArm")
    fore.head, fore.tail = forearm, (forearm[0], forearm[1] + 0.1, forearm[2])
    fore.parent = arm
    bpy.ops.object.mode_set(mode="OBJECT")

    mesh = bpy.data.meshes.new("RiggedMesh")
    mesh.from_pydata([(0.15, 0, 1.4), (0.45, 0, 1.4), (0.3, 0.1, 1.4)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("RiggedMesh", mesh)
    bpy.context.collection.objects.link(obj)
    obj.vertex_groups.new(name="Hips").add([0], 1.0, "REPLACE")
    obj.vertex_groups.new(name="LeftArm").add([1], 1.0, "REPLACE")
    obj.vertex_groups.new(name="LeftForeArm").add([2], 1.0, "REPLACE")
    obj.modifiers.new("Armature", "ARMATURE").object = rig
    obj["gmi_component_id"] = "body"
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj, rig


def _drop_rig_objects():
    for existing in list(bpy.data.objects):
        if existing.name in ("AuthorMesh", "RiggedMesh", "Rig"):
            bpy.data.objects.remove(existing, do_unlink=True)


def _create_png(path):
    image = bpy.data.images.new("png", 2, 2, alpha=True)
    image.generated_color = (0.2, 0.4, 0.8, 1.0)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()


with tempfile.TemporaryDirectory(prefix="gmi-blender-e2e-") as tmp:
    tmp = Path(tmp)
    profile = _write_profile(tmp)
    base = tmp / "base.png"
    shade = tmp / "shade.png"
    _create_png(base)
    _create_png(shade)
    packed = tmp / "packed.dds"
    gakumas_mi.core.write_rgba8_dds(
        packed, 2, 2,
        bytes((10, 20, 30, 255, 40, 50, 60, 255,
               70, 80, 90, 255, 100, 110, 120, 255)),
        srgb=False,
    )

    gakumas_mi.register()
    try:
        obj = _create_mesh()
        scene = bpy.context.scene
        scene.gmi_profile_dir = str(profile)
        scene.gmi_output_dir = str(tmp / "out")
        scene.gmi_package_id = "test.blender.e2e"
        scene.gmi_package_name = "Blender E2E"
        scene.gmi_author = "GakumasMI"
        scene.gmi_neutral_material = False
        scene.gmi_outline_width_mode = "DISABLE_ALL"
        scene.gmi_vertex_color_mode = "CONSTANT_BLACK"
        scene.gmi_base_color_file = str(base)
        scene.gmi_packed_mask_file = str(packed)
        scene.gmi_shade_color_file = str(shade)

        package = tmp / "out" / "test.blender.e2e"
        # bundle 导出直接消费源模型自带顶点组，不存在传权这一步。
        assert bpy.ops.gmi.export_bundle_source() == {"FINISHED"}
        bundle_src = package / "bundle-src"
        for relative in (
            "mdl_chr_test-cstm-0000_body.geojson.txt",
            "test.blender.e2e_bones.json.txt",
            "body_slot0_t0.png", "body_slot0_t1.png", "body_slot0_t4.png",
            "mod.json",
        ):
            assert (bundle_src / relative).is_file(), relative
        bundle_manifest = json.loads((bundle_src / "mod.json").read_text(encoding="utf-8"))
        assert bundle_manifest["replacements"][0]["replaceMaterials"] is False
        assert len(bundle_manifest["replacements"][0]["textures"]) == 3

        # 「沿用源模型顶点色」：逐顶点原样出包。别的模式按材质槽写常量，同一个槽里的皮肤
        # 和布料会拿到同一行 ramp —— IP 源（一个 m_bdy 槽装皮肤+布料）就是这么渲染坏的。
        colour = (obj.data.color_attributes.get("COLOR")
                  or obj.data.color_attributes.new(name="COLOR", type="FLOAT_COLOR", domain="POINT"))
        marks = [(index / 255.0, 0.125, 0.0588, 1.0) for index in range(len(obj.data.vertices))]
        colour.data.foreach_set("color", [channel for mark in marks for channel in mark])
        scene.gmi_outline_width_mode = "KEEP"
        scene.gmi_vertex_color_mode = "SOURCE"
        assert bpy.ops.gmi.export_bundle_source() == {"FINISHED"}
        exported = json.loads(
            (bundle_src / "mdl_chr_test-cstm-0000_body.geojson.txt").read_text(encoding="utf-8")
        )["m_Colors"]
        seen = {tuple(round(value, 4) for value in exported[index:index + 4])
                for index in range(0, len(exported), 4)}
        assert seen == {tuple(round(channel, 4) for channel in mark) for mark in marks}, seen
        obj.data.color_attributes.remove(obj.data.color_attributes["COLOR"])
        try:                                         # 坏样本要报：没有 COLOR 就不许出包
            result = bpy.ops.gmi.export_bundle_source()
        except RuntimeError:
            result = {"CANCELLED"}
        assert result == {"CANCELLED"}, "SOURCE 模式缺逐顶点 COLOR 必须拦下，不能静默换描边色"
        scene.gmi_outline_width_mode = "DISABLE_ALL"
        scene.gmi_vertex_color_mode = "CONSTANT_BLACK"

        # 一键打包成功后，游戏要读取的 mod.json 必须和成品 bundle 并排，
        # bundle-src 内仍保留一份供 patch 脚本和排错使用。
        def fake_bundle_patch(_scene, mod_root, output_bundle, asset_id=""):
            assert Path(mod_root) == bundle_src
            # 模板要按目标资源名去找，所以导出器必须把资源名传下来 —— 传空就等于
            # 又退回让作者自己挑文件
            assert asset_id, "导出器没有把目标资源名传给模板查找"
            Path(output_bundle).write_bytes(b"test-bundle")
            return output_bundle

        with patch.object(operators, "_run_bundle_patch", side_effect=fake_bundle_patch):
            assert bpy.ops.gmi.export_bundle_source(also_patch=True) == {"FINISHED"}
        output_bundle = package / "test.blender.e2e.bundle"
        output_manifest = package / "mod.json"
        assert output_bundle.read_bytes() == b"test-bundle"
        assert output_manifest.is_file()
        assert output_manifest.read_bytes() == (bundle_src / "mod.json").read_bytes()
        # bindPose 的键序：写入必须和 _bind_pose_matrix / patch_unity_bundle 的读取一致
        # （AssetStudio 约定 M<列><行>，平移落在 M30..M32）。写成转置时，游戏原始骨不受
        # 影响、只有插件新增的源专属骨炸开，很难一眼看出来，所以在这里锁死。
        from mathutils import Matrix
        sample = Matrix(((0.36, -0.48, 0.80, 1.5), (0.80, 0.60, 0.0, -2.5),
                         (-0.48, 0.64, 0.60, 3.5), (0.0, 0.0, 0.0, 1.0)))
        encoded = operators._matrix_json(sample)
        assert [round(encoded[f"M3{i}"], 4) for i in range(3)] == [1.5, -2.5, 3.5], encoded
        decoded = operators._bind_pose_matrix(encoded)
        assert all(abs(sample[r][c] - decoded[r][c]) < 1e-6
                   for r in range(4) for c in range(4)), decoded

        # 新骨的两个约定：四元数是 (x,y,z,w)，且挂在游戏骨下的链根要按游戏骨架静止姿势
        # 重算 local。写错任一个，游戏原始骨都不受影响、只有装饰件变形，很难一眼看出来。
        from mathutils import Quaternion, Vector
        turn = Quaternion((0.0, 0.0, 1.0), 1.2)          # 绕 Z 轴，w 与 xyz 都不为 0
        assert operators._quaternion_xyzw(turn) == [turn.x, turn.y, turn.z, turn.w]
        assert operators._quaternion_xyzw(turn)[3] == turn.w, "w 必须在末位"

        # 游戏骨架：Hips 在 y=1.0；作者骨架把新骨摆在世界 (0.1, 1.3, 0.2)
        fake_skeleton = {"nodes": [{
            "name": "Hips", "parent": -1,
            "localPosition": [0.0, 1.0, 0.0],
            "localRotation": [0.0, 0.0, 0.0, 1.0], "localScale": [1.0, 1.0, 1.0],
        }]}
        authored = Matrix.LocRotScale(Vector((0.1, 1.3, 0.2)), turn, Vector((1.0, 1.0, 1.0)))
        new_bones = [{"name": "Bow_A", "parentName": "Hips",
                      "localPosition": [9.0, 9.0, 9.0],      # 故意填错，必须被重算掉
                      "localRotation": [0.0, 0.0, 0.0, 1.0], "localScale": [1.0, 1.0, 1.0]}]
        assert operators._retarget_new_bone_roots(
            new_bones, [{"name": "Bow_A", "worldMatrix": authored}], fake_skeleton) == 1
        parent_world = operators._target_rest_world(fake_skeleton)["Hips"]
        item = new_bones[0]
        x, y, z, w = item["localRotation"]
        rebuilt = parent_world @ Matrix.LocRotScale(
            Vector(item["localPosition"]), Quaternion((w, x, y, z)), Vector(item["localScale"]))
        assert (rebuilt.translation - authored.translation).length < 1e-6, rebuilt.translation

        # --- 对齐尺子（P2 的仪表）--------------------------------------------
        # 游戏骨的 bindPose 由**导出器那条已在用的路径**（_source_bone_sidecar_records）
        # 从一副 0° 滚转的作者骨架生成 —— 即"游戏骨恰好长在作者骨的位置上"。三个判据：
        #   同一副骨架        → 0.0mm / 0.0° 全绿（尺子不许在正常样本上误报）
        #   只差绕骨轴 172°   → 仍然全绿（Blender 侧没保留 roll，按 roll 判会把原版自己判红）
        #   小臂方向差 172°   → 大臂报红，且**大臂自己的位置差仍然是 0**（只量位置看不见它）
        _drop_rig_objects()
        aligned_obj, _rig = _create_rigged_mesh(roll=0.0)
        records = {item["name"]: item for item in
                   operators._source_bone_sidecar_records(aligned_obj)}
        rig_profile = _write_profile(tmp, "profile-rig", nodes=[
            {"name": name, "parent": index - 1, "weightedIndex": index,
             "bindPose": records[name]["bindPose"]}
            for index, name in enumerate(("Hips", "LeftArm", "LeftForeArm"))
        ])
        scene.gmi_profile_dir = str(rig_profile)
        scene.gmi_skeleton_json = ""
        assert bpy.ops.gmi.report_rig_alignment() == {"FINISHED"}
        report = json.loads(scene.gmi_rig_report)
        assert report["measured"] == 3, report
        assert {row["grade"] for row in report["alignment"]} == {"green"}, report
        assert max(row["mm"] for row in report["alignment"]) < 1e-4, report
        assert max(row["deg"] or 0.0 for row in report["alignment"]) < 1e-3, report

        _drop_rig_objects()
        _create_rigged_mesh(roll=math.radians(172.0))
        assert bpy.ops.gmi.report_rig_alignment() == {"FINISHED"}
        rolled = json.loads(scene.gmi_rig_report)["alignment"]
        assert {row["grade"] for row in rolled} == {"green"}, rolled

        # 小臂绕肘往身后转 172°：大臂→小臂的方向变了，大臂自己的位置一点没动
        angle = math.radians(180.0 - 172.0)
        _drop_rig_objects()
        _create_rigged_mesh(forearm=(0.15 - 0.25 * math.cos(angle), 0.0,
                                     1.40 + 0.25 * math.sin(angle)))
        assert bpy.ops.gmi.report_rig_alignment() == {"FINISHED"}
        bent = {row["bone"]: row for row in json.loads(scene.gmi_rig_report)["alignment"]}
        assert bent["LeftArm"]["grade"] == "red", bent
        assert abs(bent["LeftArm"]["deg"] - 172.0) < 1.0, bent
        assert bent["LeftArm"]["mm"] < 1e-4, bent           # 位置一点没动
        assert bent["LeftArm"]["child"] == "LeftForeArm", bent
        assert bent["Hips"]["grade"] == "green", bent

        # P4 闸门 7：导出前拦住朝向差。两个方向都要钉（贯穿规矩 2）——这个包必须被拦，
        # 上面那副对齐好的骨架必须放行。位置差不拦（重定向会吸收它）。
        rig_skeleton = gakumas_mi.core.load_json(
            rig_profile / "Reference" / "Geo_Body.skeleton.json")
        bent_obj = bpy.data.objects["RiggedMesh"]
        bent_remap = {name: name for name in ("Hips", "LeftArm", "LeftForeArm")}
        bent_report = {"bodyBones": list(bent_remap)}
        message = operators._rest_orientation_error(
            bent_obj, rig_skeleton, bent_remap, bent_report)
        assert message and "LeftArm" in message, message
        _drop_rig_objects()
        aligned_again, _rig = _create_rigged_mesh(roll=0.0)
        assert operators._rest_orientation_error(
            aligned_again, rig_skeleton, bent_remap, bent_report) is None

        print("GMI_BLENDER_E2E_OK", bpy.app.version_string)
    finally:
        gakumas_mi.unregister()


# ── 模板按目标资源名自动查找 ────────────────────────────────────────────
# 作者多半不知道抓帧抓到的那套衣服叫 ttmr-cstm-0111 —— 让他从几百个模板里挑一个，
# 挑错了导出照样跑，出来的是坏包。文件名是**算出来的**（`template_<资源名>.bundle`，
# 由 build_phase3_templates 固定这么命名），不是猜的。
with tempfile.TemporaryDirectory() as _tmp:
    _templates = Path(_tmp) / "templates"
    _templates.mkdir()
    _wanted = _templates / "template_mdl_chr_ttmr-cstm-0111_body.bundle"
    _wanted.write_bytes(b"stub")
    (_templates / "template_mdl_chr_atbm-cstm-0140_body.bundle").write_bytes(b"stub")

    class _Scene:
        gmi_bundle_template = str(_templates)

    # 目录 + 资源名 → 唯一确定的那一个
    assert Path(operators._resolve_bundle_template(
        _Scene(), "mdl_chr_ttmr-cstm-0111_body")) == _wanted

    # 直接给文件也认（老 .blend 存的是文件路径；别人单发一个模板也是这种）
    _Scene.gmi_bundle_template = str(_wanted)
    assert Path(operators._resolve_bundle_template(_Scene(), "")) == _wanted

    # 目录里没有对应模板：报错必须点出**缺哪个文件名**，作者拿它去素材包补
    _Scene.gmi_bundle_template = str(_templates)
    try:
        operators._resolve_bundle_template(_Scene(), "mdl_chr_hski-cstm-0000_body")
    except ValueError as exc:
        assert "template_mdl_chr_hski-cstm-0000_body.bundle" in str(exc), exc
    else:
        raise AssertionError("模板不存在却没报错")

    # 留空、路径不存在：两种都要报错，不能默默往下走
    for _bad in ("", str(Path(_tmp) / "nope")):
        _Scene.gmi_bundle_template = _bad
        try:
            operators._resolve_bundle_template(_Scene(), "mdl_chr_ttmr-cstm-0111_body")
        except ValueError:
            pass
        else:
            raise AssertionError(f"无效模板路径没报错：{_bad!r}")

print(f"GMI_TEMPLATE_LOOKUP_OK {bpy.app.version_string}")
