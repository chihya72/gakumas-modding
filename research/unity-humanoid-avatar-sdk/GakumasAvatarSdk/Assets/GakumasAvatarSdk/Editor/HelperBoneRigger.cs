// The corrective helper bones every stock body skins its joints to, and the weight split that makes
// them do anything.
//
// Linear blend skinning collapses a joint that rotates far — the game rests the arms in a T and
// stands them at the side, 67° away, and a vertex weighted half to the shoulder and half to the
// rotated arm lands inside the limb. This game does not solve that with a wide weight band. It
// solves it with corrective bones: `Arm_H` counter-rotates 80% of the shoulder's own muscle, so the
// deltoid only ever sees 20% of the rotation, and `Arm_Roll_H` spreads the remaining twist down the
// arm. QuartzDriverRigger has driven them all along; nothing imported ever had the bones.
//
// Measured off the shipped bodies by tools/measure_helper_rig.py — 530/530 carry all eight per side,
// 17% of a body's whole weight mass sits on them, and at the shoulder joint the humanoid `Arm`
// carries *none*. Both tables below are medians over 1060 limbs and the placements are identical to
// four decimals across every costume: these are middleware constants, not per-costume art.
//
// What this does NOT do is trust the source's own twist bones. A rip usually has some — this one
// has `+UpperArmTwist L A01/A02` and `Bone_ForearmTwistA01_L`, carrying twice what the humanoid arm
// bone does — but nothing in this game drives them, so they ride rigidly with the parent and pull
// the collapse right back in. Their placement follows their home game's rig, not this one's, so
// adopting them by name would be guessing at semantics. They get folded back into the humanoid bone
// and redistributed by the target's rules, which is the same layering the rest of the pipeline uses.
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class HelperBoneRigger
    {
        /// <summary>A limb bone, the child that defines its axis, and the helpers carved out of it.</summary>
        private class Family
        {
            public string Bone;
            public string Child;
            public string[] Helpers;
            /// <summary>Where each helper sits, as a fraction of the bone towards its child.</summary>
            public float[] Placement;
            /// <summary>Ten buckets along the bone; each row is the split across {Bone} ∪ Helpers.</summary>
            public float[][] Profile;
        }

        private static readonly Family[] Families =
        {
            new Family
            {
                Bone = "{0}Arm", Child = "{0}ForeArm",
                Helpers = new[] { "{0}Arm_H", "{0}Arm_Roll_H" },
                Placement = new[] { 0.000f, 0.605f },
                Profile = new[]
                {
                    new[] { 0.00f, 0.99f, 0.01f }, new[] { 0.00f, 0.92f, 0.08f },
                    new[] { 0.00f, 0.81f, 0.19f }, new[] { 0.00f, 0.63f, 0.37f },
                    new[] { 0.00f, 0.48f, 0.52f }, new[] { 0.00f, 0.15f, 0.85f },
                    new[] { 0.16f, 0.02f, 0.82f }, new[] { 0.54f, 0.01f, 0.45f },
                    new[] { 0.72f, 0.00f, 0.28f }, new[] { 0.77f, 0.00f, 0.23f },
                },
            },
            new Family
            {
                Bone = "{0}ForeArm", Child = "{0}Hand",
                // Hand_H hangs off the forearm but is driven by the *hand*: it is the wrist's
                // corrective, and at the wrist it carries the forearm's entire share.
                Helpers = new[] { "{0}ForeArm_H", "{0}ForeArm_Roll_H", "{0}Hand_H" },
                Placement = new[] { 0.000f, 0.581f, 0.910f },
                Profile = new[]
                {
                    new[] { 0.50f, 0.49f, 0.01f, 0.00f }, new[] { 0.89f, 0.04f, 0.07f, 0.00f },
                    new[] { 0.82f, 0.00f, 0.18f, 0.00f }, new[] { 0.61f, 0.00f, 0.39f, 0.00f },
                    new[] { 0.30f, 0.00f, 0.70f, 0.00f }, new[] { 0.07f, 0.00f, 0.89f, 0.04f },
                    new[] { 0.00f, 0.00f, 0.82f, 0.18f }, new[] { 0.00f, 0.00f, 0.58f, 0.42f },
                    new[] { 0.00f, 0.00f, 0.25f, 0.75f }, new[] { 0.00f, 0.00f, 0.00f, 1.00f },
                },
            },
            new Family
            {
                Bone = "{0}UpLeg", Child = "{0}Leg",
                Helpers = new[] { "{0}UpLeg_H", "{0}UpLeg_Roll_H" },
                Placement = new[] { 0.000f, 0.360f },
                Profile = new[]
                {
                    new[] { 0.00f, 0.93f, 0.07f }, new[] { 0.00f, 0.79f, 0.21f },
                    new[] { 0.00f, 0.51f, 0.49f }, new[] { 0.01f, 0.24f, 0.75f },
                    new[] { 0.12f, 0.04f, 0.84f }, new[] { 0.37f, 0.00f, 0.63f },
                    new[] { 0.73f, 0.00f, 0.27f }, new[] { 0.91f, 0.00f, 0.09f },
                    new[] { 0.99f, 0.00f, 0.01f }, new[] { 1.00f, 0.00f, 0.00f },
                },
            },
            new Family
            {
                // The knee's corrective only owns the joint itself; the shin is all humanoid bone.
                Bone = "{0}Leg", Child = "{0}Foot",
                Helpers = new[] { "{0}Leg_H" },
                Placement = new[] { 0.000f },
                Profile = new[]
                {
                    new[] { 0.71f, 0.29f }, new[] { 1.00f, 0.00f }, new[] { 1.00f, 0.00f },
                    new[] { 1.00f, 0.00f }, new[] { 1.00f, 0.00f }, new[] { 1.00f, 0.00f },
                    new[] { 1.00f, 0.00f }, new[] { 1.00f, 0.00f }, new[] { 1.00f, 0.00f },
                    new[] { 1.00f, 0.00f },
                },
            },
        };

        // A rip's own twist bones, by the naming every rig in the wild uses. Folded into the humanoid
        // bone they hang off, never driven where they are.
        private static readonly string[] TwistNames = { "twist", "roll" };

        // What the game's own skinning runs at, and what every stock mesh is authored to.
        private const int MaxInfluences = 4;

        /// <summary>Creates the corrective bones and moves the joint weight onto them.</summary>
        public static int Rig(GameObject root)
        {
            var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            if (renderer == null || renderer.sharedMesh == null)
            {
                Debug.LogWarning("[SDK] 矫正骨：没有 SkinnedMeshRenderer，跳过");
                return 0;
            }

            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                byName[transform.name] = transform;

            var created = new List<Transform>();
            var present = new List<string>();
            foreach (var family in Families)
                foreach (var side in new[] { "Left", "Right" })
                {
                    var bone = Named(byName, family.Bone, side);
                    var child = Named(byName, family.Child, side);
                    if (bone == null || child == null)
                    {
                        Debug.LogWarning($"[SDK] 矫正骨：缺 {string.Format(family.Bone, side)} 或其子骨，跳过这一段");
                        continue;
                    }
                    for (var index = 0; index < family.Helpers.Length; index++)
                    {
                        var name = string.Format(family.Helpers[index], side);
                        if (byName.ContainsKey(name))
                        {
                            // A source from the same middleware ships its own — sucu has eight.
                            present.Add(name);
                            continue;
                        }
                        var helper = new GameObject(name).transform;
                        helper.SetParent(bone, false);
                        helper.position = Vector3.Lerp(bone.position, child.position, family.Placement[index]);
                        helper.rotation = bone.rotation;
                        helper.localScale = Vector3.one;
                        byName[name] = helper;
                        created.Add(helper);
                    }
                }

            if (created.Count == 0)
            {
                Debug.Log($"[SDK] 矫正骨：骨架已带 {present.Count} 根 `_H`，不再新建");
                return 0;
            }

            Redistribute(renderer, byName, created);
            Debug.Log($"[SDK] 矫正骨装配完成: 新建 {created.Count} 根（{string.Join(", ", created.Select(c => c.name))}）"
                      + (present.Count > 0 ? $"，源自带 {present.Count} 根保留" : ""));
            return created.Count;
        }

        private static Transform Named(IReadOnlyDictionary<string, Transform> byName, string pattern, string side) =>
            byName.TryGetValue(string.Format(pattern, side), out var bone) ? bone : null;

        /// <summary>Moves each limb bone's weight onto its helpers, following the stock profile.</summary>
        private static void Redistribute(SkinnedMeshRenderer renderer, IReadOnlyDictionary<string, Transform> byName,
                                         List<Transform> created)
        {
            var mesh = renderer.sharedMesh;
            var bones = renderer.bones.ToList();
            var bindposes = mesh.bindposes.ToList();
            var slot = new Dictionary<Transform, int>();
            for (var index = 0; index < bones.Count; index++)
                if (bones[index] != null)
                    slot[bones[index]] = index;

            var toLocal = renderer.transform.worldToLocalMatrix;
            foreach (var helper in created)
            {
                slot[helper] = bones.Count;
                bones.Add(helper);
                bindposes.Add(helper.worldToLocalMatrix * renderer.transform.localToWorldMatrix);
            }

            // Fold the source's own twist bones into the humanoid bone above them first: they hold
            // real weight (0.36% of this model on the upper arms alone, twice what the arm bone
            // holds) and nothing here drives them, so left alone they ride rigidly and put back the
            // collapse the helpers exist to remove.
            var fold = new int[bones.Count];
            for (var index = 0; index < bones.Count; index++)
                fold[index] = index;
            var folded = new List<string>();
            foreach (var family in Families)
                foreach (var side in new[] { "Left", "Right" })
                {
                    var bone = Named(byName, family.Bone, side);
                    var child = Named(byName, family.Child, side);
                    if (bone == null || !slot.TryGetValue(bone, out var target))
                        continue;
                    foreach (var descendant in bone.GetComponentsInChildren<Transform>(true))
                    {
                        if (descendant == bone || !slot.TryGetValue(descendant, out var index))
                            continue;
                        // Stop at the next humanoid joint: its own twist bones are its business.
                        if (child != null && (descendant == child || descendant.IsChildOf(child)))
                            continue;
                        // `Arm_Roll_H` matches "roll" too, and folding a corrective bone into the
                        // bone it corrects undoes the whole point — on a re-shaped prefab, or on a
                        // source from this middleware, that would quietly wipe the rig it already had.
                        if (descendant.name.EndsWith("_H"))
                            continue;
                        var lower = descendant.name.ToLowerInvariant();
                        if (!TwistNames.Any(lower.Contains))
                            continue;
                        fold[index] = target;
                        folded.Add(descendant.name);
                    }
                }

            // Which helper each family's weight can go to, in the profile's own column order.
            var plans = new List<(int Bone, Vector3 Origin, Vector3 Axis, float Length, int[] Column, float[][] Profile)>();
            foreach (var family in Families)
                foreach (var side in new[] { "Left", "Right" })
                {
                    var bone = Named(byName, family.Bone, side);
                    var child = Named(byName, family.Child, side);
                    if (bone == null || child == null || !slot.TryGetValue(bone, out var boneSlot))
                        continue;
                    var origin = toLocal.MultiplyPoint3x4(bone.position);
                    var tip = toLocal.MultiplyPoint3x4(child.position);
                    var axis = tip - origin;
                    if (axis.sqrMagnitude < 1e-8f)
                        continue;
                    var column = new int[family.Helpers.Length + 1];
                    column[0] = boneSlot;
                    for (var index = 0; index < family.Helpers.Length; index++)
                        column[index + 1] = slot.TryGetValue(byName[string.Format(family.Helpers[index], side)],
                                                             out var helperSlot) ? helperSlot : -1;
                    plans.Add((boneSlot, origin, axis.normalized, axis.magnitude, column, family.Profile));
                }
            var planOf = new Dictionary<int, int>();
            for (var index = 0; index < plans.Count; index++)
                planOf[plans[index].Bone] = index;

            var vertices = mesh.vertices;
            var perVertex = mesh.GetBonesPerVertex();
            var weights = mesh.GetAllBoneWeights();
            var newCounts = new List<byte>(vertices.Length);
            var newWeights = new List<BoneWeight1>(weights.Length);
            var moved = 0f;
            var total = 0f;
            var clipped = 0;

            var cursor = 0;
            var bucket = new Dictionary<int, float>();
            for (var vertex = 0; vertex < vertices.Length; vertex++)
            {
                var influences = vertex < perVertex.Length ? perVertex[vertex] : 0;
                bucket.Clear();
                for (var i = 0; i < influences; i++, cursor++)
                {
                    var weight = weights[cursor];
                    if (weight.weight <= 0f)
                        continue;
                    total += weight.weight;
                    var index = fold[weight.boneIndex];
                    if (!planOf.TryGetValue(index, out var which))
                    {
                        Accumulate(bucket, index, weight.weight);
                        continue;
                    }
                    var plan = plans[which];
                    var t = Vector3.Dot(vertices[vertex] - plan.Origin, plan.Axis) / plan.Length;
                    var share = Sample(plan.Profile, t);
                    for (var column = 0; column < share.Length; column++)
                    {
                        if (share[column] <= 0f || plan.Column[column] < 0)
                            continue;
                        Accumulate(bucket, plan.Column[column], weight.weight * share[column]);
                        if (column > 0)
                            moved += weight.weight * share[column];
                    }
                }

                // Descending order and at most four, which is what the game skins with and what every
                // stock mesh ships; a fifth influence would be dropped silently at load.
                var ordered = bucket.OrderByDescending(entry => entry.Value).ToList();
                if (ordered.Count > MaxInfluences)
                {
                    ordered = ordered.Take(MaxInfluences).ToList();
                    clipped++;
                }
                var sum = ordered.Sum(entry => entry.Value);
                if (sum <= 0f)
                {
                    newCounts.Add(0);
                    continue;
                }
                newCounts.Add((byte)ordered.Count);
                foreach (var entry in ordered)
                    newWeights.Add(new BoneWeight1 { boneIndex = entry.Key, weight = entry.Value / sum });
            }
            perVertex.Dispose();
            weights.Dispose();

            using (var counts = new Unity.Collections.NativeArray<byte>(newCounts.ToArray(), Unity.Collections.Allocator.Temp))
            using (var flat = new Unity.Collections.NativeArray<BoneWeight1>(newWeights.ToArray(), Unity.Collections.Allocator.Temp))
                mesh.SetBoneWeights(counts, flat);
            mesh.bindposes = bindposes.ToArray();
            renderer.bones = bones.ToArray();
            EditorUtility.SetDirty(mesh);
            EditorUtility.SetDirty(renderer);

            if (folded.Count > 0)
                Debug.Log($"[SDK] 矫正骨：源自带的 {folded.Count} 根扭转骨权重已折回主骨"
                          + $"（{string.Join(", ", folded.Distinct())}），再按目标规矩重分配");
            // Stock sits at 17%, but that is not a target to hit: it counts what stock puts on its
            // limb bones in the first place, and a rip that hangs the same geometry off `Shoulder`
            // or `Hand` instead has less to move and needs to move less. What matters is that the
            // joints themselves came off the humanoid bone, which audit_body_bundle.py measures
            // per joint. Only a near-zero here means the redistribution did not run at all.
            Debug.Log($"[SDK] 矫正骨：{moved / Mathf.Max(total, 1e-6f) * 100:F1}% 的全身权重已移到矫正骨上"
                      + $"（原版量级 17%，随源模型权重分布不同）"
                      + $"{(clipped > 0 ? $"，{clipped} 个顶点超过 4 骨已截断" : "")}");
            if (moved / Mathf.Max(total, 1e-6f) < 0.01f)
                Debug.LogWarning("[SDK] 矫正骨：几乎没有权重移过去，关节还压在人形骨上");
        }

        private static void Accumulate(IDictionary<int, float> bucket, int index, float weight) =>
            bucket[index] = bucket.TryGetValue(index, out var existing) ? existing + weight : weight;

        /// <summary>The profile between bucket centres; flat outside the bone's own span.</summary>
        private static float[] Sample(IReadOnlyList<float[]> profile, float t)
        {
            var scaled = Mathf.Clamp(t, 0f, 1f) * profile.Count - 0.5f;
            var low = Mathf.Clamp(Mathf.FloorToInt(scaled), 0, profile.Count - 1);
            var high = Mathf.Clamp(low + 1, 0, profile.Count - 1);
            var blend = Mathf.Clamp01(scaled - low);
            var result = new float[profile[low].Length];
            for (var index = 0; index < result.Length; index++)
                result[index] = Mathf.Lerp(profile[low][index], profile[high][index], blend);
            return result;
        }
    }
}
