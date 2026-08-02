import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_phase3_templates as phase3

bones_from_mesh = phase3.bones_from_mesh


def test_renderer_sidecar_names_are_hash_checked():
    mesh = {
        "m_BindPose": [{}, {}],
        "m_BoneNameHashes": [11, 22],
    }
    sidecar = {
        "nodes": [
            {"weightedIndex": 0, "boneNameHash": 99, "name": "WrongRendererBone"},
            {"weightedIndex": 1, "boneNameHash": 22, "name": "RightBone"},
        ]
    }
    result = bones_from_mesh(mesh, sidecar, {11: "MappedBone"})
    assert [item["name"] for item in result["bones"]] == ["MappedBone", "RightBone"]


def test_failed_later_batch_does_not_mutate_stable_library(tmp_path, monkeypatch):
    other = tmp_path / "other"
    unity = tmp_path / "Unity.exe"
    project = tmp_path / "unity-project"
    output = tmp_path / "templates"
    source_dir = tmp_path / "json"
    other.mkdir()
    unity.touch()
    project.mkdir()
    output.mkdir()
    source_dir.mkdir()
    stable = output / "template_one.bundle"
    stable.write_bytes(b"old-stable-template")

    items = [
        ("body", "one", source_dir, other / "one"),
        ("body", "two", source_dir, other / "two"),
    ]
    generated = project / "GakumasTemplateBuild" / "Windows" / "template_one.bundle"
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b"new-template")
    calls = 0

    def fake_build_chunk(chunk, *_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [generated]
        raise RuntimeError("later Unity batch failed")

    monkeypatch.setattr(phase3, "ROOT", tmp_path)
    monkeypatch.setattr(phase3, "TEXTURE_ROOT", tmp_path / ".local" / "p3-textures")
    monkeypatch.setattr(phase3, "asset_ids", lambda _other: items)
    monkeypatch.setattr(phase3, "build_chunk", fake_build_chunk)
    monkeypatch.setattr(phase3, "cleanup_unity_work", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_phase3_templates.py",
            "--other",
            str(other),
            "--unity",
            str(unity),
            "--unity-project",
            str(project),
            "--output-dir",
            str(output),
            "--chunk-size",
            "1",
            "--skip-textures",
        ],
    )

    with pytest.raises(RuntimeError, match="later Unity batch failed"):
        phase3.main()

    assert stable.read_bytes() == b"old-stable-template"


if __name__ == "__main__":
    test_renderer_sidecar_names_are_hash_checked()
    print("phase3 template contract OK")
