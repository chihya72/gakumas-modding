// The swing parameters of the ONE costume being replaced, instead of the median of all 530.
//
// SwingRigger's table is the median over every stock body, which is the right default when nothing
// is known about the target. But a mod replaces a specific body, and that body's own numbers were
// already scanned into mod-workspace/libraries/vanilla-swing/vanilla-swing-bones.json — 106 bones
// for `atbm-cstm-0140` alone, every field the component needs, plus the chain host.
//
// The medians are not close. For that costume's skirt: stiffness 0.005-0.02 against the median
// row's 0.01-0.05 (10x at the root), mass 0.4 flat against 0.5/0.75/0.8, and the chain hangs off
// `Pelvis` while geometry classification put ours on `Spine` — a pivot one whole torso out, which
// is what "swings, but wrong" looks like.
//
// Roadmap 第 9 步 says to prefer the original data and synthesise only when there is none. That was
// read as "the source model has no physics data, so synthesise" — true, but the OTHER side of the
// replacement had the data all along.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

namespace GakumasSdk
{
    public static class VanillaSwingTruth
    {
        [Serializable]
        private class Bone
        {
            public string bundle, name, part, chainHost;
            public int tier;
            public bool isTip, isChainRoot;
            public float damping, stiffness, spring, pendulum, pendulumRange, mass, wind, rootWeight;
            public int useLimit, dynamicType, resetType, collisionMask;
            public int[] limitX, limitY, limitZ;
            public float colliderRadius, colliderRadiusSub;
            public int colliderType;
        }

        [Serializable]
        private class Layer { public int active, around, bones; public float radius, smoothing; }

        [Serializable]
        private class Chain { public string bundle, host; public int roots; public Layer[] layers; }

        [Serializable]
        private class File { public Bone[] bones; public Chain[] chains; }

        /// <summary>What a stock costume does for one (category, role); null when it has no such part.</summary>
        public class Row
        {
            public float Damping, Stiffness, Spring, Pendulum, PendulumRange, Mass, Wind, RootWeight;
            public int UseLimit, DynamicType;
            public int[] LimitX, LimitY, LimitZ;
            public float ColliderRadius, ColliderRadiusSub;
            // Stock masks are per-part and NOT a single value: on atbm-cstm-0140 the skirt is 1,
            // the jacket 64, streamers 256, and sleeves and leg skin are 0 — they take part in no
            // collision at all. Rigging everything as -1 puts 28 ribbon and sleeve bones into
            // every one of the 30 static colliders at once, which is not swing, it is a brawl.
            public int CollisionMask, ResetType, ColliderType;
            public int Samples;
        }

        /// <summary>Geometric category -> the stock part names that play the same role.</summary>
        private static readonly Dictionary<string, string[]> PartsOf = new Dictionary<string, string[]>
        {
            ["skirt"] = new[] { "Skirt", "TopSkirt", "SkirtAcce" },
            ["ribbon"] = new[] { "Ribbon", "LRibbon", "Acce", "TopAcce", "UnderAcce" },
            ["sleeve"] = new[] { "Sleeve" },
            ["cloth"] = new[] { "Cloth", "Jacket", "TopJacket" },
            ["skin"] = new[] { "LegSkin", "UpLegSkin", "ArmSkin" },
        };

        public static string SourcePath;
        public static string Bundle;

        private static Dictionary<(string, string), Row> _rows;
        private static Dictionary<string, string> _hosts;

        /// <summary>Chain host this costume actually uses for a category, or null.</summary>
        public static string HostFor(string category) =>
            _hosts != null && _hosts.TryGetValue(category, out var host) ? host : null;

