// Turn a skeleton's `_S` bones into a rig the game will actually drive.
//
// Three things have to be right, and each one was wrong at some point:
//
// 1. The per-bone parameters. They are not one flat set: stock costumes pick them by part category
//    (ribbon / cloth / sleeve / skirt) and by where the bone sits on its strand (root / mid / tip).
//    The table below is the median over the 530 stock bodies, scanned by
//    `tools/scan_vanilla_swing_bones.py` into `mod-workspace/libraries/vanilla-swing/swing_presets.json`.
//    Guessing here does not produce a bad-looking swing, it produces *no* swing: a flat
//    `stiffness 0.3` (stock skirts use 0.01-0.05) holds every bone at its rest pose, `wind 0` removes
//    the only force acting on an idle character, and `pendulumRange 0.2` scales the gravity term down.
// 2. ActorSwingChain. The per-bone component alone is inert — measured in game, bones with only an
//    ActorSwingDynamicBone never move. The chain sits on an anchor bone, lists each strand's first
//    segment, and carries one layer per segment depth, tips included. Stock data only chains some
//    categories: skirt 94%, cloth 54%, sleeve 25%, ribbon 2.6% — a chain is the ring-collision
//    structure a skirt needs, not a general "make it swing" switch.
// 3. ActorSwingStaticBone. The collision cage; see SwingColliderCage.
//
// The angle limits are copied straight from stock, which is only safe because the source's child
// bones run down local -X exactly like this game's (measured: 14/14 on chs-sucu-00). A model whose
// chains run down another axis would have its real swing axis locked by limitX = [0,0] and would sit
// perfectly still with every parameter correct — re-measure before trusting this table on a new source.
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using ActorAnimation;
using Unity.Mathematics;
using UnityEngine;

namespace GakumasSdk
{
    public static class SwingRigger
    {
        public const string SwingSuffix = "_S";

        private enum Role { Root, Mid, Tip }

        private struct Preset
        {
            public float Damping, Stiffness, Spring, Pendulum, PendulumRange, Mass, Wind, RootWeight;
            public int UseLimit, DynamicType;
            public int2 LimitX, LimitY, LimitZ;
            public byte ColliderType;
            public float ColliderRadius, ColliderRadiusSub;
        }

        private static Preset P(float damping, float stiffness, float spring, float pendulum, float pendulumRange,
            float mass, int useLimit, int2 limitX, int2 limitY, int2 limitZ, int dynamicType,
            byte colliderType, float radius, float radiusSub) => new Preset
        {
            Damping = damping, Stiffness = stiffness, Spring = spring, Pendulum = pendulum,
            PendulumRange = pendulumRange, Mass = mass, Wind = 1f, RootWeight = 0.3f,
            UseLimit = useLimit, LimitX = limitX, LimitY = limitY, LimitZ = limitZ,
            DynamicType = dynamicType, ColliderType = colliderType,
            ColliderRadius = radius, ColliderRadiusSub = radiusSub,
        };

