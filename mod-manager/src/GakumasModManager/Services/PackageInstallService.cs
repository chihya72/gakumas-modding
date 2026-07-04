using System.IO;
using System.IO.Compression;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface IPackageInstallService
{
    OperationResult Install(string modsPath, IReadOnlyList<string> sourcePaths);
}

public sealed class PackageInstallService : IPackageInstallService
{
    public OperationResult Install(string modsPath, IReadOnlyList<string> sourcePaths)
    {
        if (string.IsNullOrWhiteSpace(modsPath) || !Directory.Exists(modsPath))
        {
            return new OperationResult(false, "未找到 Mods 目录，无法安装。请先设置有效的游戏路径并刷新。", Severity: "Error");
        }

        var installed = new List<string>();
        var errors = new List<string>();
        foreach (var source in sourcePaths)
        {
            try
            {
                var name = InstallOne(modsPath, source);
                if (name is not null)
                {
                    installed.Add(name);
                }
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException)
            {
                errors.Add($"{Path.GetFileName(source)}：{ex.Message}");
            }
        }

        if (installed.Count == 0 && errors.Count == 0)
        {
            return new OperationResult(false, "拖入的内容不是有效的 mod（需为文件夹或 .zip）。", Severity: "Warning");
        }

        var parts = new List<string>();
        if (installed.Count > 0)
        {
            parts.Add($"已安装 {installed.Count} 个：{string.Join(", ", installed)}");
        }
        if (errors.Count > 0)
        {
            parts.Add($"失败 {errors.Count} 个：{string.Join("; ", errors)}");
        }

        return new OperationResult(errors.Count == 0, string.Join("；", parts), Severity: errors.Count == 0 ? "Info" : "Warning");
    }

    // Returns the installed folder name, or null if the source isn't a folder or a .zip.
    private static string? InstallOne(string modsPath, string source)
    {
        if (Directory.Exists(source))
        {
            var name = new DirectoryInfo(source).Name;
            CopyInto(modsPath, name, source);
            return name;
        }

        if (File.Exists(source) && Path.GetExtension(source).Equals(".zip", StringComparison.OrdinalIgnoreCase))
        {
            return InstallZip(modsPath, source);
        }

        return null;
    }

    private static string InstallZip(string modsPath, string zipPath)
    {
        var temp = Path.Combine(Path.GetTempPath(), "gkms-mm-install-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            ZipFile.ExtractToDirectory(zipPath, temp);

            // If the zip is a single top-level folder, use it as the package root so we don't
            // double-nest (Mods/Foo/Foo/...). Otherwise treat the whole zip as one package.
            var entries = Directory.GetFileSystemEntries(temp);
            string root = temp;
            var name = Path.GetFileNameWithoutExtension(zipPath);
            if (entries.Length == 1 && Directory.Exists(entries[0]))
            {
                root = entries[0];
                name = new DirectoryInfo(entries[0]).Name;
            }

            CopyInto(modsPath, name, root);
            return name;
        }
        finally
        {
            if (Directory.Exists(temp))
            {
                Directory.Delete(temp, recursive: true);
            }
        }
    }

    private static void CopyInto(string modsPath, string name, string sourceDir)
    {
        var target = Path.Combine(modsPath, name);
        if (Directory.Exists(target))
        {
            throw new IOException($"目标已存在，跳过：{name}");
        }

        // CopyDirectory (not Move) so extraction from %TEMP% works across drives.
        Directory.CreateDirectory(target);
        foreach (var file in Directory.GetFiles(sourceDir, "*", SearchOption.AllDirectories))
        {
            var destination = Path.Combine(target, Path.GetRelativePath(sourceDir, file));
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            File.Copy(file, destination, overwrite: false);
        }
    }
}
