// Menu entry points and the build. The bundle must target StandaloneWindows64: the player
// rejects any other build target outright ("not built with the right version or build target"),
// while the Unity version itself has slack — a 6000.0.67f1 bundle loads in the 6000.0.77f1 game.
//
// The pipeline is split in two on purpose:
//
//   front end  produce a *plain* GameObject — skeleton, mesh, materials, nothing game-specific
//   back end   `Shape()` — everything the game requires: IK anchors, hand IK correction, the swing
//              rig, the collider cage, validation, prefab and bundle
//
// The back end is the product; the front end is whichever source the author happens to have. Today
// there are two: an AssetStudio JSON export (how chs-sucu-00 got in) and any prefab already in the
// project, which is the one the SDK is actually supposed to offer — see README §3.1. Splitting them
// is what makes the second possible at all; before this the whole thing was one hardcoded path.
using System.IO;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class SdkPipeline
    {
        // ponytail: still hardcoded, and deliberately — it is the one source we can regression-test
        // against a known-good in-game result. An author-facing importer needs a window, and a window
        // needs the prefab front end below to be the primary path first.
        private const string ExportRoot = @"D:/GIT/IP/01-unpacking/exports/mdl_chr_chs-sucu-00_body/export";
        private const string BodyName = "mdl_chr_chs-sucu-00_body";
        private const string WorkDirectory = "Assets/Mods";
        private const string OutputDirectory = "Build/AssetBundles";

        [MenuItem("Gakumas SDK/一键：导入 + 装配摇物 + 构建")]
        public static void RunAll()
        {
            var prefab = ImportAndRig(true);
            if (prefab != null)
                BuildBundle();
        }

        // Isolation build: everything except the swing rig. If the actor loads with this and not
        // with the full one, the fault is in the swing components rather than the model.
        [MenuItem("Gakumas SDK/对照：不装摇物 + 构建")]
        public static void RunWithoutSwing()
        {
            var prefab = ImportAndRig(false);
            if (prefab != null)
                BuildBundle();
        }

        [MenuItem("Gakumas SDK/1. 导入模型并装配摇物")]
        public static GameObject ImportAndRig() => ImportAndRig(true);

        public static GameObject ImportAndRig(bool withSwing) =>
            Shape(ImportGeometry(), BodyName, withSwing, $"{ExportRoot}/{BodyName}/components.json");

        /// <summary>Front end A: rebuild geometry from an AssetStudio JSON export. No rigging.</summary>
        [MenuItem("Gakumas SDK/前端 A：从 JSON 导入几何（不装配）")]
        public static void ImportGeometryMenu() => ImportGeometry();

        private static GameObject ImportGeometry()
        {
            var meshJson = $"{ExportRoot}/{BodyName}/Geo_Body.json";
            // Full transform tree, not just the skinned bones: strand tip bones (`*_S_End`), hand
            // helpers and BodyScaleRatio_DIS carry no weights but the actor build binds them,
            // and a missing one aborts the process from inside a Burst job with no stack.
            var skeletonJson = $"{ExportRoot}/{BodyName}/Geo_Body.skeleton.full.json";
            var textures = $"{ExportRoot}/full";
            foreach (var required in new[] { meshJson, skeletonJson })
                if (!File.Exists(required))
                {
                    Debug.LogError($"[SDK] 缺少输入文件: {required}");
                    return null;
                }

            // Textures have to live inside the project before AssetDatabase will hand them back.
            Directory.CreateDirectory(WorkDirectory);
            return BodyImporter.Import(meshJson, skeletonJson, CopyTextures(textures), WorkDirectory);
        }

        /// <summary>
        /// Front end B: take whatever is selected in the project — the author's own model, already
        /// skinned, with its own skeleton. This is the entry point the SDK is meant to have.
        /// </summary>
        [MenuItem("Gakumas SDK/前端 B：装配选中的 prefab + 构建")]
        public static void ShapeSelection()
        {
            var selected = Selection.activeGameObject;
            if (selected == null)
            {
                Debug.LogError("[SDK] 先在 Project 或 Hierarchy 里选中一个模型根对象");
                return;
            }
            // Work on a copy: the author's asset is an input, never an output.
            var root = Object.Instantiate(selected);
            root.name = selected.name;
            if (Shape(root, selected.name, withSwing: true) != null)
                BuildBundle();
        }

        [MenuItem("Gakumas SDK/前端 B：装配选中的 prefab + 构建", isValidateFunction: true)]
        private static bool ShapeSelectionValidate() => Selection.activeGameObject != null;

        /// <summary>
        /// Back end: turn a plain skinned model into something this game can build an actor from,
        /// then write the prefab and mark it for the bundle. Every step is skipped if the input
        /// already carries it, so a prefab can be re-shaped without doubling up.
        /// </summary>
        /// <param name="componentsManifest">
        /// The source model's own rig, exported by tools/export_source_components.py. Null when the
        /// source ships none — and it must be null rather than "whatever path was hardcoded", or a
        /// model from one game gets another game's colliders bolted onto its Pelvis and Spine,
        /// which are the two bone names every skeleton has.
        /// </param>
        /// <param name="stockJointRig">
        /// Rebuild this game's corrective joint rig on the model: synthesise the `*_H` bones, move
        /// the author's weight onto them by the stock profile, and turn eight bones into the stock
        /// rest frames so the drivers' coefficients mean what they do in stock.
        ///
        /// Off by default, and that is the whole design of this back end. Everything else here is
        /// *additive* — new nodes, new components, new materials — and leaves the source's mesh,
        /// weights and skeleton exactly as the author built them. This one is destructive: it
        /// rewrites bone weights (and truncates any vertex past four influences) and re-expresses
        /// bones in a frame that is not theirs, which is a lot of surface for a conversion step that
        /// has never yet been shown to change a pixel on screen. The collapse it exists to prevent is
        /// real and measured (shoulder half-width 17.4cm → 12.6cm across a 67° re-pose) but it is a
        /// *rigging* problem, and rigging belongs to whoever authored the model, in their own DCC,
        /// where they can see it. Turn this on deliberately, with a before/after render.
        /// </param>
        public static GameObject Shape(GameObject root, string name, bool withSwing,
                                       string componentsManifest = null, bool stockJointRig = false)
        {
            if (root == null)
                return null;

            if (root.GetComponentInChildren<SkinnedMeshRenderer>(true) == null)
            {
                Debug.LogError($"[SDK] {name} 下没有 SkinnedMeshRenderer，不是可用的身体模型");
                Object.DestroyImmediate(root);
                return null;
            }

            // Unconditional, and it was not always: this used to be bolted to `stockJointRig`, which
            // is off by default — so the pass written to fix a wrung hand quietly stopped running and
            // the hand came back wrung. It does not belong to the corrective rig. `Turn` moves
            // nothing (children keep their world transforms, only this bone's bind pose is recomputed),
            // so it is additive in the same sense every other step here is.
            //
            // Retargeting absorbs bone *direction* — that is why a baked T-pose is enough and why
            // RestPoseNormalizer died. It does not absorb *roll*: two bones pointing the same way but
            // 180° apart about their own axis take the same muscle with the sign flipped. Measured on
            // this rip: 38 of the 40 driven bones sit >90° off stock, both hands ~174-180°, every
            // finger ~172-180°, and replaying the game's own recorded pose through the shipped mesh
            // put the blown triangles overwhelmingly on the side that is 180° out.
            TPoseBaker.AlignDrivenBoneAxes(root);

            if (stockJointRig)
                HelperBoneRigger.Rig(root);
            else
                Debug.Log("[SDK] 关节矫正 rig：跳过（保留源模型自己的权重）"
                          + " —— 收益只在扭转工况，且已由扭转骨认领拿到，见 HANDOFF §8.4");

            System.Collections.Generic.List<ChainClassifier.Strand> classified = null;
            if (!withSwing)
                Debug.Log("[SDK] 对照组：跳过摇物装配");
            else if (root.GetComponentInChildren<ActorAnimation.ActorSwingDynamicBone>(true) != null)
                Debug.Log("[SDK] 已带摇物组件，跳过摇物装配");
            else if (SwingRigger.FindStrands(root).Count > 0)
                SwingRigger.Rig(root);
            else
            {
                // Nothing matched the `_S` naming, so this model did not come from this family.
                // Fall back to geometry — where a chain hangs, not what it is called.
                Debug.Log("[SDK] 没有 `_S` 命名的摇物骨，改用几何分类");
                classified = ChainClassifier.Classify(root);
                ChainClassifier.Report(classified);
                SwingRigger.Rig(root, classified);
            }

            if (root.transform.Find("IKBody") != null)
                Debug.Log("[SDK] 已带 IK 锚点，跳过 IK 装配");
            else
                IkRigger.Rig(root);

            // Hand this game's twist drivers to the bones the source already has for the job. Additive:
            // no rename, no reweight — see TwistAdopter for why that is enough and where it is not.
            TwistAdopter.Adopt(root);

            // Pose-driven correction: a system of its own, separate from swing. 528 of 530 stock bodies
            // carry 16 of these; see QuartzDriverRigger and docs/body-component-inventory.md.
            if (root.GetComponentInChildren<ActorAnimation.ActorAnimationQuartzDriverRotationBone>(true) != null)
                Debug.Log("[SDK] 已带姿势驱动器，跳过");
            else
                QuartzDriverRigger.Rig(root, classified);

            if (root.GetComponentInChildren<ActorAnimation.ActorSwingBreastBone>(true) != null)
                Debug.Log("[SDK] 已带胸部驱动，跳过");
            else
                BreastRigger.Rig(root);

            // Last, and on purpose: everything above synthesises from the stock tables, and this
            // overwrites whatever the source model authored itself. A source with no rig of its own
            // simply has no manifest and keeps the synthesised values. See ComponentTransfer.
            if (componentsManifest != null)
                ComponentTransfer.Apply(root, componentsManifest);

            // Nothing here touches the rest pose. Bone axes were once normalised at this point and
            // that whole idea is gone: the body is driven by Humanoid muscle retargeting, which
            // absorbs axes entirely (measured — the bench reads the same numbers with and without
            // it). What the rest pose *has* to be is a T-pose, and that is TPoseBaker's job, back in
            // the front end where the mesh can still be baked along with it.
            Validator.Check(root);

            return SavePrefab(root, name);
        }

        /// <summary>Writes the prefab and marks it for the bundle. Shared with the hair path.</summary>
        public static GameObject SavePrefab(GameObject root, string name)
        {
            Directory.CreateDirectory(WorkDirectory);
            var prefabPath = $"{WorkDirectory}/{name}.prefab";
            var prefab = PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
            Object.DestroyImmediate(root);

            var importer = AssetImporter.GetAtPath(prefabPath);
            importer.assetBundleName = $"{name}.bundle";
            AssetDatabase.SaveAssets();
            Debug.Log($"[SDK] 已生成 prefab: {prefabPath}");
            return prefab;
        }

        private static string CopyTextures(string source)
        {
            const string destination = WorkDirectory + "/Textures";
            Directory.CreateDirectory(destination);
            foreach (var file in Directory.GetFiles(source, "*.png"))
            {
                var target = Path.Combine(destination, Path.GetFileName(file));
                if (!File.Exists(target) || File.GetLastWriteTimeUtc(file) > File.GetLastWriteTimeUtc(target))
                    File.Copy(file, target, true);
            }
            AssetDatabase.Refresh();
            Debug.Log($"[SDK] 贴图已就位: {destination}");
            return destination;
        }

        [MenuItem("Gakumas SDK/2. 构建 AB 包 (StandaloneWindows64)")]
        public static void BuildBundle()
        {
            Directory.CreateDirectory(OutputDirectory);
            BuildPipeline.BuildAssetBundles(OutputDirectory,
                BuildAssetBundleOptions.ChunkBasedCompression,
                BuildTarget.StandaloneWindows64);
            AssetDatabase.Refresh();
            Debug.Log($"[SDK] AB 包已输出到 {Path.GetFullPath(OutputDirectory)}");
        }
    }

    /// Rules learned the hard way in-game; each one crashed or silently broke a run before it
    /// became a check here.
    public static class Validator
    {
        private static readonly string[] ForbiddenBones = { "Head_Hair", "Head_Face" };

        public static bool Check(GameObject root)
        {
            var ok = true;
            var names = new System.Collections.Generic.HashSet<string>();

            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
            {
                // The bone-name map is global across body / face / hair parts, so a body that
                // brings its own Head_Hair collides with the hair part and aborts the actor build.
                foreach (var forbidden in ForbiddenBones)
                    if (transform.name == forbidden)
                    {
                        Debug.LogError($"[SDK] 骨名 {forbidden} 属于脸/头发部件，身体包不能带（会打断建模）");
                        ok = false;
                    }
                if (!names.Add(transform.name))
                    Debug.LogWarning($"[SDK] 骨名重复: {transform.name}（跨部件必须唯一）");
            }

            // Root-level nodes the actor build binds by name. Each of these, when absent, produced
            // a null-transform failure that hangs the load rather than reporting anything useful.
            foreach (var required in new[]
                     {
                         "Reference", "Move", "IKBody", "LookAt",
                         "IKGoal_LeftFoot", "IKGoal_RightFoot", "IKGoal_LeftHand", "IKGoal_RightHand",
                         "IKHint_LeftKnee", "IKHint_RightKnee", "IKHint_LeftElbow", "IKHint_RightElbow",
                     })
                if (root.transform.Find(required) == null)
                {
                    Debug.LogError($"[SDK] 根节点下缺少 {required}");
                    ok = false;
                }
            foreach (var required in new[] { "Hips", "Spine", "Head" })
                if (!names.Contains(required))
                {
                    Debug.LogError($"[SDK] 缺少人形必需骨 {required}，Avatar 会构建失败");
                    ok = false;
                }

            Debug.Log(ok ? "[SDK] 校验通过" : "[SDK] 校验未通过，见上方错误");
            return ok;
        }
    }
}