        // wind is 1.0 and rootWeight 0.3 for every category and role in stock data — constants, not
        // knobs, so they live in P() rather than in every row.
        private static readonly Dictionary<(string, Role), Preset> Presets = new()
        {
            [("ribbon", Role.Root)] = P(0.5f, 0.05f, 0f, 0f, 1f, 0.1f, 1, new int2(0, 0), new int2(-30, 30), new int2(-90, 0), 0, 0, 0.028f, 0.05f),
            [("ribbon", Role.Mid)] = P(0.5f, 0.008f, 0.3f, 0.003f, 1f, 0.7f, 1, new int2(0, 0), new int2(-30, 30), new int2(-60, 0), 0, 0, 0.018f, 0.05f),
            [("ribbon", Role.Tip)] = P(0.5f, 0.006f, 0.5f, 0.003f, 1f, 0.6f, 1, new int2(0, 0), new int2(-30, 30), new int2(-180, 180), 0, 0, 0.015f, 0.05f),

            [("cloth", Role.Root)] = P(0.5f, 0.05f, 0f, 0f, 1f, 0f, 1, new int2(0, 0), new int2(-10, 10), new int2(-40, 0), 0, 0, 0.03f, 0.05f),
            [("cloth", Role.Mid)] = P(0.5f, 0.01f, 0.3f, 0.0075f, 1f, 0.5f, 1, new int2(0, 0), new int2(-20, 20), new int2(-60, 60), 0, 0, 0.022f, 0.05f),
            [("cloth", Role.Tip)] = P(0.5f, 0.01f, 0.3f, 0.003f, 1f, 0.5f, 1, new int2(0, 0), new int2(-10, 10), new int2(-180, 180), 0, 0, 0.02f, 0.05f),

            [("sleeve", Role.Root)] = P(0.5f, 0.05f, 0f, 0f, 1f, 0f, 0, new int2(-180, 180), new int2(-180, 180), new int2(-180, 180), 0, 0, 0.05f, 0.05f),
            [("sleeve", Role.Mid)] = P(0.4f, 0.1f, 0.3f, 0.06f, 0.8f, 0.2f, 1, new int2(0, 0), new int2(-5, 5), new int2(-5, 5), 1, 4, 0.05f, 0.05f),
            [("sleeve", Role.Tip)] = P(0.5f, 0.02f, 0.4f, 0.002f, 1f, 0.5f, 1, new int2(0, 0), new int2(-180, 180), new int2(-180, 180), 1, 4, 0.05f, 0.05f),

            [("skirt", Role.Root)] = P(0.5f, 0.05f, 0.1f, 0f, 1f, 0.5f, 1, new int2(0, 0), new int2(-10, 10), new int2(-30, 0), 0, 0, 0.02f, 0.05f),
            [("skirt", Role.Mid)] = P(0.5f, 0.02f, 0.5f, 0.003f, 1f, 0.75f, 1, new int2(0, 0), new int2(-30, 30), new int2(-20, 0), 0, 0, 0.02f, 0.05f),
            [("skirt", Role.Tip)] = P(0.5f, 0.01f, 0.5f, 0.005f, 1f, 0.8f, 1, new int2(0, 0), new int2(-30, 30), new int2(-90, 10), 0, 0, 0.02f, 0.05f),
        };

        // Chained in stock data: skirt 94%, cloth 54%, sleeve 25%, ribbon 2.6%. Following the majority
        // keeps wings and tails off the ring-collision path they were never on.
        private static readonly HashSet<string> Chained = new() { "skirt", "cloth" };

        // Which cage channels a bone is allowed to hit. `-1` (Everything) is not the safe default it
        // looks like: the cage's `Hips` capsule is 0.23 m and sits on channels 64|128, so an
        // Everything skirt bone gets pushed out to a 23 cm radius around the hips — a fitted skirt
        // stands off the thigh and every panel rides against a sphere, which is what "stiff and not
        // touching the leg" was. Stock pairs the two sides: over 60 costumes the dominant per-bone
        // mask is skirt 1 (51% of 2493 bones), cloth 64 (48%), ribbon 256 (28%), sleeve 0 (42%),
        // skin 0 (63%) — and every cage collider a skirt should meet (Pelvis, Leg, Foot, UpLeg) has
        // channel 1 while the hips/spine/arm capsules do not.
        //
        // ponytail: only skirt is switched over. The other rows are measured and sitting right here,
        // but wings and the bow render correctly on Everything today, and a channel is only right if
        // the costume being replaced authored the same convention — move one category at a time, when
        // there is something on screen to check it against.
        //
        // ponytail: measured stock values for the other three rows are ribbon 256 / cloth 64 / sleeve 0
        // (60 costumes, 2493 bones). Switching them on is queued behind confirming the chain gate fix —
        // it only moves `Bone_HairSideC`, the one chain that really does rest inside the `Hips` ball.
        private static readonly Dictionary<string, int> ColliderMasks = new() { ["skirt"] = 1 };

        // Ring radius per layer, off mdl_chr_hmsz-cstm-0059_body's own skirt chain: layer 0 is the
        // anchored one at 0.05, and the free layers widen as they hang.
        private static readonly float[] LayerRadius = { 0.05f, 0.015f, 0.02f, 0.03f, 0.04f };

