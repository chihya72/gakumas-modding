param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [Parameter(Mandatory=$true)][string]$MeshJson,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$UnityVersion = "6000.0.67f1"
)

$ErrorActionPreference = 'Stop'
$env:GMI_BUNDLE = (Resolve-Path $Bundle).Path
$env:GMI_MESH_JSON = (Resolve-Path $MeshJson).Path
$env:GMI_SKELETON_OUT = [IO.Path]::GetFullPath($Output)
$env:GMI_UNITY_VERSION = $UnityVersion

@'
import json
import os
from pathlib import Path

import UnityPy


def vec3(value):
    return [value.X, value.Y, value.Z]


def quat(value):
    return [value.X, value.Y, value.Z, value.W]


UnityPy.config.FALLBACK_UNITY_VERSION = os.environ["GMI_UNITY_VERSION"]
env = UnityPy.load(os.environ["GMI_BUNDLE"])
renderer_object = next(obj for obj in env.objects if obj.type.name == "SkinnedMeshRenderer")
renderer = renderer_object.read()
mesh = json.loads(Path(os.environ["GMI_MESH_JSON"]).read_text(encoding="utf-8"))

weighted = [ptr.read() for ptr in renderer.m_Bones]
weighted_by_path = {bone.path_id: index for index, bone in enumerate(weighted)}
needed = {}
for bone in weighted:
    current = bone
    while current and current.path_id not in needed:
        needed[current.path_id] = current
        father = current.m_Father
        current = father.read() if father and father.path_id else None

def depth(transform):
    result = 0
    father = transform.m_Father
    while father and father.path_id and father.path_id in needed:
        result += 1
        transform = father.read()
        father = transform.m_Father
    return result

ordered = sorted(needed.values(), key=lambda item: (depth(item), item.path_id))
node_index = {node.path_id: index for index, node in enumerate(ordered)}
nodes = []
for node in ordered:
    father_id = node.m_Father.path_id if node.m_Father else 0
    weighted_index = weighted_by_path.get(node.path_id)
    entry = {
        "name": node.m_GameObject.read().m_Name,
        "pathId": node.path_id,
        "parent": node_index.get(father_id, -1),
        "weightedIndex": weighted_index,
        "localPosition": vec3(node.m_LocalPosition),
        "localRotation": quat(node.m_LocalRotation),
        "localScale": vec3(node.m_LocalScale),
    }
    if weighted_index is not None:
        entry["boneNameHash"] = mesh["m_BoneNameHashes"][weighted_index]
        entry["bindPose"] = mesh["m_BindPose"][weighted_index]
    nodes.append(entry)

out = {
    "schemaVersion": 1,
    "unityVersion": os.environ["GMI_UNITY_VERSION"],
    "rendererPathId": renderer_object.path_id,
    "rootBonePathId": renderer.m_RootBone.path_id,
    "weightedBoneCount": len(weighted),
    "nodeCount": len(nodes),
    "nodes": nodes,
}
target = Path(os.environ["GMI_SKELETON_OUT"])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Exported {len(nodes)} nodes / {len(weighted)} weighted bones to {target}")
'@ | python -

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
