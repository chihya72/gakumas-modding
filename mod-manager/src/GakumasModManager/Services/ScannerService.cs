using System.IO;
using System.Text.Json;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface IScannerService
{
    ScanResult ScanGameDirectory(string gamePath);
}

public sealed class ScannerService : IScannerService
{
    private const string DisabledPrefix = "DISABLED";

    public ScanResult ScanGameDirectory(string gamePath)
    {
        var issues = new List<ValidationIssue>();
        var normalizedGamePath = string.IsNullOrWhiteSpace(gamePath)
            ? Directory.GetCurrentDirectory()
            : Environment.ExpandEnvironmentVariables(gamePath.Trim().Trim('"'));

        var modsPath = ResolveModsPath(normalizedGamePath);
        if (modsPath is null)
        {
            return new ScanResult(
                normalizedGamePath,
                "",
                [],
                [new ValidationIssue("未找到 Mods 目录", "Warning")]);
        }

        var packages = new List<ModPackage>();
        foreach (var directory in Directory.EnumerateDirectories(modsPath).OrderBy(Path.GetFileName))
        {
            var package = ScanPackageDirectory(directory);
            if (package is not null)
            {
                packages.Add(package);
            }
        }

        return new ScanResult(normalizedGamePath, modsPath, ApplyGlobalConflicts(packages), issues);
    }

    private static string? ResolveModsPath(string gamePath)
    {
        if (!Directory.Exists(gamePath))
        {
            return null;
        }

        if (string.Equals(Path.GetFileName(gamePath), "Mods", StringComparison.OrdinalIgnoreCase))
        {
            return gamePath;
        }

        var modsPath = Path.Combine(gamePath, "Mods");
        return Directory.Exists(modsPath) ? modsPath : null;
    }

    private static ModPackage? ScanPackageDirectory(string directory)
    {
        var manifestPath = Path.Combine(directory, "manifest.json");
        var iniFiles = Directory.EnumerateFiles(directory, "*.ini", SearchOption.TopDirectoryOnly)
            .OrderBy(Path.GetFileName)
            .ToArray();

        if (File.Exists(manifestPath))
        {
            return ScanGakumasMiPackage(directory, manifestPath, iniFiles);
        }

        if (iniFiles.Length > 0)
        {
            return ScanGenericPackage(directory, iniFiles);
        }

        return null;
    }

    private static ModPackage ScanGenericPackage(string directory, IReadOnlyList<string> iniFiles)
    {
        var directoryName = Path.GetFileName(directory);
        var isEnabled = !directoryName.StartsWith(DisabledPrefix, StringComparison.OrdinalIgnoreCase);
        return new ModPackage
        {
            Name = DisplayNameFromDirectory(directoryName),
            Type = PackageType.Generic3Dmigoto,
            Status = isEnabled ? PackageStatus.Enabled : PackageStatus.Disabled,
            IsEnabled = isEnabled,
            Target = "通用",
            DirectoryPath = directory,
            IniFiles = iniFiles,
            Checks = [new ValidationIssue("通用 3DMigoto 包，仅支持启用/禁用")],
        };
    }

