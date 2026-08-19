// The swing driver. Without one of these the per-bone components are never scheduled — measured
// in game, bones carrying only an ActorSwingDynamicBone stay rigid.
//
// It sits on an anchor bone (Pelvis / Spine / Head_Hair on stock costumes), lists each strand's
// first segment in rootBones, and carries one layer per segment depth, so every strand in a chain
// must be the same length.
//
// Its own file for the same reason as ActorSwingDynamicBone: Unity only creates a MonoScript for
// a MonoBehaviour whose class name matches the file name.
using System.Collections.Generic;
using UnityEngine;

namespace ActorAnimation
{
    public class ActorSwingChain : MonoBehaviour
    {
        public List<ActorSwingDynamicBone> rootBones;
        public ChainInfo chains;
    }
}
