// Rename an arbitrary model's body bones to the names this game expects, using Unity's Humanoid
// mapping as the bridge.
//
// The game rebuilds the Avatar from whatever skeleton the mod ships and maps it **by bone name**, so
// until now the pipeline only accepted sources whose bones were already named like this game's —
// which is to say, sources from one other game. A Genshin rip calls the left thigh `Bip001 L Thigh`,
// an MMD model calls it `左足`, and neither gets an actor.
//
// Unity already solves exactly this problem: configure the model as Humanoid and its Avatar knows
// which transform is the left upper leg, whatever it is called. That is the one mapping nobody has
// to author — Unity's own auto-mapper handles Biped, Mixamo and MMD naming — and everything below
// is a fixed table from Unity's HumanBodyBones to this game's names, measured off a stock body
// (mdl_chr_hmsz-cstm-0059_body: 174 bones, of which these 55 are the body).
//
// What this does NOT touch is every other bone: skirts, ribbons, wings, hair. Humanoid has no
// concept of them, they keep the author's names, and ChainClassifier works out what they are from
// where they hang instead of from what they are called.
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace GakumasSdk
{
    public static class HumanoidBridge
    {
        // Public because AvatarBench builds the game's Avatar from the same table — the bench is only
        // worth anything if it maps bones exactly the way the actor build does.
        public static readonly (HumanBodyBones Bone, string Name)[] Map =
        {
            (HumanBodyBones.Hips, "Hips"),
            (HumanBodyBones.Spine, "Spine"),
            (HumanBodyBones.Chest, "Spine1"),
            (HumanBodyBones.UpperChest, "Spine2"),
            (HumanBodyBones.Neck, "Neck"),
            (HumanBodyBones.Head, "Head"),

            (HumanBodyBones.LeftShoulder, "LeftShoulder"),
            (HumanBodyBones.LeftUpperArm, "LeftArm"),
            (HumanBodyBones.LeftLowerArm, "LeftForeArm"),
            (HumanBodyBones.LeftHand, "LeftHand"),
            (HumanBodyBones.RightShoulder, "RightShoulder"),
            (HumanBodyBones.RightUpperArm, "RightArm"),
            (HumanBodyBones.RightLowerArm, "RightForeArm"),
            (HumanBodyBones.RightHand, "RightHand"),

            (HumanBodyBones.LeftUpperLeg, "LeftUpLeg"),
            (HumanBodyBones.LeftLowerLeg, "LeftLeg"),
            (HumanBodyBones.LeftFoot, "LeftFoot"),
            (HumanBodyBones.LeftToes, "LeftToeBase"),
            (HumanBodyBones.RightUpperLeg, "RightUpLeg"),
            (HumanBodyBones.RightLowerLeg, "RightLeg"),
            (HumanBodyBones.RightFoot, "RightFoot"),
            (HumanBodyBones.RightToes, "RightToeBase"),

            (HumanBodyBones.LeftThumbProximal, "LeftHandThumb1"),
            (HumanBodyBones.LeftThumbIntermediate, "LeftHandThumb2"),
            (HumanBodyBones.LeftThumbDistal, "LeftHandThumb3"),
            (HumanBodyBones.LeftIndexProximal, "LeftHandIndex1"),
            (HumanBodyBones.LeftIndexIntermediate, "LeftHandIndex2"),
            (HumanBodyBones.LeftIndexDistal, "LeftHandIndex3"),
            (HumanBodyBones.LeftMiddleProximal, "LeftHandMiddle1"),
            (HumanBodyBones.LeftMiddleIntermediate, "LeftHandMiddle2"),
            (HumanBodyBones.LeftMiddleDistal, "LeftHandMiddle3"),
            (HumanBodyBones.LeftRingProximal, "LeftHandRing1"),
            (HumanBodyBones.LeftRingIntermediate, "LeftHandRing2"),
            (HumanBodyBones.LeftRingDistal, "LeftHandRing3"),
            (HumanBodyBones.LeftLittleProximal, "LeftHandPinky1"),
            (HumanBodyBones.LeftLittleIntermediate, "LeftHandPinky2"),
            (HumanBodyBones.LeftLittleDistal, "LeftHandPinky3"),

            (HumanBodyBones.RightThumbProximal, "RightHandThumb1"),
            (HumanBodyBones.RightThumbIntermediate, "RightHandThumb2"),
            (HumanBodyBones.RightThumbDistal, "RightHandThumb3"),
            (HumanBodyBones.RightIndexProximal, "RightHandIndex1"),
            (HumanBodyBones.RightIndexIntermediate, "RightHandIndex2"),
            (HumanBodyBones.RightIndexDistal, "RightHandIndex3"),
            (HumanBodyBones.RightMiddleProximal, "RightHandMiddle1"),
            (HumanBodyBones.RightMiddleIntermediate, "RightHandMiddle2"),
            (HumanBodyBones.RightMiddleDistal, "RightHandMiddle3"),
            (HumanBodyBones.RightRingProximal, "RightHandRing1"),
            (HumanBodyBones.RightRingIntermediate, "RightHandRing2"),
            (HumanBodyBones.RightRingDistal, "RightHandRing3"),
            (HumanBodyBones.RightLittleProximal, "RightHandPinky1"),
            (HumanBodyBones.RightLittleIntermediate, "RightHandPinky2"),
            (HumanBodyBones.RightLittleDistal, "RightHandPinky3"),
        };

        /// <summary>Every name this game treats as body rather than garment.</summary>
        public static readonly HashSet<string> BodyBones = BuildBodyBoneSet();

        private static HashSet<string> BuildBodyBoneSet()
        {
            var set = new HashSet<string> { "Reference", "Pelvis" };
            foreach (var (_, name) in Map)
                set.Add(name);
            return set;
        }

        /// <summary>
        /// Renames the body bones and returns how many were mapped, or -1 when the model carries no
        /// Humanoid avatar — which is the author's job to fix, and the message says so.
        /// </summary>
        public static int Apply(GameObject root)
        {
            var animator = root.GetComponent<Animator>() ?? root.GetComponentInChildren<Animator>();
            if (animator == null || animator.avatar == null || !animator.avatar.isHuman)
            {
                Debug.LogError("[SDK] 模型没有 Humanoid Avatar。在 FBX 的 Import Settings → Rig 里把 "
                               + "Animation Type 设成 Humanoid（Configure 里确认骨映射），再来一次。"
                               + "骨名桥依赖它来认哪根骨是哪根。");
                return -1;
            }

            // Two passes: a source bone may already hold a target name while meaning something else
            // (a Genshin rip has its own `Head`), and renaming into an occupied name silently makes
            // two bones indistinguishable to everything downstream, which resolves by name.
            var mapped = new List<(Transform Transform, string Name)>();
            foreach (var (bone, name) in Map)
            {
                var transform = animator.GetBoneTransform(bone);
                if (transform != null)
                    mapped.Add((transform, name));
            }
            var claimed = new HashSet<string>();
            foreach (var (_, name) in mapped)
                claimed.Add(name);
            var displaced = 0;
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
            {
                if (!claimed.Contains(transform.name))
                    continue;
                if (mapped.Exists(entry => entry.Transform == transform))
                    continue;
                transform.name = $"{transform.name}_src";
                displaced++;
            }

            var renamed = 0;
            foreach (var (transform, name) in mapped)
            {
                if (transform.name == name)
                    continue;
                transform.name = name;
                renamed++;
            }

            EnsurePelvis(animator);
            EnsureSpine2(animator);
            Deduplicate(root);
            var missing = new List<string>();
            foreach (var (bone, name) in Map)
                if (animator.GetBoneTransform(bone) == null)
                    missing.Add(name);
            Debug.Log($"[SDK] Humanoid 骨名桥：映射 {mapped.Count} 根，改名 {renamed} 根"
                      + (displaced > 0 ? $"，让位 {displaced} 根同名骨" : ""));
            if (missing.Count > 0)
                Debug.LogWarning($"[SDK] Humanoid 里没有这些骨，依赖它们的组件会跳过: {string.Join(", ", missing)}");
            return mapped.Count;
        }

        // The actor build keys its bone map by name across every part of the character at once, so two
        // bones sharing a name is not cosmetic — it is the "An item with the same key has already been
        // added" that took a whole session to find the first time. Model files routinely carry a pair
        // of wrapper nodes named after the file, which is exactly such a collision.
        private static void Deduplicate(GameObject root)
        {
            var seen = new HashSet<string>();
            var renamed = new List<string>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
            {
                if (seen.Add(transform.name))
                    continue;
                var suffix = 2;
                while (!seen.Add($"{transform.name}_{suffix}"))
                    suffix++;
                renamed.Add($"{transform.name} → {transform.name}_{suffix}");
                transform.name = $"{transform.name}_{suffix}";
            }
            if (renamed.Count > 0)
                Debug.Log($"[SDK] 骨名去重 {renamed.Count} 处（跨部件必须唯一）：{string.Join(", ", renamed)}");
        }

        /// <summary>
        /// Stock runs Spine → Spine1 → Spine2 → { Neck, Shoulders }, and the game binds `Spine2` by
        /// name — it is where the chest driver lives and it is in REQUIRED_NODES. Unity's Humanoid
        /// calls it UpperChest and treats it as optional, so any two-spine rig arrives without one:
        /// an MMD standard skeleton has 上半身 / 上半身2 and nothing above them, which is every MMD
        /// model, not this one. Grow the node and slide the shoulders and neck under it; world
        /// placement is unchanged, so no vertex moves.
        /// </summary>
        private static void EnsureSpine2(Animator animator)
        {
            var spine1 = animator.GetBoneTransform(HumanBodyBones.Chest);
            if (spine1 == null || animator.GetBoneTransform(HumanBodyBones.UpperChest) != null
                || spine1.Find("Spine2") != null)
                return;

            var moving = new List<Transform>();
            foreach (Transform child in spine1)
                moving.Add(child);

            var spine2 = new GameObject("Spine2").transform;
            spine2.SetParent(spine1, worldPositionStays: false);
            spine2.localPosition = Vector3.zero;
            spine2.localRotation = Quaternion.identity;
            spine2.localScale = Vector3.one;
            foreach (var child in moving)
                child.SetParent(spine2, worldPositionStays: true);
            Debug.Log($"[SDK] 补了 Spine2 节点：Spine1 → Spine2 → {{{string.Join(", ", moving.Select(c => c.name))}}}"
                      + "（原版拓扑；胸部驱动和必需节点都认这根）");
        }

        // Stock skeletons run Hips → Pelvis → { LeftUpLeg, RightUpLeg }, and the hem chains hang off
        // Pelvis — it is where 758 of 1537 stock swing chains are anchored. Humanoid has no such
        // bone (its Hips *is* the pelvis), so a bridged skeleton would leave every cage entry and
        // chain anchor that names it unresolved. Growing the node keeps the world placement.
        private static void EnsurePelvis(Animator animator)
        {
            var hips = animator.GetBoneTransform(HumanBodyBones.Hips);
            if (hips == null || hips.Find("Pelvis") != null)
                return;
            var pelvis = new GameObject("Pelvis").transform;
            pelvis.SetParent(hips, worldPositionStays: false);
            pelvis.localPosition = Vector3.zero;
            pelvis.localRotation = Quaternion.identity;
            pelvis.localScale = Vector3.one;

            foreach (var bone in new[] { HumanBodyBones.LeftUpperLeg, HumanBodyBones.RightUpperLeg })
            {
                var leg = animator.GetBoneTransform(bone);
                if (leg != null && leg.parent == hips)
                    leg.SetParent(pelvis, worldPositionStays: true);
            }
            Debug.Log("[SDK] 补了 Pelvis 节点：Hips → Pelvis → 双腿（原版拓扑，摇物链和碰撞笼都认这根）");
        }
    }
}
