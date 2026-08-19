using System;
using UnityEngine;

namespace Gakumas.AvatarSdk
{

public enum AvatarRendererRole
{
    Auto,
    Body,
    Face,
    Hair,
    Accessory,
    Effect,
    Ignore,
}

public enum AvatarExpressionMode
{
    Max,
    AddClamp,
    Multiply,
}

[DisallowMultipleComponent]
public sealed class AvatarRendererAuthoring : MonoBehaviour
{
    public AvatarRendererRole role = AvatarRendererRole.Auto;
}

[Serializable]
public sealed class AvatarExpressionEntry
{
    public string channel = string.Empty;
    public SkinnedMeshRenderer renderer = null!;
    public string blendShape = string.Empty;
    [Range(-4f, 4f)] public float scale = 1f;
    public AvatarExpressionMode mode = AvatarExpressionMode.Max;
}

public sealed class AvatarExpressionAuthoring : MonoBehaviour
{
    public AvatarExpressionEntry[] entries = Array.Empty<AvatarExpressionEntry>();
}

[Serializable]
public sealed class AvatarSpringChainEntry
{
    public string id = string.Empty;
    public Transform[] nodes = Array.Empty<Transform>();
    [Min(0f)] public float stiffness = 0.5f;
    [Min(0f)] public float damping = 0.5f;
    public float gravity;
}

public sealed class AvatarSpringAuthoring : MonoBehaviour
{
    public AvatarSpringChainEntry[] chains = Array.Empty<AvatarSpringChainEntry>();
}

public enum AvatarColliderShape
{
    Sphere,
    Capsule,
}

[Serializable]
public sealed class AvatarColliderEntry
{
    public string id = string.Empty;
    public Transform target = null!;
    public AvatarColliderShape shape = AvatarColliderShape.Sphere;
    [Min(0.001f)] public float radius = 0.05f;
    [Min(0.001f)] public float height = 0.1f;
}

public sealed class AvatarColliderAuthoring : MonoBehaviour
{
    public AvatarColliderEntry[] colliders = Array.Empty<AvatarColliderEntry>();
}

}
