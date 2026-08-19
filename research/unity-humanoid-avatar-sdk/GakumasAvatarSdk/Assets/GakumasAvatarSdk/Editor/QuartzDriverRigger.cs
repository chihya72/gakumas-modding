// The pose-driven correction rig: everything in the QuartzDriver family.
//
// This exists because the previous approach — fix whatever the last screenshot showed — kept finding
// one more missing component. So the whole thing was inventoried instead: all 530 stock body bundles
// scanned for every MonoBehaviour they carry, cross-checked against the component classes in
// `ActorAnimation.Runtime` and the lists `CampusActorAnimationInitializeData` consumes. Results in
// `docs/body-component-inventory.md`. This file covers the drivers; swing is in SwingRigger.
//
// Carry rates from that scan, and the values below are *exactly* consistent across every costume that
// has them (120/120 for each host bone), so these are tables, not guesses:
//
//   528/530  HumanoidArm / HumanoidUpLeg / HumanoidHand / Rotation   16 per body, always the same bones
//   379/530  Skirt                                                   one per hem panel
//   230/530  Waist · 78 Frill · 39 Poncho · 33 LateRotationSimple · 26+9 Sleeve · 25 Furisode
//
// The last row is not implemented: those are garment-specific and the source model has no such parts.
using System.Collections.Generic;
using ActorAnimation;
using Unity.Mathematics;
using UnityEngine;

namespace GakumasSdk
{
    public static class QuartzDriverRigger
    {
        // UnityEngine.HumanPartDof: LeftLeg 2, RightLeg 3, LeftArm 4, RightArm 5.
        private static readonly (string Bone, int Dof, float Coefficient)[] ArmDrivers =
        {
            ("LeftArm_H", 4, -0.8f), ("LeftArm_Roll_H", 4, -0.3f),
            ("RightArm_H", 5, -0.8f), ("RightArm_Roll_H", 5, -0.3f),
        };

        private static readonly (string Bone, int Dof, float Coefficient)[] HandDrivers =
        {
            ("LeftHand_H", 4, 0.9f), ("LeftForeArm_Roll_H", 4, 0.5f),
            ("RightHand_H", 5, 0.9f), ("RightForeArm_Roll_H", 5, 0.5f),
        };

        private static readonly (string Bone, int Dof, float Coefficient)[] UpLegDrivers =
        {
            ("LeftUpLeg_H", 2, -1.0f), ("LeftUpLeg_Roll_H", 2, -0.6f),
            ("RightUpLeg_H", 3, -1.0f), ("RightUpLeg_Roll_H", 3, -0.6f),
        };

        // Rotation drivers follow a real bone: the forearm helpers take 40% of the forearm's twist,
        // the shin helpers 50% of the knee's bend on Z. rotationOrder / composeType differ between the
        // two, which is why this is a table and not a formula.
        private static readonly (string Bone, string Reference, int RotationOrder, float3 Coefficient)[] RotationDrivers =
        {
            ("LeftForeArm_H", "LeftForeArm", 1, new float3(0f, -0.4f, 0f)),
            ("RightForeArm_H", "RightForeArm", 1, new float3(0f, -0.4f, 0f)),
            ("LeftLeg_H", "LeftLeg", 0, new float3(0f, 0f, -0.5f)),
            ("RightLeg_H", "RightLeg", 0, new float3(0f, 0f, -0.5f)),
        };

        // Per-panel clamps for the skirt driver, verbatim off mdl_chr_hmsz-cstm-0063_body and identical
        // across all nine stock costumes that carry them — a property of which panel it is, not of the
        // costume. innerCoefficient / outerCoefficient are the same on all eight panels everywhere.
        private static readonly (string Match, float3 Min, float3 Max)[] SkirtPanels =
        {
            ("FrontSide", new float3(-180f, -180f, -180f), new float3(180f, 50f, 50f)),
            ("BackSide", new float3(-180f, -180f, -78f), new float3(180f, 50f, 83f)),
            ("Front", new float3(-180f, -180f, -180f), new float3(180f, 40f, 20f)),
            ("Back", new float3(-180f, -180f, -58f), new float3(180f, 60f, 180f)),
        };