        public static int Rig(GameObject root) => Rig(root, null);

        /// <param name="classified">
        /// Chains found by geometry rather than by name. Pass this for any model that does not
        /// already use this game's `_S` convention — which is every model that did not come out of
        /// this game or its sibling. Null keeps the name-based path.
        /// </param>
        public static int Rig(GameObject root, List<ChainClassifier.Strand> classified)
        {
            List<List<Transform>> strands;
            Dictionary<Transform, string> byBone = null;
            if (classified != null)
            {
                strands = classified.Select(strand => strand.Bones).ToList();
                byBone = new Dictionary<Transform, string>();
                foreach (var strand in classified)
                    byBone[strand.Bones[0]] = strand.Category;
            }
            else
            {
                strands = FindStrands(root);
            }
            // The chest is driven by ActorSwingBreastBone, which owns those bones outright — stock data
            // never puts a dynamic bone on them (0 of 79), and simulating one bone twice breaks the rig.
            // Asked as "which bones will the chest driver claim", not "is it spelled Bust": the source
            // spells them its own way here, because the rename happens after this runs.
            var claimed = BreastRigger.Claim(root);
            var owned = strands.RemoveAll(strand => claimed.Contains(strand[0]));
            if (owned > 0)
                Debug.Log($"[SDK] {owned} 条链归胸部驱动，摇物跳过");

            var bones = new Dictionary<Transform, ActorSwingDynamicBone>();
            var categories = new Dictionary<Transform, string>();
            var counts = new Dictionary<string, int>();
            foreach (var strand in strands)
            {
                var category = byBone != null && byBone.TryGetValue(strand[0], out var known)
                    ? known
                    : CategoryOf(strand[0].name);
                counts[category] = counts.GetValueOrDefault(category) + strand.Count;
                foreach (var segment in strand)
                {
                    categories[segment] = category;
                    bones[segment] = AttachBone(segment, category, RoleOf(strand, segment));
                }
            }

            var chains = RigChains(strands, bones, categories);
            var colliders = RigCage(root);
            var summary = string.Join(", ", System.Linq.Enumerable.Select(counts, pair => $"{pair.Key} {pair.Value}"));
            Debug.Log($"[SDK] 摇物装配完成: {strands.Count} 条链 / {bones.Count} 根骨（{summary}）/ " +
                      $"{chains} 个 chain / {colliders} 个静态碰撞体");
            return chains;
        }

