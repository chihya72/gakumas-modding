import json
import sys
from pathlib import Path

import bpy


source = Path(sys.argv[sys.argv.index("--") + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source))

result = {"source": str(source), "objects": []}
for obj in bpy.context.scene.objects:
    entry = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "parent": obj.parent.name if obj.parent else None,
    }
    if obj.type == "MESH":
        mesh = obj.data
        triangles = sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons)
        local_min = [min(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
        local_max = [max(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
        world_points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
        world_min = [min(point[axis] for point in world_points) for axis in range(3)]
        world_max = [max(point[axis] for point in world_points) for axis in range(3)]
        entry.update({
            "vertices": len(mesh.vertices),
            "polygons": len(mesh.polygons),
            "triangles": triangles,
            "loops": len(mesh.loops),
            "materials": [material.name if material else None for material in mesh.materials],
            "uv_layers": [layer.name for layer in mesh.uv_layers],
            "color_attributes": [attribute.name for attribute in mesh.color_attributes],
            "vertex_groups": len(obj.vertex_groups),
            "modifiers": [modifier.type for modifier in obj.modifiers],
            "local_bounds": {"min": local_min, "max": local_max},
            "world_bounds": {"min": world_min, "max": world_max},
        })
    elif obj.type == "ARMATURE":
        entry["bones"] = len(obj.data.bones)
        entry["bone_names"] = [bone.name for bone in obj.data.bones]
    result["objects"].append(entry)

print("GMI_FBX_INSPECT=" + json.dumps(result, ensure_ascii=False))
