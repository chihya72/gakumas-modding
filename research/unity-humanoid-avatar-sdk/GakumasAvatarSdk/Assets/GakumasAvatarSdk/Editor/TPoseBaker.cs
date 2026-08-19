// Put an imported model into this game's rest pose — for real, mesh and all.
//
// The game drives the body through nothing but Humanoid muscle retargeting (evidence in
// docs/rest-pose-dead-end.md §零), and it builds the Avatar at runtime from the skeleton we ship.
// So the pose in the bundle *is* what Unity is told the rest pose is, and every clip plays relative
// to it: AvatarBench measured a model resting in an A-pose 69° off the canonical T, and the error
// under animation came out 69° — the same number to the decimal. Stock bodies rest in a T to within
// a degree. Matching that is the whole job.
//
// This is not RestPoseNormalizer, which wrote target rotation *values* onto the bones and is dead:
// the bench showed bone axes contribute exactly nothing, because retargeting absorbs them. What
// matters is where the bones point, and moving them means moving the skin with them:
//
//     new_v = Σ wᵢ · (rendererW2L · boneᵢ.LTW_new · bindposeᵢ_old) · v      ← skin baked into the mesh
//     bindposeᵢ_new = boneᵢ.worldToLocal_new · rendererLTW                  ← new rest becomes bind
//
// Recomputing bind poses *without* the first line is the trap: the model then passes every offline
// check (bind pose self-consistent, rest pose pixel-identical) while the skeleton stands in a T and
// the mesh stays in its A. Both lines, or neither.
using System.Collections.Generic;
using UnityEngine;

namespace GakumasSdk
{
    public static class TPoseBaker
    {
        // Parent before child: aiming the upper arm moves the forearm, and the forearm is aimed from
        // where it ends up. Canonical humanoid rest: facing +z, character's right is +x, so the left
        // arm lies along −x and both legs along −y. Stock bodies measure ±1.00 on the nose.
        private static readonly (string Bone, string Child, Vector3 Aim)[] Aims = BuildAims();

        // Fingers are part of the rest pose too, and leaving them out is the same bug as shipping an
        // A-pose: this rip was modelled gripping a claymore, so its curled fist became the zero the
        // game's finger muscles play against and the hands came out shredded. The stock reference
        // measures dead straight — every finger 0.0° off the arm axis, every knuckle 0.0°, thumb
        // exactly 45.0° — which is Unity's canonical humanoid hand. Ours measured 10–27° of knuckle
        // bend and a 24.6° thumb.
        private static (string, string, Vector3)[] BuildAims()
        {
            var aims = new List<(string, string, Vector3)>
            {
                ("LeftArm", "LeftForeArm", Vector3.left),
                ("LeftForeArm", "LeftHand", Vector3.left),
                ("RightArm", "RightForeArm", Vector3.right),
                ("RightForeArm", "RightHand", Vector3.right),
                ("LeftUpLeg", "LeftLeg", Vector3.down),
                ("LeftLeg", "LeftFoot", Vector3.down),
                ("RightUpLeg", "RightLeg", Vector3.down),
                ("RightLeg", "RightFoot", Vector3.down),
            };
            foreach (var (side, outward) in new[] { ("Left", -1f), ("Right", 1f) })
            {
                var along = new Vector3(outward, 0f, 0f);
                // 45° between the arm axis and straight ahead, measured off the reference.
                var thumb = new Vector3(outward * 0.7071f, 0f, 0.7071f);
                foreach (var finger in new[] { "Index", "Middle", "Ring", "Pinky", "Thumb" })
                {
                    var aim = finger == "Thumb" ? thumb : along;
                    // Knuckle before fingertip, same reason the shoulder comes before the elbow.
                    aims.Add(($"{side}Hand{finger}1", $"{side}Hand{finger}2", aim));
                    aims.Add(($"{side}Hand{finger}2", $"{side}Hand{finger}3", aim));
                }
            }
            return aims.ToArray();
        }

        // Roll about the limb's own axis, which the aim pass says nothing about: FromToRotation is the
        // minimal rotation onto a direction, so it carries whatever roll the source pose had — and
        // carries a different amount on each side, because the two minimal axes differ. AvatarBench
        // cannot see this at all (it compares parent→child directions, which are roll-blind: measured
        // 0.0° on all four arm probes while the arms were rolled 12–18° off and 6.4° apart from each
        // other). The muscles play relative to the rest roll, so what shows in game is the sleeve and
        // the pauldron turned around the arm.
        //
        // The target is sucu's own rest — the one body confirmed working in game, and symmetric to
        // 0.0° between its sides, which is the part that matters most. Measured as thumb→pinky across
        // the palm so it does not depend on either skeleton's bone axes.
        private static readonly Vector3 PalmAcross = new Vector3(0f, 0.35f, -0.94f);