        /// <summary>Attaches every driver this body's skeleton has bones for. Returns how many.</summary>
        /// <param name="classified">
        /// The geometry classifier's strands, when the model did not come from this family. The skirt
        /// driver is hosted by name in stock data and no rip matches that name, so without this every
        /// panel goes undriven — and the driver is what turns a panel away from the thigh that is
        /// lifting into it.
        /// </param>
        public static int Rig(GameObject root, List<ChainClassifier.Strand> classified = null)
        {
            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                byName[transform.name] = transform;

            var attached = 0;
            var missing = new List<string>();

            foreach (var (bone, dof, coefficient) in ArmDrivers)
                if (Host(byName, bone, missing) is { } host)
                {
                    host.AddComponent<ActorAnimationQuartzDriverHumanoidArmBone>().setting =
                        new ActorAnimationQuartzDriverHumanoidArmSetting { humanPartDof = dof, coefficient = coefficient };
                    attached++;
                }

            foreach (var (bone, dof, coefficient) in HandDrivers)
                if (Host(byName, bone, missing) is { } host)
                {
                    host.AddComponent<ActorAnimationQuartzDriverHumanoidHandBone>().setting =
                        new ActorAnimationQuartzDriverHumanoidHandSetting { humanPartDof = dof, coefficient = coefficient };
                    attached++;
                }

            foreach (var (bone, dof, coefficient) in UpLegDrivers)
                if (Host(byName, bone, missing) is { } host)
                {
                    host.AddComponent<ActorAnimationQuartzDriverHumanoidUpLegBone>().setting =
                        new ActorAnimationQuartzDriverHumanoidUpLegSetting { humanPartDof = dof, coefficient = coefficient };
                    attached++;
                }

            foreach (var (bone, reference, order, coefficient) in RotationDrivers)
            {
                if (Host(byName, bone, missing) is not { } host)
                    continue;
                if (!byName.TryGetValue(reference, out var target))
                {
                    missing.Add(reference);
                    continue;
                }
                host.AddComponent<ActorAnimationQuartzDriverRotationBone>().setting =
                    new ActorAnimationQuartzDriverRotationSetting
                    {
                        rotationOrder = order,
                        limitMin = new float3(-180f, -180f, -180f),
                        limitMax = new float3(180f, 180f, 180f),
                        coefficient = coefficient,
                        connectionAxis = 0,
                        decomposeType = 0,
                        composeType = 3,
                        referenceBone = target.gameObject,
                    };
                attached++;
            }

            var skirt = RigSkirt(root, byName);
            if (skirt == 0 && classified != null)
                skirt = RigSkirtByGeometry(root, byName, classified);
            attached += skirt;

            if (missing.Count > 0)
                Debug.LogWarning($"[SDK] 骨架缺这些骨，对应姿势驱动器跳过: {string.Join(", ", missing)}");
            Debug.Log($"[SDK] 姿势驱动器装配完成: {attached} 个（原版每套 16 个必备 + 每片裙摆 1 个）");
            return attached;
        }

