#if UNITY_EDITOR

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Gakumas.AvatarSdk.Editor
{

public static class GakumasAvatarSdkBuilder
{
    private const string BuildRoot = "Assets/GakumasAvatarSdk/Build";
    private const string SdkVersion = "0.1.0-p1";
    private const string UnityVersion = "6000.0.67f1";

    [MenuItem("Gakumas/Avatar SDK/Build Selected Avatar Bundle")]
    public static void BuildSelectedAvatarBundle()
    {
        var prefab = Selection.activeObject as GameObject;
        if (prefab == null)
            throw new InvalidOperationException("Select a prefab asset with a Humanoid Animator first.");

        var packageId = MakePackageId(prefab.name);
        var output = EditorUtility.SaveFolderPanel("Avatar bundle output", "AvatarSdkBuild/Windows", packageId);
        if (string.IsNullOrWhiteSpace(output))
            return;

        var targetChoice = EditorUtility.DisplayDialogComplex(
            "Target character",
            "Choose the initial runtime target. This controls generated mod.json only.",
            "fktn", "Cancel", "custom");
        if (targetChoice == 1)
            return;
        var targetCharacterId = targetChoice == 0 ? "fktn" : "custom";
        BuildAvatarBundle(prefab, output, targetCharacterId);
    }

    public static void BuildAvatarBundleFromArgs()
    {
        var arguments = Environment.GetCommandLineArgs();
        var prefabPath = Argument(arguments, "-avatarPrefab");
        var output = Argument(arguments, "-avatarOutput");
        var target = Argument(arguments, "-avatarTarget");
        if (string.IsNullOrWhiteSpace(prefabPath) || string.IsNullOrWhiteSpace(output))
            throw new ArgumentException("Expected -avatarPrefab <Assets/...prefab> -avatarOutput <directory> [-avatarTarget <characterId>]");
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
        if (prefab == null)
            throw new FileNotFoundException("Avatar prefab not found", prefabPath);
        BuildAvatarBundle(prefab, output, string.IsNullOrWhiteSpace(target) ? "fktn" : target);
    }

    private static void BuildAvatarBundle(GameObject prefab, string output, string targetCharacterId)
    {
        var packageId = MakePackageId(prefab.name);
        var result = BuildDescriptor(prefab, packageId);
        if (result.Errors.Count != 0)
        {
            var text = string.Join("\n", result.Errors);
            EditorUtility.DisplayDialog("Avatar SDK validation failed", text, "OK");
            throw new InvalidOperationException(text);
        }

        var buildDirectory = BuildRoot + "/" + packageId;
        EnsureFolder(BuildRoot);
        EnsureFolder(buildDirectory);
        var prefabPath = AssetDatabase.GetAssetPath(prefab);
        var descriptorPath = buildDirectory + "/" + packageId + ".avatar.json";
        var manifestPath = buildDirectory + "/mod.json";
        var bundleName = packageId + ".bundle";
        File.WriteAllText(ToProjectFilePath(descriptorPath), JsonUtility.ToJson(result.Descriptor, true));
        File.WriteAllText(ToProjectFilePath(manifestPath), JsonUtility.ToJson(CreateManifest(packageId, prefabPath, descriptorPath, bundleName, targetCharacterId), true));
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        AssignBundle(prefabPath, bundleName);
        AssignBundle(descriptorPath, bundleName);
        AssignBundle(manifestPath, bundleName);
        AssetDatabase.SaveAssets();

        Directory.CreateDirectory(output);
        var manifest = BuildPipeline.BuildAssetBundles(
            output,
            BuildAssetBundleOptions.ChunkBasedCompression,
            BuildTarget.StandaloneWindows64);
        if (manifest == null)
            throw new InvalidOperationException("Unity AssetBundle build returned no manifest.");

        var report = new BuildReport
        {
            packageId = packageId,
            bundle = bundleName,
            descriptor = descriptorPath,
            manifest = manifestPath,
            rendererCount = result.Descriptor.renderers.Length,
            expressionCount = result.Descriptor.expressions.Length,
            springChainCount = result.Descriptor.springChains.Length,
            outputDirectory = output,
        };
        File.WriteAllText(Path.Combine(output, packageId + ".build-report.json"), JsonUtility.ToJson(report, true));
        EditorUtility.RevealInFinder(output);
        Debug.Log("Avatar SDK bundle built: " + output + "/" + bundleName);
    }

    private static string Argument(string[] arguments, string name)
    {
        for (var index = 0; index + 1 < arguments.Length; index++)
        {
            if (string.Equals(arguments[index], name, StringComparison.OrdinalIgnoreCase))
                return arguments[index + 1];
        }
        return string.Empty;
    }

    private static BuildResult BuildDescriptor(GameObject prefab, string packageId)
    {
        var instance = PrefabUtility.InstantiatePrefab(prefab) as GameObject
                      ?? throw new InvalidOperationException("Could not instantiate selected prefab.");
        try
        {
            var errors = new List<string>();
            var animator = instance.GetComponentInChildren<Animator>(true);
            if (animator == null)
            {
                errors.Add("No Animator found under prefab.");
                return new BuildResult(new Descriptor(), errors);
            }
            if (animator.avatar == null || !animator.avatar.isValid || !animator.avatar.isHuman)
                errors.Add("Animator must reference a valid Humanoid Avatar.");

            var requiredBones = new[]
            {
                HumanBodyBones.Hips, HumanBodyBones.Spine, HumanBodyBones.Head,
                HumanBodyBones.LeftUpperArm, HumanBodyBones.RightUpperArm,
                HumanBodyBones.LeftUpperLeg, HumanBodyBones.RightUpperLeg,
            };
            foreach (var bone in requiredBones)
            {
                if (animator.GetBoneTransform(bone) == null)
                    errors.Add("Required Humanoid bone is missing: " + bone);
            }

            var renderers = instance.GetComponentsInChildren<Renderer>(true)
                .Where(renderer => renderer is SkinnedMeshRenderer || renderer is MeshRenderer)
                .Select(renderer => CreateRendererSpec(instance.transform, renderer, errors))
                .ToArray();
            var paths = new HashSet<string>(StringComparer.Ordinal);
            foreach (var renderer in renderers)
            {
                if (!paths.Add(renderer.path))
                    errors.Add("Duplicate renderer path: " + renderer.path);
            }

            var descriptor = new Descriptor
            {
                protocol = 1,
                sdkVersion = SdkVersion,
                unityVersion = UnityVersion,
                buildId = packageId + "-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss"),
                avatarRoot = "Root",
                animator = RelativePath(instance.transform, animator.transform),
                renderers = renderers,
                expressions = BuildExpressions(instance, renderers, errors),
                springChains = BuildSpringChains(instance.transform, instance, errors),
                colliders = BuildColliders(instance.transform, instance, errors),
                rootMotion = new RootMotion(),
                materials = new Materials(),
            };
            return new BuildResult(descriptor, errors);
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(instance);
        }
    }

    private static RendererSpec CreateRendererSpec(Transform root, Renderer renderer, List<string> errors)
    {
        var path = RelativePath(root, renderer.transform);
        var authoring = renderer.GetComponent<Gakumas.AvatarSdk.AvatarRendererAuthoring>();
        var role = authoring == null || authoring.role == Gakumas.AvatarSdk.AvatarRendererRole.Auto
            ? InferRole(renderer.name)
            : ToRole(authoring.role);
        var blendShapes = renderer is SkinnedMeshRenderer skinned && skinned.sharedMesh != null
            ? Enumerable.Range(0, skinned.sharedMesh.blendShapeCount)
                .Select(index => skinned.sharedMesh.GetBlendShapeName(index)).ToArray()
            : Array.Empty<string>();
        if (renderer is SkinnedMeshRenderer skinnedRenderer && skinnedRenderer.sharedMesh == null)
            errors.Add("SkinnedMeshRenderer has no mesh: " + path);
        if (renderer is SkinnedMeshRenderer withBones && withBones.bones.Length == 0)
            errors.Add("SkinnedMeshRenderer has no bones: " + path);
        return new RendererSpec
        {
            path = path,
            role = role,
            rendererType = renderer is SkinnedMeshRenderer ? "SkinnedMeshRenderer" : "MeshRenderer",
            blendShapes = blendShapes,
        };
    }

    private static Expression[] BuildExpressions(GameObject root, RendererSpec[] renderers, List<string> errors)
    {
        var explicitAuthoring = root.GetComponentsInChildren<Gakumas.AvatarSdk.AvatarExpressionAuthoring>(true)
            .SelectMany(component => component.entries ?? Array.Empty<Gakumas.AvatarSdk.AvatarExpressionEntry>())
            .ToArray();
        if (explicitAuthoring.Length != 0)
        {
            var explicitExpressions = new List<Expression>();
            foreach (var entry in explicitAuthoring)
            {
                if (entry == null || string.IsNullOrWhiteSpace(entry.channel))
                {
                    errors.Add("Expression mapping has an empty channel.");
                    continue;
                }
                if (entry.renderer == null || entry.renderer.sharedMesh == null)
                {
                    errors.Add("Expression mapping has no renderer or mesh: " + entry.channel);
                    continue;
                }
                var rendererPath = RelativePath(root.transform, entry.renderer.transform);
                var rendererSpec = renderers.FirstOrDefault(item => item.path == rendererPath);
                if (rendererSpec == null)
                {
                    errors.Add("Expression mapping renderer is not exported: " + rendererPath);
                    continue;
                }
                if (string.IsNullOrWhiteSpace(entry.blendShape) ||
                    !rendererSpec.blendShapes.Contains(entry.blendShape, StringComparer.Ordinal))
                {
                    errors.Add("Expression blendshape is missing: " + rendererPath + "/" + entry.blendShape);
                    continue;
                }
                var expression = explicitExpressions.FirstOrDefault(item => item.channel == entry.channel);
                if (expression == null)
                {
                    expression = new Expression { channel = entry.channel, outputs = Array.Empty<ExpressionOutput>() };
                    explicitExpressions.Add(expression);
                }
                var outputs = expression.outputs.ToList();
                outputs.Add(new ExpressionOutput
                {
                    rendererPath = rendererPath,
                    blendShape = entry.blendShape,
                    scale = entry.scale,
                    mode = ToExpressionMode(entry.mode),
                });
                expression.outputs = outputs.ToArray();
            }
            return explicitExpressions.ToArray();
        }

        var face = renderers.FirstOrDefault(renderer => renderer.role == "face");
        if (face == null)
            return Array.Empty<Expression>();
        var aliases = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
        {
            ["smile"] = new[] { "Smile", "笑顔", "mouth_a" },
            ["blink"] = new[] { "Blink", "まばたき", "blink" },
            ["aa"] = new[] { "あ", "A", "vrc.v_aa" },
            ["ih"] = new[] { "い", "I", "vrc.v_ih" },
            ["ou"] = new[] { "う", "U", "vrc.v_ou" },
            ["ee"] = new[] { "え", "E", "vrc.v_ee" },
            ["oh"] = new[] { "お", "O", "vrc.v_oh" },
        };
        var expressions = new List<Expression>();
        foreach (var alias in aliases)
        {
            var shape = alias.Value.FirstOrDefault(candidate =>
                face.blendShapes.Contains(candidate, StringComparer.OrdinalIgnoreCase));
            if (shape == null)
                continue;
            expressions.Add(new Expression
            {
                channel = alias.Key,
                outputs = new[]
                {
                    new ExpressionOutput
                    {
                        rendererPath = face.path,
                        blendShape = shape,
                        scale = 1f,
                        mode = "max",
                    },
                },
            });
        }
        return expressions.ToArray();
    }

    private static SpringChain[] BuildSpringChains(Transform root, GameObject instance, List<string> errors)
    {
        var components = instance.GetComponentsInChildren<Gakumas.AvatarSdk.AvatarSpringAuthoring>(true);
        var chains = new List<SpringChain>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var component in components)
        {
            foreach (var entry in component.chains ?? Array.Empty<Gakumas.AvatarSdk.AvatarSpringChainEntry>())
            {
                if (entry == null || string.IsNullOrWhiteSpace(entry.id))
                {
                    errors.Add("Spring chain has an empty id.");
                    continue;
                }
                if (!ids.Add(entry.id))
                {
                    errors.Add("Duplicate spring chain id: " + entry.id);
                    continue;
                }
                if (entry.nodes == null || entry.nodes.Length < 2 || entry.nodes.Any(node => node == null))
                {
                    errors.Add("Spring chain needs at least two nodes: " + entry.id);
                    continue;
                }
                chains.Add(new SpringChain
                {
                    id = entry.id,
                    nodes = entry.nodes.Select(node => RelativePath(root, node)).ToArray(),
                    stiffness = entry.stiffness,
                    damping = entry.damping,
                    gravity = entry.gravity,
                });
            }
        }
        return chains.ToArray();
    }

    private static ColliderSpec[] BuildColliders(Transform root, GameObject instance, List<string> errors)
    {
        var components = instance.GetComponentsInChildren<Gakumas.AvatarSdk.AvatarColliderAuthoring>(true);
        var colliders = new List<ColliderSpec>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var component in components)
        {
            foreach (var entry in component.colliders ?? Array.Empty<Gakumas.AvatarSdk.AvatarColliderEntry>())
            {
                if (entry == null || string.IsNullOrWhiteSpace(entry.id))
                {
                    errors.Add("Collider has an empty id.");
                    continue;
                }
                if (!ids.Add(entry.id))
                {
                    errors.Add("Duplicate collider id: " + entry.id);
                    continue;
                }
                if (entry.target == null)
                {
                    errors.Add("Collider has no target: " + entry.id);
                    continue;
                }
                if (entry.radius <= 0f || entry.height <= 0f)
                {
                    errors.Add("Collider dimensions must be positive: " + entry.id);
                    continue;
                }
                colliders.Add(new ColliderSpec
                {
                    path = RelativePath(root, entry.target),
                    shape = entry.shape == Gakumas.AvatarSdk.AvatarColliderShape.Capsule ? "capsule" : "sphere",
                    radius = entry.radius,
                    height = entry.height,
                });
            }
        }
        return colliders.ToArray();
    }

    private static string InferRole(string rendererName)
    {
        var name = rendererName.ToLowerInvariant();
        if (name.Contains("face") || name.Contains("head") || name.Contains("eye") || name.Contains("mouth")) return "face";
        if (name.Contains("hair") || name.Contains("髪")) return "hair";
        if (name.Contains("body") || name.Contains("skin")) return "body";
        return "accessory";
    }

    private static string ToRole(Gakumas.AvatarSdk.AvatarRendererRole role)
    {
        return role switch
        {
            Gakumas.AvatarSdk.AvatarRendererRole.Body => "body",
            Gakumas.AvatarSdk.AvatarRendererRole.Face => "face",
            Gakumas.AvatarSdk.AvatarRendererRole.Hair => "hair",
            Gakumas.AvatarSdk.AvatarRendererRole.Accessory => "accessory",
            Gakumas.AvatarSdk.AvatarRendererRole.Effect => "effect",
            Gakumas.AvatarSdk.AvatarRendererRole.Ignore => "ignore",
            _ => "accessory",
        };
    }

    private static string ToExpressionMode(Gakumas.AvatarSdk.AvatarExpressionMode mode)
    {
        return mode switch
        {
            Gakumas.AvatarSdk.AvatarExpressionMode.AddClamp => "addClamp",
            Gakumas.AvatarSdk.AvatarExpressionMode.Multiply => "multiply",
            _ => "max",
        };
    }

    private static string RelativePath(Transform root, Transform child)
    {
        if (root == child) return "Root";
        var parts = new List<string>();
        for (var current = child; current != null && current != root; current = current.parent)
            parts.Add(current.name);
        parts.Reverse();
        return string.Join("/", parts);
    }

    private static string MakePackageId(string name)
    {
        var chars = name.ToLowerInvariant()
            .Select(character => char.IsLetterOrDigit(character) ? character : '-').ToArray();
        var id = new string(chars).Trim('-');
        return string.IsNullOrWhiteSpace(id) ? "avatar-package" : id;
    }

    private static void EnsureFolder(string path)
    {
        var parts = path.Split('/');
        var current = parts[0];
        for (var index = 1; index < parts.Length; index++)
        {
            var next = current + "/" + parts[index];
            if (!AssetDatabase.IsValidFolder(next))
                AssetDatabase.CreateFolder(current, parts[index]);
            current = next;
        }
    }

    private static void AssignBundle(string assetPath, string bundleName)
    {
        var importer = AssetImporter.GetAtPath(assetPath);
        if (importer == null)
            throw new InvalidOperationException("Asset is not importable: " + assetPath);
        importer.assetBundleName = bundleName;
    }

    private static string ToProjectFilePath(string assetPath)
    {
        return Path.GetFullPath(Path.Combine(Application.dataPath, "..", assetPath));
    }

    private static Manifest CreateManifest(string packageId, string asset, string descriptor, string bundle, string targetCharacterId)
    {
        return new Manifest
        {
            schemaVersion = 1,
            id = packageId,
            name = packageId,
            version = "0.1.0",
            author = Environment.UserName,
            enabled = true,
            bundle = bundle,
            asset = asset,
            descriptor = descriptor,
            targets = new[] { new Target { characterId = targetCharacterId } },
        };
    }

    [Serializable] private sealed class BuildResult
    {
        public Descriptor Descriptor;
        public List<string> Errors;
        public BuildResult(Descriptor descriptor, List<string> errors) { Descriptor = descriptor; Errors = errors; }
    }
    [Serializable] private sealed class Descriptor
    {
        public int protocol;
        public string sdkVersion = string.Empty;
        public string unityVersion = string.Empty;
        public string buildId = string.Empty;
        public string avatarRoot = string.Empty;
        public string animator = string.Empty;
        public RendererSpec[] renderers = Array.Empty<RendererSpec>();
        public Expression[] expressions = Array.Empty<Expression>();
        public SpringChain[] springChains = Array.Empty<SpringChain>();
        public ColliderSpec[] colliders = Array.Empty<ColliderSpec>();
        public RootMotion rootMotion = new();
        public Materials materials = new();
    }
    [Serializable] private sealed class RendererSpec
    {
        public string path = string.Empty;
        public string role = string.Empty;
        public string rendererType = string.Empty;
        public string[] blendShapes = Array.Empty<string>();
    }
    [Serializable] private sealed class Expression { public string channel = string.Empty; public ExpressionOutput[] outputs = Array.Empty<ExpressionOutput>(); }
    [Serializable] private sealed class ExpressionOutput { public string rendererPath = string.Empty; public string blendShape = string.Empty; public float scale; public string mode = "max"; }
    [Serializable] private sealed class SpringChain { public string id = string.Empty; public string[] nodes = Array.Empty<string>(); public float stiffness; public float damping; public float gravity; }
    [Serializable] private sealed class ColliderSpec { public string path = string.Empty; public string shape = "sphere"; public float radius = 0.05f; public float height; }
    [Serializable] private sealed class RootMotion { public string mode = "actorAnchored"; public float groundOffset; public string scaleMode = "author"; }
    [Serializable] private sealed class Materials { public string mode = "standard"; }
    [Serializable] private sealed class Manifest
    {
        public int schemaVersion;
        public string id = string.Empty;
        public string name = string.Empty;
        public string version = string.Empty;
        public string author = string.Empty;
        public bool enabled;
        public string bundle = string.Empty;
        public string asset = string.Empty;
        public string descriptor = string.Empty;
        public Target[] targets = Array.Empty<Target>();
    }
    [Serializable] private sealed class Target { public string characterId = string.Empty; }
    [Serializable] private sealed class BuildReport
    {
        public string packageId = string.Empty;
        public string bundle = string.Empty;
        public string descriptor = string.Empty;
        public string manifest = string.Empty;
        public int rendererCount;
        public int expressionCount;
        public int springChainCount;
        public string outputDirectory = string.Empty;
    }
}

}

#endif
