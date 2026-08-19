// Body volume the hand IK correction pushes the hands out of. Stock bodies carry exactly one, on
// Hips. Unlike the goals this is a list on the rig, so an empty list is legal — it is included
// because without it the hands sink into the hips on every stock animation.
//
// Field names / types / order come from the game's compiled class (il2cpp dump 3.2.3).
using UnityEngine;

namespace ActorAnimation
{
    public class ActorAnimationIKCorrectionCollider : MonoBehaviour
    {
        // ActorAnimationIKCorrectionColliderType is byte-backed: Sphere 0, Capsule 1.
        public byte type;
        public float weight;
        public float radius;
        public float radiusSub;
        public float dampArea;
        public float length;
        public Vector3 offset;
        public Vector3 rotation;
    }
}
