using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    /// <summary>
    /// Builds a T-pose Claymore body bundle for the native source-proxy experiment.
    ///
    /// It runs ExternalModelImporter.Import() — the same staging, Humanoid renaming, body-section
    /// filtering, T-pose bake, texture rebuild and vertex-colour write the SDK route uses — and then
    /// stops. No SdkPipeline.Shape, no rig builders: under protocol 2 the proxy bones carry a
    /// `__gmi_sp_` prefix and the game cannot reach them by name, so a rig step here would only put
    /// a second variable into an in-game test.
    ///
    /// Two things this file used to get wrong, both silent:
    ///
    /// - It loaded `External-Out/m_bdy*.mat` as "proven Claymore materials". That directory is shared
    ///   by every external model, so the bundle shipped whatever model ran last — in game, Claymore's
    ///   geometry wearing the previous mod's textures. Import() rebuilds the surfaces from THIS
    ///   model's own maps under a model-scoped name, and writes the vertex colours the outline pass
    ///   reads.
    /// - Every model wrote one `mdl_chr_external_body.bundle`. A run that produced no bundle left the
    ///   previous model's file in place and it packaged itself as Claymore. The model name is set per
    ///   run here, so prefab, mesh, textures, labels and bundle are all distinct files.
    ///
    /// There is no a-pose mode: the protocol is permanently T-pose (roadmap §2.1), and a loadable
    /// A-pose package only invites someone to test it.
    /// </summary>
    public static class ClaymoreBundleExperiment
    {
        private const string ModelName = "mdl_chr_external_tpose_body";

        // Which stock costume this package stands in for. Only used to pick that costume's own
        // swing numbers out of the scan; the package itself is target-agnostic.
        private const string TargetBody = "mdl_chr_atbm-cstm-0140_body";
        private const string BundleRelativePath = "Build/AssetBundles/" + ModelName + ".bundle";

        [Serializable]
        private sealed class Report
        {
            public string sourceFbx;
            public string declaredRestPose;
            public string modelName;
            public string bundlePath;
            public bool tPoseBakeApplied;
            public bool drivenAxisAlignmentApplied;
            public float leftArmFromTposeDegrees;
            public float rightArmFromTposeDegrees;
            public int sourceVertexCount;
            public int sourceBoneCount;
            public int sourceBindposeCount;
            public int submeshCount;
            public bool weightsPreserved;
            public bool vertexColorsWritten;
            public string[] materialNames;
            public string[] baseMapNames;
            public long bundleBytes;
        }

        [Serializable]
        private sealed class BoneRecord
        {
            public string name;
            public string sourceName;
            public int parentIndex;
            public float[] localPosition;
            public float[] localRotation;
            public float[] localScale;
        }

        [Serializable]
        private sealed class SourceMetadata
        {
            public string renderer;
            public string mesh;
            public string declaredRestPose;
            public string rootBone;
            public int vertexCount;
            public int boneCount;
            public int bindposeCount;
            public int rootRecordCount;
            public int collapsedAncestorCount;
            public float maxCollapsedShearResidual;
            public BoneRecord[] bones;
        }

        public static void Run()
        {
            var reportPath = GetArgument("-bundleReport");
            if (string.IsNullOrWhiteSpace(reportPath))
                throw new ArgumentException("missing -bundleReport");
            var metadataPath = GetArgument("-bundleMetadata");
            if (string.IsNullOrWhiteSpace(metadataPath))
                throw new ArgumentException("missing -bundleMetadata");

            // Snapshot the author's weights straight off the staged FBX. Nothing in this route may
            // rewrite them; the destructive rig steps that do are exactly what is not running here.
            var staged = ExternalModelImporter.Stage();
            if (staged == null)
                throw new InvalidOperationException("Claymore FBX staging/import failed");
            var sourceWeights = staged.GetComponentsInChildren<SkinnedMeshRenderer>(true)
                .FirstOrDefault(candidate => candidate.name == "Body")?.sharedMesh.boneWeights;
            if (sourceWeights == null)
                throw new InvalidOperationException("staged FBX has no Body renderer");

            ExternalModelImporter.ModelName = ModelName;
            var root = ExternalModelImporter.Import();
            if (root == null)
                throw new InvalidOperationException("external model import failed");
            try
            {
                var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
                if (renderer == null || renderer.sharedMesh == null)
                    throw new InvalidOperationException("import produced no body renderer");

                // Opt-in, because the source-proxy route this file was written for deliberately
                // runs no rig steps at all — leave that build byte-identical as the control group.
                //
                // The whole-object route needs the opposite: the game is handed this prefab and
                // builds the actor from it, so the anchors CreateFullBodyIK binds have to exist.
                // Without them the load hangs on exactly the exception IkRigger's header predicts —
                // measured 2026-08-17, `ArgumentNullException: Parameter name: transform` out of
                // ActorAnimationFullBodyIKMovePart..ctor.
                //
                // Placed BEFORE the gates below on purpose: the weight-equality check then covers
                // the rig step too, which is the whole claim being made about it (additive only).
                if (HasFlag("-withGameRig"))
                {
                    IkRigger.Rig(root);
                    // The 14 `*_H` bones are collected BY COMPONENT TYPE, not by name — only
                    // reference/hips/head/moveReference are bound by identity — so the source's
                    // own twist bones can take the drivers under whatever names they were born
                    // with.  That is the additive half of the "70 base bones" contract;
                    // HelperBoneRigger is the destructive half (synthesise + re-split weights)
                    // and is deliberately NOT run: it would trip the weight-equality gate below,
                    // and its measured benefit is 0.0% in bending, twist-only — which this gets.
                    var adopted = TwistAdopter.Adopt(root);
                    // Axis alignment was excluded from this route because the proxy bridge
                    // absorbed any rest-orientation difference every frame — the source rig
                    // could sit 178 degrees off stock and nothing downstream cared.
                    //
                    // Under whole-object there is no absorber: our hand bone IS the game's hand
                    // bone, and props, IK and colliders read its frame directly.  Measured on
                    // this rip, both hands rest 173-178 degrees from stock, which is exactly the
                    // microphone landing on the back of the hand, upside down.
                    var alignedFrames = TPoseBaker.AlignDrivenBoneAxes(root);
                    var alignedHead = TPoseBaker.AlignHeadAxes(root);
                    Debug.Log($"[ClaymoreBundle] game rig applied (Reference / Move / IK goals), "
                              + $"twist bones adopted: {adopted}, "
                              + $"driven frames aligned: {alignedFrames}, head: {alignedHead}");

                    // The physics and pose-driver half of the contract, in SdkPipeline's order.
                    // These are exactly the component classes the runtime's contract-gap probe
                    // reports as missing: ActorSwing{Chain,DynamicBone,StaticBone,BreastBone} and
                    // the QuartzDriver* family.  The source rig has no `_S` naming, so the swing
                    // strands come from geometry.
                    // Roadmap 第 9 步: prefer the original data. The source FBX carries none — a
                    // Genshin rip loses the game's physics on export — but the costume being
                    // REPLACED has its own 106 scanned bones sitting in the repo, and those beat
                    // the 530-body median that would otherwise be used.
                    VanillaSwingTruth.Load(GetArgument("-swingTruth"), TargetBody);
                    var classified = ChainClassifier.Classify(root);
                    ChainClassifier.Report(classified);
                    SwingRigger.Rig(root, classified);
                    QuartzDriverRigger.Rig(root, classified);
                    BreastRigger.Rig(root);
                }

                var mesh = renderer.sharedMesh;

                var leftArm = LimbAngle(root, "LeftArm", "LeftForeArm", Vector3.left);
                var rightArm = LimbAngle(root, "RightArm", "RightForeArm", Vector3.right);
                // The whole protocol rests on the declared pose being the real one, so verify the
                // outcome rather than trusting that the bake ran.
                if (leftArm > 1f || rightArm > 1f)
                    throw new InvalidOperationException(
                        $"T-pose bake left the arms at {leftArm:F1}/{rightArm:F1} degrees from T");

                var weightsPreserved = sourceWeights.SequenceEqual(mesh.boneWeights);
                if (!weightsPreserved)
                    throw new InvalidOperationException("bone weights changed; nothing here may rewrite them");
                // Missing vertex colours are invisible until the model reaches the game with no
                // outline at all — the colour channel is what drives it.
                var colors = mesh.colors;
                if (colors == null || colors.Length != mesh.vertexCount)
                    throw new InvalidOperationException(
                        $"mesh carries {colors?.Length ?? 0} vertex colours for {mesh.vertexCount} vertices");

                // Name every map that actually ended up on the renderer. This is the check that
                // would have caught the previous mod's textures riding along.
                var materialNames = renderer.sharedMaterials
                    .Select(material => material == null ? "<null>" : material.name).ToArray();
                // `_BaseMap`, not `mainTexture` — the placeholder shader has no `_MainTex`, so
                // `mainTexture` is null on every slot and reads as "no texture at all".
                var baseMapNames = renderer.sharedMaterials
                    .Select(material => material == null || material.GetTexture("_BaseMap") == null
                        ? "<null>" : material.GetTexture("_BaseMap").name).ToArray();
                var foreign = baseMapNames.Where(name => !name.Contains(ModelName)).ToArray();
                if (foreign.Length > 0)
                    throw new InvalidOperationException(
                        $"base maps from another model leaked in: {string.Join(", ", foreign)}");

                var metadata = BuildMetadata(root.transform, renderer);
                Directory.CreateDirectory(Path.GetDirectoryName(metadataPath));
                File.WriteAllText(metadataPath, JsonUtility.ToJson(metadata, true), new UTF8Encoding(false));

                var report = new Report
                {
                    sourceFbx = ExternalModelImporter.SourceFbx,
                    declaredRestPose = "t-pose",
                    modelName = ModelName,
                    bundlePath = Path.GetFullPath(BundleRelativePath),
                    tPoseBakeApplied = true,
                    drivenAxisAlignmentApplied = HasFlag("-withGameRig"),
                    leftArmFromTposeDegrees = leftArm,
                    rightArmFromTposeDegrees = rightArm,
                    sourceVertexCount = mesh.vertexCount,
                    sourceBoneCount = renderer.bones.Length,
                    sourceBindposeCount = mesh.bindposes.Length,
                    submeshCount = mesh.subMeshCount,
                    weightsPreserved = weightsPreserved,
                    vertexColorsWritten = true,
                    materialNames = materialNames,
                    baseMapNames = baseMapNames,
                };

                SdkPipeline.SavePrefab(root, ModelName);
                root = null;
                SdkPipeline.BuildBundle();

                // The stale-bundle failure was silent because nobody checked that this run wrote the
                // file it claims.
                if (!File.Exists(BundleRelativePath))
                    throw new FileNotFoundException("bundle was not built", BundleRelativePath);
                report.bundleBytes = new FileInfo(BundleRelativePath).Length;

                Directory.CreateDirectory(Path.GetDirectoryName(reportPath));
                File.WriteAllText(reportPath, JsonUtility.ToJson(report, true), new UTF8Encoding(false));
                Debug.Log($"[ClaymoreBundleExperiment] PASS: arms={leftArm:F1}/{rightArm:F1} degrees from T, "
                          + $"vertices={report.sourceVertexCount}, bones={report.sourceBoneCount}, "
                          + $"submeshes={report.submeshCount}, weightsPreserved=1, vertexColors=1, "
                          + $"baseMaps={string.Join("/", baseMapNames)}, bundle={report.bundleBytes} bytes");
            }
            finally
            {
                if (root != null)
                    UnityEngine.Object.DestroyImmediate(root);
            }
        }

        private static SourceMetadata BuildMetadata(Transform prefabRoot, SkinnedMeshRenderer renderer)
        {
            var bones = renderer.bones;
            var indexByBone = new Dictionary<Transform, int>();
            for (var index = 0; index < bones.Length; index++)
                if (bones[index] != null && !indexByBone.ContainsKey(bones[index]))
                    indexByBone.Add(bones[index], index);

            var records = new BoneRecord[bones.Length];
            var roots = 0;
            var collapsed = 0;
            var maxShear = 0f;
            for (var index = 0; index < bones.Length; index++)
            {
                var bone = bones[index];
                if (bone == null)
                    throw new InvalidOperationException($"renderer bone {index} is null");
                var directParent = bone.parent;
                var ancestor = directParent;
                var parentIndex = -1;
                while (ancestor != null)
                {
                    if (indexByBone.TryGetValue(ancestor, out var candidate) && candidate < index)
                    {
                        parentIndex = candidate;
                        break;
                    }
                    ancestor = ancestor.parent;
                }

                Matrix4x4 local;
                if (parentIndex >= 0)
                {
                    local = bones[parentIndex].worldToLocalMatrix * bone.localToWorldMatrix;
                    if (directParent != bones[parentIndex])
                        collapsed++;
                }
                else
                {
                    local = prefabRoot.worldToLocalMatrix * bone.localToWorldMatrix;
                    roots++;
                }

                Decompose(local, out var position, out var rotation, out var scale, out var shear);
                maxShear = Mathf.Max(maxShear, shear);
                records[index] = new BoneRecord
                {
                    name = bone.name,
                    sourceName = bone.name,
                    parentIndex = parentIndex,
                    localPosition = new[] { position.x, position.y, position.z },
                    localRotation = new[] { rotation.x, rotation.y, rotation.z, rotation.w },
                    localScale = new[] { scale.x, scale.y, scale.z },
                };
            }

            return new SourceMetadata
            {
                renderer = "Geo_Body",
                mesh = renderer.sharedMesh.name,
                declaredRestPose = "t-pose",
                rootBone = renderer.rootBone != null ? renderer.rootBone.name : string.Empty,
                vertexCount = renderer.sharedMesh.vertexCount,
                boneCount = bones.Length,
                bindposeCount = renderer.sharedMesh.bindposes.Length,
                rootRecordCount = roots,
                collapsedAncestorCount = collapsed,
                maxCollapsedShearResidual = maxShear,
                bones = records,
            };
        }

        private static void Decompose(Matrix4x4 matrix, out Vector3 position, out Quaternion rotation,
                                      out Vector3 scale, out float residual)
        {
            position = matrix.GetColumn(3);
            var x = (Vector3)matrix.GetColumn(0);
            var y = (Vector3)matrix.GetColumn(1);
            var z = (Vector3)matrix.GetColumn(2);
            scale = new Vector3(x.magnitude, y.magnitude, z.magnitude);
            if (scale.x < 1e-10f || scale.y < 1e-10f || scale.z < 1e-10f)
                throw new InvalidOperationException("source transform has a zero scale axis");
            x /= scale.x;
            y /= scale.y;
            z /= scale.z;
            if (Vector3.Dot(Vector3.Cross(x, y), z) < 0f)
            {
                scale.x = -scale.x;
                x = -x;
            }
            rotation = Quaternion.LookRotation(z, y);
            var rebuilt = Matrix4x4.TRS(position, rotation, scale);
            residual = 0f;
            for (var row = 0; row < 3; row++)
                for (var column = 0; column < 3; column++)
                    residual = Mathf.Max(residual, Mathf.Abs(matrix[row, column] - rebuilt[row, column]));
        }

        private static float LimbAngle(GameObject root, string boneName, string childName, Vector3 tPoseDirection)
        {
            var bones = root.GetComponentsInChildren<Transform>(true)
                .GroupBy(transform => transform.name)
                .ToDictionary(group => group.Key, group => group.First());
            if (!bones.TryGetValue(boneName, out var bone) || !bones.TryGetValue(childName, out var child))
                return -1f;
            var direction = child.position - bone.position;
            return direction.sqrMagnitude < 1e-12f
                ? -1f
                : Vector3.Angle(direction, root.transform.TransformDirection(tPoseDirection));
        }

        private static bool HasFlag(string name)
        {
            return Environment.GetCommandLineArgs()
                .Any(argument => string.Equals(argument, name, StringComparison.OrdinalIgnoreCase));
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
