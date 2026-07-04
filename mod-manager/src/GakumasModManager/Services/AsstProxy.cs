using GakumasModManager.Models;
using System.IO;

namespace GakumasModManager.Services;

public interface IModManagerCore
{
    string GetDefaultGamePath();

    ScanResult ScanGameDirectory(string gamePath);

    OperationResult SetPackageEnabled(ModPackage package, bool enabled);

    OperationResult ReloadGame(string gamePath);

    D3dxSettings LoadD3dxSettings(string gamePath);

    OperationResult BackupD3dxIni(string gamePath, int keepCount);
}

public sealed class AsstProxy(
    IScannerService scannerService,
    IPackageActionsService packageActionsService,
    IReloadGameService reloadGameService,
    ID3dxConfigService d3dxConfigService) : IModManagerCore
{
    public string GetDefaultGamePath()
    {
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

    public D3dxSettings LoadD3dxSettings(string gamePath)
    {
        return d3dxConfigService.LoadSettings(gamePath);
    }

    public OperationResult BackupD3dxIni(string gamePath, int keepCount)
    {
        return d3dxConfigService.BackupD3dxIni(gamePath, keepCount);
    }
}