        private static readonly (string Arm, string Hand, string Thumb, string Pinky)[] Rolls =
        {
            ("LeftArm", "LeftHand", "LeftHandThumb1", "LeftHandPinky1"),
            ("RightArm", "RightHand", "RightHandThumb1", "RightHandPinky1"),
        };

        /// <summary>Aims the limbs at the game's rest directions and bakes the skin onto it.</summary>
        /// <returns>How many bones moved, or -1 when the skeleton is not one this can work on.</returns>
        public static int Bake(GameObject root)
        {
            var renderers = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            if (renderers.Length == 0)
            {
                Debug.LogError("[SDK] T-pose 烘焙：没有 SkinnedMeshRenderer");
                return -1;
            }

            var bones = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                bones[transform.name] = transform;

            // Snapshot before anything moves: the bake needs each skin bone's bind pose from before
            // the aiming, and a bone that is not aimed still has to contribute an identity delta
            // rather than a missing entry.
            var restBindposes = new Dictionary<SkinnedMeshRenderer, Matrix4x4[]>();
            foreach (var renderer in renderers)
                restBindposes[renderer] = renderer.sharedMesh.bindposes;

            var moved = new List<string>();
            foreach (var (boneName, childName, aim) in Aims)
            {
                if (!bones.TryGetValue(boneName, out var bone) || !bones.TryGetValue(childName, out var child))
                {
                    Debug.LogWarning($"[SDK] T-pose 烘焙：缺 {boneName} 或 {childName}，跳过");
                    continue;
                }
                var current = child.position - bone.position;
                if (current.sqrMagnitude < 1e-12f)
                    continue;
                var target = root.transform.TransformDirection(aim);
                var angle = Vector3.Angle(current, target);
                bone.rotation = Quaternion.FromToRotation(current, target) * bone.rotation;
                if (angle > 0.01f)
                    moved.Add($"{boneName} {angle:F1}°");
            }

            // After the aims — the arm has to be straight before "roll about the arm" means anything.
            var rolled = new List<string>();
            foreach (var (armName, handName, thumbName, pinkyName) in Rolls)
            {
                if (!bones.TryGetValue(armName, out var arm) || !bones.TryGetValue(handName, out var hand)
                    || !bones.TryGetValue(thumbName, out var thumb) || !bones.TryGetValue(pinkyName, out var pinky))
                {
                    Debug.LogWarning($"[SDK] T-pose 烘焙：{armName} 一路缺骨，滚转没法量，跳过");
                    continue;
                }
                var axis = (hand.position - arm.position).normalized;
                if (axis.sqrMagnitude < 0.5f)
                    continue;
                var current = Vector3.ProjectOnPlane(pinky.position - thumb.position, axis).normalized;
                var target = Vector3.ProjectOnPlane(root.transform.TransformDirection(PalmAcross), axis).normalized;
                if (current.sqrMagnitude < 0.5f || target.sqrMagnitude < 0.5f)
                    continue;
                var twist = Vector3.SignedAngle(current, target, axis);
                // Rotating about the arm's own axis leaves every aim intact — the limb is straight, so
                // the forearm and hand stay on the same line and only turn around it.
                arm.rotation = Quaternion.AngleAxis(twist, axis) * arm.rotation;
                if (Mathf.Abs(twist) > 0.01f)
                    rolled.Add($"{armName} {twist:F1}°");
            }

            // Verify first, transform only if it has to. A source that already rests in a T needs
            // nothing from this file: every delta is identity, the solve is identity, and the mesh
            // comes out the same up to float noise. Saying so and stopping is worth more than a
            // silent no-op — it tells an author their FBX is already in the shape this game wants,
            // and it keeps the one destructive step in the pipeline from running when it has no work.
            if (moved.Count == 0 && rolled.Count == 0)
            {
                Debug.Log("[SDK] T-pose 校验通过：源模型本来就是标准 T-pose，网格和 bindpose 一个字节都没动");
                return 0;
            }

            foreach (var renderer in renderers)
                BakeSkin(renderer, restBindposes[renderer]);

            Debug.Log($"[SDK] T-pose 烘焙：摆正 {moved.Count} 根骨（{string.Join(", ", moved)}）"
                      + (rolled.Count > 0 ? $"，滚转对齐 {string.Join(", ", rolled)}" : "")
                      + $"，{renderers.Length} 个网格的顶点与 bindpose 已随之重算");
            return moved.Count;
        }

