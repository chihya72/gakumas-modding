using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class ClaymoreSourceRestExperiment
    {
        private const string ModelAsset =
            "Assets/ExperimentClaymore/Input/Avatar_Girl_Claymore_MarionetteNew.fbx";

        [Serializable]
        private sealed class BoneRecord
        {
            public string name;
            public int parentIndex;
            public string anchorName;
            public float[] anchorSourceRestWorld;
            public float[] sourceRestWorld;
            public float[] bindpose;
        }

        [Serializable]
        private sealed class MeshDump
        {
            public string rendererName;
            public string meshName;
            public int vertexCount;
            public int boneCount;
            public BoneRecord[] bones;
            public float[] vertices;
            public float[] normals;
            public float[] uv;
            public int[] triangles;
            public int[] triangleSubmeshes;
            public string[] materialNames;
            public int[] boneIndices;
            public float[] boneWeights;
        }

        [Serializable]
        private sealed class ExperimentReport
        {
            public string modelAsset;
            public bool humanoid;
            public int mappedBones;
            public int movedBones;
            public int alignedDrivenFrames;
            public bool alignedHeadFrame;
            public float leftArmBefore;
            public float leftArmAfter;
            public float rightArmBefore;
            public float rightArmAfter;
            public int rendererCount;
            public string bodyRenderer;
            public int bodyVertices;
            public int bodyBones;
        }

        public static void Run()
        {
            try
            {
                var output = GetArgument("-claymoreOutput");
                if (string.IsNullOrWhiteSpace(output))
                    throw new ArgumentException("missing -claymoreOutput");
                Directory.CreateDirectory(output);

                ConfigureHumanoidImporter();
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(ModelAsset);
                if (prefab == null)
                    throw new InvalidOperationException($"cannot load {ModelAsset}");
                var instance = UnityEngine.Object.Instantiate(prefab);
                instance.name = "ClaymoreSourceRestExperiment";
                try
                {
                    var animator = instance.GetComponent<Animator>() ?? instance.GetComponentInChildren<Animator>();
                    if (animator == null || animator.avatar == null || !animator.avatar.isHuman)
                        throw new InvalidOperationException("Unity did not produce a valid Humanoid Avatar");

                    var mapped = HumanoidBridge.Apply(instance);
                    if (mapped < 0)
                        throw new InvalidOperationException("HumanoidBridge failed");

                    var renderers = instance.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                    foreach (var renderer in renderers)
                    {
                        if (renderer.sharedMesh == null)
                            continue;
                        var clone = UnityEngine.Object.Instantiate(renderer.sharedMesh);
                        clone.name = renderer.sharedMesh.name + "_TPoseExperiment";
                        renderer.sharedMesh = clone;
                    }

                    var leftBefore = LimbAngle(instance, "LeftArm", "LeftForeArm", Vector3.left);
                    var rightBefore = LimbAngle(instance, "RightArm", "RightForeArm", Vector3.right);
                    var moved = TPoseBaker.Bake(instance);
                    if (moved < 0)
                        throw new InvalidOperationException("TPoseBaker failed");
                    var leftAfter = LimbAngle(instance, "LeftArm", "LeftForeArm", Vector3.left);
                    var rightAfter = LimbAngle(instance, "RightArm", "RightForeArm", Vector3.right);
                    var alignedDrivenFrames = TPoseBaker.AlignDrivenBoneAxes(instance);
                    if (alignedDrivenFrames < 0)
                        throw new InvalidOperationException("driven-bone frame alignment failed");
                    var alignedHeadFrame = TPoseBaker.AlignHeadAxes(instance);

                    var body = renderers.FirstOrDefault(renderer => renderer.name == "Body")
                               ?? renderers.OrderByDescending(renderer =>
                                   renderer.sharedMesh != null ? renderer.sharedMesh.vertexCount : 0).First();
                    var dump = BuildDump(body);
                    File.WriteAllText(Path.Combine(output, "unity-tpose-frames-body-dump.json"),
                        JsonUtility.ToJson(dump, true), new UTF8Encoding(false));
                    WriteObj(body.sharedMesh, Path.Combine(output, "unity-tpose-frames-body.obj"));

                    var report = new ExperimentReport
                    {
                        modelAsset = ModelAsset,
                        humanoid = true,
                        mappedBones = mapped,
                        movedBones = moved,
                        alignedDrivenFrames = alignedDrivenFrames,
                        alignedHeadFrame = alignedHeadFrame,
                        leftArmBefore = leftBefore,
                        leftArmAfter = leftAfter,
                        rightArmBefore = rightBefore,
                        rightArmAfter = rightAfter,
                        rendererCount = renderers.Length,
                        bodyRenderer = body.name,
                        bodyVertices = body.sharedMesh.vertexCount,
                        bodyBones = body.bones.Length,
                    };
                    File.WriteAllText(Path.Combine(output, "unity-tpose-frames-report.json"),
                        JsonUtility.ToJson(report, true), new UTF8Encoding(false));

                    Debug.Log($"[ClaymoreExperiment] mapped={mapped}, moved={moved}, "
                              + $"frames={alignedDrivenFrames}, head={alignedHeadFrame}, "
                              + $"arms={leftBefore:F1}/{rightBefore:F1} -> {leftAfter:F1}/{rightAfter:F1}, "
                              + $"body={body.sharedMesh.vertexCount} verts/{body.bones.Length} bones");
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(instance);
                }
                EditorApplication.Exit(0);
            }
            catch (Exception exception)
            {
                Debug.LogException(exception);
                EditorApplication.Exit(1);
            }
        }

        private static void ConfigureHumanoidImporter()
        {
            AssetDatabase.ImportAsset(ModelAsset, ImportAssetOptions.ForceSynchronousImport);
            var importer = AssetImporter.GetAtPath(ModelAsset) as ModelImporter;
            if (importer == null)
                throw new InvalidOperationException("FBX has no ModelImporter");
            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.importAnimation = false;
            importer.SaveAndReimport();
        }

        private static float LimbAngle(GameObject root, string boneName, string childName, Vector3 aim)
        {
            var bones = root.GetComponentsInChildren<Transform>(true)
                .GroupBy(transform => transform.name)
                .ToDictionary(group => group.Key, group => group.First());
            if (!bones.TryGetValue(boneName, out var bone) || !bones.TryGetValue(childName, out var child))
                return -1f;
            var direction = child.position - bone.position;
            return direction.sqrMagnitude < 1e-12f
                ? -1f
                : Vector3.Angle(direction, root.transform.TransformDirection(aim));
        }

        private static MeshDump BuildDump(SkinnedMeshRenderer renderer)
        {
            var mesh = renderer.sharedMesh;
            var bones = renderer.bones;
            var boneIndex = new Dictionary<Transform, int>();
            for (var index = 0; index < bones.Length; index++)
                if (bones[index] != null && !boneIndex.ContainsKey(bones[index]))
                    boneIndex.Add(bones[index], index);

            var records = new BoneRecord[bones.Length];
            for (var index = 0; index < bones.Length; index++)
            {
                var bone = bones[index];
                var parent = bone != null ? bone.parent : null;
                while (parent != null && !boneIndex.ContainsKey(parent))
                    parent = parent.parent;
                var anchor = bone;
                while (anchor != null && !HumanoidBridge.BodyBones.Contains(anchor.name))
                    anchor = anchor.parent;
                if (anchor == null)
                    anchor = renderer.rootBone;
                records[index] = new BoneRecord
                {
                    name = bone != null ? bone.name : $"<null:{index}>",
                    parentIndex = parent != null ? boneIndex[parent] : -1,
                    anchorName = anchor != null ? anchor.name : "Hips",
                    anchorSourceRestWorld = Matrix(renderer.transform.worldToLocalMatrix
                                                   * (anchor != null ? anchor.localToWorldMatrix
                                                     : renderer.transform.localToWorldMatrix)),
                    sourceRestWorld = Matrix(renderer.transform.worldToLocalMatrix
                                             * (bone != null ? bone.localToWorldMatrix : renderer.transform.localToWorldMatrix)),
                    bindpose = Matrix(mesh.bindposes[index]),
                };
            }

            var vertices = mesh.vertices;
            var normals = mesh.normals;
            var uv = mesh.uv;
            var weights = mesh.boneWeights;
            var packedIndices = new int[weights.Length * 4];
            var packedWeights = new float[weights.Length * 4];
            for (var vertex = 0; vertex < weights.Length; vertex++)
            {
                var weight = weights[vertex];
                var offset = vertex * 4;
                packedIndices[offset] = weight.boneIndex0;
                packedIndices[offset + 1] = weight.boneIndex1;
                packedIndices[offset + 2] = weight.boneIndex2;
                packedIndices[offset + 3] = weight.boneIndex3;
                packedWeights[offset] = weight.weight0;
                packedWeights[offset + 1] = weight.weight1;
                packedWeights[offset + 2] = weight.weight2;
                packedWeights[offset + 3] = weight.weight3;
            }

            var triangles = new List<int>();
            var triangleSubmeshes = new List<int>();
            for (var submesh = 0; submesh < mesh.subMeshCount; submesh++)
            {
                var values = mesh.GetTriangles(submesh);
                triangles.AddRange(values);
                for (var index = 0; index + 2 < values.Length; index += 3)
                    triangleSubmeshes.Add(submesh);
            }

            return new MeshDump
            {
                rendererName = renderer.name,
                meshName = mesh.name,
                vertexCount = vertices.Length,
                boneCount = bones.Length,
                bones = records,
                vertices = Flatten(vertices),
                normals = Flatten(normals),
                uv = Flatten(uv),
                triangles = triangles.ToArray(),
                triangleSubmeshes = triangleSubmeshes.ToArray(),
                materialNames = renderer.sharedMaterials
                    .Select(material => material != null ? material.name : "<null>").ToArray(),
                boneIndices = packedIndices,
                boneWeights = packedWeights,
            };
        }

        private static float[] Matrix(Matrix4x4 value)
        {
            var result = new float[16];
            for (var row = 0; row < 4; row++)
                for (var column = 0; column < 4; column++)
                    result[row * 4 + column] = value[row, column];
            return result;
        }

        private static float[] Flatten(Vector3[] values)
        {
            var result = new float[values.Length * 3];
            for (var index = 0; index < values.Length; index++)
            {
                result[index * 3] = values[index].x;
                result[index * 3 + 1] = values[index].y;
                result[index * 3 + 2] = values[index].z;
            }
            return result;
        }

        private static float[] Flatten(Vector2[] values)
        {
            var result = new float[values.Length * 2];
            for (var index = 0; index < values.Length; index++)
            {
                result[index * 2] = values[index].x;
                result[index * 2 + 1] = values[index].y;
            }
            return result;
        }

        private static void WriteObj(Mesh mesh, string path)
        {
            var culture = CultureInfo.InvariantCulture;
            using var writer = new StreamWriter(path, false, new UTF8Encoding(false));
            foreach (var vertex in mesh.vertices)
                writer.WriteLine(string.Format(culture, "v {0:R} {1:R} {2:R}", vertex.x, vertex.y, vertex.z));
            foreach (var value in mesh.uv)
                writer.WriteLine(string.Format(culture, "vt {0:R} {1:R}", value.x, value.y));
            foreach (var normal in mesh.normals)
                writer.WriteLine(string.Format(culture, "vn {0:R} {1:R} {2:R}", normal.x, normal.y, normal.z));
            var triangles = mesh.triangles;
            for (var index = 0; index + 2 < triangles.Length; index += 3)
            {
                var a = triangles[index] + 1;
                var b = triangles[index + 1] + 1;
                var c = triangles[index + 2] + 1;
                writer.WriteLine($"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}");
            }
        }

        private static string GetArgument(string name)
        {
            var arguments = Environment.GetCommandLineArgs();
            for (var index = 0; index + 1 < arguments.Length; index++)
                if (string.Equals(arguments[index], name, StringComparison.OrdinalIgnoreCase))
                    return arguments[index + 1];
            return null;
        }
    }
}