        /// <summary>
        /// This costume's row for (category, role), falling back to a NEIGHBOURING role of the same
        /// category before giving up.
        ///
        /// A costume does not have to use all three roles: atbm-cstm-0140's ribbons and jacket are
        /// two bones deep, so they have Root and Tip and no Mid at all. A strand of ours that is
        /// deeper asks for the missing role, and without this the whole bone fell back to the
        /// 530-body median — including `collisionMask = -1`, which put it in every collider.
        /// Measured in the built bundle: ribbon bones came out with the median's stiffness 0.008 /
        /// mass 0.7 / mask -1 while the skirt right next to them carried the costume's own values.
        /// </summary>
        public static Row For(string category, string role)
        {
            if (_rows == null)
                return null;
            if (_rows.TryGetValue((category, role), out var exact))
                return exact;
            // Mid is the interpolating role, so a missing Mid is best served by Root (the anchored
            // end) rather than Tip, whose values are tuned for a free end.
            foreach (var fallback in role == "Mid" ? new[] { "Root", "Tip" }
                     : role == "Tip" ? new[] { "Mid", "Root" }
                     : new[] { "Mid", "Tip" })
            {
                if (_rows.TryGetValue((category, fallback), out var near))
                    return near;
            }
            return null;
        }

        private static Chain[] _chains;

        /// <summary>
        /// This costume's own ring radii for a chain of `depth` layers on `host`, or null.
        ///
        /// The hardcoded table was copied off `hmsz-cstm-0059`'s skirt — a DIFFERENT costume — and
        /// is 50% wide at the first free layer and 60% wide by the fourth. The ring is what bounds
        /// lateral travel, so being wide everywhere is the "swings too far, snaps back" look.
        /// </summary>
        public static float[] LayerRadii(string host, int depth)
        {
            if (_chains == null || _chains.Length == 0)
                return null;
            var candidates = _chains.Where(c => c.host == host && c.layers != null).ToArray();
            if (candidates.Length == 0)
                candidates = _chains.Where(c => c.layers != null).ToArray();
            if (candidates.Length == 0)
                return null;
            // Closest layer count wins: a 3-layer chain's radii describe a 3-deep hang, and using
            // a 4-layer chain's would put the widest ring one level too early.
            var best = candidates.OrderBy(c => Math.Abs(c.layers.Length - depth)).First();
            return best.layers.Select(l => l.radius).ToArray();
        }

        /// <summary>Part -> bone count for the replaced costume; the target a classifier should hit.</summary>
        public static Dictionary<string, int> PartHistogram { get; private set; }

        /// <summary>Load the target costume's own numbers. Returns how many bones backed them.</summary>
        public static int Load(string path, string bundle)
        {
            _rows = null;
            _hosts = null;
            if (string.IsNullOrEmpty(path) || !System.IO.File.Exists(path))
            {
                Debug.LogWarning($"[SDK] 摇物真值文件不存在，回退中位数预设: {path}");
                return 0;
            }

            var parsed = JsonUtility.FromJson<File>(System.IO.File.ReadAllText(path));
            var mine = parsed.bones.Where(b => b.bundle == bundle).ToArray();
            if (mine.Length == 0)
            {
                Debug.LogWarning($"[SDK] 摇物真值里没有 {bundle}，回退中位数预设");
                return 0;
            }

            Bundle = bundle;
            _chains = (parsed.chains ?? new Chain[0]).Where(c => c.bundle == bundle).ToArray();
            PartHistogram = mine.GroupBy(b => b.part).ToDictionary(g => g.Key, g => g.Count());
            _rows = new Dictionary<(string, string), Row>();
            _hosts = new Dictionary<string, string>();
            foreach (var (category, parts) in PartsOf.Select(p => (p.Key, p.Value)))
            {
                var group = mine.Where(b => parts.Contains(b.part)).ToArray();
                if (group.Length == 0)
                    continue;
                // A chain host is a name, so take the one this costume uses most for the category.
                var host = group.Where(b => !string.IsNullOrEmpty(b.chainHost) && b.chainHost != "None")
                    .GroupBy(b => b.chainHost).OrderByDescending(g => g.Count()).FirstOrDefault();
                if (host != null)
                    _hosts[category] = host.Key;

                foreach (var role in new[] { "Root", "Mid", "Tip" })
                {
                    var rows = group.Where(b => RoleOf(b) == role).ToArray();
                    if (rows.Length == 0)
                        continue;
                    // Median, not mean: a single outlier bone should not drag a whole category.
                    _rows[(category, role)] = new Row
                    {
                        Damping = Median(rows, b => b.damping),
                        Stiffness = Median(rows, b => b.stiffness),
                        Spring = Median(rows, b => b.spring),
                        Pendulum = Median(rows, b => b.pendulum),
                        PendulumRange = Median(rows, b => b.pendulumRange),
                        Mass = Median(rows, b => b.mass),
                        Wind = Median(rows, b => b.wind),
                        RootWeight = Median(rows, b => b.rootWeight),
                        UseLimit = Mode(rows, b => b.useLimit),
                        DynamicType = Mode(rows, b => b.dynamicType),
                        LimitX = rows[0].limitX,
                        LimitY = rows[0].limitY,
                        LimitZ = rows[0].limitZ,
                        ColliderRadius = Median(rows, b => b.colliderRadius),
                        ColliderRadiusSub = Median(rows, b => b.colliderRadiusSub),
                        CollisionMask = Mode(rows, b => b.collisionMask),
                        ResetType = Mode(rows, b => b.resetType),
                        ColliderType = Mode(rows, b => b.colliderType),
                        Samples = rows.Length,
                    };
                }
            }

            Debug.Log($"[SDK] 摇物真值：{bundle} 自带 {mine.Length} 根，"
                      + $"归并成 {_rows.Count} 组 (category,role)，锚点 "
                      + string.Join(", ", _hosts.Select(h => $"{h.Key}→{h.Value}")));
            return mine.Length;
        }

