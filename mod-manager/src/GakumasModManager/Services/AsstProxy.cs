using GakumasModManager.Models;
using System.IO;

namespace GakumasModManager.Services;

public interface IModManagerCore
{
    string GetDefaultGamePath();

    void SaveGamePath(string gamePath);

    ScanResult ScanGameDirectory(string gamePath);

    OperationResult SetPackageEnabled(ModPackage package, bool enabled);

    OperationResult ReloadGame(string gamePath);

    OperationResult OpenPackageFolder(ModPackage package);

    OperationResult InstallPackages(string modsPath, IReadOnlyList<string> sourcePaths);

    OperationResult OpenD3dmigotoLog(string gamePath);

    OperationResult OpenShortcutsDoc(string gamePath);
}

public sealed class AsstProxy(
    IScannerService scannerService,
    IPackageActionsService packageActionsService,
    IReloadGameService reloadGameService,
    ISettingsService settingsService,
    IPackageInstallService packageInstallService) : IModManagerCore
{
    public string GetDefaultGamePath()
    {
        var saved = settingsService.LoadGamePath();
        if (!string.IsNullOrWhiteSpace(saved) && Directory.Exists(saved))
        {
            return saved;
        }

        const string realTestModsPath = @"D:\Games\gakumas\Mods";
        if (Directory.Exists(realTestModsPath))
        {
            return realTestModsPath;
        }

        var current = Directory.GetCurrentDirectory();
        var fromCurrent = Path.Combine(current, "3dmigoto-gkms");
        if (Directory.Exists(fromCurrent))
        {
            return fromCurrent;
        }

        var cursor = new DirectoryInfo(AppContext.BaseDirectory);
        while (cursor is not null)
        {
            var candidate = Path.Combine(cursor.FullName, "3dmigoto-gkms");
            if (Directory.Exists(candidate))
            {
                return candidate;
            }

            cursor = cursor.Parent;
        }

        return current;
    }

    public void SaveGamePath(string gamePath)
    {
        settingsService.SaveGamePath(gamePath);
    }

    public ScanResult ScanGameDirectory(string gamePath)
    {
        return scannerService.ScanGameDirectory(gamePath);
    }

    public OperationResult SetPackageEnabled(ModPackage package, bool enabled)
    {
        return packageActionsService.SetEnabled(package, enabled);
    }

    public OperationResult ReloadGame(string gamePath)
    {
        return reloadGameService.SendReloadKey(gamePath);
    }

    public OperationResult OpenPackageFolder(ModPackage package)
    {
        var path = package.DirectoryPath;
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path))
        {
            return new OperationResult(false, $"目录不存在：{path}", Severity: "Error");
        }

        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = path,
                UseShellExecute = true,
            });
            return new OperationResult(true, $"已打开目录：{path}");
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception)
        {
            return new OperationResult(false, $"打开目录失败：{ex.Message}", Severity: "Error");
        }
    }

    public OperationResult InstallPackages(string modsPath, IReadOnlyList<string> sourcePaths)
    {
        return packageInstallService.Install(modsPath, sourcePaths);
    }

    public OperationResult OpenD3dmigotoLog(string gamePath)
    {
        var logPath = Path.Combine(ResolveGameRoot(gamePath), "d3d11_log.txt");
        if (!File.Exists(logPath))
        {
            return new OperationResult(false,
                $"未找到 3DMigoto 日志（{logPath}）。需在游戏目录 d3dx.ini 里设 [Logging] calls=1 并重进游戏。",
                Severity: "Warning");
        }

        return OpenWithShell(logPath, "3DMigoto 日志");
    }

    public OperationResult OpenShortcutsDoc(string gamePath)
    {
        var docPath = Path.Combine(ResolveGameRoot(gamePath), "键位说明.txt");
        if (!File.Exists(docPath))
        {
            return new OperationResult(false,
                $"未找到键位说明（{docPath}）。它随插件安装在游戏根目录。",
                Severity: "Warning");
        }

        return OpenWithShell(docPath, "键位说明");
    }

    // 游戏根目录：gamePath 可能是根目录本身或其下的 Mods，统一归一到根。
    private static string ResolveGameRoot(string gamePath)
    {
        var path = string.IsNullOrWhiteSpace(gamePath)
            ? Directory.GetCurrentDirectory()
            : Environment.ExpandEnvironmentVariables(gamePath.Trim().Trim('"'));
        if (string.Equals(Path.GetFileName(path), "Mods", StringComparison.OrdinalIgnoreCase))
        {
            path = Directory.GetParent(path)?.FullName ?? path;
        }

        return path;
    }

    private static OperationResult OpenWithShell(string path, string label)
    {
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo { FileName = path, UseShellExecute = true });
            return new OperationResult(true, $"已打开{label}：{path}");
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception)
        {
            return new OperationResult(false, $"打开{label}失败：{ex.Message}", Severity: "Error");
        }
    }
}
