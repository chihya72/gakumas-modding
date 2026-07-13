"""Generate a runtime-only GakumasMI Profile from a 3DMigoto FrameAnalysis dump."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "gakumas_mi" / "core.py"


def _load_core():
    spec = importlib.util.spec_from_file_location("gakumas_mi_core", CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(
        description="从 3DMigoto FrameAnalysis 抓帧目录生成 runtime-only body profile。"
    )
    parser.add_argument("capture", type=Path, help="FrameAnalysis-* 抓帧目录")
    parser.add_argument("output", type=Path, help="输出 profile 目录")
    parser.add_argument("--component", default="body", help="组件名，默认 body")
    parser.add_argument(
        "--draw",
        type=int,
        default=0,
        help="手动指定主 Draw 编号；0 表示自动选择候选",
    )
    parser.add_argument("--body-json-library", type=Path, help="AssetStudio body JSON资源库目录")
    parser.add_argument("--body-resource", default="", help="角色代号或完整 body 名，如 shro")
    args = parser.parse_args()

    core = _load_core()
    expected_vertex_count = None
    expected_vertex_counts = []
    if args.body_json_library and args.body_resource:
        hints = core.body_json_vertex_hints(
            args.body_json_library, args.body_resource,
            mesh_name=core.component_mesh_name(args.component),
        )
        expected_vertex_counts = hints["vertexCounts"]
        if hints["exact"]:
            expected_vertex_count = hints["exact"].get("vertexCount")
    report = core.extract_profile_from_frame_dump(
        args.capture,
        args.output,
        component_id=args.component,
        main_draw=args.draw or None,
        expected_vertex_count=expected_vertex_count,
        expected_vertex_counts=expected_vertex_counts,
        body_resource=(args.body_resource or None),
    )
    selected = report["selected"]
    print(f"生成完成：{args.output}")
    print(
        f"主 Draw {selected['draw']:06d} / IB {selected.get('ibHash')} / "
        f"{selected['vertices']} 顶点 / {selected['indices']} 索引"
    )
    print(f"候选数量：{report['candidateCount']}，报告：{args.output / 'extraction-report.json'}")


if __name__ == "__main__":
    main()
