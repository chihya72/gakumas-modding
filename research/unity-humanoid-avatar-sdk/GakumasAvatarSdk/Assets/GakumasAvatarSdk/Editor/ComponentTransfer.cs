// Carry the source model's own rig over, instead of rebuilding one from stock medians.
//
// The riggers in this folder derive every swing parameter from the median of 530 stock costumes.
// That is the right answer for a source that ships no rig — an MMD or VRM model — and the wrong one
// for a source that does. IDOLY PRIDE's chs-sucu-00 carries 42 tuned dynamic bones, 12 colliders, a
// breast driver and 22 pose drivers, authored for this exact garment, and the medians miss them by
// up to 7x (its accessory strand: mass 0.1 vs our 0.7, spring 0.8 vs 0.3, limitX ±3 vs locked 0).
// Six of this route's bugs came from guessing values the source already had. See
// docs/component-transfer-route.md.
//
// This runs *after* the riggers and overwrites what the source knows better, rather than replacing
// them: a bone the manifest does not mention keeps its synthesised values, and the target-only
// fields (`wind`, `rootWeight`, `pendulum`, `resetType`, `modelingTransform` — gakumas has them,
// IDOLY PRIDE does not) stay as the stock tables set them. One code path, no fallback branch.
//
// What is deliberately NOT transferred:
//   collisionMask   a channel convention, not a value. Both games ship -1 on the bone side, but the
//                   target's cage assigns real channels, and -1 there means a skirt collides with
//                   the 0.23 m `Hips` capsule and gets held off the leg. Target's table wins.
//   IK effectors    the SDK synthesises all ten and both sides carry the same fixed table.
//   `*_H` drivers   the target's own humanoid convention, on 528/530 stock bodies.
using System;
using System.Collections.Generic;
using System.IO;
using ActorAnimation;
using Unity.Mathematics;
using UnityEngine;

namespace GakumasSdk
{
    public static class ComponentTransfer
    {
        [Serializable]
        public class DynamicBoneEntry
        {
            public string bone;
            public float damping, stiffness, spring, mass;
            public int useWindGlobalForce;
            public int colliderType, colliderMask;
            public float[] colliderVectorA, colliderVectorB;
            public float colliderRadius, colliderRadiusSub;
            public int useLimit;
            public float[] limitX, limitY, limitZ;
        }

        [Serializable]
        public class StaticBoneEntry
        {
            public string bone;
            public int type, mask;
            public float[] vectorA, vectorB;
            public float radius, radiusSub;
        }

        [Serializable]
        public class CurveKey
        {
            public float time, value, inSlope, outSlope;
        }

        [Serializable]
        public class BreastBoneEntry
        {
            public string bone;
            public float damping, stiffness, spring, average;
            public int useArmCorrection, useLimit;
            public float[] limitX, limitY, limitZ;
            public int colliderType, colliderMask;
            public float colliderRadius, colliderRadiusSub;
            public string leftBreast, rightBreast, leftBreastEnd, rightBreastEnd, leftLowerArm, rightLowerArm;
            public CurveKey[] upCurve, sideCurve;
        }

        [Serializable]
        public class RotationDriverEntry
        {
            public string bone, reference;
            public int rotationOrder;
            public float[] coefficient, limitMin, limitMax;
        }

        [Serializable]
        public class Manifest
        {
            public string source;
            public DynamicBoneEntry[] dynamicBones;
            public StaticBoneEntry[] staticBones;
            public BreastBoneEntry[] breastBones;
            public RotationDriverEntry[] rotationDrivers;
            public string[] skipped;
        }

        [Serializable]
        public class RangeEntry
        {
            public string klass, field;
            public float min, max, median;
            public int samples;
        }

        [Serializable]
        public class RangeTable
        {
            public RangeEntry[] entries;
        }

        // Same field name is not the same units. A source value outside everything the target game
        // itself ever ships is the signal that the two solvers disagree about that field — measured,
        // not assumed: over 529 stock breast drivers this game only uses damping 0.20-0.35 and
        // stiffness 0.06-0.12, and IDOLY PRIDE's arrives at 0.15 / 0.03. Transferred as-is it is
        // under-damped and jitters forever. All 42 of that same model's swing bones land inside
        // range, so this clamp is a no-op for them — it bites exactly what is broken.
        //
        // Ranges live in reference/target-value-ranges.json (tools/inventory_target_ranges.py), so
        // the SDK and the verifier read one copy. Only solver parameters are clamped; collider radii,
        // angle limits and bone references are per-garment geometry and transfer untouched.
        private static Dictionary<string, RangeEntry> _ranges;

