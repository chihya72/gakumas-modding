// The chest driver. See ActorSwingBreastBone for why it is one component and not per-bone.
//
// Every value here is the mode over the 79 stock costumes that carry one, and the ones that matter
// most are unanimous: host Spine2 (79/79), rootWeight 0.5 (79/79), useArmCorrection true (79/79),
// collider identical (79/79), and the six bone references identical (79/79). The response curves are
// copied verbatim off mdl_chr_hmsz-cstm-0059_body.
using System.Collections.Generic;
using System.Linq;
using ActorAnimation;
using Unity.Mathematics;
using UnityEngine;

namespace GakumasSdk
{
    public static class BreastRigger
    {
        /// <summary>What happened, for report.json. Null until Rig has run.</summary>
        public static string Status;

        // Every rig in the wild spells the chest bone one of these ways.
        private static readonly string[] Tokens = { "bust", "breast", "胸", "乳" };

        /// <summary>
        /// The two bones this driver claims, source-named or stock-named. Selection only — nothing is
        /// moved or renamed here, so the swing rig can ask the same question *before* the rename and
        /// get the same answer.
        /// </summary>
        public static HashSet<Transform> Claim(GameObject root)
        {
            var weighted = TwistAdopter.WeightedBones(root.GetComponentInChildren<SkinnedMeshRenderer>(true));
            var candidates = new List<Transform>();
            foreach (var node in root.GetComponentsInChildren<Transform>(true))
            {
                var lower = node.name.ToLowerInvariant();
                if (!Tokens.Any(lower.Contains) || !weighted.Contains(node))
                    continue;
                // Chest ornaments are spelled the same way in some rigs (MMD ships 胸紐, 胸飾り), so
                // the token alone is not enough: the driver's bone hangs off the spine directly, which
                // an ornament hanging off another ornament does not.
                var host = node.parent;
                if (host == null || !(host.name.Contains("Spine") || host.name.Contains("Chest")
                                      || host.name.Contains("上半身") || Tokens.Any(host.name.ToLowerInvariant().Contains)))
                    continue;
                candidates.Add(node);
            }

            var claimed = new HashSet<Transform>();
            foreach (var side in new[] { -1f, 1f })
            {
                // Character's left is −x (TPoseBaker's canonical rest), and the bone nearest the spine
                // is the one the driver drives; anything hanging below it follows.
                var best = candidates
                    .Where(c => Mathf.Sign(root.transform.InverseTransformPoint(c.position).x) == side)
                    .Where(c => !candidates.Any(other => other != c && c.IsChildOf(other)))
                    .OrderBy(Depth)
                    .FirstOrDefault();
                if (best != null)
                    claimed.Add(best);
            }
            return claimed;
        }

        private static int Depth(Transform node)
        {
            var depth = 0;
            for (var walk = node.parent; walk != null; walk = walk.parent)
                depth++;
            return depth;
        }

        /// <summary>
        /// Give the source's own chest bones this game's names and the tip bone the driver reads.
        ///
        /// Additive: the bones are re-expressed in the stock rest frame (`TPoseBaker.Turn` — children
        /// keep their world transforms, only the bind pose is recomputed) and one unweighted tip node
        /// is added per side. No vertex moves, no weight changes.
        ///
        /// This has to run *after* the swing rig, and that is why it lives here rather than in the
        /// importer: the moment a bone is called `..._S`, `SwingRigger.FindStrands` picks it up as a
        /// strand and the geometry classifier's whole result shifts under it.
        /// </summary>
        private static void Adopt(GameObject root)
        {
            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                byName[transform.name] = transform;
            var adopted = new List<string>();
            foreach (var bone in Claim(root))
            {
                var side = root.transform.InverseTransformPoint(bone.position).x < 0f ? "Left" : "Right";
                if (byName.ContainsKey($"{side}Bust1_S"))
                    continue;
                // The chest sim owns this bone now; stock never puts a dynamic bone on one (0 of 79),
                // and a bone simulated by two systems fights itself.
                foreach (var swing in bone.GetComponents<Component>())
                    if (swing is ActorSwingDynamicBone || swing is ActorSwingStaticBone)
                        Object.DestroyImmediate(swing);
                TPoseBaker.Turn(root, bone, root.transform.rotation * Quaternion.LookRotation(RestForward, RestUp));
                var was = bone.name;
                bone.name = $"{side}Bust1_S";
                adopted.Add($"{was}→{bone.name}");
            }

            // Separately from the rename, because a model can arrive stock-named and still be missing
            // the tip: it carries no weight, so a weighted-bones-only skeleton export drops it.
            foreach (var side in new[] { "Left", "Right" })
            {
                var bust = root.GetComponentsInChildren<Transform>(true)
                    .FirstOrDefault(t => t.name == $"{side}Bust1_S");
                if (bust != null && bust.Find($"{side}Bust2_S_End") == null)
                    AddTip(bust, $"{side}Bust2_S_End");
            }

            if (adopted.Count > 0)
                Debug.Log($"[SDK] 胸部骨认领 {adopted.Count} 根（改名 + 补尖端骨，网格和权重不动）："
                          + string.Join(", ", adopted));
        }