    private static ModPackage ScanGakumasMiPackage(string directory, string manifestPath, IReadOnlyList<string> iniFiles)
    {
        var checks = new List<ValidationIssue>();
        var conflicts = new List<string>();
        var directoryName = Path.GetFileName(directory);
        var isEnabled = !directoryName.StartsWith(DisabledPrefix, StringComparison.OrdinalIgnoreCase);

        string? id = null;
        var name = DisplayNameFromDirectory(directoryName);
        string? author = null;
        string? version = null;
        string? target = null;
        string? coverPath = null;
        var manifestBroken = false;
        var missingFileCount = 0;
        var invalidDdsCount = 0;

        try
        {
            using var stream = File.OpenRead(manifestPath);
            using var document = JsonDocument.Parse(stream, new JsonDocumentOptions
            {
                AllowTrailingCommas = true,
                CommentHandling = JsonCommentHandling.Skip,
            });

            var root = document.RootElement;
            id = ReadString(root, "id");
            name = ReadString(root, "name") ?? name;
            author = ReadString(root, "author");
            version = ReadString(root, "version");
            target = ReadStringArray(root, "targets");
            conflicts.AddRange(ReadStringArrayItems(root, "conflicts"));
            coverPath = ResolveCoverPath(directory, ReadString(root, "cover"));

            checks.Add(new ValidationIssue("manifest.json 正常"));
            if (id is null)
            {
                checks.Add(new ValidationIssue("manifest 缺少 id", "Warning"));
            }
            if (version is null)
            {
                checks.Add(new ValidationIssue("manifest 缺少 version", "Warning"));
            }
            if (!root.TryGetProperty("materials", out _))
            {
                checks.Add(new ValidationIssue("manifest 缺少 materials，抓帧补全不可用", "Warning"));
            }
            else
            {
                var fileCheck = CheckManifestFileReferences(directory, root, checks);
                missingFileCount += fileCheck.MissingFileCount;
                invalidDdsCount += fileCheck.InvalidDdsCount;
            }

            if (conflicts.Count > 0)
            {
                checks.Add(new ValidationIssue($"声明冲突键 {conflicts.Count} 个"));
            }
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            manifestBroken = true;
            checks.Add(new ValidationIssue($"manifest.json 读取失败：{ex.Message}", "Error"));
        }

        var modIni = Path.Combine(directory, "mod.ini");
        if (File.Exists(modIni))
        {
            checks.Add(new ValidationIssue("mod.ini 正常"));
        }
        else
        {
            checks.Add(new ValidationIssue("缺少 mod.ini", "Error"));
        }

        if (coverPath is not null)
        {
            checks.Add(new ValidationIssue("封面图正常"));
        }

        var status = manifestBroken || checks.Any(issue => issue.Severity == "Error")
            ? PackageStatus.Broken
            : isEnabled ? PackageStatus.Enabled : PackageStatus.Disabled;

        return new ModPackage
        {
            Id = id,
            Name = name,
            Author = author,
            Version = version,
            Type = PackageType.GakumasMi,
            Status = status,
            IsEnabled = isEnabled,
            Target = target,
            DirectoryPath = directory,
            ManifestPath = manifestPath,
            CoverPath = coverPath,
            IniFiles = iniFiles,
            MissingFileCount = missingFileCount,
            InvalidDdsCount = invalidDdsCount,
            Checks = checks,
            Conflicts = conflicts,
        };
    }

    private static string DisplayNameFromDirectory(string directoryName)
    {
        return directoryName.StartsWith(DisabledPrefix, StringComparison.OrdinalIgnoreCase)
            ? directoryName[DisabledPrefix.Length..].TrimStart(' ', '_', '-')
            : directoryName;
    }

    private static string? ResolveCoverPath(string directory, string? cover)
    {
        var candidates = new List<string>();
        if (!string.IsNullOrWhiteSpace(cover))
        {
            candidates.Add(Path.Combine(directory, cover));
        }
        candidates.Add(Path.Combine(directory, "cover.png"));

        return candidates.FirstOrDefault(File.Exists);
    }

    private static IReadOnlyList<ModPackage> ApplyGlobalConflicts(IReadOnlyList<ModPackage> packages)
    {
        var enabledConflictGroups = packages
            .Where(package => package.IsEnabled)
            .SelectMany(package => package.Conflicts.Select(key => new { Key = key, Package = package }))
            .GroupBy(item => item.Key)
            .Where(group => group.Select(item => item.Package.DirectoryPath).Distinct().Count() > 1)
            .ToDictionary(group => group.Key, group => group.Select(item => item.Package).ToList());

        if (enabledConflictGroups.Count == 0)
        {
            return packages;
        }

        return packages.Select(package =>
        {
            var matchedKeys = package.Conflicts.Where(enabledConflictGroups.ContainsKey).ToList();
            if (!package.IsEnabled || matchedKeys.Count == 0 || package.Status == PackageStatus.Broken)
            {
                return package;
            }

            var extraChecks = matchedKeys
                .Select(key =>
                {
                    var others = enabledConflictGroups[key]
                        .Where(other => other.DirectoryPath != package.DirectoryPath)
                        .Select(other => other.Name)
                        .Distinct();
                    return new ValidationIssue($"与 {string.Join(", ", others)} 冲突：{key}", "Warning");
                });

            return package with
            {
                Status = PackageStatus.Conflict,
                Checks = package.Checks.Concat(extraChecks).ToList(),
            };
        }).ToList();
    }

