// rui-nurs-00 -> hmsz-cstm-0000 body,AB 路线。
// 不走 FBX:直接从处理好的 Geo_Body JSON 建 Mesh(colors32 精确保留 packed 描边字节),
// 建命名骨层级(骨 TRS 无所谓,运行时按名 remap 到 hmsz 活体骨;root 名必须=Hips)。
// 菜单:Gakumas Mod/RuiNurs0000/Build DMM Bundle
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class BuildGakumasModBundleRuiNurs0000
{
    private const string BundleName = "hmsz_0000_ruinurs.bundle";
    private const string OutputPath = "AssetBundles/Windows";
    private const string ModRoot = "Assets/Mods/hmsz_0000";
    private const string GeoJson = ModRoot + "/mdl_chr_hmsz-cstm-0000_body.geojson.txt";
    private const string BonesJson = ModRoot + "/rui_bones.json.txt";
    private const string MeshAsset = ModRoot + "/mdl_chr_hmsz-cstm-0000_body_mesh.asset";
    private const string PrefabPath = ModRoot + "/mdl_chr_hmsz-cstm-0000_body.prefab";
    private const string RootBoneName = "Hips"; // hmsz-0000 与 rui 的 SMR rootBone 同为 Hips

    // ---- JSON 映射(字段名须与 Geo_Body JSON 一致)----
    [Serializable] private class Skin { public float[] weight; public int[] boneIndex; }
    [Serializable] private class BindPose {
        public float M00, M01, M02, M03, M10, M11, M12, M13, M20, M21, M22, M23, M30, M31, M32, M33;
        public Matrix4x4 ToMatrix() {
            // AssetStudio 的 M<r><c> 是转置存的(平移落在 M30/M31/M32 底行),
            // Unity Matrix4x4 列主序要求平移在 m03/m13/m23 → Unity m[r][c] = JSON M[c][r]。
            var m = new Matrix4x4();
            m.m00 = M00; m.m01 = M10; m.m02 = M20; m.m03 = M30;
            m.m10 = M01; m.m11 = M11; m.m12 = M21; m.m13 = M31;
            m.m20 = M02; m.m21 = M12; m.m22 = M22; m.m23 = M32;
            m.m30 = M03; m.m31 = M13; m.m32 = M23; m.m33 = M33;
            return m;
        }
    }
    [Serializable] private class SubMesh { public int indexCount; public int firstVertex; public int vertexCount; public int firstByte; public int baseVertex; }
    [Serializable] private class Geo {
        public int m_VertexCount;
        public float[] m_Vertices, m_Normals, m_Tangents, m_UV0, m_Colors;
        public int[] m_Indices;
        public Skin[] m_Skin;
        public BindPose[] m_BindPose;
        public SubMesh[] m_SubMeshes;
    }
    [Serializable] private class BoneEntry { public int index; public string name; }
    [Serializable] private class Bones { public BoneEntry[] bones; }

    [MenuItem("Gakumas Mod/RuiNurs0000/Build DMM Bundle")]
    public static void Build()
    {
        var mesh = BuildMesh(out var boneNames);
        AssetDatabase.CreateAsset(mesh, MeshAsset);
        AssetDatabase.SaveAssets();

        var prefab = BuildPrefab(mesh, boneNames);
        PrefabUtility.SaveAsPrefabAsset(prefab, PrefabPath);
        UnityEngine.Object.DestroyImmediate(prefab);

        ConfigureTextures();
        AssignBundleName();
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        Directory.CreateDirectory(OutputPath);
        BuildPipeline.BuildAssetBundles(OutputPath, BuildAssetBundleOptions.ChunkBasedCompression,
            BuildTarget.StandaloneWindows64);
        Debug.Log("Built " + BundleName + " -> " + Path.GetFullPath(OutputPath));
    }

    private static Mesh BuildMesh(out string[] boneNames)
    {
        var geo = JsonUtility.FromJson<Geo>(File.ReadAllText(GeoJson));
        var bones = JsonUtility.FromJson<Bones>(File.ReadAllText(BonesJson));
        boneNames = new string[bones.bones.Length];
        foreach (var b in bones.bones) boneNames[b.index] = b.name;

        int V = geo.m_VertexCount;
        var verts = new Vector3[V];
        var norms = new Vector3[V];
        var tans = new Vector4[V];
        var uvs = new Vector2[V];
        var cols = new Color32[V];
        var bw = new BoneWeight[V];
        for (int i = 0; i < V; i++)
        {
            verts[i] = new Vector3(geo.m_Vertices[i * 3], geo.m_Vertices[i * 3 + 1], geo.m_Vertices[i * 3 + 2]);
            norms[i] = new Vector3(geo.m_Normals[i * 3], geo.m_Normals[i * 3 + 1], geo.m_Normals[i * 3 + 2]);
            tans[i] = new Vector4(geo.m_Tangents[i * 4], geo.m_Tangents[i * 4 + 1], geo.m_Tangents[i * 4 + 2], geo.m_Tangents[i * 4 + 3]);
            uvs[i] = new Vector2(geo.m_UV0[i * 2], geo.m_UV0[i * 2 + 1]);
            cols[i] = new Color32(
                (byte)Mathf.RoundToInt(Mathf.Clamp01(geo.m_Colors[i * 4]) * 255f),
                (byte)Mathf.RoundToInt(Mathf.Clamp01(geo.m_Colors[i * 4 + 1]) * 255f),
                (byte)Mathf.RoundToInt(Mathf.Clamp01(geo.m_Colors[i * 4 + 2]) * 255f),
                (byte)Mathf.RoundToInt(Mathf.Clamp01(geo.m_Colors[i * 4 + 3]) * 255f));
            var s = geo.m_Skin[i];
            bw[i] = new BoneWeight {
                boneIndex0 = s.boneIndex[0], boneIndex1 = s.boneIndex[1],
                boneIndex2 = s.boneIndex[2], boneIndex3 = s.boneIndex[3],
                weight0 = s.weight[0], weight1 = s.weight[1], weight2 = s.weight[2], weight3 = s.weight[3],
            };
        }
        var binds = new Matrix4x4[geo.m_BindPose.Length];
        for (int i = 0; i < binds.Length; i++) binds[i] = geo.m_BindPose[i].ToMatrix();

        var mesh = new Mesh { name = "mdl_chr_hmsz-cstm-0000_body", indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
        mesh.vertices = verts;
        mesh.normals = norms;
        mesh.tangents = tans;
        mesh.uv = uvs;
        mesh.colors32 = cols;
        mesh.boneWeights = bw;
        mesh.bindposes = binds;
        mesh.subMeshCount = geo.m_SubMeshes.Length;
        for (int si = 0; si < geo.m_SubMeshes.Length; si++)
        {
            var sm = geo.m_SubMeshes[si];
            int start = sm.firstByte / 2;              // R16 index -> element offset
            var tri = new int[sm.indexCount];
            Array.Copy(geo.m_Indices, start, tri, 0, sm.indexCount);
            mesh.SetTriangles(tri, si, false);
        }
        mesh.RecalculateBounds();
        return mesh;
    }

    private static GameObject BuildPrefab(Mesh mesh, string[] boneNames)
    {
        var root = new GameObject("mdl_chr_hmsz-cstm-0000_body");
        var geoBody = new GameObject("Geo_Body");
        geoBody.transform.SetParent(root.transform, false);

        // 命名骨:扁平挂 root 下即可,TRS 无所谓(运行时按名 remap 到 hmsz 活体骨并覆盖 bindpose)。
        var bones = new Transform[boneNames.Length];
        Transform rootBone = null;
        for (int i = 0; i < boneNames.Length; i++)
        {
            var go = new GameObject(boneNames[i] ?? ("bone" + i));
            go.transform.SetParent(root.transform, false);
            bones[i] = go.transform;
            if (boneNames[i] == RootBoneName) rootBone = go.transform;
        }
        if (rootBone == null) rootBone = root.transform;

        var smr = geoBody.AddComponent<SkinnedMeshRenderer>();
        smr.sharedMesh = mesh;
        smr.bones = bones;
        smr.rootBone = rootBone;
        smr.updateWhenOffscreen = true;
        var mats = new Material[mesh.subMeshCount];       // 占位;运行时复用 hmsz 原材质,只覆盖贴图
        var shader = Shader.Find("Standard") ?? Shader.Find("Universal Render Pipeline/Lit");
        for (int i = 0; i < mats.Length; i++) mats[i] = new Material(shader) { name = "m_slot" + i };
        smr.sharedMaterials = mats;
        return root;
    }

    private static void ConfigureTextures()
    {
        // t1(_DefMap,packed 数据图)必须线性;t0/t4 是颜色,sRGB。否则 packed mask 被
        // gamma 解码歪掉 → toon 阈值/光滑度错 → 整体发暗。
        foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { ModRoot }))
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            if (AssetImporter.GetAtPath(path) is not TextureImporter ti) continue;
            bool isDef = path.Contains("_t1");           // rui_bdy_t1 / rui_bdyco_t1
            ti.sRGBTexture = !isDef;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.mipmapEnabled = false;
            ti.isReadable = true;
            ti.SaveAndReimport();
        }
    }

    private static void AssignBundleName()
    {
        foreach (var guid in AssetDatabase.FindAssets(string.Empty, new[] { ModRoot }))
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var importer = AssetImporter.GetAtPath(path);
            if (importer != null) { importer.assetBundleName = BundleName; importer.SaveAndReimport(); }
        }
    }
}
