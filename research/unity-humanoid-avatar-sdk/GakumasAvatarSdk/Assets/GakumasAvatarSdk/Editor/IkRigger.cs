// Create the full-body IK anchors the actor build expects.
//
// CampusActorAnimationJob.CreateFullBodyIK binds these transforms into the animation stream, so a
// body without them fails with "ArgumentNullException: Parameter name: transform" and hangs the
// load. Stock bodies carry all ten as direct children of the body root; the layout below is copied
// from mdl_chr_chs-sucu-00_body.
using System.Collections.Generic;
using System.Linq;
using ActorAnimation;
using UnityEngine;
using VL.IK;

namespace GakumasSdk
{
    public static class IkRigger
    {
        // Values match UnityEngine.AvatarIKGoal / AvatarIKHint.
        private static readonly (string Name, int Goal)[] Goals =
        {
            ("IKGoal_LeftFoot", 0), ("IKGoal_RightFoot", 1),
            ("IKGoal_LeftHand", 2), ("IKGoal_RightHand", 3),
        };

        private static readonly (string Name, int Hint)[] Hints =
        {
            ("IKHint_LeftKnee", 0), ("IKHint_RightKnee", 1),
            ("IKHint_LeftElbow", 2), ("IKHint_RightElbow", 3),
        };

        public static void Rig(GameObject root)
        {
            EnsureReference(root);
            AdoptStrays(root);
            foreach (var (name, goal) in Goals)
                Create(root, name).AddComponent<IKGoalEffector>().goal = goal;
            foreach (var (name, hint) in Hints)
                Create(root, name).AddComponent<IKHintEffector>().hint = hint;
            Create(root, "IKBody").AddComponent<IKBodyEffector>();
            Create(root, "LookAt").AddComponent<LookAtEffector>();
            // Bare transform, no component — but ActorAnimationFullBodyIKMovePart binds it, and
            // without it CreateFullBodyIK throws on a null transform and the load never finishes.
            Create(root, "Move");
            RigCorrection(root);
            Debug.Log($"[SDK] IK 装配完成: {Goals.Length} goal + {Hints.Length} hint + IKBody + LookAt + Move");
        }

        // Stock bodies sit Hips under a `Reference` node — root → Reference → { Hips,
        // BodyScaleRatio_DIS } — and the actor build takes Reference as the actor's reference
        // transform (`CampusActorAnimationInitializeData.reference`, and the renderer's root bone
        // path is .../Root_Body/Reference/Hips). A model authored anywhere else arrives with Hips at
        // its root, so grow the node and slide Hips underneath, world placement unchanged.
        //
        // BodyScaleRatio_DIS is deliberately *not* synthesised: it carries no weights and nothing in
        // the game looks it up, it is simply a bone the source asset happened to have.
        private static void EnsureReference(GameObject root)
        {
            if (root.transform.Find("Reference") != null)
                return;
            var hips = Find(root, "Hips").transform;
            var reference = Create(root, "Reference").transform;
            hips.SetParent(reference, worldPositionStays: true);
            Debug.Log("[SDK] 补了 Reference 节点：root → Reference → Hips（原版结构）");
        }