        // Stock anchors are `<side><panel>Skirt_A`, and so are IDOLY PRIDE's — the `_Repulsion_A`
        // node next to them is an extra level, not a rename (see the skip below).
        private static int RigSkirt(GameObject root, Dictionary<string, Transform> byName)
        {
            var attached = 0;
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
            {
                var name = transform.name;
                if (!name.Contains("Skirt") || !name.EndsWith("_A"))
                    continue;
                // IDOLY PRIDE inserts an extra `_Repulsion_A` node between the panel root and the
                // swing chain: Skirt_Leftside_O → LeftBackSideSkirt_A → LeftBackSideSkirt_Repulsion_A
                // → LeftBackSideSkirt1_S. Stock hosts the driver on the panel root only — across the
                // 530 scanned bundles the hosts are the eight `<side><panel>Skirt_A` bones, 8.1 per
                // costume, and not one `_Repulsion_A`. Without this every panel got two nested
                // drivers, parent and child both writing the same chain (14 instead of 8).
                if (name.Contains("_Repulsion"))
                    continue;
                // The driver reads its own side's thigh: left panels follow LeftUpLeg, right RightUpLeg.
                var side = name.StartsWith("Left") ? "LeftUpLeg" : name.StartsWith("Right") ? "RightUpLeg" : null;
                if (side == null || !byName.TryGetValue(side, out var reference))
                {
                    Debug.LogWarning($"[SDK] {name}: 认不出左右或缺 {side ?? "UpLeg"}，跳过裙摆驱动器");
                    continue;
                }

                var panel = SkirtPanels[SkirtPanels.Length - 1];
                foreach (var candidate in SkirtPanels)
                    if (name.Contains(candidate.Match))
                    {
                        panel = candidate;
                        break;
                    }

                transform.gameObject.AddComponent<ActorAnimationQuartzDriverSkirtBone>().setting =
                    new ActorAnimationQuartzDriverSkirtSetting
                    {
                        rotationOrder = 0,
                        connectionAxis = 0,
                        innerCoefficient = new float3(0f, 0.1f, 0.1f),
                        outerCoefficient = new float3(1f, 1f, 1f),
                        limitMin = panel.Min,
                        limitMax = panel.Max,
                        referenceBone = reference.gameObject,
                    };
                attached++;
                Debug.Log($"[SDK] 裙摆驱动器: {name} ← {side}（{panel.Match} 档）");
            }
            return attached;
        }

