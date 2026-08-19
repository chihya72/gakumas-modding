// Front end C: an arbitrary model file — FBX, from any game or any DCC — into a body this game can
// wear.
//
// Front end A rebuilds geometry from an AssetStudio JSON export, which only exists for a model that
// was already a Unity asset in a sibling game. Front end B shapes a prefab that is already named and
// laid out like this game's. Neither accepts what an author actually has: one FBX and a folder of
// PNGs, with its own bone names, its own material split, and no rig.
//
// The three things that made that impossible are now solved elsewhere, and this file is only the
// wiring:
//
//   bone names   HumanoidBridge, via Unity's own Humanoid mapping
//   physics      ChainClassifier, by where a chain hangs rather than what it is called
//   textures     TextureRewriter synthesises the shade and def sheets a foreign model never has
//
// What is deliberately not automatic: which meshes to keep. A rip carries face, brows, eyes, pupils,
// hair and effect meshes, and only the author knows whether the head is coming along. That is one
// list of names, at the top.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class ExternalModelImporter
    {
        // ponytail: same hardcoded-input deal as SdkPipeline — one known model we can regression-test
        // against a real in-game result. The author-facing version of this is a window.
        // Defaults for the menu items; ModBuilder overwrites them when Blender drives the build.
        public static string SourceFbx =
            @"C:/Users/10725/Downloads/Avatar_Girl_Claymore_MarionetteNew_by_hiragara_ef9a45f949260db07a9125c1484dc4db/Avatar_Girl_Claymore_MarionetteNew/Avatar_Girl_Claymore_MarionetteNew.fbx";
        public static string ModelName = "mdl_chr_external_body";
        private const string StageDirectory = "Assets/Mods/External";
        // Its own folder, not the JSON front end's: the texture rewriter finds a section's maps by
        // globbing `*_bdy_col*.png`, so two models staged in one directory silently swap sheets.
        private const string WorkDirectory = "Assets/Mods/External-Out";
        private const string TextureDirectory = WorkDirectory + "/Textures";
        private const string PlaceholderShader = "GakumasSdk/BodyPlaceholder";

        /// <summary>Mesh objects to keep. Everything else in the file is dropped.</summary>
        public static string[] KeepMeshes = { "Body" };

        /// <summary>
        /// Material name fragments that mark a section as head or effect. The name says the section is
        /// head, never that it is *only* head — a rip's hair sheet routinely carries body geometry as
        /// well — so the section is trimmed by skinning rather than deleted, see KeepBodyOnly.
        /// </summary>
        public static string[] DropMaterials = { "Hair", "Face", "Eye", "Brow", "Pupil", "Default" };

        [MenuItem("Gakumas SDK/前端 C：导入外部模型（FBX）+ 装配 + 构建")]
        public static void RunAll() => RunAll(false);

        /// <summary>The same, plus this game's corrective joint rig — which rewrites the author's
        /// bone weights. See SdkPipeline.Shape's `stockJointRig`.</summary>
        [MenuItem("Gakumas SDK/前端 C：导入外部模型 + 关节矫正 rig（会改权重）+ 构建")]
        public static void RunAllWithJointRig() => RunAll(true);

        private static void RunAll(bool stockJointRig)
        {
            var root = Import();
            if (root == null)
                return;
            if (SdkPipeline.Shape(root, ModelName, true, null, stockJointRig) != null)
                SdkPipeline.BuildBundle();
        }

        [MenuItem("Gakumas SDK/前端 C：只导入外部模型（不装配）")]
        public static GameObject Import()
        {
            var asset = Stage();
            if (asset == null)
                return null;

            var root = Object.Instantiate(asset);
            root.name = ModelName;

            if (HumanoidBridge.Apply(root) < 0)
            {
                Object.DestroyImmediate(root);
                return null;
            }

            var renderer = KeepBodyOnly(root);
            if (renderer == null)
            {
                Object.DestroyImmediate(root);
                return null;
            }

            // Before the surfaces, and long before rigging: the chain classifier reads directions,
            // the collider cage reads bone axes, and the surface step writes the mesh out as an
            // asset — all three have to see the final rest pose. This is also the one step that
            // decides whether the model animates correctly at all, see TPoseBaker.
            TPoseBaker.Bake(root);
            // After the bake (it moves Head with the spine) and before the rigging, which reads bone
            // axes when it orients colliders — the game's axes are what those should be measured in.
            TPoseBaker.AlignHeadAxes(root);
            BuildSurfaces(root, renderer);
            Debug.Log($"[SDK] 外部模型导入完成：骨 {root.GetComponentsInChildren<Transform>(true).Length}，"
                      + $"顶点 {renderer.sharedMesh.vertexCount}，子网格 {renderer.sharedMesh.subMeshCount}，"
                      + $"蒙皮骨 {renderer.bones.Length}");
            return root;
        }

        /// <summary>Copies the file into the project and forces the import settings the rest relies on.</summary>
        // Public for controlled experiments that need the exact same FBX import settings while
        // deliberately skipping later production steps such as TPoseBaker.
        public static GameObject Stage()
        {
            if (!File.Exists(SourceFbx))
            {
                Debug.LogError($"[SDK] 找不到源模型 {SourceFbx}");
                return null;
            }
            Directory.CreateDirectory(StageDirectory);
            var staged = $"{StageDirectory}/{Path.GetFileName(SourceFbx)}";
            if (!File.Exists(staged) || File.GetLastWriteTimeUtc(SourceFbx) > File.GetLastWriteTimeUtc(staged))
            {
                File.Copy(SourceFbx, staged, true);
                foreach (var texture in Directory.GetFiles(Path.GetDirectoryName(SourceFbx), "*.png"))
                    File.Copy(texture, $"{StageDirectory}/{Path.GetFileName(texture)}", true);
                AssetDatabase.Refresh();
            }

            var importer = (ModelImporter)AssetImporter.GetAtPath(staged);
            if (importer == null)
            {
                Debug.LogError($"[SDK] {staged} 没被 Unity 当成模型导入");
                return null;
            }
            // Humanoid is the whole bone-name bridge; without it HumanoidBridge has nothing to read.
            // Materials/textures on, because the material's own main texture is how the surface step
            // finds each section's base map without guessing at file names.
            //
            // `materialName` is pinned on purpose. Unity's default names an imported material after its
            // *texture*, so the moment a source arrives with textures wired the material the author
            // declared as `ch_pr001_017kth_face_m` lands in the project as `017gt003_09` — and every
            // name-keyed decision silently misses. Measured on the MMD model: the same FBX dropped 11
            // sections when its materials had no textures and 2 sections once they did, leaving the
            // face and hair in the body bundle while the log still said it had filtered them.
            if (importer.animationType != ModelImporterAnimationType.Human
                || importer.materialImportMode == ModelImporterMaterialImportMode.None
                || importer.materialName != ModelImporterMaterialName.BasedOnMaterialName)
            {
                importer.animationType = ModelImporterAnimationType.Human;
                importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
                importer.materialLocation = ModelImporterMaterialLocation.External;
                importer.materialName = ModelImporterMaterialName.BasedOnMaterialName;
                importer.isReadable = true;
                importer.SaveAndReimport();
                Debug.Log("[SDK] 已把 FBX 的 Rig 设成 Humanoid、材质按材质名命名，并重新导入");
            }
            return AssetDatabase.LoadAssetAtPath<GameObject>(staged);
        }

        /// <summary>Drops every mesh but the body, and every body section the brief excludes.</summary>
        // Public for controlled source-pose experiments; this method only filters geometry and
        // renames the renderer. It does not alter vertices, weights, bindposes, or the rest pose.
        public static SkinnedMeshRenderer KeepBodyOnly(GameObject root)
        {
            SkinnedMeshRenderer kept = null;
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (KeepMeshes.Contains(renderer.name))
                    kept = renderer;
                else
                    Object.DestroyImmediate(renderer.gameObject);
            }
            foreach (var renderer in root.GetComponentsInChildren<MeshRenderer>(true))
                Object.DestroyImmediate(renderer.gameObject);
            if (kept == null)
            {
                Debug.LogError($"[SDK] 模型里没有名为 {string.Join("/", KeepMeshes)} 的网格");
                return null;
            }

            var source = kept.sharedMesh;
            var materials = kept.sharedMaterials;
            var underHead = HeadScope(kept);
            var weights = source.boneWeights;
            var keep = new List<int>();
            var triangles = new List<int[]>();
            var trimmed = new List<string>();
            var emptied = new List<string>();
            for (var slot = 0; slot < source.subMeshCount && slot < materials.Length; slot++)
            {
                var name = materials[slot] == null ? "" : materials[slot].name;
                var section = source.GetTriangles(slot);
                // A name in DropMaterials means "this section is head or effect", not "this section is
                // only head". This model's `..._Tex_Hair_Diffuse` sheet is hair *and* the whole lower
                // body — stockings, thighs and shoes are on the same atlas — so dropping the section
                // took the legs with it. What the section really covers is in the skinning, so the cut
                // is per triangle: a triangle whose three vertices all hang off Head is head geometry,
                // anything else is body and stays.
                if (DropMaterials.Any(token => name.Contains(token)))
                {
                    var body = TrimHead(section, weights, underHead);
                    if (body.Length == 0)
                    {
                        emptied.Add(name);
                        continue;
                    }
                    if (body.Length < section.Length)
                        trimmed.Add($"{name} {(section.Length - body.Length) / 3}→头部三角丢弃"
                                    + $"，剩 {body.Length / 3} 个是身体");
                    section = body;
                }
                keep.Add(slot);
                triangles.Add(section);
            }
            if (keep.Count == 0)
            {
                Debug.LogError("[SDK] 过滤后一个子网格都不剩，检查 DropMaterials");
                return null;
            }

            // Vertices are left alone — only the triangle lists are rebuilt. Unused vertices cost a
            // little size and nothing visually, and keeping the array intact keeps every bone weight,
            // bind pose and UV index valid without a remap.
            var mesh = Object.Instantiate(source);
            mesh.name = ModelName;
            mesh.subMeshCount = keep.Count;
            for (var index = 0; index < keep.Count; index++)
                mesh.SetTriangles(triangles[index], index, false);
            mesh.RecalculateBounds();

            kept.sharedMesh = mesh;
            kept.sharedMaterials = keep.Select(slot => materials[slot]).ToArray();
            // Stock bodies put the renderer on a node called Geo_Body (`<actor>/Root_Body/Geo_Body`).
            // Nothing has been proven to read that name, but matching it costs one line and removes a
            // difference from stock that would otherwise have to be ruled out later.
            kept.gameObject.name = "Geo_Body";
            Debug.Log($"[SDK] 只留 {kept.name}：子网格 {source.subMeshCount} → {keep.Count}"
                      + (emptied.Count > 0 ? $"，丢掉 {string.Join(", ", emptied)}" : "")
                      + (trimmed.Count > 0 ? $"；{string.Join("；", trimmed)}" : ""));
            return kept;
        }

        /// <summary>Per skinning bone: true if it is Head or hangs off it. Hair and face live here.</summary>
        private static bool[] HeadScope(SkinnedMeshRenderer renderer)
        {
            var bones = renderer.bones;
            var scope = new bool[bones.Length];
            for (var index = 0; index < bones.Length; index++)
                for (var node = bones[index]; node != null; node = node.parent)
                    if (node.name == "Head")
                    {
                        scope[index] = true;
                        break;
                    }
            return scope;
        }

        /// <summary>Triangle list minus the triangles that are entirely head geometry.</summary>
        private static int[] TrimHead(int[] triangles, BoneWeight[] weights, bool[] underHead)
        {
            var body = new List<int>(triangles.Length);
            for (var index = 0; index < triangles.Length; index += 3)
            {
                // boneIndex0 is the heaviest influence — Unity sorts BoneWeight descending.
                if (IsHead(weights, triangles[index], underHead)
                    && IsHead(weights, triangles[index + 1], underHead)
                    && IsHead(weights, triangles[index + 2], underHead))
                    continue;
                body.Add(triangles[index]);
                body.Add(triangles[index + 1]);
                body.Add(triangles[index + 2]);
            }
            return body.ToArray();
        }

        private static bool IsHead(BoneWeight[] weights, int vertex, bool[] underHead)
        {
            if (vertex >= weights.Length)
                return false;
            var bone = weights[vertex].boneIndex0;
            return weights[vertex].weight0 > 0 && bone >= 0 && bone < underHead.Length && underHead[bone];
        }

        /// <summary>Base maps out of the model's own materials, then this game's t1/t4 and vertex COLOR.</summary>
        private static void BuildSurfaces(GameObject root, SkinnedMeshRenderer renderer)
        {
            Directory.CreateDirectory(TextureDirectory);
            // Every model imported here shares this one directory, and the rewriter finds its inputs by
            // globbing it. A `_sdw`/`_def` sheet left by an earlier run therefore gets *rewritten*
            // instead of resynthesised from this run's base map — silently, with a normal-looking log
            // line. Drop this model's generated sheets first; `_col` is re-staged below and a
            // hand-painted `_skin` mask is author input, so neither is touched.
            foreach (var stale in Directory.GetFiles(TextureDirectory, $"t_{ModelName}_*")
                         .Where(f => f.Contains("_sdw") || f.Contains("_def")))
                File.Delete(stale);
            var mesh = renderer.sharedMesh;
            var count = mesh.subMeshCount;
            // Every section is a plain opaque body section. Naming them after this game's `bdyco` /
            // `bdytrs` slots by index was a guess, and an expensive one: those slots are the
            // alpha-tested ones (`_ALPHATEST_ON`, `_Cutoff` 0.5), and the actor build hands each mod
            // slot the vanilla material whose name matches. Three of four sections landed on an
            // alpha-test material with a base map whose alpha is a foreign mask — all clipped away.
            // A source that really does have a transparent section says so through the labels asset.
            var groups = new string[count];
            for (var slot = 0; slot < count; slot++)
                groups[slot] = slot == 0 ? "bdy" : $"bdy{slot + 1}";

            // Stage each section's base map under the name the rewriter looks for. Which file that is
            // comes from the material itself, not from a file-name convention — Unity already
            // resolved it at import.
            for (var slot = 0; slot < count; slot++)
            {
                var material = renderer.sharedMaterials[slot];
                var texture = material == null ? null : material.mainTexture;
                if (texture == null)
                {
                    Debug.LogWarning($"[SDK] 子网格 {slot}（{material?.name}）没有主贴图，这一段会没有底色");
                    continue;
                }
                var sourcePath = AssetDatabase.GetAssetPath(texture);
                var target = $"{TextureDirectory}/t_{ModelName}_{groups[slot]}_col.png";
                TextureRewriter.CopyOpaqueBaseMap(sourcePath, target);
                Debug.Log($"[SDK] 子网格 {slot} 底色 ← {Path.GetFileName(sourcePath)}（{material.name}）");

                // The source's own shading sheet, if it has one. A Genshin rip ships
                // `..._Lightmap.png` beside the diffuse; its G channel is a smooth 0-146 field
                // (measured on this model: mean 82.5, 138 distinct values) — an AO / shadow
                // threshold. Without it the shade sheet is base x one constant, which is exactly
                // the flat, grey look. Roadmap 第 9 步's "prefer the original data" is not only
                // about physics.
                var shading = Path.Combine(Path.GetDirectoryName(sourcePath) ?? "",
                    Path.GetFileNameWithoutExtension(sourcePath).Replace("_Diffuse", "_Lightmap") + ".png");
                if (System.IO.File.Exists(shading))
                {
                    var shadingTarget = $"{TextureDirectory}/t_{ModelName}_{groups[slot]}_lightmap.png";
                    System.IO.File.Copy(shading, shadingTarget, true);
                    Debug.Log($"[SDK] 子网格 {slot} 明暗 ← {Path.GetFileName(shading)}（源自带，将驱动 t4 逐像素变化）");
                }
            }
            AssetDatabase.Refresh();

            var labels = GakumasBodyLabels.LoadOrCreate($"{WorkDirectory}/{ModelName}.labels.asset", count,
                slot => groups[slot]);
            var rewrites = new TextureRewriter.Rewrite[count];
            for (var slot = 0; slot < count; slot++)
                rewrites[slot] = TextureRewriter.Build(TextureDirectory, groups[slot], labels.submeshes[slot], ModelName);

            WriteVertexColors(mesh, rewrites, labels);
            AssetDatabase.CreateAsset(mesh, $"{WorkDirectory}/{ModelName}.mesh.asset");
            renderer.sharedMaterials = BuildMaterials(groups, rewrites);
            renderer.rootBone = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == "Hips")
                                ?? renderer.rootBone;
            AssetDatabase.SaveAssets();
        }

        // Same semantics as the JSON front end: every vertex takes its submesh's surface preset,
        // overridden per vertex by the skin mask where a section mixes in bare skin. The submesh a
        // vertex belongs to has to come from the triangle lists here, since a Unity mesh has no
        // per-vertex section the way the export JSON does.
        private static void WriteVertexColors(Mesh mesh, TextureRewriter.Rewrite[] rewrites, GakumasBodyLabels labels)
        {
            var uvs = new List<Vector2>();
            mesh.GetUVs(0, uvs);
            var colors = new Color32[mesh.vertexCount];
            var assigned = new bool[mesh.vertexCount];
            var skin = 0;
            var report = new List<string>();

            for (var slot = 0; slot < mesh.subMeshCount; slot++)
            {
                var label = labels.For(slot);
                var surface = label?.surface ?? SurfaceClass.Cloth;
                var color = SurfacePresets.Of(surface).Color;
                var skinColor = SurfacePresets.Of(SurfaceClass.Skin).Color;
                var rewrite = slot < rewrites.Length ? rewrites[slot] : null;
                var slotSkin = 0;
                foreach (var index in mesh.GetTriangles(slot))
                {
                    if (assigned[index])
                        continue;
                    assigned[index] = true;
                    var bare = uvs.Count == mesh.vertexCount && rewrite?.Mask != null && rewrite.IsSkinAt(uvs[index]);
                    colors[index] = bare ? skinColor : color;
                    if (bare)
                        slotSkin++;
                }
                skin += slotSkin;
                report.Add($"{label?.material ?? $"submesh{slot}"}={surface}" + (slotSkin > 0 ? $"(皮肤 {slotSkin})" : ""));
            }
            // A vertex no kept triangle references keeps a sane value rather than transparent black.
            for (var index = 0; index < colors.Length; index++)
                if (!assigned[index])
                    colors[index] = SurfacePresets.Of(SurfaceClass.Cloth).Color;

            mesh.colors32 = colors;
            Debug.Log($"[SDK] 顶点 COLOR 按学马语义写入 {colors.Length} 个：{string.Join(", ", report)}；"
                      + $"皮肤共 {skin} 个 [{GakumasVertexColor.Describe(SurfacePresets.Of(SurfaceClass.Skin).Color)}]");
        }

        private static Material[] BuildMaterials(string[] groups, TextureRewriter.Rewrite[] rewrites)
        {
            var shader = Shader.Find(PlaceholderShader);
            if (shader == null)
                throw new System.InvalidOperationException($"[SDK] 找不到 {PlaceholderShader}，贴图会全部丢失");
            var materials = new Material[groups.Length];
            for (var slot = 0; slot < groups.Length; slot++)
            {
                var material = new Material(shader) { name = $"m_{groups[slot]}" };
                BindPath(material, "_BaseMap", $"{TextureDirectory}/t_{ModelName}_{groups[slot]}_col.png", srgb: true);
                BindPath(material, "_ShadeMap", rewrites[slot].ShadePath, srgb: true);
                BindPath(material, "_DefMap", rewrites[slot].DefPath, srgb: false);
                AssetDatabase.CreateAsset(material, $"{WorkDirectory}/{material.name}.mat");
                materials[slot] = material;
            }
            return materials;
        }

        private static void BindPath(Material material, string property, string path, bool srgb)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
                return;
            TextureRewriter.ConfigureImport(path, srgb);
            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            if (texture != null)
                material.SetTexture(property, texture);
        }
    }
}