        private static float Clamp(string klass, string field, float value, List<string> clamped)
        {
            if (_ranges == null)
            {
                _ranges = new Dictionary<string, RangeEntry>();
                var path = "../reference/target-value-ranges.json";
                if (File.Exists(path))
                    foreach (var entry in JsonUtility.FromJson<RangeTable>(File.ReadAllText(path)).entries)
                        _ranges[$"{entry.klass}.{entry.field}"] = entry;
                else
                    Debug.LogWarning($"[SDK] 找不到 {path}，搬运不做取值域夹取");
            }
            if (!_ranges.TryGetValue($"{klass}.{field}", out var range))
                return value;
            var result = Mathf.Clamp(value, range.min, range.max);
            if (!Mathf.Approximately(result, value))
                clamped.Add($"{field} {value:0.###}→{result:0.###}（目标域 {range.min:0.###}~{range.max:0.###}）");
            return result;
        }

        /// <summary>Applies the manifest if there is one. Returns false when the source ships no rig.</summary>
        public static bool Apply(GameObject root, string manifestPath)
        {
            if (!File.Exists(manifestPath))
            {
                Debug.Log($"[SDK] 没有源组件清单（{manifestPath}），沿用按原版中位数合成的 rig");
                return false;
            }

            var manifest = JsonUtility.FromJson<Manifest>(File.ReadAllText(manifestPath));
            var bones = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                bones[transform.name] = transform;

            var missing = new List<string>();
            var clamped = new List<string>();
            var counts = new Dictionary<string, int>();
            void Count(string key) => counts[key] = counts.GetValueOrDefault(key) + 1;

            Transform Bone(string name)
            {
                if (name != null && bones.TryGetValue(name, out var transform))
                    return transform;
                if (!string.IsNullOrEmpty(name) && !missing.Contains(name))
                    missing.Add(name);
                return null;
            }

            foreach (var entry in manifest.dynamicBones ?? Array.Empty<DynamicBoneEntry>())
            {
                var bone = Bone(entry.bone);
                if (bone == null)
                    continue;
                var component = bone.GetComponent<ActorSwingDynamicBone>();
                if (component == null)
                {
                    // The rigger walks `_S` strands; a source bone outside that naming never got one.
                    Debug.LogWarning($"[SDK] {entry.bone} 不在摇物链里（名字不以 _S 结尾？），源参数无处可搬");
                    continue;
                }
                const string dynamic = "ActorSwingDynamicBone";
                component.damping = Clamp(dynamic, "damping", entry.damping, clamped);
                component.stiffness = Clamp(dynamic, "stiffness", entry.stiffness, clamped);
                component.spring = Clamp(dynamic, "spring", entry.spring, clamped);
                component.mass = Clamp(dynamic, "mass", entry.mass, clamped);
                component.useWindGlobalForce = entry.useWindGlobalForce != 0;
                component.limitInfo = new LimitInfo
                {
                    useLimit = entry.useLimit,
                    axisX = Int2(entry.limitX),
                    axisY = Int2(entry.limitY),
                    axisZ = Int2(entry.limitZ),
                };
                component.dynamicCollider = new ActorSwingDynamicCollider
                {
                    type = (byte)entry.colliderType,
                    // Channel stays the target's; see the header.
                    collisionMask = component.dynamicCollider?.collisionMask ?? -1,
                    vector3_A = Vec(entry.colliderVectorA),
                    vector3_B = Vec(entry.colliderVectorB),
                    float_A = entry.colliderRadius,
                    float_B = entry.colliderRadiusSub,
                };
                Count("摇物骨");
            }

            if ((manifest.staticBones?.Length ?? 0) > 0)
            {
                // The cage is all-or-nothing: ours is a union across stock costumes, the source's is
                // what this garment was authored against. Mixing them is how a 0.23 m capsule nobody
                // asked for ends up holding the hem off the thigh.
                var synthesized = 0;
                foreach (var existing in root.GetComponentsInChildren<ActorSwingStaticBone>(true))
                {
                    UnityEngine.Object.DestroyImmediate(existing);
                    synthesized++;
                }
                foreach (var entry in manifest.staticBones)
                {
                    var bone = Bone(entry.bone);
                    if (bone == null)
                        continue;
                    bone.gameObject.AddComponent<ActorSwingStaticBone>().staticCollider = new ActorSwingStaticCollider
                    {
                        type = (byte)entry.type,
                        collisionMask = entry.mask,
                        vector3_A = Vec(entry.vectorA),
                        vector3_B = Vec(entry.vectorB),
                        float_A = entry.radius,
                        float_B = entry.radiusSub,
                    };
                    Count("静态碰撞体");
                }
                Debug.Log($"[SDK] 碰撞笼换成源模型自带的：拆掉合成的 {synthesized} 个，装上源的 {counts.GetValueOrDefault("静态碰撞体")} 个");
            }

            foreach (var entry in manifest.breastBones ?? Array.Empty<BreastBoneEntry>())
            {
                var bone = Bone(entry.bone);
                var component = bone == null ? null : bone.GetComponent<ActorSwingBreastBone>();
                if (component == null)
                {
                    Debug.LogWarning($"[SDK] {entry.bone} 上没有胸部驱动，源参数无处可搬");
                    continue;
                }
                const string breast = "ActorSwingBreastBone";
                component.damping = Clamp(breast, "damping", entry.damping, clamped);
                component.stiffness = Clamp(breast, "stiffness", entry.stiffness, clamped);
                component.spring = Clamp(breast, "spring", entry.spring, clamped);
                component.average = Clamp(breast, "average", entry.average, clamped);
                component.useArmCorrection = entry.useArmCorrection != 0;
                component.limitInfo = new LimitInfo
                {
                    useLimit = entry.useLimit,
                    axisX = Int2(entry.limitX),
                    axisY = Int2(entry.limitY),
                    axisZ = Int2(entry.limitZ),
                };
                component.breastCollider = new ActorSwingStaticCollider
                {
                    type = (byte)entry.colliderType,
                    collisionMask = entry.colliderMask,
                    float_A = entry.colliderRadius,
                    float_B = entry.colliderRadiusSub,
                };
                component.upCurve = Curve(entry.upCurve);
                component.sideCurve = Curve(entry.sideCurve);
                Count("胸部驱动");
            }

            if ((manifest.rotationDrivers?.Length ?? 0) > 0)
            {
                // The source drives each hem panel off its own thigh — `*Skirt_A` follows it 1:1 and
                // `*_Repulsion_A` counter-rotates within per-panel limits. That pair *is* the fitted
                // silhouette. Our synthesised skirt driver is one guessed component on the `_A` node
                // with the stock median clamps; keeping both would drive the same bone twice.
                var dropped = 0;
                foreach (var existing in root.GetComponentsInChildren<ActorAnimationQuartzDriverSkirtBone>(true))
                {
                    UnityEngine.Object.DestroyImmediate(existing);
                    dropped++;
                }
                foreach (var group in CollapseLineages(manifest.rotationDrivers, bones))
                {
                    var bone = Bone(group.Host);
                    var target = Bone(group.Reference);
                    if (bone == null || target == null)
                        continue;
                    bone.gameObject.AddComponent<ActorAnimationQuartzDriverRotationBone>().setting =
                        new ActorAnimationQuartzDriverRotationSetting
                        {
                            rotationOrder = group.RotationOrder,
                            coefficient = group.Coefficient,
                            limitMin = group.LimitMin,
                            limitMax = group.LimitMax,
                            // No source equivalent; these are the values every stock rotation driver
                            // carries (see QuartzDriverRigger).
                            connectionAxis = 0,
                            decomposeType = 0,
                            composeType = 3,
                            referenceBone = target.gameObject,
                        };
                    Count("姿势驱动器");
                }
                Debug.Log($"[SDK] 裙摆驱动换成源模型自带的：拆掉合成的 {dropped} 个 SkirtBone，装上源的 {counts.GetValueOrDefault("姿势驱动器")} 个 RotationBone");
            }

            var summary = string.Join(", ", System.Linq.Enumerable.Select(counts, pair => $"{pair.Key} {pair.Value}"));
            Debug.Log($"[SDK] 源组件搬运完成（{manifest.source}）：{summary}");
            if (clamped.Count > 0)
                Debug.LogWarning($"[SDK] {clamped.Count} 个源值超出目标游戏实测取值域，已夹取: {string.Join("; ", clamped)}");
            if (missing.Count > 0)
                Debug.LogWarning($"[SDK] 骨架里找不到这些骨，对应源组件跳过: {string.Join(", ", missing)}");
            if (manifest.skipped != null && manifest.skipped.Length > 0)
                Debug.Log($"[SDK] 导出时已跳过 {manifest.skipped.Length} 个源组件（{manifest.skipped[0]} …）");
            return true;
        }

