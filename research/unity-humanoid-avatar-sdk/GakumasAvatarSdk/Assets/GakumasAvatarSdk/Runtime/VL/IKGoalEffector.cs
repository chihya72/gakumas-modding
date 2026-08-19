// Full-body IK anchor. The actor build calls CreateFullBodyIK and binds these transforms into the
// animation stream; without them BindStreamTransform throws ArgumentNullException and the actor
// never finishes loading.
//
// `goal` matches UnityEngine.AvatarIKGoal: LeftFoot 0, RightFoot 1, LeftHand 2, RightHand 3.
// Assembly name (vl-unity.Runtime) and namespace are part of the identity the player resolves by.
using UnityEngine;

namespace VL.IK
{
    public class IKGoalEffector : MonoBehaviour
    {
        public int goal;
    }
}
