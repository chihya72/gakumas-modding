// Reproduce, offline, the only thing that drives this game's body: Unity Humanoid retargeting.
//
// Evidence that it *is* the only thing (2026-08-14, read straight out of the shipped game with
// UnityPy, see docs/rest-pose-dead-end.md §零): the body clips in gakumas_Data/data.unity3d
// (`mot_all_chr_cmn_idle-001-add_lp_b`) carry 130 bindings, every one of them classID 95 = Animator,
// path 0, attribute 7..136 — the muscle/goal index space — and zero rotation, position or euler
// curves. Not one bone is animated by path. So the pipeline is:
//
//     clip muscles → Avatar → per-bone local rotations
//
// and the Avatar is built at runtime by CampusActorController.BuildAvatar() from *our* skeleton,
// mapped by bone name. Which means the pose we ship is what Unity is told the rest pose is, and
// every clip is played relative to it. Ship an A-posed model and the arms play 60° low whatever the
// bones' axes say — that is why three rounds of axis alignment went three different ways.
//
// Two measurements per model, neither of which needs the game:
//
//   1. 静止姿势 — the shipped rest, against the canonical T. This is the absolute gate: a stock body
//      is a T-pose to within a couple of degrees (sucu measures 0.8°), and the avatar is built from
//      whatever we ship here.
//   2. 同一组肌肉值下与参照模型的差 — drive both the reference and the candidate with one muscle
//      vector and compare where the limbs end up. That difference *is* the in-game error, in
//      degrees, and it covers what the rest-pose check cannot: whether bone axes matter at all.
//
// Muscle zero is deliberately NOT compared against the canonical T: Unity's zero is the middle of
// each muscle's range, not the rest pose, and the known-good sucu sits 131° from T there. Measured,
// not assumed — the first version of this bench failed its own control on exactly that point.
//
// The reference is mdl_chr_chs-sucu-00_body, the one model confirmed working in game. A stock body
// would be better still; it is not in the project, and importing one needs the JSON library.
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class AvatarBench
    {
        // Unity humanoid canonical rest: facing +z, up +y, so the character's right is +x and its
        // left arm lies along −x. Stock bodies match this exactly (arms ±1.00, legs −1.00).
        private static readonly (string From, string To, Vector3 Expect, string What)[] Probes =
        {
            ("Hips", "Head", Vector3.up, "躯干"),
            ("LeftArm", "LeftForeArm", Vector3.left, "左大臂"),
            ("LeftForeArm", "LeftHand", Vector3.left, "左小臂"),
            ("RightArm", "RightForeArm", Vector3.right, "右大臂"),
            ("RightForeArm", "RightHand", Vector3.right, "右小臂"),
            ("LeftUpLeg", "LeftLeg", Vector3.down, "左大腿"),
            ("LeftLeg", "LeftFoot", Vector3.down, "左小腿"),
            ("RightUpLeg", "RightLeg", Vector3.down, "右大腿"),
            ("RightLeg", "RightFoot", Vector3.down, "右小腿"),
        };

        private const string DefaultReference = "Assets/Mods/mdl_chr_chs-sucu-00_body.prefab";

        // sucu's shipped rest is 0.8°–4.0° off the canonical T (the 4° is spine curvature, and the
        // torso probe spans five joints). 10° is slack for a differently built body; past 20° the
        // arms are visibly in the wrong place in every clip.
        private const float WarnDegrees = 10f;
        private const float FailDegrees = 20f;

        [MenuItem("Gakumas SDK/台架：离线复现游戏的 Avatar 驱动")]
        public static void RunMenu() => Run(AllModPrefabs(), DefaultReference);

        /// <summary>
        /// Batchmode: -executeMethod GakumasSdk.AvatarBench.RunFromArgs [-prefabs a,b] [-reference p]
        /// </summary>
        public static void RunFromArgs()
        {
            var args = Environment.GetCommandLineArgs();
            var prefabs = Argument(args, "-prefabs")?.Split(',') ?? AllModPrefabs();
            Run(prefabs, Argument(args, "-reference") ?? DefaultReference);
        }

        private static string Argument(IReadOnlyList<string> args, string name)
        {
            var index = args.ToList().IndexOf(name);
            return index >= 0 && index + 1 < args.Count ? args[index + 1] : null;
        }

        private static string[] AllModPrefabs() => AssetDatabase
            .FindAssets("t:Prefab", new[] { "Assets/Mods" })
            .Select(AssetDatabase.GUIDToAssetPath)
            .ToArray();

        public static void Run(IReadOnlyList<string> prefabPaths, string referencePath)
        {
            var reference = Sample(referencePath);
            if (reference == null)
            {
                Debug.LogError($"[台架] 参照模型不可用: {referencePath}");
                return;
            }
            Debug.Log($"[台架] 参照 = {reference.Name}（实机已验证可用）");

            foreach (var path in prefabPaths)
            {
                var trimmed = path.Trim();
                if (trimmed == referencePath)
                    continue;
                var candidate = Sample(trimmed);
                if (candidate == null)
                    continue;
                Compare(candidate, reference);
            }
        }

        private class Sampled
        {
            public string Name;
            public bool AvatarOk;
            public Dictionary<string, Vector3> Rest = new();
            public Dictionary<string, Vector3> Zero = new();
        }

        /// <summary>Instantiate, measure the shipped rest, build the game's avatar, measure again.</summary>
        private static Sampled Sample(string prefabPath)
        {
            var asset = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (asset == null)
            {
                Debug.LogError($"[台架] 找不到 prefab: {prefabPath}");
                return null;
            }
            var root = (GameObject)PrefabUtility.InstantiatePrefab(asset);
            var result = new Sampled { Name = asset.name };
            try
            {
                var bones = new Dictionary<string, Transform>();
                foreach (var t in root.GetComponentsInChildren<Transform>(true))
                    bones[t.name] = t;

                result.Rest = Directions(root, bones);
                var avatar = BuildAvatar(root, bones);
                result.AvatarOk = avatar != null && avatar.isValid && avatar.isHuman;
                if (!result.AvatarOk)
                {
                    // The interesting failure: the game would get no animation at all, and the body
                    // would stay in the rest pose — which is what "lying down, floating" looks like.
                    Debug.LogError($"[台架] ❌ {result.Name} 的 Avatar 构建失败"
                                   + $"（isValid={avatar != null && avatar.isValid}, isHuman={avatar != null && avatar.isHuman}）。"
                                   + "游戏里这副身体一帧动画都吃不到。");
                    return result;
                }

                // One arbitrary but identical pose for every model. Zero is convenient, not special.
                var handler = new HumanPoseHandler(avatar, root.transform);
                var pose = new HumanPose();
                handler.GetHumanPose(ref pose);
                for (var i = 0; i < pose.muscles.Length; i++)
                    pose.muscles[i] = 0f;
                pose.bodyPosition = Vector3.zero;
                pose.bodyRotation = Quaternion.identity;
                handler.SetHumanPose(ref pose);
                handler.Dispose();

                result.Zero = Directions(root, bones);
                return result;
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        // Built the way CampusActorController does it: human bones by name off the same table the
        // bone bridge renames to, skeleton straight off the instantiated hierarchy. The description
        // scalars are Unity's defaults — the game overrides GetHumanDescription and may set its own,
        // but none of them move the rest pose, which is what this measures.
        private static Avatar BuildAvatar(GameObject root, IReadOnlyDictionary<string, Transform> bones)
        {
            var human = new List<HumanBone>();
            var missing = new List<string>();
            foreach (var (bone, name) in HumanoidBridge.Map)
            {
                if (!bones.ContainsKey(name))
                {
                    missing.Add(name);
                    continue;
                }
                human.Add(new HumanBone
                {
                    humanName = HumanTrait.BoneName[(int)bone],
                    boneName = name,
                    limit = new HumanLimit { useDefaultValues = true },
                });
            }
            if (missing.Count > 0)
                Debug.LogWarning($"[台架] 骨架里没有这些人形骨（{missing.Count} 根）: {string.Join(", ", missing)}");

            var skeleton = root.GetComponentsInChildren<Transform>(true).Select(t => new SkeletonBone
            {
                name = t.name,
                position = t.localPosition,
                rotation = t.localRotation,
                scale = t.localScale,
            }).ToArray();

            var description = new HumanDescription
            {
                human = human.ToArray(),
                skeleton = skeleton,
                upperArmTwist = 0.5f,
                lowerArmTwist = 0.5f,
                upperLegTwist = 0.5f,
                lowerLegTwist = 0.5f,
                armStretch = 0.05f,
                legStretch = 0.05f,
                feetSpacing = 0f,
                hasTranslationDoF = false,
            };
            Debug.Log($"[台架] {root.name}: 映射 {human.Count} 根人形骨 / 骨架 {skeleton.Length} 根，BuildHumanAvatar");
            return AvatarBuilder.BuildHumanAvatar(root, description);
        }

        private static Dictionary<string, Vector3> Directions(GameObject root, IReadOnlyDictionary<string, Transform> bones)
        {
            var directions = new Dictionary<string, Vector3>();
            foreach (var (from, to, _, what) in Probes)
                if (bones.TryGetValue(from, out var a) && bones.TryGetValue(to, out var b))
                    // In the model's own frame, so a rotated root does not read as a bent limb.
                    directions[what] = root.transform.InverseTransformDirection(b.position - a.position).normalized;
            return directions;
        }

        private static void Compare(Sampled candidate, Sampled reference)
        {
            Debug.Log($"[台架] ==================== {candidate.Name} ====================");

            var rest = new List<string>();
            var worstRest = 0f;
            foreach (var (_, _, expect, what) in Probes)
            {
                if (!candidate.Rest.TryGetValue(what, out var direction))
                {
                    rest.Add($"  —  {what}（缺骨）");
                    continue;
                }
                var angle = Vector3.Angle(direction, expect);
                worstRest = Mathf.Max(worstRest, angle);
                rest.Add($"  {Mark(angle)} {what,-4} ({direction.x,6:F2},{direction.y,6:F2},{direction.z,6:F2})"
                         + $"  应为 ({expect.x,4:F0},{expect.y,4:F0},{expect.z,4:F0})  偏 {angle,5:F1}°");
            }
            Debug.Log($"[台架] ① 出包静止姿势 vs 标准 T-pose（Avatar 就是照它建的）最大偏差 {worstRest:F1}°\n"
                      + string.Join("\n", rest));

            if (!candidate.AvatarOk)
                return;

            var driven = new List<string>();
            var worstDriven = 0f;
            foreach (var (_, _, _, what) in Probes)
            {
                if (!candidate.Zero.TryGetValue(what, out var mine) || !reference.Zero.TryGetValue(what, out var theirs))
                    continue;
                var angle = Vector3.Angle(mine, theirs);
                worstDriven = Mathf.Max(worstDriven, angle);
                driven.Add($"  {Mark(angle)} {what,-4} 我方 ({mine.x,6:F2},{mine.y,6:F2},{mine.z,6:F2})"
                           + $"  参照 ({theirs.x,6:F2},{theirs.y,6:F2},{theirs.z,6:F2})  差 {angle,5:F1}°");
            }
            Debug.Log($"[台架] ② 同一组肌肉值下 vs {reference.Name}，最大差 {worstDriven:F1}°"
                      + "（这就是实机上的偏差）\n" + string.Join("\n", driven));

            Debug.Log(worstRest < FailDegrees && worstDriven < FailDegrees
                ? $"[台架] ✅ {candidate.Name} 通过：静止 {worstRest:F1}°，驱动后 {worstDriven:F1}°"
                : $"[台架] ❌ {candidate.Name} 未通过：静止 {worstRest:F1}°，驱动后 {worstDriven:F1}° —— 出包也是白跑一趟");
        }

        private static string Mark(float angle) => angle >= FailDegrees ? "❌" : angle >= WarnDegrees ? "⚠️" : "✅";
    }
}
