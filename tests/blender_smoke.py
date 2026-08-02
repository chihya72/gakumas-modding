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
        print("GMI_BLENDER_E2E_OK", bpy.app.version_string)
    finally:
        gakumas_mi.unregister()