        private static int RigChains(List<List<Transform>> strands, Dictionary<Transform, ActorSwingDynamicBone> bones,
            Dictionary<Transform, string> categories)
        {
            // Every strand in a chain must be the same length — stock layers are strictly rectangular,
            // every layer holding exactly one bone per strand (checked across the scanned costumes) —
            // so depth is part of the key. What is *not* part of it is the immediate parent: a chain is
            // a ring, and `around` collision only means something when a layer holds the panels
            // side by side. Stock hosts them on a common ancestor, overwhelmingly `Pelvis` (758 of 1537
            // chain instances), with 4-8 strands each; grouping by immediate parent instead gave this
            // costume eight chains of one strand — eight rings of one panel, which is no ring at all.
            var groups = new Dictionary<(string, int), List<List<Transform>>>();
            foreach (var strand in strands)
            {
                var category = categories[strand[0]];
                if (!Chained.Contains(category))
                    continue;
                var key = (category, strand.Count);
                if (!groups.TryGetValue(key, out var group))
                    groups[key] = group = new List<List<Transform>>();
                group.Add(strand);
            }

            foreach (var pair in groups)
            {
                var depth = pair.Key.Item2;
                var anchor = CommonAncestor(pair.Value);
                // The common ancestor is where the SOURCE model happened to hang its strands; the
                // chain host is where THIS GAME solves them from. For atbm-cstm-0140 every skirt
                // chain hosts on `Pelvis`, while the source's skirt bones sit under `Spine` — a
                // pivot one whole torso too high, which is what the swing looked like.
                var wanted = VanillaSwingTruth.HostFor(pair.Key.Item1);
                if (!string.IsNullOrEmpty(wanted) && pair.Value.Count > 0)
                {
                    var host = pair.Value[0][0].root.GetComponentsInChildren<Transform>(true)
                        .FirstOrDefault(candidate => candidate.name == wanted);
                    if (host != null && host != anchor)
                    {
                        Debug.Log($"[SDK] chain 锚点按原版真值改挂: {anchor?.name} → {wanted}"
                                  + $"（类别 {pair.Key.Item1}）");
                        anchor = host;
                    }
                }
                if (anchor == null)
                    continue;
                var truthRadii = VanillaSwingTruth.LayerRadii(anchor.name, depth);
                var chain = anchor.gameObject.AddComponent<ActorSwingChain>();
                chain.rootBones = new List<ActorSwingDynamicBone>();
                chain.chains = new ChainInfo { layers = new List<ChainLayerInfo>() };
                foreach (var strand in pair.Value)
                    chain.rootBones.Add(bones[strand[0]]);

                for (var level = 0; level < depth; level++)
                {
                    var layerBones = new List<ActorSwingDynamicBone>();
                    foreach (var strand in pair.Value)
                        layerBones.Add(bones[strand[level]]);
                    chain.chains.layers.Add(new ChainLayerInfo
                    {
                        // Layer 0 is the anchored one: stock data has it active 0 / around 0.
                        active = level != 0,
                        // `around` is a per-chain choice in stock and never mixed within one chain: of
                        // 223 scanned chains with free layers, 138 have it off on every layer and 85
                        // have it on. Do NOT read that 62% as "off is safer" — it was tried, and the
                        // skirt, wings and back streamers all blew up. The ring is what bounds lateral
                        // travel here; without it nothing does. Follow the costume being replaced
                        // instead of the population: hmsz-cstm-0059's own skirt chain has around=1 on
                        // every free layer.
                        around = level != 0,
                        // This costume's own rings when we have them; the hardcoded table is
                        // another costume's skirt and runs 50-60% wide.
                        radius = truthRadii != null && level < truthRadii.Length
                            ? truthRadii[level]
                            : LayerRadius[Mathf.Min(level, LayerRadius.Length - 1)],
                        smoothing = 0f,
                        bones = layerBones,
                    });
                }
                Debug.Log($"[SDK] chain: 锚点 {anchor.name} 深度 {depth} 链数 {pair.Value.Count} " +
                          $"类别 {categories[pair.Value[0][0]]}");
            }
            return groups.Count;
        }

        /// <summary>Deepest transform above every strand in the group — where stock hosts the chain.</summary>
        private static Transform CommonAncestor(List<List<Transform>> strands)
        {
            var path = new List<Transform>();
            for (var cursor = strands[0][0].parent; cursor != null; cursor = cursor.parent)
                path.Add(cursor);                       // deepest first
            foreach (var strand in strands)
            {
                var ancestors = new HashSet<Transform>();
                for (var cursor = strand[0].parent; cursor != null; cursor = cursor.parent)
                    ancestors.Add(cursor);
                path.RemoveAll(candidate => !ancestors.Contains(candidate));
            }
            return path.Count > 0 ? path[0] : null;
        }

        private static int RigCage(GameObject root)
        {
            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                byName[transform.name] = transform;

            var attached = 0;
            var missing = new List<string>();
            foreach (var entry in SwingColliderCage.Entries)
            {
                if (!byName.TryGetValue(entry.Bone, out var bone))
                {
                    if (!missing.Contains(entry.Bone))
                        missing.Add(entry.Bone);
                    continue;
                }
                var component = bone.gameObject.AddComponent<ActorSwingStaticBone>();
                component.staticCollider = new ActorSwingStaticCollider
                {
                    type = entry.Type,
                    collisionMask = entry.Mask,
                    vector3_A = entry.A,
                    vector3_B = entry.B,
                    float_A = entry.FloatA * SwingColliderCage.RadiusScale,
                    float_B = entry.FloatB * SwingColliderCage.RadiusScale,
                };
                attached++;
            }
            if (missing.Count > 0)
                Debug.LogWarning($"[SDK] 骨架缺这些骨，对应碰撞体跳过: {string.Join(", ", missing)}");
            if (!Mathf.Approximately(SwingColliderCage.RadiusScale, 1f))
                Debug.LogWarning($"[SDK] 诊断模式：碰撞体半径 ×{SwingColliderCage.RadiusScale}，不要用这个包出成品");
            return attached;
        }

