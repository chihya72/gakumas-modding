// Give the source's own twist bones this game's drivers. Nothing is renamed, nothing is re-weighted.
//
// What the 14 `*_H` bones actually do was read out of the game (il2cpp 3.2.3): ten of them are twist
// distributors and four are elbow/knee half-angle correctives —
//
//   Arm_H −0.8 / Arm_Roll_H −0.3        MuscleHandle 41/50  = Arm Twist In-Out
//   ForeArm_Roll_H 0.5 / Hand_H 0.9     MuscleHandle 43/52  = Forearm Twist In-Out
//   UpLeg_H −1.0 / UpLeg_Roll_H −0.6    MuscleHandle 23/31  = Upper Leg Twist In-Out
//   ForeArm_H (0,−0.4,0) / Leg_H (0,0,−0.5)   read the elbow's / knee's own rotation
//
// None of them is a shoulder-swing corrective; this game has no such thing. So an imported model is
// not missing "anti-collapse" bones, it is missing *twist distribution* — the thing that stops a
// forearm shearing when the wrist turns. And almost every rip already carries those bones, because
// every game needs them: Genshin ships `+UpperArmTwist L A01`, MMD ships `左腕捩`, and they sit at
// the same fraction along the bone that this game's do.
//
// So this does not synthesise anything. It finds the bone that already plays the role and hands it
// the driver. The game collects drivers by component type — `CampusActorAnimationInitializeData`
// holds `List<ActorAnimationQuartzDriverHumanoidArmBone>` and friends, and only `reference`, `hips`,
// `head` and `moveReference` are bound by identity — so the bone keeps whatever name it was born
// with. The author's skeleton, weights and bind poses come out byte-identical.
using System.Collections.Generic;
using System.Linq;
using ActorAnimation;
using Unity.Mathematics;
using UnityEngine;

namespace GakumasSdk
{
    public static class TwistAdopter
    {
        /// <summary>Author overrides from the job file: bone name -> role.</summary>
        public static Dictionary<string, string> Overrides = new Dictionary<string, string>();

        /// <summary>
        /// Roles no bone in the source could play, for report.json. A vacancy is not a build failure —
        /// it is a bone the author has to add in their DCC, and nothing here can synthesise it without
        /// rewriting their weights.
        /// </summary>
        public static List<string> Vacant = new List<string>();

        /// <summary>
        /// Stock role name -> the source bone that took it. Published because the bone keeps its own
        /// name: anything downstream that looks a role up by its stock name (QuartzDriverRigger does)
        /// would otherwise call a covered role missing, and 6 covered twist roles read as a 16-driver
        /// hole in the report.
        /// </summary>
        public static readonly Dictionary<string, Transform> AdoptedByRole =
            new Dictionary<string, Transform>();

        private class Role
        {
            public string Name;             // 这个角色在原版里叫什么，仅用于日志和覆盖表
            public string Limb;             // 候选骨必须挂在这根人形骨的子树里
            public string Tip;              // 沿骨方向的参照，用来算位置比例
            public float Fraction;          // 原版这根骨在骨长上的位置
            public float Coefficient;
            public int Dof;                 // HumanPartDof：LeftLeg 2 RightLeg 3 LeftArm 4 RightArm 5
            public string Driver;           // arm / hand / upleg
        }

        // Positions are the stock constants (measured over 1060 limbs, spread ±0.0001), coefficients
        // and dofs are the stock driver tables.
        private static IEnumerable<Role> Roles(string side)
        {
            var dofLimb = side == "Left" ? 4 : 5;
            var dofLeg = side == "Left" ? 2 : 3;
            yield return new Role { Name = $"{side}Arm_H", Limb = $"{side}Arm", Tip = $"{side}ForeArm",
                                    Fraction = 0.000f, Coefficient = -0.8f, Dof = dofLimb, Driver = "arm" };
            yield return new Role { Name = $"{side}Arm_Roll_H", Limb = $"{side}Arm", Tip = $"{side}ForeArm",
                                    Fraction = 0.605f, Coefficient = -0.3f, Dof = dofLimb, Driver = "arm" };
            yield return new Role { Name = $"{side}ForeArm_Roll_H", Limb = $"{side}ForeArm", Tip = $"{side}Hand",
                                    Fraction = 0.581f, Coefficient = 0.5f, Dof = dofLimb, Driver = "hand" };
            yield return new Role { Name = $"{side}Hand_H", Limb = $"{side}ForeArm", Tip = $"{side}Hand",
                                    Fraction = 0.910f, Coefficient = 0.9f, Dof = dofLimb, Driver = "hand" };
            yield return new Role { Name = $"{side}UpLeg_H", Limb = $"{side}UpLeg", Tip = $"{side}Leg",
                                    Fraction = 0.000f, Coefficient = -1.0f, Dof = dofLeg, Driver = "upleg" };
            yield return new Role { Name = $"{side}UpLeg_Roll_H", Limb = $"{side}UpLeg", Tip = $"{side}Leg",
                                    Fraction = 0.360f, Coefficient = -0.6f, Dof = dofLeg, Driver = "upleg" };
        }

        // Every rig in the wild spells it one of these ways.
        private static readonly string[] TwistTokens = { "twist", "roll", "捩", "_h" };

