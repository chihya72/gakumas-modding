// Serialized helper types shared by the swing components. These are plain [Serializable] classes,
// not MonoBehaviours, so they may share a file.
//
// Classes rather than structs on purpose: Unity's serializer does not handle a struct that holds a
// List when that struct is itself inside a List. A [Serializable] class is written inline exactly
// like a struct, so the byte layout the game reads is unchanged.
//
// Unity.Mathematics types are deliberate — the game serialises float3 / quaternion / bool3 / int2,
// and Vector3 / Quaternion would not lay out the same way.
using System;
using System.Collections.Generic;
using Unity.Mathematics;
using UnityEngine;

namespace ActorAnimation
{
    [Serializable]
    public class ActorSwingDynamicCollider
    {
        public byte type;
        public int collisionMask;
        public Vector3 vector3_A;
        public Vector3 vector3_B;
        public float float_A;
        public float float_B;
    }

    // ActorSwingStaticCollider derives from the same ActorSwingCollider as the dynamic one and adds a
    // single field; Unity writes base fields first, so the layout is the dynamic collider's plus
    // `seatDynamicCorrectionDisableCollisionMask` at the end.
    [Serializable]
    public class ActorSwingStaticCollider
    {
        public byte type;
        public int collisionMask;
        public Vector3 vector3_A;
        public Vector3 vector3_B;
        public float float_A;
        public float float_B;
        public int seatDynamicCorrectionDisableCollisionMask;
    }

    [Serializable]
    public class LimitInfo
    {
        public int useLimit;
        public int2 axisX;
        public int2 axisY;
        public int2 axisZ;
    }

    [Serializable]
    public class ReferenceLimitInfo
    {
        public ActorSwingDynamicBone bone;
        public bool3 min;
        public bool3 max;
    }

    [Serializable]
    public class InitialTransform
    {
        public float3 localPosition;
        public quaternion localRotation;
        public float3 position;
        public quaternion rotation;
    }

    [Serializable]
    public class ChainLayerInfo
    {
        public bool active;
        public bool around;
        public float radius;
        public float smoothing;
        public List<ActorSwingDynamicBone> bones;
    }

    [Serializable]
    public class ChainInfo
    {
        public List<ChainLayerInfo> layers;
    }
}
