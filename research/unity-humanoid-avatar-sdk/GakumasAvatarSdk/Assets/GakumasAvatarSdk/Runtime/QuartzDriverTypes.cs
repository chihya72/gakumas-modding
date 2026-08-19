// Settings for the QuartzDriver family — the pose-driven correction system, separate from swing.
//
// Field names, types and order from the game's own compiled classes (il2cpp 3.2.3). `static readonly`
// members of those classes are not serialized and are omitted here. `math.RotationOrder`,
// `HumanPartDof` and the decompose/compose enums are int-backed, so they are plain ints. Note
// `referenceBone` is a **GameObject**, not a Transform.
//
// These are [Serializable] helpers, not MonoBehaviours, so they may share one file.
using System;
using Unity.Mathematics;
using UnityEngine;

namespace ActorAnimation
{
    /// <summary>Twist distribution for arm / thigh helper bones. Every stock body has 12 of these.</summary>
    [Serializable]
    public class ActorAnimationQuartzDriverHumanoidArmSetting
    {
        // UnityEngine.HumanPartDof: LeftLeg 2, RightLeg 3, LeftArm 4, RightArm 5.
        public int humanPartDof;
        public float coefficient;
    }

    [Serializable]
    public class ActorAnimationQuartzDriverHumanoidUpLegSetting
    {
        public int humanPartDof;
        public float coefficient;
    }

    [Serializable]
    public class ActorAnimationQuartzDriverHumanoidHandSetting
    {
        public int humanPartDof;
        public float coefficient;
    }

    /// <summary>Generic "follow another bone's rotation, scaled and clamped" driver.</summary>
    [Serializable]
    public class ActorAnimationQuartzDriverRotationSetting
    {
        public int rotationOrder;
        public float3 limitMin;
        public float3 limitMax;
        public float3 coefficient;
        public int connectionAxis;
        public int decomposeType;
        public int composeType;
        public GameObject referenceBone;
    }

    /// <summary>
    /// The skirt "repulsion" driver: rotates a hem panel out of its own side's thigh. See
    /// ActorAnimationQuartzDriverSkirtBone.
    /// </summary>
    [Serializable]
    public class ActorAnimationQuartzDriverSkirtSetting
    {
        public int rotationOrder;
        public float3 innerCoefficient;
        public float3 outerCoefficient;
        public float3 limitMin;
        public float3 limitMax;
        public int connectionAxis;
        public GameObject referenceBone;
    }
}
