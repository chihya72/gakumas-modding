"""Blender-side FBX skin exporter used by offline compatibility checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
import numpy as np


source = Path(sys.argv[sys.argv.index("--") + 1])
output = Path(sys.argv[sys.argv.index("--") + 2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source))

mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if len(mesh_objects) != 1:
    raise RuntimeError(f"Expected one mesh, found {len(mesh_objects)}")
obj = mesh_objects[0]
mesh = obj.data
armature = next(
    (modifier.object for modifier in obj.modifiers if modifier.type == "ARMATURE"), None
)
if armature is None:
    raise RuntimeError("Mesh has no Armature modifier")

group_names = [group.name for group in obj.vertex_groups]
influences = []
max_influences = 0
for vertex in mesh.vertices:
    row = sorted(
        ((group_names[item.group], float(item.weight)) for item in vertex.groups),
        key=lambda item: item[1], reverse=True,
    )
    influences.append(row)
    max_influences = max(max_influences, len(row))

positions = np.asarray([tuple(vertex.co) for vertex in mesh.vertices], dtype=np.float32)
normals = np.asarray([tuple(vertex.normal) for vertex in mesh.vertices], dtype=np.float32)
output.mkdir(parents=True, exist_ok=True)
np.save(output / "positions.npy", positions)
np.save(output / "normals.npy", normals)
(output / "skin.json").write_text(
    json.dumps(
        {
            "source": str(source),
            "mesh": obj.name,
            "armature": armature.name,
            "vertexCount": len(mesh.vertices),
            "polygonCount": len(mesh.polygons),
            "objectMatrixWorld": [list(row) for row in obj.matrix_world],
            "armatureMatrixWorld": [list(row) for row in armature.matrix_world],
            "boneNames": [bone.name for bone in armature.data.bones],
            "vertexGroupNames": group_names,
            "maxInfluences": max_influences,
            "influences": influences,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
print(f"GMI_FBX_SKIN={output}")
