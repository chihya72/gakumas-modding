using System.Text.Json.Serialization;

namespace Gakumas.AvatarRuntime.Core;

/// <summary>
/// Unity SDK output contract. The Unity adapter can deserialize this same shape
/// and resolve the relative paths against the loaded AssetBundle.
/// </summary>
public sealed record AvatarDescriptor
{
    [JsonPropertyName("protocol")]
    public int Protocol { get; init; } = 1;

    [JsonPropertyName("sdkVersion")]
    public string SdkVersion { get; init; } = string.Empty;

    [JsonPropertyName("unityVersion")]
    public string UnityVersion { get; init; } = string.Empty;

    [JsonPropertyName("buildId")]
    public string BuildId { get; init; } = string.Empty;

    [JsonPropertyName("avatarRoot")]
    public string AvatarRoot { get; init; } = string.Empty;

    [JsonPropertyName("animator")]
    public string Animator { get; init; } = string.Empty;

    [JsonPropertyName("renderers")]
    public IReadOnlyList<AvatarRenderer> Renderers { get; init; } = Array.Empty<AvatarRenderer>();

    [JsonPropertyName("expressions")]
    public IReadOnlyList<AvatarExpression> Expressions { get; init; } = Array.Empty<AvatarExpression>();

    [JsonPropertyName("springChains")]
    public IReadOnlyList<AvatarSpringChain> SpringChains { get; init; } = Array.Empty<AvatarSpringChain>();

    [JsonPropertyName("colliders")]
    public IReadOnlyList<AvatarCollider> Colliders { get; init; } = Array.Empty<AvatarCollider>();

    [JsonPropertyName("rootMotion")]
    public AvatarRootMotion RootMotion { get; init; } = new();

    [JsonPropertyName("materials")]
    public AvatarMaterials Materials { get; init; } = new();
}

public sealed record AvatarRenderer
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; init; } = string.Empty;

    [JsonPropertyName("rendererType")]
    public string RendererType { get; init; } = "SkinnedMeshRenderer";

    [JsonPropertyName("blendShapes")]
    public IReadOnlyList<string> BlendShapes { get; init; } = Array.Empty<string>();
}

public sealed record AvatarExpression
{
    [JsonPropertyName("channel")]
    public string Channel { get; init; } = string.Empty;

    [JsonPropertyName("outputs")]
    public IReadOnlyList<AvatarExpressionOutput> Outputs { get; init; } = Array.Empty<AvatarExpressionOutput>();
}

public sealed record AvatarExpressionOutput
{
    [JsonPropertyName("rendererPath")]
    public string RendererPath { get; init; } = string.Empty;

    [JsonPropertyName("blendShape")]
    public string BlendShape { get; init; } = string.Empty;

    [JsonPropertyName("scale")]
    public float Scale { get; init; } = 1f;

    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "max";
}

public sealed record AvatarSpringChain
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;

    [JsonPropertyName("nodes")]
    public IReadOnlyList<string> Nodes { get; init; } = Array.Empty<string>();

    [JsonPropertyName("stiffness")]
    public float Stiffness { get; init; } = 0.5f;

    [JsonPropertyName("damping")]
    public float Damping { get; init; } = 0.5f;

    [JsonPropertyName("gravity")]
    public float Gravity { get; init; } = 0f;
}

public sealed record AvatarCollider
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("radius")]
    public float Radius { get; init; } = 0.05f;

    [JsonPropertyName("shape")]
    public string Shape { get; init; } = "sphere";

    [JsonPropertyName("height")]
    public float Height { get; init; } = 0.1f;
}

public sealed record AvatarRootMotion
{
    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "actorAnchored";

    [JsonPropertyName("groundOffset")]
    public float GroundOffset { get; init; }

    [JsonPropertyName("scaleMode")]
    public string ScaleMode { get; init; } = "author";
}

public sealed record AvatarMaterials
{
    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "standard";
}
