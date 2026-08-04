"""Blender 内的最小 AB bundle 导出闭环，不依赖游戏抓帧或 gitignored 资产。"""

import json
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


def _write_profile(root):
    profile = root / "profile"
    (profile / "Reference").mkdir(parents=True)
    inverse = {
        "sourceVertexCount": 1,
        "weightedBoneCount": 1,
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
        "weightedBoneCount": 1,
        "nodes": [{"name": "Bone", "weightedIndex": 0, "bindPose": IDENTITY_BIND}],
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

        # 一键打包成功后，游戏要读取的 mod.json 必须和成品 bundle 并排，
        # bundle-src 内仍保留一份供 patch 脚本和排错使用。
        def fake_bundle_patch(_scene, mod_root, output_bundle):
            assert Path(mod_root) == bundle_src
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

        print("GMI_BLENDER_E2E_OK", bpy.app.version_string)
    finally:
        gakumas_mi.unregister()
