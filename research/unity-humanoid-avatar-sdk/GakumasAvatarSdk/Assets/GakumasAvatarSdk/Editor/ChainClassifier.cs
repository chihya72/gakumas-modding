// Work out what a model's non-body bone chains *are* — skirt, sleeve, cape, ribbon — without reading
// their names.
//
// The swing rigger used to find chains by name: a bone counted as swing if it ended in `_S`, and its
// category came from tokens like "skirt" / "ribbon". That works for a source that happens to share
// this game's naming convention, and finds exactly zero bones on anything else. A Genshin rip calls
// its hem `Bone_HemA01_L`, an MMD model calls it `スカート`, and both get no physics at all.
//
// Three signals replace the name, in order of how much they can be trusted:
//
//   1. Skinned or not.   A bone with no weight on the mesh is a helper — an AO proxy, an attach
//                        point, a camera anchor. Whatever it is, moving it changes no pixel.
//   2. Which body bone it hangs from. Every garment chain, in every model, eventually parents into a
//                        Humanoid bone, and that bone says most of what the chain is: hips → hem,
//                        shoulder/arm → sleeve, head → hair. Measured on the stock library too:
//                        of 1537 stock chains the anchors are Pelvis 758, Spine2 86, Spine 82,
//                        UpLeg_H 80, Shoulder 50 — all body bones.
//   3. Which way it hangs. Only needed to split the chest family, where a cape drapes down, a wing
//                        goes back and out, and the bust goes forward.
//
// It will be wrong sometimes — a wing and a cape from the same shoulder are genuinely ambiguous — so
// the design is "be wrong cheaply": every chain's verdict is logged with the evidence, and one line
// in the labels asset overrides it. tools/measure_chain_classifier.py mirrors these rules and scores
// them against the 530 stock bodies; keep the two in sync when editing.
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace GakumasSdk
{
    public static class ChainClassifier
    {
        /// <summary>Author overrides from the job file: strand root bone name -> category.</summary>
        public static Dictionary<string, string> Overrides = new Dictionary<string, string>();

        public sealed class Strand
        {
            public List<Transform> Bones;
            public Transform Anchor;
            public int Siblings;
            public string Category;
            public string Evidence;

            /// <summary>Farthest vertex this strand's bones dominate, measured from its first bone.</summary>
            public float Reach;

            /// <summary>Where that geometry sits relative to the first bone, in root space.</summary>
            public Vector3 ReachDirection;

            /// <summary>How much of that geometry's weight goes to humanoid bones — body skin vs a shell.</summary>
            public float BodyShare;

            /// <summary>Layer 0 came from a weightless pivot node rather than from the source's chain.</summary>
            public bool PivotAnchored;
        }

        /// <summary>Anchor body bone -> category, when the anchor alone decides it.</summary>
        private static string ByAnchor(string anchor)
        {
            if (anchor == null)
                return null;
            if (anchor.Contains("Hand") || anchor.Contains("ForeArm") || anchor.Contains("Arm")
                || anchor.Contains("Shoulder"))
                return "sleeve";
            if (anchor == "Head" || anchor == "Neck")
                return "ribbon";           // hair and head accessories: the ribbon row is the soft one
            if (anchor.Contains("Leg") || anchor.Contains("Foot") || anchor.Contains("Toe"))
                return "skirt";            // boot tops, leg ribbons — same clamps as a hem
            if (anchor == "Hips" || anchor == "Pelvis" || anchor == "Spine")
                return "skirt";
            return null;                   // Spine1 / Spine2: needs the direction test below
        }

        public static List<Strand> Classify(GameObject root)
        {
            var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            var weighted = WeightedBones(renderer);
            var body = HumanoidBridge.BodyBones;

            bool IsGarment(Transform bone) =>
                bone != null && !body.Contains(bone.name) && weighted.Contains(bone);

            // A strand runs while exactly one child continues it, and every branch of a fork starts
            // its own. Getting that second half wrong cost the whole front and back of a skirt: the
            // panels hung off a garment bone (`Bone_SpineTwist01_M`, `Bone_BowknotC01_M`) that forked
            // three ways, so the parent's strand ended at one bone and was dropped as a stub, while
            // the branches never started one of their own — "parent is a garment bone" disqualified
            // them. Eleven panels carrying 19% of the body's weight came out welded to the spine, and
            // nothing offline noticed because every bone was still bound and still drawn.
            bool Continues(Transform bone)
            {
                if (!IsGarment(bone.parent))
                    return false;
                var siblings = 0;
                foreach (Transform child in bone.parent)
                    if (IsGarment(child))
                        siblings++;
                return siblings == 1;
            }

            var strands = new List<Strand>();
            var skippedStubs = new List<string>();
            foreach (var candidate in root.GetComponentsInChildren<Transform>(true))
            {
                if (!IsGarment(candidate) || Continues(candidate))
                    continue;
                var bones = new List<Transform> { candidate };
                var cursor = candidate;
                while (true)
                {
                    Transform next = null;
                    var found = 0;
                    foreach (Transform child in cursor)
                        if (IsGarment(child))
                        {
                            next = child;
                            found++;
                        }
                    if (found != 1)
                        break;
                    cursor = next;
                    bones.Add(cursor);
                }

                // A lone bone is not a chain. It has no tail to swing about, and layer 0 of a chain is
                // the anchored one — so a one-bone strand simulates nothing however it is tuned (the
                // same reason three of chs-sucu-00's hem panels sat rigid until `_S_End` was let in).
                // What it usually *is* is a body helper: an elbow or knee corrective, a forearm twist,
                // a breast bone — all of which sit at their parent with zero extent, and all of which
                // would make the body itself jiggle if handed to the swing solver.
                //
                // Unless the missing layer 0 is sitting right there: a decoration is often hung on a
                // weightless pivot node, and `IsGarment` rejects that node for carrying no weight, so
                // the piece below it starts its own strand, comes out one bone long and is dropped.
                // `Bone_AccessoriesKeyB01_M` is exactly that — no weight, not even in the bone list —
                // and the 2120-vertex decoration under it (24 cm out behind the spine) therefore never
                // got a swing component and stood rigid in game. Taking the pivot as the anchor makes
                // the strand two long, with the weighted bone free to move where it belongs.
                var pivotAnchored = false;
                if (bones.Count < 2)
                {
                    var pivot = candidate.parent;
                    if (pivot != null && !body.Contains(pivot.name) && !weighted.Contains(pivot))
                    {
                        bones.Insert(0, pivot);
                        pivotAnchored = true;
                    }
                    else
                    {
                        skippedStubs.Add(candidate.name);
                        continue;
                    }
                }

                var anchor = candidate.parent;
                while (anchor != null && !body.Contains(anchor.name))
                    anchor = anchor.parent;
                strands.Add(new Strand { Bones = bones, Anchor = anchor, PivotAnchored = pivotAnchored });
            }

            Transform hips = null;
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                if (transform.name == "Hips")
                {
                    hips = transform;
                    break;
                }

            // How many strands share an anchor — a hem is a ring of panels, a cape is one sheet.
            var perAnchor = new Dictionary<Transform, int>();
            foreach (var strand in strands)
                if (strand.Anchor != null)
                    perAnchor[strand.Anchor] = perAnchor.GetValueOrDefault(strand.Anchor) + 1;
            MeasureGeometry(strands, renderer, root.transform, body);
            // A pivot-anchored strand exists only because a weightless node was accepted as its layer
            // 0 — the source never declared it a chain, so that is this file's guess and it must not
            // be allowed to hand *body skin* to the swing solver. `+PelvisTwist CF A01` hangs off the
            // rip's own `Bip001` pivot and deforms the pelvis and belly; simulating it would wobble
            // the stomach. Geometry decides: skin shares its vertices with the humanoid skeleton
            // (measured 76% there), a decoration is its own shell.
            strands.RemoveAll(strand =>
            {
                if (!strand.PivotAnchored || strand.BodyShare <= 0.25f)
                    return false;
                skippedStubs.Add($"{strand.Bones[strand.Bones.Count - 1].name}"
                                 + $"（人形骨共权重 {strand.BodyShare * 100:0}% → 身体的皮）");
                return true;
            });
            foreach (var strand in strands)
            {
                strand.Siblings = strand.Anchor != null ? perAnchor[strand.Anchor] : 1;
                Decide(strand, root.transform, hips);
            }
            if (skippedStubs.Count > 0)
                Debug.Log($"[SDK] 跳过 {skippedStubs.Count} 根单骨（无链尾，摇不起来，多半是肘/膝/扭转类体内辅助骨）："
                          + string.Join(", ", skippedStubs.Take(8)) + (skippedStubs.Count > 8 ? " …" : ""));
            return strands;
        }

        /// <summary>
        /// How far the geometry each strand drives actually extends, and whether it is body skin.
        ///
        /// The extent test below used to read the *bones*, and that is the wrong ruler: a decoration
        /// can hang off a two-bone hinge whose bones sit on the same spot. Measured on the Genshin rip,
        /// `Bone_AccessoriesKeyB01_M → B02_M` are **0.00 cm** apart and drive 2120 vertices reaching
        /// 24 cm out behind the spine — the strand was filed as a zero-extent body helper and pinned,
        /// so in game that decoration stood out horizontally and never moved.
        /// </summary>
        private static void MeasureGeometry(List<Strand> strands, SkinnedMeshRenderer renderer,
                                            Transform root, ICollection<string> body)
        {
            if (renderer == null || renderer.sharedMesh == null)
                return;
            var bones = renderer.bones;
            var owner = new Dictionary<Transform, Strand>();
            foreach (var strand in strands)
                foreach (var bone in strand.Bones)
                    owner[bone] = strand;

            var vertices = renderer.sharedMesh.vertices;
            var weights = renderer.sharedMesh.boneWeights;
            var bodyWeight = new Dictionary<Strand, float>();
            var totalWeight = new Dictionary<Strand, float>();
            var count = Mathf.Min(vertices.Length, weights.Length);
            for (var index = 0; index < count; index++)
            {
                var weight = weights[index];
                if (weight.boneIndex0 >= bones.Length || bones[weight.boneIndex0] == null
                    || !owner.TryGetValue(bones[weight.boneIndex0], out var strand))
                    continue;
                // Vertices this strand *dominates*; a vertex it merely touches belongs to whatever
                // holds most of it.
                var point = renderer.transform.TransformPoint(vertices[index]);
                var offset = root.InverseTransformVector(point - strand.Bones[0].position);
                if (offset.magnitude > strand.Reach)
                {
                    strand.Reach = offset.magnitude;
                    strand.ReachDirection = offset.normalized;
                }
                // Only the *co*-influences: the strand's own bones dominate these vertices by
                // definition, and counting them dilutes the ratio to nothing (`+PelvisTwist CF A01`
                // measured 20% body with them in and 92% with them out). What the question really is:
                // of the other bones deforming this geometry, are they the humanoid skeleton?
                foreach (var (slot, share) in new[]
                         {
                             (weight.boneIndex0, weight.weight0), (weight.boneIndex1, weight.weight1),
                             (weight.boneIndex2, weight.weight2), (weight.boneIndex3, weight.weight3),
                         })
                {
                    if (share <= 0f || slot >= bones.Length || bones[slot] == null
                        || owner.ContainsKey(bones[slot]))
                        continue;
                    totalWeight[strand] = totalWeight.GetValueOrDefault(strand) + share;
                    if (body.Contains(bones[slot].name))
                        bodyWeight[strand] = bodyWeight.GetValueOrDefault(strand) + share;
                }
            }
            foreach (var strand in strands)
                strand.BodyShare = totalWeight.GetValueOrDefault(strand) > 0f
                    ? bodyWeight.GetValueOrDefault(strand) / totalWeight[strand]
                    : 0f;
        }

        private static void Decide(Strand strand, Transform root, Transform hips)
        {
            var anchorName = strand.Anchor == null ? null : strand.Anchor.name;
            var head = strand.Bones[0].position;
            var tail = strand.Bones[strand.Bones.Count - 1].position;
            // Root space, so a rotated import does not change the verdict.
            var direction = root.InverseTransformVector(tail - head);
            var length = direction.magnitude;
            if (length > 0.0001f)
                direction /= length;

            // Measured on the stock library (tools/measure_chain_classifier.py): a hem runs 18 cm, a
            // ribbon 10 cm, a cape 14 cm — and the skin helpers that deform a thigh or a shoulder sit
            // at a median of 0.0 cm, their bones stacked on the same spot. A chain with no extent
            // cannot swing whatever row it is given, and handing it to the solver makes the *body*
            // jiggle. Stock pins exactly these with resetType=Skin; so does this.
            if (length < 0.02f)
            {
                // Stacked bones, so the bone ruler says nothing. What separates a body helper from a
                // decoration on a hinge is *what it deforms*: a helper's vertices are body skin, shared
                // with the humanoid bone it hangs off, while a decoration is its own shell reaching
                // away from the body. Read the geometry instead and only pin the former.
                if (strand.BodyShare > 0.25f || strand.Reach < 0.02f)
                {
                    strand.Category = "skin";
                    strand.Evidence = $"锚点 {anchorName}，链长 {length * 100:0.#}cm ≈ 0，"
                                      + $"驱动的几何 {strand.Reach * 100:0.#}cm / 人形骨占比 "
                                      + $"{strand.BodyShare * 100:0}% → 体内辅助骨，钉住";
                    return;
                }
                // A shell on a hinge: keep it, and take its direction and extent from the geometry.
                direction = strand.ReachDirection;
                length = strand.Reach;
                anchorName = anchorName ?? "";
            }

            var category = ByAnchor(anchorName);
            var reason = category != null ? $"锚点 {anchorName}" : null;
            if (category == "skirt" && strand.Siblings < 4)
            {
                // A hem is a ring: stock hems hang 4-8 panels off one anchor. One or two strands off
                // the hips is an apron, a tail or a sash — the cloth row, not the skirt row.
                category = "cloth";
                reason = $"锚点 {anchorName}，同锚点只有 {strand.Siblings} 条 → 不是一圈裙摆";
            }
            if (category == null)
            {
                // Chest family: down = a sheet that drapes (cape/coat), out or back = a wing or a
                // stole, forward = the bust, which the breast driver owns outright.
                if (direction.y < -0.6f)
                {
                    category = "cloth";
                    reason = $"锚点 {anchorName}，向下垂（y {direction.y:0.00}）";
                }
                else if (direction.z > 0.4f)
                {
                    category = "ribbon";
                    reason = $"锚点 {anchorName}，朝前（z {direction.z:0.00}）—— 胸口一带，按软饰品处理";
                }
                else
                {
                    category = "ribbon";
                    reason = $"锚点 {anchorName}，向后/向外（z {direction.z:0.00} x {direction.x:0.00}）—— 翅膀/披挂";
                }
            }

            // Anything that hangs off the waist and points down is a skirt panel, whichever spine
            // bone it technically anchors to. Measured on 381 stock costumes: all 3000+ `*Skirt_A`
            // panels start between +0.3 cm and +17.4 cm above Hips, median +7.2 cm. This model's back
            // panels hang off a bow at the small of the back, so their nearest body bone is Spine1
            // and there are only three of them — the anchor table sends Spine1 to the direction test
            // and the ring test then downgrades a group of three to cloth. Both readings are
            // defensible and both are wrong here: cloth keeps collisionMask −1, so the panel fights
            // the 23 cm capsule around the hips instead of the thigh, which is the "stiff skirt that
            // will not hug the leg" from chs-sucu-00 all over again.
            if (hips != null && category != "skirt" && category != "sleeve" && direction.y < -0.5f)
            {
                var above = root.InverseTransformPoint(head).y - root.InverseTransformPoint(hips.position).y;
                if (above > -0.05f && above < 0.20f)
                {
                    category = "skirt";
                    reason = $"根部在腰上 {above * 100:0.#}cm 且向下垂（原版裙摆 +0.3..+17.4cm）";
                }
            }

            // The author's word beats every rule above it — that is what the override list is for.
            if (Overrides.TryGetValue(strand.Bones[0].name, out var declared))
            {
                category = declared;
                reason = "作者指定";
            }

            strand.Category = category;
            strand.Evidence = $"{reason}，{strand.Bones.Count} 骨，长 {length * 100:0.#}cm";
        }

        private static HashSet<Transform> WeightedBones(SkinnedMeshRenderer renderer)
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

        /// <summary>One line per chain, so a wrong verdict is visible before the game ever runs.</summary>
        public static void Report(List<Strand> strands)
        {
            var counts = new Dictionary<string, int>();
            foreach (var strand in strands)
                counts[strand.Category] = counts.GetValueOrDefault(strand.Category) + strand.Bones.Count;
            Debug.Log($"[SDK] 按几何分类出 {strands.Count} 条链 / {strands.Sum(s => s.Bones.Count)} 根骨："
                      + string.Join(", ", counts.Select(pair => $"{pair.Key} {pair.Value}")));
            // Geometry is all this classifier has, but the costume being replaced is a target it
            // can be held against — the first objective check this step has ever had.
            VanillaSwingTruth.ReportClassification(counts);
            foreach (var strand in strands.OrderBy(s => s.Category).ThenBy(s => s.Bones[0].name))
                Debug.Log($"[SDK]   {strand.Bones[0].name} … {strand.Bones[strand.Bones.Count - 1].name}"
                          + $" → {strand.Category}（{strand.Evidence}）");
        }
    }
}