        /// <summary>
        /// Points Head's own axes the way this game's do, without moving anything.
        ///
        /// This is not the RestPoseNormalizer the bench killed: bone axes really are absorbed by
        /// retargeting, and the *body* does not care. The hair and face parts do — the actor build
        /// parents them under Head rather than skinning them to it, and a child inherits its parent's
        /// world rotation raw, with no Avatar in the path. A Biped skeleton rests with Head's +Y
        /// pointing forward and +Z pointing left, so both parts came out turned by exactly that:
        /// measured 121.7° in-game, against three stock actors that agree with each other within 3°.
        /// </summary>
        // ponytail: Head only, because it is the only bone the actor build hangs a part on. Hands take
        // props the same way — extend the list here if a prop ever lands crooked.
        public static bool AlignHeadAxes(GameObject root)
        {
            Transform head = null;
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                if (transform.name == "Head")
                    head = head ?? transform;
            if (head == null)
            {
                Debug.LogWarning("[SDK] Head 轴向对齐：找不到 Head，跳过（头发/脸会跟着源模型的轴向转）");
                return false;
            }

            var angle = Turn(root, head, root.transform.rotation);
            if (angle <= 0f)
                return false;
            Debug.Log($"[SDK] Head 轴向对齐：转了 {angle:F1}°（头发/脸是挂在 Head 下面的，直接继承它的朝向）");
            return true;
        }

        /// <summary>
        /// The rest frames the pose drivers are written against, measured off 60 stock costumes and
        /// identical in all of them to two decimals.
        ///
        /// A driver's coefficient is a number in its host bone's own axes, and stock uses the *same*
        /// sign on both sides of the body — `Arm_H` is −0.8 left and right, `ForeArm_H` is (0,−0.4,0)
        /// left and right. That only mirrors correctly because stock's two sides are themselves
        /// mirrored: the left arm rests at identity while the right rests 180° round from it. A rip
        /// whose two arms carry the *same* frame therefore gets the correction applied the right way
        /// on one side and inverted on the other — the shoulder eats +0.8 of its own rotation instead
        /// of −0.8, nine times the deflection of a correct one, which in game is an arm wrung round.
        /// </summary>
        public static readonly (string Bone, Vector3 Forward, Vector3 Up)[] DrivenFrames = BuildFrames();

        private static (string, Vector3, Vector3)[] BuildFrames()
        {
            var frames = new List<(string, Vector3, Vector3)>
            {
                ("LeftArm", Vector3.forward, Vector3.up), ("LeftForeArm", Vector3.forward, Vector3.up),
                ("RightArm", Vector3.back, Vector3.down), ("RightForeArm", Vector3.back, Vector3.down),
                ("LeftUpLeg", Vector3.right, Vector3.forward), ("LeftLeg", Vector3.right, Vector3.forward),
                ("RightUpLeg", Vector3.right, Vector3.back), ("RightLeg", Vector3.right, Vector3.back),
            };
            // The hand is the same story and cost a mangled right fist to find. Nothing drives these
            // through a QuartzDriver — they are pure muscle — but a Biped rip carries the *same* frame
            // on both hands where stock carries mirrored ones, so every right finger sat at local −x
            // against stock's +x. Replaying the game's own recorded pose through the shipped mesh put
            // 280 of 510 blown-out triangles inside the right hand and none in the left.
            // Measured over 60 costumes, spread ±0.000: fingers follow their own arm's frame, and the
            // thumb has its own, rolled 45° into the palm.
            foreach (var (side, forward, up, thumbForward, thumbUp) in new[]
                     {
                         ("Left", Vector3.forward, Vector3.up, Vector3.down, new Vector3(0.7071f, 0f, 0.7071f)),
                         ("Right", Vector3.back, Vector3.down, Vector3.up, new Vector3(0.7071f, 0f, -0.7071f)),
                     })
            {
                frames.Add(($"{side}Hand", forward, up));
                foreach (var finger in new[] { "Index", "Middle", "Ring", "Pinky", "Thumb" })
                for (var joint = 1; joint <= 3; joint++)
                    frames.Add(finger == "Thumb"
                        ? ($"{side}Hand{finger}{joint}", thumbForward, thumbUp)
                        : ($"{side}Hand{finger}{joint}", forward, up));
            }
            return frames.ToArray();
        }

