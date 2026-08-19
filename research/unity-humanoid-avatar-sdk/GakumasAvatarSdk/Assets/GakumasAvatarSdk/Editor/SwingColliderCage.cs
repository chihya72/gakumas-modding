// The collider cage cloth is pushed out of. Covers the whole body, not one costume's needs.
//
// Two rules, and they are not in conflict:
//
//   never blend  every row is one real collider from one real costume, verbatim. Mixing vector3_A
//                from one capsule with vector3_B from another produces shapes nobody authored.
//   cover all    but *which bones* get a collider is a union across costumes, not a copy of one.
//
// The second rule is why this is a union and not a copy of one costume: each stock costume only cages
// what its own garment can reach, so a cage copied wholesale from hmsz-cstm-0059 has nothing for a
// cape, a hakama or a hem that reaches the toes. The author must never have to know the word
// "collider".
//
// The costs are NOT symmetric in the direction first assumed here. "A collider the garment never
// reaches costs nothing" is true only if the garment really never reaches it: a capsule the hem does
// touch holds that hem off the body, which on a fitted garment reads as a stiff skirt floating over
// the thigh. Coverage is still the rule, but a collider added on a *guess* about clipping is a
// change to the silhouette — see the thigh entry below for the one that was added on a wrong
// diagnosis and removed. Sizes are the per-bone median across costumes, taken as one real row rather
// than averaged.
//
// collisionMask is a channel bitfield, kept as stock authored it, and it is load-bearing. The bone
// side has to agree: with mod bones on -1 (Everything) a skirt hits `Hips` — a 0.23 m capsule on
// channels 64|128 that stock skirts never touch — and gets held 23 cm off the hips. Stock skirt bones
// use channel 1, which is exactly the set Pelvis / Leg / Foot / UpLeg carry here. See
// SwingRigger.ColliderMasks.
//
// ponytail: no `Head` collider. Stock puts one on 3 of 60 costumes and it exists for long hair, which
// lives in a different part we do not replace — add it if a body-part cape ever reaches the head.
using UnityEngine;

namespace GakumasSdk
{
    public static class SwingColliderCage
    {
        /// <summary>
        /// Diagnostic only — multiplies every collider radius. 1 is the shipping value.
        ///
        /// Set it to 5 to answer a question no amount of parameter tuning can: *is the collision path
        /// running at all for these bones?* An absurd radius either visibly blows the skirt outward
        /// (collision is alive, so the sizes are what need work) or changes nothing whatsoever
        /// (collision never reaches these bones, and every size we pick is irrelevant). It was run,
        /// and it answered: ×5 threw stock hair around and left this skirt untouched — because the
        /// panels were inert (no free chain layer), not because collision was off. "Nothing moved"
        /// means check the thing being pushed before you keep sizing the pusher.
        /// </summary>
        public static float RadiusScale = 1f;

        // Sphere 0 · Capsule 1 · Line 2 · Plane 3 · None 4
        public readonly struct Entry
        {
            public readonly string Bone;
            public readonly byte Type;
            public readonly int Mask;
            public readonly Vector3 A;
            public readonly Vector3 B;
            public readonly float FloatA;
            public readonly float FloatB;

            public Entry(string bone, byte type, int mask, Vector3 a, Vector3 b, float floatA, float floatB)
            {
                Bone = bone;
                Type = type;
                Mask = mask;
                A = a;
                B = b;
                FloatA = floatA;
                FloatB = floatB;
            }
        }