        // The stock rest frame of `*Bust1_S`, read off 40 stock skeletons and identical in all of them
        // to four decimals — and, unlike the arms, *not* mirrored between sides. The tip sits at local
        // (−0.1025, 0, 0) with identity rotation in 60 of 60 bundles scanned, i.e. 10.25 cm straight
        // ahead of the chest bone, 5° down. The driver's limits are per-axis in this frame, so an
        // adopted bone has to be expressed in it or the limits pin the wrong axes.
        private static readonly Vector3 RestForward = new Vector3(1f, 0f, 0f);
        private static readonly Vector3 RestUp = new Vector3(0f, 0.9962f, 0.0872f);
        private static readonly Vector3 TipOffset = new Vector3(-0.1025f, 0f, 0f);

        private static void AddTip(Transform bone, string name)
        {
            var tip = new GameObject(name).transform;
            tip.SetParent(bone, false);
            tip.localPosition = TipOffset;
            tip.localRotation = Quaternion.identity;
            tip.localScale = Vector3.one;
        }

        public static bool Rig(GameObject root)
        {
            Adopt(root);

            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                byName[transform.name] = transform;

            var wanted = new[]
            {
                "Spine2", "LeftBust1_S", "RightBust1_S", "LeftBust2_S_End", "RightBust2_S_End",
                "LeftForeArm", "RightForeArm",
            };
            foreach (var bone in wanted)
                if (!byName.ContainsKey(bone))
                {
                    Status = $"没装胸部驱动：模型里找不到胸部骨（缺 {bone}）";
                    Debug.LogWarning($"[SDK] 缺骨 {bone}，跳过胸部驱动（原版 527/530 套都有一个）");
                    return false;
                }

            var component = byName["Spine2"].gameObject.AddComponent<ActorSwingBreastBone>();
            component.damping = 0.27f;
            component.stiffness = 0.08f;
            component.spring = 1f;
            component.pendulum = 0.04f;
            component.pendulumRange = 0.25f;
            component.average = 0.24f;
            component.rootWeight = 0.5f;
            component.useArmCorrection = true;
            component.limitInfo = new LimitInfo
            {
                useLimit = 1,
                axisX = new int2(-8, 8),
                axisY = new int2(-8, 8),
                axisZ = new int2(-8, 8),
            };
            component.breastCollider = new ActorSwingStaticCollider
            {
                type = 0,
                collisionMask = -1,
                float_A = 0.05f,
                float_B = 0.05f,
            };

            component.leftBreast = byName["LeftBust1_S"];
            component.rightBreast = byName["RightBust1_S"];
            component.leftBreastEnd = byName["LeftBust2_S_End"];
            component.rightBreastEnd = byName["RightBust2_S_End"];
            component.leftLowerArm = byName["LeftForeArm"];
            component.rightLowerArm = byName["RightForeArm"];

            component.modelingLeftTransform = Modeling(component.leftBreast);
            component.modelingRightTransform = Modeling(component.rightBreast);
            component.modelingLeftEndTransform = Modeling(component.leftBreastEnd);
            component.modelingRightEndTransform = Modeling(component.rightBreastEnd);

            // Verbatim off hmsz-cstm-0059. The odd first key at t = -1 is in the stock data too.
            component.upCurve = Curve(
                (-1f, 0f, 0.002f), (0.504f, 0.003f, 0.007f), (0.870f, 0.011f, 0.060f), (1.003f, 0.025f, 0.172f));
            component.sideCurve = Curve(
                (0f, 0.020f, -0.002f), (0.317f, 0.013f, -0.053f), (0.549f, 0.006f, -0.010f),
                (2.187f, -0.002f, -0.006f), (2.503f, -0.009f, -0.040f));

            Status = "胸部驱动已装（Spine2 ← Bust1_S/Bust2_S_End ×2 + 双前臂修正）";
            Debug.Log("[SDK] 胸部驱动装配完成: Spine2 ← Bust1_S/Bust2_S_End ×2 + 双前臂修正");
            return true;
        }

        // Stock curves carry the same slope in and out of every key.
        private static AnimationCurve Curve(params (float Time, float Value, float Slope)[] keys)
        {
            var curve = new AnimationCurve();
            foreach (var (time, value, slope) in keys)
                curve.AddKey(new Keyframe(time, value, slope, slope));
            // WrapMode 2 in the stock data.
            curve.preWrapMode = WrapMode.Loop;
            curve.postWrapMode = WrapMode.Loop;
            return curve;
        }

        private static InitialTransform Modeling(Transform bone) => new InitialTransform
        {
            localPosition = bone.localPosition,
            localRotation = bone.localRotation,
            position = bone.position,
            rotation = bone.rotation,
        };
    }
}
