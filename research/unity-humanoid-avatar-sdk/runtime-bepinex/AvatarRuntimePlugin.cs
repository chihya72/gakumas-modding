// P1 scaffold: compile this file against the local BepInEx/Unity game assemblies
// after the P0 live probe has produced stable actor and renderer references.
#nullable enable

using System.Text.Json;
using System.Text.Json.Serialization;
using BepInEx;
using BepInEx.Logging;
using Gakumas.AvatarRuntime.Core;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Gakumas.AvatarRuntime.BepInEx;

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
public sealed class AvatarRuntimePlugin : BaseUnityPlugin
{
    public const string PluginGuid = "gakumas.avatar.runtime";
    public const string PluginName = "Gakumas Avatar Runtime";
    public const string PluginVersion = "0.1.0-p0";

    private ManualLogSource _log = null!;
    private bool _sceneHooksInstalled;

    private void Awake()
    {
        _log = Logger;
        _log.LogInfo($"{PluginName} {PluginVersion} loaded; live AvatarHost binding is pending P0 probe.");
        InstallSceneHooks();
    }

    private void OnDestroy()
    {
        if (_sceneHooksInstalled)
            SceneManager.sceneLoaded -= OnSceneLoaded;
    }

    private void InstallSceneHooks()
    {
        if (_sceneHooksInstalled)
            return;
        SceneManager.sceneLoaded += OnSceneLoaded;
        _sceneHooksInstalled = true;
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        _log.LogDebug($"Scene loaded: {scene.name} ({mode}); package scan is intentionally deferred until live references are known.");
    }

    /// <summary>
    /// Validates a descriptor and builds the engine-independent apply plan.
    /// The actual GameObject/SkinnedMeshRenderer mutation belongs in the next
    /// adapter step and must be guarded by the P0 probe results.
    /// </summary>
    public AvatarApplyPlan LoadPlan(
        string manifestJson,
        string descriptorJson,
        string expectedTargetCharacterId)
    {
        var manifest = JsonSerializer.Deserialize<ManifestDocument>(manifestJson, JsonOptions)
                       ?? throw new InvalidOperationException("Manifest JSON is empty.");
        var target = manifest.Targets.FirstOrDefault(item =>
            string.Equals(item.CharacterId, expectedTargetCharacterId, StringComparison.OrdinalIgnoreCase));
        if (target is null)
            throw new InvalidOperationException($"Manifest has no target for '{expectedTargetCharacterId}'.");

        var package = new AvatarPackageBinding(manifest.Id, target.CharacterId, manifest.Bundle, manifest.Descriptor);
        var descriptor = JsonSerializer.Deserialize<AvatarDescriptor>(descriptorJson, JsonOptions)
                         ?? throw new InvalidOperationException("Descriptor JSON is empty.");
        return AvatarRuntimePlan.Create(package, descriptor, expectedTargetCharacterId);
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    private sealed record ManifestDocument
    {
        [JsonPropertyName("id")]
        public string Id { get; init; } = string.Empty;

        [JsonPropertyName("bundle")]
        public string Bundle { get; init; } = string.Empty;

        [JsonPropertyName("descriptor")]
        public string Descriptor { get; init; } = string.Empty;

        [JsonPropertyName("targets")]
        public IReadOnlyList<ManifestTarget> Targets { get; init; } = Array.Empty<ManifestTarget>();
    }

    private sealed record ManifestTarget
    {
        [JsonPropertyName("characterId")]
        public string CharacterId { get; init; } = string.Empty;
    }
}
