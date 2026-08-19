// The static side of swing collision: the capsules and lines a skirt is pushed out of.
//
// Without these a chain has nothing to collide against and cloth passes straight through the legs.
// Every stock costume ships a cage of them on body bones — 12 to 39 of them, 17 being typical over
// the 60 costumes scanned; arms, forearms, hands and neck appear in all of them.
//
// One MonoBehaviour per file, or Unity emits m_Script: {fileID: 0}.
using UnityEngine;

namespace ActorAnimation
{
    public class ActorSwingStaticBone : MonoBehaviour
    {
        public ActorSwingStaticCollider staticCollider;
    }
}