        /// <summary>
        /// Report the geometric classification against what the replaced costume actually has.
        ///
        /// Until now "is the classifier right?" could only be answered by looking at the model and
        /// guessing. The costume being replaced is a target: it has 32 Skirt + 24 TopSkirt + 11
        /// Jacket + 4 Ribbon bones, so 24 bones landing in `ribbon` and none in `cloth` is a
        /// mismatch that shows up as a number instead of as a feeling — and a category with no
        /// chain in stock (`ribbon`) swallowing a jacket means that cloth ends up with no chain
        /// solving it at all.
        ///
        /// Reported, not corrected: the mapping from stock part names to geometric categories is a
        /// judgement, and silently reshuffling strands to hit a histogram would be fitting to the
        /// number rather than to the model.
        /// </summary>
        public static void ReportClassification(Dictionary<string, int> ours)
        {
            if (PartHistogram == null || ours == null)
                return;
            var expected = new Dictionary<string, int>();
            foreach (var (category, parts) in PartsOf.Select(p => (p.Key, p.Value)))
                expected[category] = PartHistogram.Where(p => parts.Contains(p.Key)).Sum(p => p.Value);

            var lines = expected.Keys.Union(ours.Keys).OrderBy(k => k).Select(category =>
            {
                ours.TryGetValue(category, out var mine);
                expected.TryGetValue(category, out var stock);
                var flag = stock == 0 && mine > 0 ? " ←原版没有这类"
                    : mine == 0 && stock > 0 ? " ←原版有我们没有"
                    : stock > 0 && (mine > stock * 2 || mine * 2 < stock) ? " ←数量差一倍以上"
                    : "";
                return $"{category} {mine}/{stock}{flag}";
            });
            Debug.Log($"[SDK] 分类对照（我们/原版 {Bundle}）：{string.Join("  ", lines)}"
                      + $"；原版部位构成 {string.Join(", ", PartHistogram.OrderByDescending(p => p.Value).Select(p => $"{p.Key}={p.Value}"))}");
        }

        private static string RoleOf(Bone bone) =>
            bone.isChainRoot || bone.tier <= 1 ? "Root" : bone.isTip ? "Tip" : "Mid";

        private static float Median(Bone[] rows, Func<Bone, float> pick)
        {
            var values = rows.Select(pick).OrderBy(v => v).ToArray();
            return values.Length % 2 == 1
                ? values[values.Length / 2]
                : 0.5f * (values[values.Length / 2 - 1] + values[values.Length / 2]);
        }

        private static int Mode(Bone[] rows, Func<Bone, int> pick) =>
            rows.Select(pick).GroupBy(v => v).OrderByDescending(g => g.Count()).First().Key;
    }
}
