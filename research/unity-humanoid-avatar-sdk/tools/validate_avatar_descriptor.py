"""Validate the portions of an Avatar descriptor that can be checked offline."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ROLES = {"body", "face", "hair", "accessory", "effect", "ignore"}
RENDERER_TYPES = {"SkinnedMeshRenderer", "MeshRenderer"}
EXPRESSION_MODES = {"max", "addClamp", "multiply"}


def _error(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _local_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and not (len(value) >= 2 and value[1] == ":")
        and "\\" not in value
        and ".." not in value.split("/")
    )


def validate_descriptor(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["$: descriptor must be an object"]
    if data.get("protocol") != 1:
        _error(errors, "$.protocol", "must be integer 1")
    for key in ("sdkVersion", "unityVersion", "buildId"):
        if not isinstance(data.get(key), str) or not data[key]:
            _error(errors, f"$.{key}", "must be a non-empty string")
    for key in ("avatarRoot", "animator"):
        if not _local_path(data.get(key)):
            _error(errors, f"$.{key}", "must be a relative forward-slash path")

    renderers = data.get("renderers")
    if not isinstance(renderers, list):
        _error(errors, "$.renderers", "must be an array")
        renderers = []
    renderer_paths: set[str] = set()
    for index, renderer in enumerate(renderers):
        path = f"$.renderers[{index}]"
        if not isinstance(renderer, dict):
            _error(errors, path, "must be an object")
            continue
        renderer_path = renderer.get("path")
        if not _local_path(renderer_path):
            _error(errors, f"{path}.path", "must be a relative forward-slash path")
        elif renderer_path in renderer_paths:
            _error(errors, f"{path}.path", "duplicates another renderer path")
        else:
            renderer_paths.add(renderer_path)
        if renderer.get("role") not in ROLES:
            _error(errors, f"{path}.role", "is not a supported renderer role")
        if renderer.get("rendererType") not in RENDERER_TYPES:
            _error(errors, f"{path}.rendererType", "is not a supported renderer type")
        if "blendShapes" in renderer:
            shapes = renderer["blendShapes"]
            if not isinstance(shapes, list) or any(not isinstance(item, str) or not item for item in shapes):
                _error(errors, f"{path}.blendShapes", "must be an array of non-empty strings")

    expressions = data.get("expressions")
    if not isinstance(expressions, list):
        _error(errors, "$.expressions", "must be an array")
        expressions = []
    for index, expression in enumerate(expressions):
        path = f"$.expressions[{index}]"
        if not isinstance(expression, dict):
            _error(errors, path, "must be an object")
            continue
        if not isinstance(expression.get("channel"), str) or not expression["channel"]:
            _error(errors, f"{path}.channel", "must be a non-empty string")
        outputs = expression.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            _error(errors, f"{path}.outputs", "must be a non-empty array")
            continue
        for output_index, output in enumerate(outputs):
            output_path = f"{path}.outputs[{output_index}]"
            if not isinstance(output, dict):
                _error(errors, output_path, "must be an object")
                continue
            if output.get("rendererPath") not in renderer_paths:
                _error(errors, f"{output_path}.rendererPath", "does not name a declared renderer")
            if not isinstance(output.get("blendShape"), str) or not output["blendShape"]:
                _error(errors, f"{output_path}.blendShape", "must be a non-empty string")
            if not _finite_number(output.get("scale")):
                _error(errors, f"{output_path}.scale", "must be a finite number")
            if output.get("mode") not in EXPRESSION_MODES:
                _error(errors, f"{output_path}.mode", "is not a supported expression mode")

    chains = data.get("springChains")
    if not isinstance(chains, list):
        _error(errors, "$.springChains", "must be an array")
        chains = []
    chain_ids: set[str] = set()
    for index, chain in enumerate(chains):
        path = f"$.springChains[{index}]"
        if not isinstance(chain, dict):
            _error(errors, path, "must be an object")
            continue
        chain_id = chain.get("id")
        if not isinstance(chain_id, str) or not chain_id:
            _error(errors, f"{path}.id", "must be a non-empty string")
        elif chain_id in chain_ids:
            _error(errors, f"{path}.id", "duplicates another chain")
        else:
            chain_ids.add(chain_id)
        nodes = chain.get("nodes")
        if not isinstance(nodes, list) or len(nodes) < 2 or any(not _local_path(node) for node in nodes):
            _error(errors, f"{path}.nodes", "must contain at least two relative paths")
        for parameter in ("stiffness", "damping", "gravity"):
            if not _finite_number(chain.get(parameter)):
                _error(errors, f"{path}.{parameter}", "must be a finite number")

    root_motion = data.get("rootMotion")
    if not isinstance(root_motion, dict):
        _error(errors, "$.rootMotion", "must be an object")
    else:
        if root_motion.get("mode") not in {"actorAnchored", "matchGameHeight"}:
            _error(errors, "$.rootMotion.mode", "is not supported")
        if not _finite_number(root_motion.get("groundOffset")):
            _error(errors, "$.rootMotion.groundOffset", "must be a finite number")
        if root_motion.get("scaleMode") not in {"author", "matchGame"}:
            _error(errors, "$.rootMotion.scaleMode", "is not supported")

    materials = data.get("materials")
    if not isinstance(materials, dict) or materials.get("mode") not in {"standard", "custom", "hybrid"}:
        _error(errors, "$.materials.mode", "must be standard, custom or hybrid")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor", type=Path)
    args = parser.parse_args()
    with args.descriptor.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    errors = validate_descriptor(data)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"OK {args.descriptor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