        /// <summary>
        /// Bring weighted bones that got left outside `Reference` along with Hips.
        ///
        /// `EnsureReference` slides Hips under the new node. A bone that hung off the *source file's*
        /// own root rather than off a humanoid bone does not come with it, and the game animates
        /// nothing outside Reference — so those vertices stay pinned to the actor's root object while
        /// the animated body walks away from them, and the skin opens up until the character arrives.
        ///
        /// Measured on the Genshin rip: exactly one such bone, `+PelvisTwist CF A01` under `Bip001`,
        /// holding 0.86% of the body's weight over 392 vertices across the pelvis, lower belly and
        /// thigh tops. That is the hole at the waist while walking.
        ///
        /// Where a stray goes is read off the mesh rather than guessed from position: the bone it
        /// shares the most vertex weight with is the one whose geometry it deforms alongside.
        /// </summary>
        private static void AdoptStrays(GameObject root)
        {
            var reference = root.transform.Find("Reference");
            var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            if (reference == null || renderer == null || renderer.sharedMesh == null)
                return;

            var bones = renderer.bones;
            var weights = renderer.sharedMesh.boneWeights;
            var strays = new Dictionary<int, Dictionary<int, float>>();
            for (var index = 0; index < bones.Length; index++)
                if (bones[index] != null && !bones[index].IsChildOf(reference))
                    strays[index] = new Dictionary<int, float>();
            if (strays.Count == 0)
                return;

            foreach (var weight in weights)
            {
                var slots = new[]
                {
                    (weight.boneIndex0, weight.weight0), (weight.boneIndex1, weight.weight1),
                    (weight.boneIndex2, weight.weight2), (weight.boneIndex3, weight.weight3),
                };
                foreach (var (index, value) in slots)
                {
                    if (value <= 0f || !strays.TryGetValue(index, out var shared))
                        continue;
                    foreach (var (other, amount) in slots)
                        if (amount > 0f && other != index && !strays.ContainsKey(other))
                            shared[other] = (shared.TryGetValue(other, out var had) ? had : 0f) + amount;
                }
            }

            var hips = root.GetComponentsInChildren<Transform>(true)
                .FirstOrDefault(t => t.name == "Hips" && t.IsChildOf(reference));
            var moved = new List<string>();
            foreach (var (index, shared) in strays)
            {
                // Not "whichever bone shares the most" — a bone sitting on the body's centre line
                // splits its co-weight between the two mirrored bones it spans, and the winner is
                // decided by noise. `+PelvisTwist CF A01` measures RightUpLeg 42.8% / LeftUpLeg 35.7%,
                // and parenting a pelvis bone to one thigh makes the belly follow that leg. So take
                // everything that shares comparably and hand the bone to their common ancestor —
                // which for those two is `Pelvis`, exactly where a pelvis twist belongs.
                var host = hips;
                if (shared.Count > 0)
                {
                    var top = shared.Max(pair => pair.Value);
                    var contenders = shared.Where(pair => pair.Value >= top * 0.5f)
                        .Select(pair => pair.Key)
                        .Where(slot => slot < bones.Length && bones[slot] != null)
                        .Select(slot => bones[slot])
                        .ToList();
                    host = CommonAncestor(contenders, reference) ?? host;
                }
                if (host == null || bones[index].IsChildOf(host))
                    continue;
                moved.Add($"{bones[index].name}→{host.name}");
                bones[index].SetParent(host, worldPositionStays: true);
            }
            if (moved.Count > 0)
                Debug.Log($"[SDK] {moved.Count} 根有权重的骨掉在 Reference 子树外面（游戏不驱动那里，"
                          + $"角色一走这块皮就留在原地），已按共同权重认领回去：{string.Join(", ", moved)}");
        }

        /// <summary>Deepest node that is an ancestor of (or is) every one of these bones.</summary>
        private static Transform CommonAncestor(List<Transform> bones, Transform limit)
        {
            if (bones.Count == 0)
                return null;
            var candidate = bones[0];
            while (candidate != null && candidate != limit.parent
                   && !bones.All(bone => bone == candidate || bone.IsChildOf(candidate)))
                candidate = candidate.parent;
            return candidate == null || candidate == limit.parent ? null : candidate;
        }

        // The hand correction goals are the one part of the IK wiring that hangs off bones instead
        // of root-level anchors, and the only part whose absence kills the run: see
        // ActorAnimationIKCorrectionGoal for why a null goal aborts inside the Burst job.
        private static void RigCorrection(GameObject root)
        {
            // Values read off live stock actors (fktn / jsna / atbm all agree on everything except
            // the hip volume, which follows the costume): goal radius 0.06, hips capsule weight 0.75
            // and dampArea 0.01. radius / radiusSub / length are fktn's — 0.1/0.18/0.2 sits in the
            // middle of the three, and they are the knobs to touch if the hands clip the skirt.
            foreach (var (bone, goal) in new[] { ("LeftHand", 2), ("RightHand", 3) })
            {
                var component = Find(root, bone).AddComponent<ActorAnimationIKCorrectionGoal>();
                component.goal = goal;
                component.enable = true;
                component.radius = 0.06f;
            }

            var collider = Find(root, "Hips").AddComponent<ActorAnimationIKCorrectionCollider>();
            collider.type = 1; // Capsule
            collider.weight = 0.75f;
            collider.radius = 0.1f;
            collider.radiusSub = 0.18f;
            collider.dampArea = 0.01f;
            collider.length = 0.2f;
            Debug.Log("[SDK] IK 修正装配完成: LeftHand/RightHand goal + Hips collider");
        }

        private static GameObject Find(GameObject root, string bone)
        {
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                if (transform.name == bone)
                    return transform.gameObject;
            throw new System.InvalidOperationException($"[SDK] 骨架里找不到 {bone}，IK 修正无法装配");
        }

        private static GameObject Create(GameObject root, string name)
        {
            var node = new GameObject(name);
            node.transform.SetParent(root.transform, false);
            return node;
        }
    }
}