        /// <summary>
        /// Puts the eight driven limb bones into this game's own rest frames. Nothing moves.
        ///
        /// Retargeting absorbs bone axes, which is why RestPoseNormalizer was deleted and why the
        /// bench reads the same numbers with or without it — but the pose drivers are not retargeted.
        /// They read and write bone-local axes directly, so for them the frame is the whole meaning
        /// of the number. This is the one place axes matter, and it is limited to the bones a driver
        /// hosts or references; every other bone keeps whatever the source authored.
        /// </summary>
        public static int AlignDrivenBoneAxes(GameObject root)
        {
            var byName = new Dictionary<string, Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                if (!byName.ContainsKey(transform.name))
                    byName[transform.name] = transform;

            var turned = new List<string>();
            foreach (var (bone, forward, up) in DrivenFrames)
            {
                if (!byName.TryGetValue(bone, out var node))
                    continue;
                var angle = Turn(root, node, root.transform.rotation * Quaternion.LookRotation(forward, up));
                if (angle > 0f)
                    turned.Add($"{bone} {angle:F0}°");
            }
            if (turned.Count > 0)
                Debug.Log($"[SDK] 驱动骨轴向对齐：{turned.Count} 根转到原版静止坐标系"
                          + $"（{string.Join(", ", turned)}）—— 只换表达坐标系，位置和网格不动");
            else
                Debug.Log("[SDK] 驱动骨轴向已是原版坐标系，无需对齐");
            return turned.Count;
        }

        /// <summary>
        /// Re-expresses one bone in a new frame without moving anything: children keep their world
        /// transforms and only this bone's bind pose is recomputed, so `bone.LTW · bindpose` still
        /// resolves to the same skin. Returns the angle turned, or 0 when it was already there.
        /// </summary>
        public static float Turn(GameObject root, Transform bone, Quaternion target)
        {
            var angle = Quaternion.Angle(bone.rotation, target);
            if (angle < 0.01f)
                return 0f;

            var children = new List<(Transform Node, Vector3 Position, Quaternion Rotation)>();
            foreach (Transform child in bone)
                children.Add((child, child.position, child.rotation));
            bone.rotation = target;
            foreach (var (node, position, rotation) in children)
            {
                node.position = position;
                node.rotation = rotation;
            }

            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var index = System.Array.IndexOf(renderer.bones, bone);
                if (index < 0)
                    continue;
                var bindposes = renderer.sharedMesh.bindposes;
                bindposes[index] = bone.worldToLocalMatrix * renderer.transform.localToWorldMatrix;
                renderer.sharedMesh.bindposes = bindposes;
            }
            return angle;
        }

        /// <summary>Quaternion product, on Vector4 so the pieces can be weighted and summed.</summary>
        private static Vector4 Multiply(Vector4 a, Vector4 b) => new Vector4(
            a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
            a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
            a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
            a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z);

        /// <summary>Dual part of the unit dual quaternion for a rigid transform: ½ · t ⊗ q.</summary>
        private static Vector4 Dual(Quaternion rotation, Vector3 translation) => 0.5f * Multiply(
            new Vector4(translation.x, translation.y, translation.z, 0f),
            new Vector4(rotation.x, rotation.y, rotation.z, rotation.w));