        private struct CollapsedDriver
        {
            public string Host, Reference;
            public int RotationOrder;
            public float3 Coefficient, LimitMin, LimitMax;
        }

        /// <summary>
        /// One driver per bone lineage. Nested drivers are a hard crash in this game — access
        /// violation at UnityPlayer+0x143EF86, hit twice: once when the skirt rigger put a
        /// QuartzDriverSkirtBone on both `<panel>Skirt_A` and its `_Repulsion_A` child, and again
        /// when this transfer carried the source's own two-node design over verbatim. Stock never
        /// nests either: its hem drivers are one per panel, on the panel root.
        ///
        /// The source games that do nest use it as a two-stage expression — follow the thigh 1:1 on
        /// the outer node, counter-rotate and clamp on the inner one — and what the skinned geometry
        /// below both nodes sees is the composition. To first order that is one driver whose
        /// coefficient is the sum and whose clamps are the innermost node's, which is what this
        /// builds. It is an approximation, and it is the difference between a mod that runs and one
        /// that kills the process.
        /// </summary>
        private static List<CollapsedDriver> CollapseLineages(RotationDriverEntry[] entries,
            Dictionary<string, Transform> bones)
        {
            var byBone = new Dictionary<string, RotationDriverEntry>();
            foreach (var entry in entries)
                byBone[entry.bone] = entry;

            // Depth below the nearest other driver, so the outermost host is the one that keeps it.
            string OuterMost(RotationDriverEntry entry)
            {
                var host = entry.bone;
                if (!bones.TryGetValue(entry.bone, out var transform))
                    return host;
                for (var cursor = transform.parent; cursor != null; cursor = cursor.parent)
                    if (byBone.ContainsKey(cursor.name))
                        host = cursor.name;
                return host;
            }

            var groups = new Dictionary<string, List<RotationDriverEntry>>();
            foreach (var entry in entries)
            {
                var host = OuterMost(entry);
                if (!groups.TryGetValue(host, out var group))
                    groups[host] = group = new List<RotationDriverEntry>();
                group.Add(entry);
            }

            var collapsed = new List<CollapsedDriver>();
            foreach (var pair in groups)
            {
                // Innermost = the one whose host sits deepest; its clamps are the ones the author
                // tightened, and the outermost's are usually wide open (±180).
                var innermost = pair.Value[0];
                var depth = -1;
                var coefficient = float3.zero;
                foreach (var entry in pair.Value)
                {
                    coefficient += Float3(entry.coefficient);
                    var entryDepth = Depth(bones, entry.bone);
                    if (entryDepth > depth)
                    {
                        depth = entryDepth;
                        innermost = entry;
                    }
                }
                if (pair.Value.Count > 1)
                    Debug.Log($"[SDK] 合并同一条骨脉上的 {pair.Value.Count} 个驱动 → {pair.Key}"
                              + $"（系数相加 {coefficient}，限位取最内层 {innermost.bone}）");
                collapsed.Add(new CollapsedDriver
                {
                    Host = pair.Key,
                    Reference = innermost.reference,
                    RotationOrder = innermost.rotationOrder,
                    Coefficient = coefficient,
                    LimitMin = Float3(innermost.limitMin),
                    LimitMax = Float3(innermost.limitMax),
                });
            }
            return collapsed;
        }

        private static int Depth(Dictionary<string, Transform> bones, string name)
        {
            if (!bones.TryGetValue(name, out var transform))
                return 0;
            var depth = 0;
            for (var cursor = transform.parent; cursor != null; cursor = cursor.parent)
                depth++;
            return depth;
        }

        private static int2 Int2(float[] value) =>
            value == null || value.Length < 2 ? new int2(0, 0) : new int2((int)value[0], (int)value[1]);

        private static Vector3 Vec(float[] value) =>
            value == null || value.Length < 3 ? Vector3.zero : new Vector3(value[0], value[1], value[2]);

        private static float3 Float3(float[] value) =>
            value == null || value.Length < 3 ? float3.zero : new float3(value[0], value[1], value[2]);

        private static AnimationCurve Curve(CurveKey[] keys)
        {
            var curve = new AnimationCurve();
            foreach (var key in keys ?? Array.Empty<CurveKey>())
                curve.AddKey(new Keyframe(key.time, key.value, key.inSlope, key.outSlope));
            // WrapMode 2 in the stock data, and the same in the source's.
            curve.preWrapMode = WrapMode.Loop;
            curve.postWrapMode = WrapMode.Loop;
            return curve;
        }
    }
}
