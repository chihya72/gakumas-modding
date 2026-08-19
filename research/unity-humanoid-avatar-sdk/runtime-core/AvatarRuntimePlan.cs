namespace Gakumas.AvatarRuntime.Core;

public sealed record AvatarPackageBinding(
    string PackageId,
    string TargetCharacterId,
    string BundlePath,
    string DescriptorPath);

public sealed record AvatarApplyPlan(
    AvatarPackageBinding Package,
    AvatarDescriptor Descriptor,
    IReadOnlyList<string> RendererPaths,
    int ExpressionCount,
    int SpringChainCount);

public static class AvatarRuntimePlan
{
    public static AvatarApplyPlan Create(
        AvatarPackageBinding package,
        AvatarDescriptor descriptor,
        string expectedTargetCharacterId)
    {
        ArgumentNullException.ThrowIfNull(package);
        ArgumentNullException.ThrowIfNull(descriptor);
        if (string.IsNullOrWhiteSpace(expectedTargetCharacterId))
            throw new ArgumentException("Target character id is required.", nameof(expectedTargetCharacterId));
        if (!string.Equals(package.TargetCharacterId, expectedTargetCharacterId, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                $"Package targets '{package.TargetCharacterId}', but the active character is '{expectedTargetCharacterId}'.");

        var errors = AvatarDescriptorValidator.Validate(descriptor);
        if (errors.Count != 0)
            throw new InvalidOperationException("Descriptor is invalid: " + string.Join("; ", errors));

        return new AvatarApplyPlan(
            package,
            descriptor,
            descriptor.Renderers.Select(renderer => renderer.Path).ToArray(),
            descriptor.Expressions.Count,
            descriptor.SpringChains.Count);
    }
}

public static class AvatarDescriptorValidator
{
    public static IReadOnlyList<string> Validate(AvatarDescriptor descriptor)
    {
        ArgumentNullException.ThrowIfNull(descriptor);
        var errors = new List<string>();
        if (descriptor.Protocol != 1)
            errors.Add("protocol must be integer 1");
        Required(descriptor.SdkVersion, "sdkVersion", errors);
        Required(descriptor.UnityVersion, "unityVersion", errors);
        Required(descriptor.BuildId, "buildId", errors);
        RelativePath(descriptor.AvatarRoot, "avatarRoot", errors);
        RelativePath(descriptor.Animator, "animator", errors);

        var rendererPaths = new HashSet<string>(StringComparer.Ordinal);
        foreach (var renderer in descriptor.Renderers)
        {
            RelativePath(renderer.Path, "renderer.path", errors);
            if (!rendererPaths.Add(renderer.Path))
                errors.Add($"duplicate renderer path: {renderer.Path}");
            if (renderer.Role is not ("body" or "hair" or "face" or "accessory" or "effect" or "ignore"))
                errors.Add($"unsupported renderer role: {renderer.Role}");
        }

        foreach (var expression in descriptor.Expressions)
        {
            Required(expression.Channel, "expression.channel", errors);
            foreach (var output in expression.Outputs)
            {
                RelativePath(output.RendererPath, "expression.rendererPath", errors);
                if (!rendererPaths.Contains(output.RendererPath))
                    errors.Add($"expression target is not a renderer: {output.RendererPath}");
                if (float.IsNaN(output.Scale) || float.IsInfinity(output.Scale))
                    errors.Add("expression scale must be finite");
                if (output.Mode is not ("max" or "addClamp" or "multiply"))
                    errors.Add($"unsupported expression mode: {output.Mode}");
            }
        }

        var springIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var chain in descriptor.SpringChains)
        {
            Required(chain.Id, "springChain.id", errors);
            if (!springIds.Add(chain.Id))
                errors.Add($"duplicate spring chain id: {chain.Id}");
            if (chain.Nodes.Count < 2)
                errors.Add($"spring chain needs at least two nodes: {chain.Id}");
            Finite(chain.Stiffness, "spring stiffness", errors);
            Finite(chain.Damping, "spring damping", errors);
            Finite(chain.Gravity, "spring gravity", errors);
        }

        return errors;
    }

    private static void Required(string value, string field, ICollection<string> errors)
    {
        if (string.IsNullOrWhiteSpace(value))
            errors.Add($"{field} is required");
    }

    private static void RelativePath(string value, string field, ICollection<string> errors)
    {
        Required(value, field, errors);
        if (string.IsNullOrWhiteSpace(value))
            return;
        if (Path.IsPathRooted(value) || value.Contains('\\') || value.Split('/').Any(part => part is "" or ".."))
            errors.Add($"{field} must be a normalized relative Unity path: {value}");
    }

    private static void Finite(float value, string field, ICollection<string> errors)
    {
        if (float.IsNaN(value) || float.IsInfinity(value))
            errors.Add($"{field} must be finite");
    }
}