        public static int Adopt(GameObject root)
        {
            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                if (!byName.ContainsKey(transform.name))
                    byName[transform.name] = transform;

            var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            var weighted = WeightedBones(renderer);
            var taken = new HashSet<Transform>();
            var adopted = new List<string>();
            var vacant = new List<string>();
            var turnedFrames = new List<string>();

            foreach (var side in new[] { "Left", "Right" })
            foreach (var role in Roles(side))
            {
                if (!byName.TryGetValue(role.Limb, out var limb) || !byName.TryGetValue(role.Tip, out var tip))
                    continue;
                var candidate = Pick(role, limb, tip, weighted, taken);
                if (candidate == null)
                {
                    vacant.Add(role.Name);
                    continue;
                }
                taken.Add(candidate);
                // The driver turns the bone about a fixed axis of its *own* frame, so an adopted bone
                // has to be expressed in this game's frame or the twist comes out about the wrong
                // axis. Turning it moves nothing: children keep their world transforms and only this
                // bone's bind pose is recomputed (same operation as TPoseBaker.AlignDrivenBoneAxes).
                var frame = TPoseBaker.DrivenFrames.FirstOrDefault(f => f.Bone == role.Limb);
                if (frame.Bone != null)
                {
                    var turned = TPoseBaker.Turn(root, candidate,
                        root.transform.rotation * Quaternion.LookRotation(frame.Forward, frame.Up));
                    if (turned > 0f)
                        turnedFrames.Add($"{candidate.name} {turned:F0}°");
                }
                Attach(candidate, role);
                AdoptedByRole[role.Name] = candidate;
                adopted.Add($"{candidate.name}→{role.Name}");
            }

            if (adopted.Count > 0)
                Debug.Log($"[SDK] 扭转骨认领 {adopted.Count} 根（不改名不改权重）：{string.Join(", ", adopted)}");
            if (turnedFrames.Count > 0)
                Debug.Log($"[SDK] 扭转骨轴向对齐 {turnedFrames.Count} 根（只换表达坐标系，位置和网格不动）："
                          + string.Join(", ", turnedFrames));
            if (vacant.Count > 0)
                Debug.Log($"[SDK] 源模型没有这些角色的骨，跳过（对应部位扭转时会剪切）：{string.Join(", ", vacant)}");
            Vacant = vacant;
            return adopted.Count;
        }

        /// <summary>The author's word first, then the bone that already plays the part.</summary>
        private static Transform Pick(Role role, Transform limb, Transform tip,
                                      IReadOnlyCollection<Transform> weighted, ICollection<Transform> taken)
        {
            foreach (var pair in Overrides)
                if (pair.Value == role.Name)
                    return limb.GetComponentsInChildren<Transform>(true)
                        .FirstOrDefault(t => t.name == pair.Key && !taken.Contains(t));

            var axis = tip.position - limb.position;
            var length = axis.magnitude;
            if (length < 1e-4f)
                return null;
            axis /= length;

            Transform best = null;
            var closest = float.MaxValue;
            foreach (var node in limb.GetComponentsInChildren<Transform>(true))
            {
                if (node == limb || node == tip || taken.Contains(node) || node.IsChildOf(tip))
                    continue;
                // Weighted, or it deforms nothing and driving it is pointless.
                if (!weighted.Contains(node))
                    continue;
                // Never onto a bone the swing solver owns: stock has 327 skirt drivers and not one
                // shares a bone with an ActorSwing* component, and the build that did it hard-crashed.
                if (node.GetComponent<ActorSwingDynamicBone>() != null
                    || node.GetComponent<ActorSwingStaticBone>() != null)
                    continue;
                var lower = node.name.ToLowerInvariant();
                if (!TwistTokens.Any(lower.Contains))
                    continue;
                var fraction = Vector3.Dot(node.position - limb.position, axis) / length;
                var distance = Mathf.Abs(fraction - role.Fraction);
                // A twist bone for this role has to sit roughly where this game puts it; a bone at the
                // far end of the limb plays a different part whatever it is called.
                if (distance > 0.3f || distance >= closest)
                    continue;
                closest = distance;
                best = node;
            }
            return best;
        }

        private static void Attach(Transform bone, Role role)
        {
            switch (role.Driver)
            {
                case "arm":
                    bone.gameObject.AddComponent<ActorAnimationQuartzDriverHumanoidArmBone>().setting =
                        new ActorAnimationQuartzDriverHumanoidArmSetting
                        { humanPartDof = role.Dof, coefficient = role.Coefficient };
                    break;
                case "hand":
                    bone.gameObject.AddComponent<ActorAnimationQuartzDriverHumanoidHandBone>().setting =
                        new ActorAnimationQuartzDriverHumanoidHandSetting
                        { humanPartDof = role.Dof, coefficient = role.Coefficient };
                    break;
                default:
                    bone.gameObject.AddComponent<ActorAnimationQuartzDriverHumanoidUpLegBone>().setting =
                        new ActorAnimationQuartzDriverHumanoidUpLegSetting
                        { humanPartDof = role.Dof, coefficient = role.Coefficient };
                    break;
            }
        }

        /// <summary>Shared with BreastRigger: a bone that deforms nothing is not the one to drive.</summary>
        public static HashSet<Transform> WeightedBones(SkinnedMeshRenderer renderer)
        {
            var weighted = new HashSet<Transform>();
            if (renderer == null || renderer.sharedMesh == null)
                return weighted;
            var bones = renderer.bones;
            foreach (var weight in renderer.sharedMesh.boneWeights)
            {
                if (weight.weight0 > 0.001f && weight.boneIndex0 < bones.Length) weighted.Add(bones[weight.boneIndex0]);
                if (weight.weight1 > 0.001f && weight.boneIndex1 < bones.Length) weighted.Add(bones[weight.boneIndex1]);
                if (weight.weight2 > 0.001f && weight.boneIndex2 < bones.Length) weighted.Add(bones[weight.boneIndex2]);
                if (weight.weight3 > 0.001f && weight.boneIndex3 < bones.Length) weighted.Add(bones[weight.boneIndex3]);
            }
            weighted.Remove(null);
            return weighted;
        }
    }
}