    private static FileReferenceCheckResult CheckManifestFileReferences(string directory, JsonElement root, List<ValidationIssue> checks)
    {
        var references = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        if (root.TryGetProperty("materials", out var materials) && materials.ValueKind == JsonValueKind.Object)
        {
            foreach (var material in materials.EnumerateObject())
            {
                AddFileReference(material.Value, references);
            }
        }

        if (root.TryGetProperty("opacityTexture", out var opacityTexture) && opacityTexture.ValueKind == JsonValueKind.Object)
        {
            AddFileReference(opacityTexture, references);
        }

        if (references.Count == 0)
        {
            checks.Add(new ValidationIssue("manifest 未声明贴图文件", "Warning"));
            return new FileReferenceCheckResult(0, 0);
        }

        var missing = 0;
        var invalidDds = 0;
        foreach (var relativePath in references)
        {
            if (!IsSafeRelativePath(relativePath))
            {
                checks.Add(new ValidationIssue($"manifest 文件路径不安全：{relativePath}", "Error"));
                missing++;
                continue;
            }

            var fullPath = Path.Combine(directory, relativePath);
            if (!File.Exists(fullPath))
            {
                checks.Add(new ValidationIssue($"缺少文件：{relativePath}", "Error"));
                missing++;
            }
            else if (Path.GetExtension(fullPath).Equals(".dds", StringComparison.OrdinalIgnoreCase)
                && !LooksLikeDds(fullPath))
            {
                checks.Add(new ValidationIssue($"DDS 文件头无效：{relativePath}", "Error"));
                invalidDds++;
            }
        }

        var existing = references.Count - missing;
        checks.Add(new ValidationIssue($"贴图文件 ({existing}/{references.Count}) 正常"));
        if (invalidDds == 0)
        {
            checks.Add(new ValidationIssue("DDS 格式校验通过"));
        }

        return new FileReferenceCheckResult(missing, invalidDds);
    }

    private static void AddFileReference(JsonElement element, ISet<string> references)
    {
        if (!element.TryGetProperty("file", out var file) || file.ValueKind != JsonValueKind.String)
        {
            return;
        }

        var path = file.GetString();
        if (!string.IsNullOrWhiteSpace(path))
        {
            references.Add(path.Replace('/', Path.DirectorySeparatorChar));
        }
    }

    private static bool IsSafeRelativePath(string path)
    {
        return !Path.IsPathFullyQualified(path)
            && !path.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                .Any(part => part == "..");
    }

    private static bool LooksLikeDds(string path)
    {
        Span<byte> header = stackalloc byte[4];
        try
        {
            using var stream = File.OpenRead(path);
            return stream.Read(header) == 4
                && header[0] == (byte)'D'
                && header[1] == (byte)'D'
                && header[2] == (byte)'S'
                && header[3] == (byte)' ';
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }

    private sealed record FileReferenceCheckResult(int MissingFileCount, int InvalidDdsCount);

    private static string? ReadString(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    private static string? ReadStringArray(JsonElement root, string propertyName)
    {
        var values = ReadStringArrayItems(root, propertyName);
        return values.Count == 0 ? null : string.Join(", ", values);
    }

    private static List<string> ReadStringArrayItems(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return value.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToList();
    }
}
