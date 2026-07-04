using System.IO;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface ID3dxReloadService
{
    OperationResult EnsureForegroundReloadEnabled(string gamePath);
}

// 确保 d3dx.ini 的 [System] check_foreground_window=0：让 3DMigoto 在游戏非前台时也响应
// F10，Mod Manager 才能在后台可靠触发重载（=1 时外部 F10 必须抢前台，Windows 抢前台不可靠
// → 概率重载）。启动时调用一次；已是 0 则不写。注意：3DMigoto 在游戏启动时读 d3dx.ini，
// 本次写入对已在运行的游戏要下次启动才生效。
public sealed class D3dxReloadService : ID3dxReloadService
{
    public OperationResult EnsureForegroundReloadEnabled(string gamePath)
    {
        var d3dxPath = ResolveD3dxIniPath(gamePath);
        if (!File.Exists(d3dxPath))
        {
            return new OperationResult(false, $"未找到 d3dx.ini：{d3dxPath}（无法自动确保 F10 后台重载）。", Severity: "Warning");
        }

        try
        {
            var text = File.ReadAllText(d3dxPath);
            if (ReadValue(text, "System", "check_foreground_window") == "0")
            {
                return new OperationResult(true, "d3dx.ini check_foreground_window 已为 0，F10 后台重载可靠。");
            }

            File.WriteAllText(d3dxPath, SetSectionValue(text, "System", "check_foreground_window", "0"));
            return new OperationResult(true,
                "已设 d3dx.ini check_foreground_window=0：游戏下次启动后 F10 重载不再依赖前台。",
                d3dxPath);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new OperationResult(false, $"自动设置 check_foreground_window 失败：{ex.Message}", Severity: "Warning");
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

    private static string? ReadValue(string text, string section, string key)
    {
        var inSection = false;
        foreach (var rawLine in text.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith(';'))
            {
                continue;
            }

            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                inSection = string.Equals(line[1..^1], section, StringComparison.OrdinalIgnoreCase);
                continue;
            }

            var eq = line.IndexOf('=');
            if (inSection && eq > 0 && string.Equals(line[..eq].Trim(), key, StringComparison.OrdinalIgnoreCase))
            {
                return line[(eq + 1)..].Trim();
            }
        }

        return null;
    }

    // 替换 section 下 key 的值，保留其余所有行/注释/换行风格；缺 key 则插到 section 头下，缺 section 则追加。
    private static string SetSectionValue(string text, string section, string key, string value)
    {
        var newline = text.Contains("\r\n") ? "\r\n" : "\n";
        var lines = text.Split('\n').Select(l => l.TrimEnd('\r')).ToList();
        var inSection = false;
        var sectionHeaderIndex = -1;

        for (var i = 0; i < lines.Count; i++)
        {
            var trimmed = lines[i].Trim();
            if (trimmed.Length == 0 || trimmed.StartsWith(';'))
            {
                continue;
            }

            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                if (inSection)
                {
                    break;
                }

                inSection = string.Equals(trimmed[1..^1], section, StringComparison.OrdinalIgnoreCase);
                if (inSection)
                {
                    sectionHeaderIndex = i;
                }

                continue;
            }

            var eq = trimmed.IndexOf('=');
            if (inSection && eq > 0 && string.Equals(trimmed[..eq].Trim(), key, StringComparison.OrdinalIgnoreCase))
            {
                var raw = lines[i];
                var rawEq = raw.IndexOf('=');
                var afterEq = raw[(rawEq + 1)..];
                var ws = afterEq[..(afterEq.Length - afterEq.TrimStart().Length)];
                lines[i] = raw[..(rawEq + 1)] + ws + value;
                return string.Join(newline, lines);
            }
        }

        if (sectionHeaderIndex >= 0)
        {
            lines.Insert(sectionHeaderIndex + 1, $"{key} = {value}");
        }
        else
        {
            if (lines.Count > 0 && lines[^1].Trim().Length != 0)
            {
                lines.Add("");
            }

            lines.Add($"[{section}]");
            lines.Add($"{key} = {value}");
        }

        return string.Join(newline, lines);
    }
}
