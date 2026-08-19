// Hand IK correction anchor. One per hand, on the LeftHand / RightHand bones.
//
// CampusActorAnimationInitializeData keeps these two as single non-list fields
// (correctionRightHandGoal / correctionLeftHandGoal). When they are null the rig still builds
// ActorAnimationIKCorrectionJobGoal, whose five PropertySceneHandles stay default — and the Burst
// job reads them unconditionally, which aborts the process with
// "InvalidOperationException: The PropertySceneHandle is invalid" and no managed stack.
// Every stock body carries both; a body without them cannot finish BuildAvatar.
//
// Field names / types / order come from the game's compiled class (il2cpp dump 3.2.3). One
// MonoBehaviour per file, or Unity emits m_Script: {fileID: 0}.
using UnityEngine;

namespace ActorAnimation
{
    public class ActorAnimationIKCorrectionGoal : MonoBehaviour
    {
        // UnityEngine.AvatarIKGoal: LeftFoot 0, RightFoot 1, LeftHand 2, RightHand 3.
        public int goal;
        public bool enable;
        public float radius;
        public Vector3 offset;
    }
}
