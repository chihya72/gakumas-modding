using System.Collections.ObjectModel;
using GakumasModManager.Models;
using GakumasModManager.Services;
using Stylet;

namespace GakumasModManager.ViewModels;

public sealed class RootViewModel : Screen
{
    private readonly IModManagerCore _core;
    private readonly IAppLogService _logService;
    private ModPackage? _selectedPackage;
    private string _gamePath = "";
    private string _modsPath = "";

    public RootViewModel(IModManagerCore core, IAppLogService logService)
    {
        _core = core;
        _logService = logService;
        DisplayName = "Gakumas Mod Manager";

        GamePath = core.GetDefaultGamePath();
        RefreshPackages();
        AddLog($"日志文件：{_logService.LogFilePath}");
    }

    public ObservableCollection<ModPackage> Packages { get; } = [];

    public ObservableCollection<LogEntry> Logs { get; } = [];

    public string GamePath
    {
        get => _gamePath;
        set => SetAndNotify(ref _gamePath, value);
    }

    public string SummaryText
    {
        get
        {
            var enabled = Packages.Count(package => package.IsEnabled);
            var conflicts = Packages.Count(package => package.Status == PackageStatus.Conflict);
            var broken = Packages.Count(package => package.Status == PackageStatus.Broken);
            return $"全部 {Packages.Count}    已启用 {enabled}    有冲突 {conflicts}    损坏 {broken}";
        }
    }

    public ModPackage? SelectedPackage
    {
        get => _selectedPackage;
        set
        {
            if (SetAndNotify(ref _selectedPackage, value))
            {
                NotifyOfPropertyChange(nameof(ToggleSelectedPackageText));
                NotifyOfPropertyChange(nameof(CanToggleSelectedPackage));
            }
        }
    }

    public string ToggleSelectedPackageText => SelectedPackage?.IsEnabled == true ? "禁用" : "启用";

    public bool CanToggleSelectedPackage => !string.IsNullOrWhiteSpace(SelectedPackage?.DirectoryPath);

    public void RefreshPackages()
    {
        RefreshPackages(null);
    }

    public void BrowseGamePath()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = "选择游戏根目录（gakumas.exe 所在文件夹）或其 Mods 目录",
        };
        if (!string.IsNullOrWhiteSpace(GamePath) && System.IO.Directory.Exists(GamePath))
        {
            dialog.InitialDirectory = GamePath;
        }

        if (dialog.ShowDialog() == true)
        {
            GamePath = dialog.FolderName;
            RefreshPackages();
        }
    }

    private void RefreshPackages(string? preferredDirectoryPath)
    {
        _core.SaveGamePath(GamePath);
        var result = _core.ScanGameDirectory(GamePath);
        _modsPath = result.ModsPath;

        Packages.Clear();
        foreach (var package in result.Packages)
        {
            Packages.Add(package);
        }

        SelectedPackage = preferredDirectoryPath is null
            ? Packages.FirstOrDefault()
            : Packages.FirstOrDefault(package => string.Equals(
                package.DirectoryPath,
                preferredDirectoryPath,
                StringComparison.OrdinalIgnoreCase)) ?? Packages.FirstOrDefault();
        NotifyOfPropertyChange(nameof(SummaryText));

        AddLog($"扫描完成，扫描到 {Packages.Count} 个包");
        if (result.Issues.Count > 0)
        {
            foreach (var issue in result.Issues)
            {
                AddLog(issue.Text, issue.Severity);
            }
        }
        else
        {
            AddLog($"Mods 目录：{result.ModsPath}");
        }
    }

    public void ToggleSelectedPackage()
    {
        if (SelectedPackage is null)
        {
            AddLog("未选择 Mod 包，无法操作。", "Warning");
            return;
        }

        var targetEnabled = !SelectedPackage.IsEnabled;
        var result = _core.SetPackageEnabled(SelectedPackage, targetEnabled);
        AddLog(result.Message, result.Severity);
        if (result.Ok)
        {
            RefreshPackages(result.NewDirectoryPath);
        }
    }

    public void ReloadGame()
    {
        var result = _core.ReloadGame(GamePath);
        AddLog(result.Message, result.Severity);
    }

    public void InstallDroppedPaths(IReadOnlyList<string> paths)
    {
        if (paths.Count == 0)
        {
            return;
        }

        var result = _core.InstallPackages(_modsPath, paths);
        AddLog(result.Message, result.Severity);
        if (result.Ok)
        {
            RefreshPackages();
        }
    }

    public void OpenSelectedPackageFolder()
    {
        if (SelectedPackage is null)
        {
            AddLog("未选择 Mod 包，无法打开目录。", "Warning");
            return;
        }

        var result = _core.OpenPackageFolder(SelectedPackage);
        AddLog(result.Message, result.Severity);
    }

    public void OpenD3dmigotoLog()
    {
        var result = _core.OpenD3dmigotoLog(GamePath);
        AddLog(result.Message, result.Severity);
    }

    public void OpenShortcutsDoc()
    {
        var result = _core.OpenShortcutsDoc(GamePath);
        AddLog(result.Message, result.Severity);
    }

    public void ClearLogs()
    {
        Logs.Clear();
        AddLog("已清空界面日志。");
    }

    public void OpenLogDirectory()
    {
        var result = _logService.OpenLogDirectory();
        AddLog(result.Message, result.Severity);
    }

    private void AddLog(string message, string level = "Info")
    {
        var entry = new LogEntry(DateTime.Now.ToString("HH:mm:ss"), message, level);
        Logs.Insert(0, entry);
        _logService.Append(entry);
    }
}