        // This used to also pre-distort the rest mesh so that the game's own linear blend, applied at
        // the source's authored pose, reproduced the source exactly — buying back the shoulder that
        // a 67° re-pose collapses (half-width 17.4cm against 12.6cm). It is gone, and deliberately.
        // It was exact at one pose and approximate everywhere else, it had to be masked off the
        // fingers, and every mask boundary creased the geometry that straddled it — the skirt once,
        // then the wrist. The collapse it was fighting is not caused by the bake at all: the game
        // re-poses *any* T-posed model, and stock bodies survive it because their joints are skinned
        // to corrective bones rather than to the humanoid bone. That rig is what HelperBoneRigger
        // now builds, so the bake goes back to being what it says it is — the same rest pose, moved.
        private static void BakeSkin(SkinnedMeshRenderer renderer, Matrix4x4[] restBindposes)
        {
            var mesh = renderer.sharedMesh;
            var bones = renderer.bones;
            if (mesh == null || bones.Length == 0 || restBindposes.Length != bones.Length)
            {
                Debug.LogWarning($"[SDK] T-pose 烘焙：{renderer.name} 的骨与 bindpose 数量对不上，跳过");
                return;
            }
            if (mesh.blendShapeCount > 0)
                // Would need every delta rotated too. No body model here has any; say so rather than
                // silently shipping shapes that pull vertices in the old pose's directions.
                Debug.LogWarning($"[SDK] T-pose 烘焙：{renderer.name} 带 {mesh.blendShapeCount} 个 BlendShape，"
                                 + "它们的偏移量没有跟着转");

            var rendererW2L = renderer.transform.worldToLocalMatrix;
            var rendererLtw = renderer.transform.localToWorldMatrix;
            var delta = new Matrix4x4[bones.Length];
            for (var index = 0; index < bones.Length; index++)
                delta[index] = bones[index] == null
                    ? Matrix4x4.identity
                    : rendererW2L * bones[index].localToWorldMatrix * restBindposes[index];
            // The deltas are rigid, so each one splits cleanly into a rotation and a translation —
            // which is what lets the blend below be done on dual quaternions instead of matrices.
            var deltaRotation = new Quaternion[bones.Length];
            var deltaDual = new Vector4[bones.Length];
            for (var index = 0; index < bones.Length; index++)
            {
                var rotation = delta[index].rotation;
                var translation = delta[index].GetColumn(3);
                deltaRotation[index] = rotation;
                deltaDual[index] = Dual(rotation, translation);
            }

            // The bind poses the bundle will ship: the new rest is the new bind.
            var bindposes = new Matrix4x4[bones.Length];
            for (var index = 0; index < bones.Length; index++)
                bindposes[index] = bones[index] == null
                    ? restBindposes[index]
                    : bones[index].worldToLocalMatrix * rendererLtw;

            var vertices = mesh.vertices;
            var normals = mesh.normals;
            var tangents = mesh.tangents;
            var perVertex = mesh.GetBonesPerVertex();
            var weights = mesh.GetAllBoneWeights();

            var cursor = 0;
            for (var vertex = 0; vertex < vertices.Length; vertex++)
            {
                var influences = vertex < perVertex.Length ? perVertex[vertex] : 0;
                if (influences == 0)
                    continue;
                // Blend the deltas as dual quaternions, not as matrices. Averaging two rotation
                // matrices shrinks the result towards the axis between them, so a vertex weighted
                // half to the shoulder and half to a 69°-rotated arm lands *inside* the arm — the
                // candy-wrapper collapse. Measured on this model before the change: the arm's radius
                // dipped from 6.4cm to 5.0cm and back to 6.2cm across the shoulder's blend band,
                // a 1.4cm waist right where the seam is, while the stock reference runs smooth.
                // The band is only 6cm wide and holds ~11 vertices per centimetre, so there is
                // nothing there to hide it. Dual quaternion blending interpolates the rotation
                // instead of the matrix and keeps the limb's volume.
                var real = Vector4.zero;
                var dual = Vector4.zero;
                var pivot = deltaRotation[weights[cursor].boneIndex];
                for (var i = 0; i < influences; i++, cursor++)
                {
                    var weight = weights[cursor];
                    var rotation = deltaRotation[weight.boneIndex];
                    // q and −q are the same rotation but average to nothing; line them all up first.
                    var sign = Quaternion.Dot(rotation, pivot) < 0f ? -weight.weight : weight.weight;
                    real += new Vector4(rotation.x, rotation.y, rotation.z, rotation.w) * sign;
                    dual += deltaDual[weight.boneIndex] * sign;
                }
                var scale = real.magnitude;
                if (scale < 1e-6f)
                    continue;
                real /= scale;
                dual /= scale;
                var blended = new Quaternion(real.x, real.y, real.z, real.w);
                // translation = 2 · (dual ⊗ conjugate(real))
                var offset = Multiply(dual, new Vector4(-real.x, -real.y, -real.z, real.w)) * 2f;
                var move = Matrix4x4.TRS(new Vector3(offset.x, offset.y, offset.z), blended, Vector3.one);

                vertices[vertex] = move.MultiplyPoint3x4(vertices[vertex]);
                // The blend is rigid, so normals and tangents just turn with it.
                if (normals.Length == vertices.Length)
                    normals[vertex] = blended * normals[vertex];
                if (tangents.Length == vertices.Length)
                {
                    // w is the bitangent sign, not a direction — it survives untouched.
                    var tangent = blended * (Vector3)tangents[vertex];
                    tangents[vertex] = new Vector4(tangent.x, tangent.y, tangent.z, tangents[vertex].w);
                }
            }
            perVertex.Dispose();
            weights.Dispose();

            mesh.vertices = vertices;
            if (normals.Length == vertices.Length)
                mesh.normals = normals;
            if (tangents.Length == vertices.Length)
                mesh.tangents = tangents;

            mesh.bindposes = bindposes;
            mesh.RecalculateBounds();
        }
    }
}