        /// <summary>
        /// The same driver, hosted on whatever the classifier called a skirt. Stock names its panels
        /// `<side><panel>Skirt_A`; a rip names them anything, so side and panel come off the geometry
        /// instead — which side of the body the panel root sits on, and where it sits around the hips.
        /// The four clamp presets are literally front / front-side / back-side / back, so the azimuth
        /// they were named for is what picks them.
        /// </summary>
        private static int RigSkirtByGeometry(GameObject root, IReadOnlyDictionary<string, Transform> byName,
                                              IEnumerable<ChainClassifier.Strand> classified)
        {
            if (!byName.TryGetValue("Hips", out var hips))
                return 0;
            var attached = 0;
            var skipped = new List<string>();
            foreach (var strand in classified)
            {
                if (strand.Category != "skirt" || strand.Bones.Count == 0)
                    continue;
                // ByAnchor also calls a boot top or a leg ribbon "skirt" — same clamps, but a panel
                // that already hangs off the leg must not be driven by that leg's own rotation.
                var anchor = strand.Anchor == null ? null : strand.Anchor.name;
                if (anchor == null || !(anchor == "Hips" || anchor == "Pelvis" || anchor.StartsWith("Spine")))
                    continue;

                var panelRoot = strand.Bones[0];
                // Stock never puts this driver on a bone the swing solver also owns: 327 skirt
                // drivers across 60 costumes, not one of them shares a bone with an ActorSwing*
                // component. Its host is the panel's `_A` anchor and the swing chain starts at the
                // `1_S` child below it. Hosting both on one bone is an arrangement this game has no
                // example of, and the build that did it hard-crashed 2.6 s after the swap with swing
                // running — the same class of failure as the two-drivers-on-one-lineage crash.
                // Re-enabling this needs the stock shape: insert an anchor above the panel *before*
                // the swing rig runs, because reparenting afterwards strands the local-space
                // transforms the swing components have already captured.
                if (panelRoot.GetComponent<ActorSwingDynamicBone>() != null)
                {
                    skipped.Add(panelRoot.name);
                    continue;
                }
                var offset = root.transform.InverseTransformPoint(panelRoot.position)
                             - root.transform.InverseTransformPoint(hips.position);
                // A centre panel has no "own" thigh, and stock never has one — all eight of its panels
                // are handed. Driving it off an arbitrary side would make it kick with one leg only.
                if (Mathf.Abs(offset.x) < 0.02f)
                {
                    skipped.Add(panelRoot.name);
                    continue;
                }
                var side = offset.x < 0f ? "LeftUpLeg" : "RightUpLeg";
                if (!byName.TryGetValue(side, out var reference))
                    continue;

                // 0° is straight ahead. The four presets are named for sectors around the hips, and
                // the boundaries are where stock actually puts them — 3000+ `*Skirt_A` panels over
                // 381 costumes: Front 11.5-55.3°, FrontSide 56.1-90.3°, BackSide 87.1-128.3°,
                // Back 119.8-172.9°. Guessing 45/115/165 instead split a mirrored pair of panels
                // across two presets at 41° and 46°, which is one arm-twist lesson too many.
                var azimuth = Mathf.Abs(Mathf.Atan2(offset.x, offset.z) * Mathf.Rad2Deg);
                var match = azimuth < 56f ? "Front"
                    : azimuth < 89f ? "FrontSide"
                    : azimuth < 124f ? "BackSide"
                    : "Back";
                var panel = SkirtPanels[SkirtPanels.Length - 1];
                foreach (var candidate in SkirtPanels)
                    if (candidate.Match == match)
                    {
                        panel = candidate;
                        break;
                    }

                panelRoot.gameObject.AddComponent<ActorAnimationQuartzDriverSkirtBone>().setting =
                    new ActorAnimationQuartzDriverSkirtSetting
                    {
                        rotationOrder = 0,
                        connectionAxis = 0,
                        innerCoefficient = new float3(0f, 0.1f, 0.1f),
                        outerCoefficient = new float3(1f, 1f, 1f),
                        limitMin = panel.Min,
                        limitMax = panel.Max,
                        referenceBone = reference.gameObject,
                    };
                attached++;
                Debug.Log($"[SDK] 裙摆驱动器（按几何）: {panelRoot.name} ← {side}"
                          + $"（方位 {azimuth:F0}° → {match} 档）");
            }
            if (skipped.Count > 0)
                Debug.Log($"[SDK] {skipped.Count} 片裙摆没挂驱动器（正中的原版也没有，"
                          + $"已是摇物骨的不能再挂——原版 327/327 从不重叠，靠摇物和碰撞躲腿）："
                          + $"{string.Join(", ", skipped)}");
            return attached;
        }

        private static GameObject Host(Dictionary<string, Transform> byName, string bone, List<string> missing)
        {
            if (!byName.TryGetValue(bone, out var transform))
            {
                // TwistAdopter hands this role's driver to the source's OWN bone and deliberately
                // does not rename it, so a stock-name lookup misses a role that is in fact covered.
                // Reported as missing, that reads as "16 drivers short" when the twist roles — the
                // only ones with measured benefit — are already done. Ask the adoption table before
                // calling it missing; the guard below then skips it for the real reason.
                if (TwistAdopter.AdoptedByRole.TryGetValue(bone, out var adopted) && adopted != null)
                {
                    transform = adopted;
                }
                else
                {
                    missing.Add(bone);
                    return null;
                }
            }
            // TwistAdopter runs first and hands the driver to whichever bone already plays the role.
            // When `stockJointRig` synthesised the helper, that bone *is* `LeftArm_Roll_H`, so a
            // name lookup here finds it again and stacks a second driver on it — 24 drivers where
            // stock has 16, two of them writing the same transform every frame, and the actor never
            // finished loading. One driver per bone, first writer wins.
            foreach (var component in transform.GetComponents<Component>())
                if (component != null && component.GetType().Name.StartsWith("ActorAnimationQuartzDriver"))
                    return null;
            return transform.gameObject;
        }
    }
}
