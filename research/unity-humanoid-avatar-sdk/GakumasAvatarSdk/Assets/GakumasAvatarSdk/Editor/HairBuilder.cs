// 发型部件：和身体是两套规矩，不能共用 Shape()。
//
// 原版发型骨架（assetstudio-hair-json 实测）：根 → `Head_Hair` → 一堆 `*_S` 发丝，78 个节点上下，
// **一根人形骨都没有**。所以身体那条路上的每一步在这里都不成立：没有 Humanoid 可建、没有 T-pose
// 可摆、没有 IK 锚点、没有 Pelvis、没有胸部驱动、没有扭转骨。
//
// 剩下成立的只有两件：发丝要摇，材质要按学马语义。前者用同一套几何分类器（发丝全部挂在
// `Head_Hair` 下，锚点判定会给 ribbon 档），后者复用 TextureRewriter。
//
// 顶点 COLOR 现在按发型自己的population写（`SurfacePresets.Hair`，379 套实测，见那里的注释）。
// **贴图语义（t1/t4）仍然没验过**：离线的发型库只有网格，没有材质也没有贴图，量不出来；
// 身体那套 t1/t4 是量过 530 套 body 包定下来的，不能直接搬到头发上。报告里会写明这一条。
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class HairBuilder
    {
        /// <summary>The one node the actor build binds a hair part by.</summary>
        public const string RootBone = "Head_Hair";

        public static GameObject Import(string fbx, string name, string[] keepMeshes)
        {
            var staged = Stage(fbx);
            if (staged == null)
                return null;

            var root = Object.Instantiate(staged);
            root.name = name;

            var renderers = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            if (renderers.Length == 0)
            {
                Debug.LogError("[SDK] 发型：模型里没有蒙皮网格");
                Object.DestroyImmediate(root);
                return null;
            }
            if (keepMeshes != null && keepMeshes.Length > 0)
                foreach (var renderer in renderers)
                    if (!keepMeshes.Contains(renderer.name))
                    {
                        Debug.Log($"[SDK] 发型：丢掉 {renderer.name}（不在 keepMeshes 里）");
                        Object.DestroyImmediate(renderer.gameObject);
                    }

            var kept = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            if (kept == null)
            {
                Debug.LogError("[SDK] 发型：keepMeshes 把网格全丢光了");
                Object.DestroyImmediate(root);
                return null;
            }

            // 发丝挂在这根上，游戏按名字绑它。源模型叫什么都行，改成这个名字即可。
            var anchor = FindAnchor(root, kept);
            if (anchor == null)
            {
                Debug.LogError("[SDK] 发型：找不到发丝的共同父骨");
                Object.DestroyImmediate(root);
                return null;
            }
            if (anchor.name != RootBone)
            {
                Debug.Log($"[SDK] 发型：把 {anchor.name} 改名成 {RootBone}（游戏按这个名字绑发型）");
                anchor.name = RootBone;
            }
            WriteVertexColors(kept, name);
            Debug.Log($"[SDK] 发型导入完成：骨 {root.GetComponentsInChildren<Transform>(true).Length}，"
                      + $"顶点 {kept.sharedMesh.vertexCount}，子网格 {kept.sharedMesh.subMeshCount}");
            return root;
        }

        /// <summary>
        /// Overwrite COLOR with this game's hair semantics. A mesh from another game carries that
        /// game's packing, and here every byte is a nibble-packed material input: the values a rip
        /// happens to ship decode as a coloured, full-width outline at full rim — the neon edge the
        /// body path already had to fix. Measured stock hair never leaves the band this preset sits in.
        ///
        /// The mesh is copied to an asset first, like the body path: editing the imported FBX's mesh in
        /// place loses the edit on the next reimport, and a mesh that is not an asset does not make it
        /// into the bundle (a 12 KB bundle is what that looks like).
        /// </summary>
        private static void WriteVertexColors(SkinnedMeshRenderer renderer, string name)
        {
            var mesh = Object.Instantiate(renderer.sharedMesh);
            var colors = new Color32[mesh.vertexCount];
            for (var index = 0; index < colors.Length; index++)
                colors[index] = SurfacePresets.Hair;
            mesh.colors32 = colors;
            const string directory = "Assets/Mods/Hair";
            Directory.CreateDirectory(directory);
            AssetDatabase.CreateAsset(mesh, $"{directory}/{name}.mesh.asset");
            renderer.sharedMesh = mesh;
            Debug.Log($"[SDK] 发型顶点 COLOR 按学马语义写入 {colors.Length} 个："
                      + GakumasVertexColor.Describe(SurfacePresets.Hair));
        }

        /// <summary>Whichever bone every weighted strand hangs from — that is the hair root.</summary>
        private static Transform FindAnchor(GameObject root, SkinnedMeshRenderer renderer)
        {
            var bones = renderer.bones.Where(b => b != null).ToList();
            if (bones.Count == 0)
                return null;
            var existing = root.GetComponentsInChildren<Transform>(true)
                .FirstOrDefault(t => t.name == RootBone);
            if (existing != null)
                return existing;
            // The deepest node that is an ancestor of every skinned bone.
            var candidate = bones[0];
            while (candidate != null && !bones.All(b => b == candidate || b.IsChildOf(candidate)))
                candidate = candidate.parent;
            return candidate != null && candidate != root.transform ? candidate : bones[0].parent;
        }

        private static GameObject Stage(string fbx)
        {
            if (!File.Exists(fbx))
            {
                Debug.LogError($"[SDK] 找不到源模型 {fbx}");
                return null;
            }
            const string directory = "Assets/Mods/Hair";
            Directory.CreateDirectory(directory);
            var staged = $"{directory}/{Path.GetFileName(fbx)}";
            File.Copy(fbx, staged, true);
            foreach (var texture in Directory.GetFiles(Path.GetDirectoryName(fbx), "*.png"))
                File.Copy(texture, $"{directory}/{Path.GetFileName(texture)}", true);
            AssetDatabase.Refresh();

            var importer = (ModelImporter)AssetImporter.GetAtPath(staged);
            if (importer == null)
            {
                Debug.LogError($"[SDK] {staged} 没被 Unity 当成模型导入");
                return null;
            }
            // Generic, not Humanoid: a hair part has no humanoid bones to map and forcing Humanoid
            // makes the import fail outright.
            importer.animationType = ModelImporterAnimationType.Generic;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.materialLocation = ModelImporterMaterialLocation.External;
            importer.isReadable = true;
            importer.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<GameObject>(staged);
        }

        /// <summary>Hair's own back end: strands swing, nothing else from the body path applies.</summary>
        public static int Rig(GameObject root)
        {
            if (root.GetComponentInChildren<ActorAnimation.ActorSwingDynamicBone>(true) != null)
            {
                Debug.Log("[SDK] 发型：已带摇物组件，跳过");
                return 0;
            }
            var classified = ChainClassifier.Classify(root);
            ChainClassifier.Report(classified);
            return SwingRigger.Rig(root, classified);
        }
    }
}
