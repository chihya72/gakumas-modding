using System.IO;
using System.Text.RegularExpressions;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface ID3dxConfigService
{
    D3dxSettings LoadSettings(string gamePath);

    OperationResult BackupD3dxIni(string gamePath, int keepCount);
}

public sealed partial class D3dxConfigService : ID3dxConfigService
{
    public D3dxSettings LoadSettings(string gamePath)
    {
        var d3dxPath = ResolveD3dxIniPath(gamePath);
        if (!File.Exists(d3dxPath))
        {
            return new D3dxSettings(d3dxPath, "1", "F8", "F10", 10);
        }

        var lines = File.ReadAllLines(d3dxPath);
        return new D3dxSettings(
            d3dxPath,
            ReadValue(lines, "Hunting", "hunting") ?? "1",
            ReadKey(lines, "Hunting", "analyse_frame") ?? "F8",
            ReadKey(lines, "Hunting", "reload_fixes") ?? "F10",
            10);
    }

    public OperationResult BackupD3dxIni(string gamePath, int keepCount)
    {
        var d3dxPath = ResolveD3dxIniPath(gamePath);
        if (!File.Exists(d3dxPath))
        {
            return new OperationResult(false, $"未找到 d3dx.ini：{d3dxPath}", Severity: "Error");
        }

        try
        {
            var backupPath = CreateBackupPath(d3dxPath);
            File.Copy(d3dxPath, backupPath, overwrite: false);
            CleanupBackups(d3dxPath, keepCount);
            return new OperationResult(true, $"已备份 d3dx.ini：{backupPath}", backupPath);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new OperationResult(false, $"备份 d3dx.ini 失败：{ex.Message}", Severity: "Error");
        }
    }

    private static string ResolveD3dxIniPath(string gamePath)
    {
        var path = string.IsNullOrWhiteSpace(gamePath)
            ? Directory.GetCurrentDirectory()
            : Environment.ExpandEnvironmentVariables(gamePath.Trim().Trim('"'));

        if (string.Equals(Path.GetFileName(path), "Mods", StringComparison.OrdinalIgnoreCase))
        {
            path = Directory.GetParent(path)?.FullName ?? path;
        }

        return Path.Combine(path, "d3dx.ini");
    }

    private static string CreateBackupPath(string d3dxPath)
    {
        var basePath = $"{d3dxPath}.bak.{DateTime.Now:yyyyMMdd-HHmmss-fff}";
        if (!File.Exists(basePath))
        {
            return basePath;
        }

        for (var index = 1; index < 1000; index++)
        {
            var candidate = $"{basePath}.{index}";
            if (!File.Exists(candidate))
            {
                return candidate;
            }
        }

        throw new IOException("无法创建唯一备份文件名。");
    }

    private static string? ReadValue(IReadOnlyList<string> lines, string section, string key)
    {
        var line = FindSectionValueLine(lines, section, key);
        if (line is null)
        {
            return null;
        }

        var index = line.IndexOf('=');
        return index < 0 ? null : line[(index + 1)..].Trim();
    }

    private static string? ReadKey(IReadOnlyList<string> lines, string section, string key)
    {
        var value = ReadValue(lines, section, key);
        if (value is null)
        {
            return null;
        }

        var matches = VkTokenRegex().Matches(value);
        return matches.Count == 0 ? value : matches[^1].Groups["key"].Value;
    }

    private static string? FindSectionValueLine(IReadOnlyList<string> lines, string section, string key)
    {
        var inSection = false;
        foreach (var rawLine in lines)
        {
            var line = rawLine.Trim();
            if (line.StartsWith(';') || line.Length == 0)
            {
                continue;
            }

            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                inSection = string.Equals(line[1..^1], section, StringComparison.OrdinalIgnoreCase);
                continue;
            }

            if (!inSection)
            {
                continue;
            }

            var index = line.IndexOf('=');
            if (index > 0 && string.Equals(line[..index].Trim(), key, StringComparison.OrdinalIgnoreCase))
            {
                return rawLine;
            }
        }

        return null;
    }

    private static void CleanupBackups(string d3dxPath, int keepCount)
    {
        if (keepCount <= 0)
        {
            keepCount = 1;
        }

        var directory = Path.GetDirectoryName(d3dxPath);
        var fileName = Path.GetFileName(d3dxPath);
        if (directory is null)
        {
            return;
        }

        var backups = Directory.EnumerateFiles(directory, $"{fileName}.bak.*")
            .OrderByDescending(File.GetCreationTimeUtc)
            .Skip(keepCount);
        foreach (var backup in backups)
        {
            File.Delete(backup);
        }
    }

    [GeneratedRegex(@"VK_(?<key>[A-Z0-9_]+)", RegexOptions.IgnoreCase)]
    private static partial Regex VkTokenRegex();
}
