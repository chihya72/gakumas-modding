// Chest simulation. One per body, on Spine2 — 527 of 530 stock bodies carry exactly one.
//
// Unlike the per-bone swing components this is a single driver that owns both sides: it takes the two
// chest bones and their tips, plus both forearms (`useArmCorrection` is true in all 79 costumes
// measured — an arm crossing the chest pushes it), and drives them from two response curves.
//
// The wiring is identical in every costume measured, so it is not a per-costume choice:
//
//   leftBreast  LeftBust1_S      leftBreastEnd  LeftBust2_S_End      leftLowerArm  LeftForeArm
//   rightBreast RightBust1_S     rightBreastEnd RightBust2_S_End     rightLowerArm RightForeArm
//
// Important: the referenced chest bones carry **no** ActorSwingDynamicBone in stock data (0 of 79) —
// this component drives them instead. Attaching both would simulate the same bone twice, so the swing
// rig skips them.
//
// Field names, types and order from the game's own compiled class (il2cpp 3.2.3); the four
// `initial*Transform` backing fields are compiler-generated and not serialized, unlike the four
// `modeling*Transform` ones which are.
using UnityEngine;

namespace ActorAnimation
{
    public class ActorSwingBreastBone : MonoBehaviour
    {
        public ActorSwingStaticCollider breastCollider;
        public float damping;
        public float stiffness;
        public float spring;
        public float pendulum;
        public float pendulumRange;
        public float average;
        public LimitInfo limitInfo;
        public float rootWeight;
        public bool useArmCorrection;
        public Transform leftLowerArm;
        public Transform rightLowerArm;
        public Transform leftBreast;
        public Transform rightBreast;
        public Transform leftBreastEnd;
        public Transform rightBreastEnd;
        public AnimationCurve upCurve;
        public AnimationCurve sideCurve;
        public InitialTransform modelingLeftTransform;
        public InitialTransform modelingRightTransform;
        public InitialTransform modelingLeftEndTransform;
        public InitialTransform modelingRightEndTransform;
    }
}
