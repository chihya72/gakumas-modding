// Pose-driven skirt correction — the thing that actually keeps a hem off a lifted thigh.
//
// This is a different system from the swing simulation, and it is the one that was missing. A spring
// bone reacts to motion; this one *reads the thigh's rotation* and rotates the skirt panel away from
// it, clamped per panel. `Calc(initialReferenceRotation, currentReferenceRotation, …)` in the game's
// own class says it plainly: the driver is a function of the reference bone's rotation, not of time.
//
// Stock evidence: 9 of 12 hmsz costumes carry exactly eight of these, one per skirt anchor
// (`LeftFrontSkirt_A`, `RightBackSideSkirt_A`, …), and every one points `referenceBone` at
// `LeftUpLeg` or `RightUpLeg` — the thigh on its own side.
//
// The source model has the same rig under another name: IDOLY PRIDE calls the anchors
// `LeftFrontSkirt_Repulsion_A`. Same middleware, same `_A` suffix, same job. The bones came across
// with the mesh; the drivers did not, so the panels had spring physics and no active avoidance —
// which is why a thigh capsule at five times its real radius still could not stop the clipping.
//
// One MonoBehaviour per file, or Unity emits m_Script: {fileID: 0}.
using UnityEngine;

namespace ActorAnimation
{
    public class ActorAnimationQuartzDriverSkirtBone : MonoBehaviour
    {
        public ActorAnimationQuartzDriverSkirtSetting setting;
    }
}
