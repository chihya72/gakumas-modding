// Per-bone swing state.
//
// A MonoBehaviour must live in a file named after the class, or Unity never creates a MonoScript
// for it and every AddComponent writes `m_Script: {fileID: 0}` — which shows up later as
// "script is missing" on every bone. That is why this class has a file to itself.
//
// Field names, types and order come from a stock costume's type tree
// (mdl_chr_atbm-trng-0000_body). Do not reorder or rename: the layout is the contract with the
// game's own compiled class, which the player resolves by class + namespace + assembly name.
using UnityEngine;

namespace ActorAnimation
{
    public class ActorSwingDynamicBone : MonoBehaviour
    {
        public ActorSwingDynamicCollider dynamicCollider;
        public int resetType;
        public int dynamicType;
        public float damping;
        public float stiffness;
        public float spring;
        public float pendulum;
        public float pendulumRange;
        public float mass;
        public float axisAddXToY;
        public float axisAddXToZ;
        public float wind;
        public bool useWindGlobalForce;
        public LimitInfo limitInfo;
        public float rootWeight;
        public float seatDynamicCorrection;
        public ReferenceLimitInfo referenceLimitInfo;
        public InitialTransform modelingTransform;
    }
}
