// Pose-driven correction on a helper bone. See QuartzDriverTypes for the setting layout and
// Editor/QuartzDriverRigger for which bone gets which values.
//
// Present on 528 of the 530 stock bodies scanned — not costume-specific like the skirt driver, but
// part of every body: the twist distribution that keeps an arm or thigh from shearing when it rolls.
//
// One MonoBehaviour per file, or Unity emits m_Script: {fileID: 0}.
using UnityEngine;

namespace ActorAnimation
{
    public class ActorAnimationQuartzDriverRotationBone : MonoBehaviour
    {
        public ActorAnimationQuartzDriverRotationSetting setting;
    }
}