        private static ActorSwingDynamicBone AttachBone(Transform bone, string category, Role role)
        {
            // Parameters for a skin bone are not in the scan's table; ribbon is the conservative row.
            var preset = Presets[(category == "skin" ? "ribbon" : category, role)];
            var truthMask = int.MinValue;
            var truthResetType = -1;
            // The replaced costume's OWN numbers win over the 530-body median when we have them:
            // for atbm-cstm-0140's skirt the median is 10x stiffer at the root and 2x the mass.
            if (VanillaSwingTruth.For(category, role.ToString()) is { } truth)
            {
                preset.Damping = truth.Damping;
                preset.Stiffness = truth.Stiffness;
                preset.Spring = truth.Spring;
                preset.Pendulum = truth.Pendulum;
                preset.PendulumRange = truth.PendulumRange;
                preset.Mass = truth.Mass;
                preset.Wind = truth.Wind;
                preset.RootWeight = truth.RootWeight;
                preset.UseLimit = truth.UseLimit;
                preset.DynamicType = truth.DynamicType;
                if (truth.LimitX != null && truth.LimitX.Length == 2)
                    preset.LimitX = new int2(truth.LimitX[0], truth.LimitX[1]);
                if (truth.LimitY != null && truth.LimitY.Length == 2)
                    preset.LimitY = new int2(truth.LimitY[0], truth.LimitY[1]);
                if (truth.LimitZ != null && truth.LimitZ.Length == 2)
                    preset.LimitZ = new int2(truth.LimitZ[0], truth.LimitZ[1]);
                preset.ColliderRadius = truth.ColliderRadius;
                preset.ColliderRadiusSub = truth.ColliderRadiusSub;
                preset.ColliderType = (byte)truth.ColliderType;
                truthMask = truth.CollisionMask;
                truthResetType = truth.ResetType;
            }
            var component = bone.gameObject.AddComponent<ActorSwingDynamicBone>();
            // ResetType { Default = 0, Skin = 1 }. Across 6576 stock swing bones, `Skin` appears on
            // exactly the 618 bones literally named *Skin (LegSkin / UpLegSkin / ArmSkin) and on no
            // skirt, ribbon or wing. It means "reset to the skinned pose", so a swing bone set to it
            // is pinned: the SDK hardcoded 1 from the start and nothing on a mod body ever moved,
            // through every round of parameter fixes, because this field is not in the scan's table.
            component.resetType = truthResetType >= 0 ? truthResetType : category == "skin" ? 1 : 0;
            component.dynamicType = preset.DynamicType;
            component.damping = preset.Damping;
            component.stiffness = preset.Stiffness;
            component.spring = preset.Spring;
            component.pendulum = preset.Pendulum;
            component.pendulumRange = preset.PendulumRange;
            component.mass = preset.Mass;
            component.wind = preset.Wind;
            component.useWindGlobalForce = true;
            component.rootWeight = preset.RootWeight;
            component.limitInfo = new LimitInfo
            {
                useLimit = preset.UseLimit,
                axisX = preset.LimitX,
                axisY = preset.LimitY,
                axisZ = preset.LimitZ,
            };
            component.referenceLimitInfo = new ReferenceLimitInfo();
            component.dynamicCollider = new ActorSwingDynamicCollider
            {
                type = preset.ColliderType,
                // Stock masks are per-part: skirt 1, jacket 64, streamers 256, and sleeves and leg
                // skin 0 — those collide with nothing. The fallback -1 puts every unclassified
                // bone into all 30 colliders at once.
                collisionMask = truthMask != int.MinValue
                    ? truthMask
                    : ColliderMasks.TryGetValue(category, out var mask) ? mask : -1,
                float_A = preset.ColliderRadius,
                float_B = preset.ColliderRadiusSub,
            };
            component.modelingTransform = new InitialTransform
            {
                localPosition = bone.localPosition,
                localRotation = bone.localRotation,
                position = bone.position,
                rotation = bone.rotation,
            };
            return component;
        }