        public static readonly Entry[] Entries =
        {
            new Entry("Hips", 1, 192, new Vector3(0f, -0.104f, 0f), new Vector3(1f, 0.61f, 0f), 0.23f, 0.18f),
            // Splits the two legs so a skirt cannot collapse inward between them. Rare in stock
            // (2/60) but cheap, and exactly the case a short flared skirt hits.
            new Entry("Pelvis", 1, 1, new Vector3(0f, -0.028f, 0.003f), new Vector3(0f, 0.217f, 0f), 0.06f, 0.06f),
            new Entry("Spine", 1, 832, new Vector3(0f, 0f, 0.008f), new Vector3(0f, 0.107f, 0f), 0.08f, 0.08f),
            new Entry("Spine1", 1, 64, new Vector3(0f, 0.045f, 0.027f), new Vector3(0f, 0.001f, 0f), 0.06f, 0.06f),
            new Entry("Spine2", 1, 256, new Vector3(0f, 0.001f, 0.031f), new Vector3(0f, 0.199f, 0f), 0.068f, 0.068f),
            new Entry("Spine2", 1, 64, new Vector3(0f, 0f, 0.027f), new Vector3(0f, 0.23f, 0f), 0.052f, 0.052f),
            new Entry("Neck", 1, 8, new Vector3(0f, 0.02f, 0.01f), new Vector3(1f, 0.001f, 0f), 0.035f, 0.035f),

            new Entry("LeftLeg", 2, 1, Vector3.zero, Vector3.zero, 0.08f, 0.065f),
            new Entry("RightLeg", 2, 1, Vector3.zero, Vector3.zero, 0.08f, 0.065f),

            // No thigh capsules. A pair copied from mdl_chr_hmsz-cstm-0063_body used to sit here,
            // added to stop the skirt passing through the thigh — but that diagnosis was wrong. The
            // real cause was in SwingRigger: `_S_End` was excluded from strands, so this costume's
            // three one-bone front panels had no free layer and never simulated at all. That is also
            // why sizing the capsule "correctly" changed nothing, and why the ×5 diagnostic moved
            // stock hair but not this skirt. With the panels alive the clipping is gone, and the
            // capsules only held the hem off the leg — wrong for a garment cut to hug it.
            // hmsz-cstm-0059 has no UpLeg collider either, nor do 34 of 60 scanned costumes.
            // Put them back only if a genuinely flared short skirt clips with live panels.
            new Entry("LeftFoot", 2, 129, Vector3.zero, Vector3.zero, 0.05f, 0.06f),
            new Entry("RightFoot", 2, 129, Vector3.zero, Vector3.zero, 0.05f, 0.06f),
            // Toes: what a floor-length skirt or hakama lands on. 8/60 stock costumes cage them.
            new Entry("LeftToeBase", 1, 2, new Vector3(0.01f, 0f, -0.008f), new Vector3(0f, 0.12f, 0f), 0.04f, 0.04f),
            new Entry("RightToeBase", 1, 4, new Vector3(-0.01f, 0f, 0.008f), new Vector3(0f, 0.12f, 0f), 0.04f, 0.04f),

            // Shoulders: what a cape, poncho or stole rests on.
            new Entry("LeftShoulder", 1, 24, new Vector3(-0.055f, 0f, 0f), new Vector3(0f, 0.035f, 0f), 0.05f, 0.04f),
            new Entry("RightShoulder", 1, 24, new Vector3(0.055f, 0f, 0f), new Vector3(0f, 0.035f, 0f), 0.04f, 0.05f),

            new Entry("LeftArm", 2, 8, new Vector3(0f, 0f, 0.005f), new Vector3(0f, 0.001f, 0f), 0.04f, 0.05f),
            new Entry("RightArm", 2, 8, Vector3.zero, Vector3.zero, 0.04f, 0.05f),
            // Hosted on the arm itself, not on `Arm_H`. Stock never puts an ActorSwingStaticBone on a
            // `_H` bone — scanned 40 costumes, the hosts are Hips, Spine1/2, Neck, Arm, ForeArm, Hand,
            // UpLeg, Leg, Foot, and `_H` appears zero times, while `Arm_H` always carries the arm
            // driver. These two entries were harmless only because the bones did not exist yet; once
            // the helper rig ran first they landed a collider on top of a driver, which is a pairing
            // this game has no example of.
            new Entry("LeftArm", 1, 64, new Vector3(-0.06f, -0.004f, 0.005f), new Vector3(0f, 0.222f, 0f), 0.055f, 0.045f),
            new Entry("LeftArm", 1, 128, new Vector3(-0.113f, 0.033f, 0f), new Vector3(0f, 0.28f, 0f), 0.02f, 0.02f),
            new Entry("RightArm", 1, 128, new Vector3(0.113f, -0.033f, 0f), new Vector3(0f, 0.28f, 0f), 0.02f, 0.02f),

            new Entry("LeftForeArm", 2, 128, new Vector3(0f, 0.055f, 0f), Vector3.zero, 0.04f, 0.02f),
            new Entry("LeftForeArm", 2, 8, Vector3.zero, Vector3.zero, 0.054f, 0.04f),
            new Entry("LeftForeArm", 1, 64, new Vector3(-0.11f, 0.034f, -0.045f), new Vector3(0f, 0.3f, 0f), 0.05f, 0.05f),
            new Entry("RightForeArm", 2, 128, new Vector3(0f, 0.055f, 0f), Vector3.zero, 0.04f, 0.02f),
            new Entry("RightForeArm", 2, 8, Vector3.zero, Vector3.zero, 0.054f, 0.04f),
            new Entry("RightForeArm", 1, 320, new Vector3(0.11f, -0.042f, 0.032f), new Vector3(0f, 0.3f, 0f), 0.05f, 0.05f),

            new Entry("LeftHand", 1, 64, new Vector3(-0.054f, 0.02f, 0f), new Vector3(0f, 0.133f, 0f), 0.025f, 0.025f),
            new Entry("LeftHand", 2, 136, Vector3.zero, Vector3.zero, 0.03f, 0.025f),
            new Entry("RightHand", 1, 320, new Vector3(0.054f, -0.02f, 0f), new Vector3(0f, 0.133f, 0f), 0.025f, 0.025f),
            new Entry("RightHand", 2, 392, Vector3.zero, Vector3.zero, 0.03f, 0.025f),
        };
    }
}
