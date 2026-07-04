using System.IO;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface IPackageActionsService
{
    OperationResult SetEnabled(ModPackage package, bool enabled);
}

public sealed class PackageActionsService : IPackageActionsService
{
    private const string DisabledPrefix = "DISABLED ";

    public OperationResult SetEnabled(ModPackage package, bool enabled)
    {
        if (string.IsNullOrWhiteSpace(package.DirectoryPath))
        {
            return new OperationResult(false, "包目录为空，无法操作。", Severity: "Error");
        }

        var source = package.DirectoryPath;
        if (!Directory.Exists(source))
        {
            return new OperationResult(false, $"包目录不存在：{source}", Severity: "Error");
        }

        if (enabled && package.IsEnabled)
        {
            return new OperationResult(true, $"{package.Name} 已经启用。", source);
        }

        if (!enabled && !package.IsEnabled)
        {
            return new OperationResult(true, $"{package.Name} 已经禁用。", source);
        }

        var parent = Directory.GetParent(source);
        if (parent is null)
        {
            return new OperationResult(false, $"无法解析父目录：{source}", Severity: "Error");
        }

        var currentName = Path.GetFileName(source);
        var targetName = enabled
            ? StripDisabledPrefix(currentName)
            : DisabledPrefix + StripDisabledPrefix(currentName);

        if (string.IsNullOrWhiteSpace(targetName))
        {
            return new OperationResult(false, "目标目录名为空，已取消操作。", Severity: "Error");
        }

        var target = Path.Combine(parent.FullName, targetName);
        if (Path.GetFullPath(source).Equals(Path.GetFullPath(target), StringComparison.OrdinalIgnoreCase))
        {
            return new OperationResult(true, $"{package.Name} 状态无需变更。", source);
        }

        if (Directory.Exists(target))
        {
            return new OperationResult(false, $"目标目录已存在：{target}", Severity: "Error");
        }

        try
        {
            Directory.Move(source, target);
            return new OperationResult(
                true,
                enabled ? $"已启用 {package.Name}" : $"已禁用 {package.Name}",
                target);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new OperationResult(false, $"目录改名失败：{ex.Message}", Severity: "Error");
        }
    }

    private static string StripDisabledPrefix(string name)
    {
        var result = name;
        while (result.StartsWith("DISABLED", StringComparison.OrdinalIgnoreCase))
        {
            result = result["DISABLED".Length..].TrimStart(' ', '_', '-');
        }

        return result;
    }
}

