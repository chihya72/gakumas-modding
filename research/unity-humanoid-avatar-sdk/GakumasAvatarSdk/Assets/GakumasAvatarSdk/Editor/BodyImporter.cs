// Rebuild a body prefab from the JSON an AssetStudio export produces.
//
// Going through JSON rather than FBX is deliberate: FBX drops vertex COLOR (which this game's
// shader reads as data, not tint) and round-trips bind poses through a different convention.
// The exported mesh JSON carries positions, normals, tangents, COLOR, UV0, skin weights and
// bind poses exactly as the source game had them.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class BodyImporter
    {
        [Serializable] private class SubMeshJson { public int indexCount; public int firstVertex; public int vertexCount; public string topology; }
        [Serializable] private class SkinJson { public float[] weight; public int[] boneIndex; }
        [Serializable] private class MatrixJson
        {
            public float M00, M01, M02, M03;
            public float M10, M11, M12, M13;
            public float M20, M21, M22, M23;
            public float M30, M31, M32, M33;

            // AssetStudio names these transposed relative to Unity: its M31 is Unity's m13. Feeding
            // (M00,M10,M20,M30) as column 0 puts the translation in the bottom row instead of column
            // 3, which leaves every bind pose non-affine — the skinned mesh lands nowhere and the
            // body renders as nothing at all. Verified against the source bundle: IP's own bind pose
            // holds the translation in m03/m13/m23.
            public Matrix4x4 ToMatrix() => new Matrix4x4(
                new Vector4(M00, M01, M02, M03),
                new Vector4(M10, M11, M12, M13),
                new Vector4(M20, M21, M22, M23),
                new Vector4(M30, M31, M32, M33));
        }

        [Serializable] private class MeshJson
        {
            public string m_Name;
            public int m_VertexCount;
            public float[] m_Vertices, m_Normals, m_Tangents, m_Colors, m_UV0;
            public int[] m_Indices;
            public List<SubMeshJson> m_SubMeshes;
            public List<SkinJson> m_Skin;
            public List<MatrixJson> m_BindPose;
        }

        [Serializable] private class Vector3Json { public float x, y, z; }
        [Serializable] private class Vector4Json { public float x, y, z, w; }
        [Serializable] private class NodeJson
        {
            public string name;
            public long pathId;
            public int parent = -1;
            public int weightedIndex = -1;
            public float[] localPosition, localRotation, localScale;
        }
        [Serializable] private class SkeletonJson
        {
            public int nodeCount;
            public int weightedBoneCount;
            public List<NodeJson> nodes;
        }

        /// <summary>Rebuilds the skeleton, mesh and renderer, and returns the prefab root.</summary>
        /// <param name="assetDirectory">Where the Mesh and Materials are saved. They must be real
        /// assets: a prefab drops references to objects that only live in memory, which is how a
        /// full body ends up as a 12 KB bundle with nothing but transforms in it.</param>
        public static GameObject Import(string meshJsonPath, string skeletonJsonPath, string texturesDirectory,
            string assetDirectory)
        {
            var mesh = JsonUtility.FromJson<MeshJson>(File.ReadAllText(meshJsonPath));
            // Unweighted nodes carry `"weightedIndex": null`, and JsonUtility turns a null int into
            // 0 — which would make every one of them claim skin bone 0.
            var skeletonText = File.ReadAllText(skeletonJsonPath).Replace("\"weightedIndex\": null", "\"weightedIndex\": -1");
            var skeleton = JsonUtility.FromJson<SkeletonJson>(skeletonText);

            var transforms = BuildSkeleton(skeleton, out var root);
            var labels = GakumasBodyLabels.LoadOrCreate(
                $"{assetDirectory}/{mesh.m_Name}.labels.asset", mesh.m_SubMeshes.Count, GroupFor);
            // Textures first: the skin mask they produce also decides each vertex's COLOR.
            var rewrites = new TextureRewriter.Rewrite[mesh.m_SubMeshes.Count];
            for (var slot = 0; slot < rewrites.Length; slot++)
                rewrites[slot] = TextureRewriter.Build(texturesDirectory, GroupFor(slot), labels.submeshes[slot]);

            var built = BuildMesh(mesh, rewrites, labels);
            AssetDatabase.CreateAsset(built, $"{assetDirectory}/{built.name}.asset");
            var renderer = AttachRenderer(root, transforms, skeleton, mesh, built, rewrites, assetDirectory, texturesDirectory);
            AssetDatabase.SaveAssets();
            Debug.Log($"[SDK] 导入 {root.name}: 骨 {transforms.Length}，顶点 {built.vertexCount}，" +
                      $"子网格 {built.subMeshCount}，蒙皮骨 {renderer.bones.Length}");
            return root;
        }

        // Each vertex takes the preset for the surface it belongs to: the author's label for its
        // submesh, overridden per vertex by the skin mask where that submesh mixes in bare skin.
        // Which submesh a vertex is in also decides *which* sheet's mask to ask, since every sheet has
        // its own UV space.
        private static List<Color> BuildColors(MeshJson source, TextureRewriter.Rewrite[] rewrites,
            GakumasBodyLabels labels, List<Vector2> uvs, int count)
        {
            var skinColor = SurfacePresets.Of(SurfaceClass.Skin).Color;
            var colors = new List<Color>(count);
            for (var index = 0; index < count; index++)
                colors.Add(Color.white);

            var skin = 0;
            var report = new List<string>();
            for (var slot = 0; slot < source.m_SubMeshes.Count; slot++)
            {
                var label = labels.For(slot);
                var surface = label?.surface ?? SurfaceClass.Cloth;
                var color = SurfacePresets.Of(surface).Color;
                var rewrite = slot < rewrites.Length ? rewrites[slot] : null;
                var subMesh = source.m_SubMeshes[slot];
                var last = Mathf.Min(subMesh.firstVertex + subMesh.vertexCount, count);
                var slotSkin = 0;
                for (var index = subMesh.firstVertex; index < last; index++)
                {
                    var bare = uvs != null && rewrite?.Mask != null && rewrite.IsSkinAt(uvs[index]);
                    colors[index] = bare ? (Color)skinColor : color;
                    if (bare)
                        slotSkin++;
                }
                skin += slotSkin;
                report.Add($"{label?.material ?? $"submesh{slot}"}={surface}" +
                           (slotSkin > 0 ? $"(皮肤 {slotSkin})" : ""));
            }

            Debug.Log($"[SDK] 顶点 COLOR 按学马语义写入 {count} 个：{string.Join(", ", report)}；" +
                      $"皮肤共 {skin} 个 [{GakumasVertexColor.Describe(skinColor)}]");
            return colors;
        }

        private static Transform[] BuildSkeleton(SkeletonJson skeleton, out GameObject root)
        {
            var transforms = new Transform[skeleton.nodes.Count];
            for (var index = 0; index < skeleton.nodes.Count; index++)
                transforms[index] = new GameObject(skeleton.nodes[index].name).transform;

            for (var index = 0; index < skeleton.nodes.Count; index++)
            {
                var node = skeleton.nodes[index];
                if (node.parent >= 0)
                    transforms[index].SetParent(transforms[node.parent], false);
                transforms[index].localPosition = new Vector3(node.localPosition[0], node.localPosition[1], node.localPosition[2]);
                transforms[index].localRotation = new Quaternion(node.localRotation[0], node.localRotation[1], node.localRotation[2], node.localRotation[3]);
                transforms[index].localScale = new Vector3(node.localScale[0], node.localScale[1], node.localScale[2]);
            }

            root = transforms[0].gameObject;
            return transforms;
        }

        // Sheet per submesh slot: the main body sheet, then the two accessory ones. Extra slots reuse
        // the last sheet, which is what the runtime's material matching already assumes.
        private static readonly string[] Groups = { "bdy", "bdyco", "bdytrs" };

        private static string GroupFor(int slot) => Groups[Mathf.Min(slot, Groups.Length - 1)];

        private static Mesh BuildMesh(MeshJson source, TextureRewriter.Rewrite[] rewrites,
            GakumasBodyLabels labels)
        {
            var mesh = new Mesh { name = source.m_Name, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
            var count = source.m_VertexCount;

            mesh.SetVertices(ToVectors(source.m_Vertices, count));
            if (source.m_Normals != null && source.m_Normals.Length > 0)
                mesh.SetNormals(ToVectors(source.m_Normals, count));
            if (source.m_Tangents != null && source.m_Tangents.Length > 0)
                mesh.SetTangents(ToTangents(source.m_Tangents, count));
            var uvs = source.m_UV0 != null && source.m_UV0.Length > 0 ? ToUVs(source.m_UV0, count) : null;
            if (uvs != null)
                mesh.SetUVs(0, uvs);
            // The source mesh's own COLOR is discarded on purpose — see GakumasVertexColor.
            mesh.SetColors(BuildColors(source, rewrites, labels, uvs, count));

            var bindPoses = new Matrix4x4[source.m_BindPose.Count];
            for (var index = 0; index < bindPoses.Length; index++)
                bindPoses[index] = source.m_BindPose[index].ToMatrix();

            var weights = new BoneWeight[count];
            for (var index = 0; index < count; index++)
            {
                var skin = source.m_Skin[index];
                weights[index] = new BoneWeight
                {
                    boneIndex0 = skin.boneIndex[0], weight0 = skin.weight[0],
                    boneIndex1 = skin.boneIndex[1], weight1 = skin.weight[1],
                    boneIndex2 = skin.boneIndex[2], weight2 = skin.weight[2],
                    boneIndex3 = skin.boneIndex[3], weight3 = skin.weight[3],
                };
            }
            mesh.boneWeights = weights;
            mesh.bindposes = bindPoses;

            mesh.subMeshCount = source.m_SubMeshes.Count;
            var offset = 0;
            for (var index = 0; index < source.m_SubMeshes.Count; index++)
            {
                var subMesh = source.m_SubMeshes[index];
                var triangles = new int[subMesh.indexCount];
                Array.Copy(source.m_Indices, offset, triangles, 0, subMesh.indexCount);
                mesh.SetTriangles(triangles, index, false);
                offset += subMesh.indexCount;
            }
            mesh.RecalculateBounds();
            return mesh;
        }

        private static SkinnedMeshRenderer AttachRenderer(GameObject root, Transform[] transforms,
            SkeletonJson skeleton, MeshJson source, Mesh mesh, TextureRewriter.Rewrite[] rewrites,
            string assetDirectory, string texturesDirectory)
        {
            var holder = new GameObject(source.m_Name);
            holder.transform.SetParent(root.transform, false);
            var renderer = holder.AddComponent<SkinnedMeshRenderer>();

            // Skin bones are addressed by index into the bind pose list; the skeleton export marks
            // which node each index belongs to.
            var bones = new Transform[source.m_BindPose.Count];
            for (var index = 0; index < skeleton.nodes.Count; index++)
            {
                var weighted = skeleton.nodes[index].weightedIndex;
                if (weighted >= 0 && weighted < bones.Length)
                    bones[weighted] = transforms[index];
            }
            renderer.bones = bones;
            renderer.rootBone = FindByName(transforms, "Hips") ?? transforms[0];
            renderer.sharedMesh = mesh;
            renderer.sharedMaterials = LoadMaterials(rewrites, texturesDirectory, assetDirectory);
            CheckBindPoses(bones, mesh.bindposes);
            return renderer;
        }

        // A wrong bind pose is invisible in the inspector and fatal on screen. inverse(bindpose) is
        // the bone's bind-time model matrix, so its translation has to land on the bone itself; the
        // import is still at the origin here, so world space is model space.
        //
        // Judge by spread, not by distance: a transposed matrix throws every bone off by more than a
        // metre (measured: 90/90 at ~1.30 m), while a handful of centimetre-scale misses is normal —
        // chs-sucu-00 has its thumbs posed after binding, and IP's own prefab carries the same 28.7 mm.
        private static void CheckBindPoses(Transform[] bones, Matrix4x4[] bindPoses)
        {
            var worst = 0f;
            var worstBone = "";
            var off = 0;
            var checked_ = 0;
            for (var index = 0; index < bindPoses.Length; index++)
            {
                if (index >= bones.Length || bones[index] == null)
                    continue;
                checked_++;
                var distance = Vector3.Distance(bindPoses[index].inverse.GetColumn(3), bones[index].position);
                if (distance > 0.001f)
                    off++;
                if (distance > worst)
                {
                    worst = distance;
                    worstBone = bones[index].name;
                }
            }
            var report = $"{off}/{checked_} 根骨偏 >1mm，最差 {worstBone} {worst * 1000f:F1}mm";
            if (off > checked_ / 4 || worst > 0.2f)
                Debug.LogError($"[SDK] bind pose 与骨架不符：{report}（矩阵转置或骨序错位）");
            else if (off > 0)
                Debug.LogWarning($"[SDK] bind pose 有个别不符：{report}（源模型绑定后摆过姿势，通常无害）");
            else
                Debug.Log($"[SDK] bind pose 校验通过（{checked_} 根骨全对）");
        }

        private const string PlaceholderShader = "GakumasSdk/BodyPlaceholder";

        // Placeholder materials: the runtime clones the game's own material (for its shader and
        // shared ramps) and moves these textures onto it, so only the texture bindings matter.
        private static Material[] LoadMaterials(TextureRewriter.Rewrite[] rewrites, string texturesDirectory,
            string assetDirectory)
        {
            // Our own shader, not URP/Lit or Standard: it is the only one that declares the three
            // property names the runtime reads back. See BodyPlaceholder.shader.
            var shader = Shader.Find(PlaceholderShader);
            if (shader == null)
                throw new InvalidOperationException($"[SDK] 找不到 {PlaceholderShader}，贴图会全部丢失");
            var materials = new Material[rewrites.Length];
            for (var slot = 0; slot < rewrites.Length; slot++)
            {
                var group = GroupFor(slot);
                var material = new Material(shader) { name = $"m_{group}" };
                Bind(material, "_BaseMap", texturesDirectory, group, "col");
                if (rewrites[slot].ShadePath != null)
                    BindPath(material, "_ShadeMap", rewrites[slot].ShadePath);
                else
                    Bind(material, "_ShadeMap", texturesDirectory, group, "sdw");
                if (rewrites[slot].DefPath != null)
                    BindPath(material, "_DefMap", rewrites[slot].DefPath);
                else
                    Bind(material, "_DefMap", texturesDirectory, group, "def");
                AssetDatabase.CreateAsset(material, $"{assetDirectory}/{material.name}.mat");
                materials[slot] = material;
            }
            return materials;
        }

        // `directory` is already a project-relative path such as Assets/Mods/Textures — AssetDatabase
        // refuses anything outside the project, so the caller stages the files first.
        private static void Bind(Material material, string property, string directory, string group, string kind)
        {
            foreach (var candidate in Directory.GetFiles(directory, $"*_{group}_{kind}*.png"))
            {
                var path = candidate.Replace('\\', '/');
                if (path.Contains(".gakumas."))
                    continue;
                // t1 (def) is data, not colour: decoding it as sRGB dims the whole body.
                TextureRewriter.ConfigureImport(path, srgb: kind != "def");
                var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                if (texture == null)
                    continue;
                material.SetTexture(property, texture);
                // Assigning to a property the shader does not declare is a no-op Unity only warns
                // about, and an unreferenced texture never reaches the bundle. Read it back.
                if (material.GetTexture(property) == null)
                    Debug.LogError($"[SDK] {material.name} 的 {property} 没写进去（shader 未声明该属性），贴图不会进包");
                return;
            }
            Debug.LogWarning($"[SDK] 没找到贴图 *_{group}_{kind}*.png（{property} 留空）");
        }

        private static void BindPath(Material material, string property, string assetPath)
        {
            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
            if (texture == null)
            {
                Debug.LogError($"[SDK] 读不到生成的贴图 {assetPath}（{property} 留空）");
                return;
            }
            material.SetTexture(property, texture);
            if (material.GetTexture(property) == null)
                Debug.LogError($"[SDK] {material.name} 的 {property} 没写进去，贴图不会进包");
        }

        private static Transform FindByName(Transform[] transforms, string name)
        {
            foreach (var transform in transforms)
                if (transform.name == name)
                    return transform;
            return null;
        }

        private static List<Vector3> ToVectors(float[] flat, int count)
        {
            var list = new List<Vector3>(count);
            for (var index = 0; index < count; index++)
                list.Add(new Vector3(flat[index * 3], flat[index * 3 + 1], flat[index * 3 + 2]));
            return list;
        }

        private static List<Vector4> ToTangents(float[] flat, int count)
        {
            var list = new List<Vector4>(count);
            for (var index = 0; index < count; index++)
                list.Add(new Vector4(flat[index * 4], flat[index * 4 + 1], flat[index * 4 + 2], flat[index * 4 + 3]));
            return list;
        }

        private static List<Vector2> ToUVs(float[] flat, int count)
        {
            var list = new List<Vector2>(count);
            for (var index = 0; index < count; index++)
                list.Add(new Vector2(flat[index * 2], flat[index * 2 + 1]));
            return list;
        }
    }
}