        // `LeftBackSideSkirt2_S` -> stem `Skirt`. Side words and the tier number are stripped, so the
        // category comes out of the naming itself rather than a list we maintain. Same construction as
        // the scanner's `part_of`; the two must agree or a part gets looked up in the wrong row.
        private static readonly string[] SideTokens =
        {
            "Left", "Right", "Center", "Front", "Back", "Side", "Upper", "Lower",
            "Inside", "Outside", "Body", "Arm", "Up",
        };

        private static readonly (string Category, string[] Tokens)[] CategoryRules =
        {
            ("skin", new[] { "skin" }),
            ("sleeve", new[] { "sleeve", "cuff" }),
            ("skirt", new[] { "skirt", "pants", "smock", "jacket", "coat", "dress", "hakama" }),
            ("ribbon", new[] { "ribbon", "string", "lace", "bow", "tie", "cord", "strap", "tassel", "rope", "chain", "acce", "neckless" }),
            ("cloth", new[] { "cloth", "poncho", "frill", "cape", "apron", "muffler", "scarf", "stole", "hood", "collar", "belt", "sash", "furisode", "gown", "shirt", "inner" }),
        };

        private static readonly Regex NamePattern = new(@"^(?<stem>.+?)(?<tier>\d+)_S(?<end>_End)?$");

        public static string CategoryOf(string boneName)
        {
            var match = NamePattern.Match(boneName);
            var stem = match.Success ? match.Groups["stem"].Value : boneName;
            var changed = true;
            while (changed)
            {
                changed = false;
                foreach (var token in SideTokens)
                    if (stem.StartsWith(token) && stem.Length > token.Length)
                    {
                        stem = stem.Substring(token.Length);
                        changed = true;
                        break;
                    }
            }
            var lower = stem.ToLowerInvariant();
            foreach (var (category, tokens) in CategoryRules)
                foreach (var token in tokens)
                    if (lower.Contains(token))
                        // `skin` is kept as its own category rather than folded away: it is the one
                        // thing that decides resetType.
                        return category;
            return "ribbon";
        }

        private static Role RoleOf(List<Transform> strand, Transform segment)
        {
            if (segment.name.EndsWith(SwingSuffix + "_End") || segment == strand[strand.Count - 1])
                return strand.Count == 1 ? Role.Root : Role.Tip;
            return segment == strand[0] ? Role.Root : Role.Mid;
        }

        /// <summary>Each `_S` chain, from its first segment downwards.</summary>
        public static List<List<Transform>> FindStrands(GameObject root)
        {
            var strands = new List<List<Transform>>();
            foreach (var candidate in root.GetComponentsInChildren<Transform>(true))
            {
                if (!IsSwing(candidate) || IsSwing(candidate.parent))
                    continue;
                var strand = new List<Transform> { candidate };
                var cursor = candidate;
                while (true)
                {
                    Transform next = null;
                    var found = 0;
                    foreach (Transform child in cursor)
                        if (IsSwing(child))
                        {
                            next = child;
                            found++;
                        }
                    if (found != 1)
                        break;
                    cursor = next;
                    strand.Add(cursor);
                }
                strands.Add(strand);
            }
            return strands;
        }

        // `_S_End` counts. Stock chains carry the tail as their last layer, active and with the widest
        // ring radius — read straight off mdl_chr_hmsz-cstm-0059_body's 8-strand skirt chain, whose
        // layer 4 is `RightBackSkirt5_S_End` … at active=1 around=1 radius=0.04. Dropping it cost every
        // panel its outermost layer, and cost a one-bone panel *all* of its motion: layer 0 is the
        // anchored one (active=0), so a strand of a single `_S` bone produced a chain that cannot move.
        // Three of this costume's seven panels are that shape — the front ones, which is what was
        // clipping the thigh.
        private static bool IsSwing(Transform transform) =>
            transform != null &&
            (transform.name.EndsWith(SwingSuffix) || transform.name.EndsWith(SwingSuffix + "_End"));
    }
}
