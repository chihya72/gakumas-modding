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
    private string _d3dxIniPath = "";
    private string _huntingMode = "1";
    private string _frameAnalysisKey = "F8";
    private string _reloadKey = "F10";
    private int _backupKeepCount = 10;

    public RootViewModel(IModManagerCore core, IAppLogService logService)
    {
        _core = core;
        _logService = logService;
        DisplayName = "Gakumas Mod Manager";

        NavigationItems = ["首页", "Mods", "抓帧", "设置", "备份"];
        Filters = ["全部", "已启用", "有冲突", "损坏", "GakumasMI 包", "通用 3DMigoto"];

        GamePath = core.GetDefaultGamePath();
        RefreshPackages();
        AddLog($"日志文件：{_logService.LogFilePath}");
    }

    public IReadOnlyList<string> NavigationItems { get; }

    public IReadOnlyList<string> Filters { get; }

    public ObservableCollection<ModPackage> Packages { get; } = [];

    public ObservableCollection<LogEntry> Logs { get; } = [];

    public string GamePath
    {
        get => _gamePath;
        set => SetAndNotify(ref _gamePath, value);
    }

    public string SearchText { get; set; } = "";

    public string D3dxIniPath
    {
        get => _d3dxIniPath;
        set => SetAndNotify(ref _d3dxIniPath, value);
    }

    public string HuntingMode
    {
        get => _huntingMode;
        set => SetAndNotify(ref _huntingMode, value);
    }

    public string FrameAnalysisKey
    {
        get => _frameAnalysisKey;
        set => SetAndNotify(ref _frameAnalysisKey, value);
    }

    public string ReloadKey
    {
        get => _reloadKey;
        set => SetAndNotify(ref _reloadKey, value);
    }

    public int BackupKeepCount
    {
        get => _backupKeepCount;
        set => SetAndNotify(ref _backupKeepCount, value);
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

    private void RefreshPackages(string? preferredDirectoryPath)
    {
        var result = _core.ScanGameDirectory(GamePath);

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
        RefreshD3dxSettings();

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

    public void BackupD3dxIni()
    {
        var result = _core.BackupD3dxIni(GamePath, BackupKeepCount);
        AddLog(result.Message, result.Severity);
    }

    public void LearnSlotVariants()
    {
        AddLog("准备从抓帧学习 slotVariants");
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

    private void RefreshD3dxSettings()
    {
        var settings = _core.LoadD3dxSettings(GamePath);
        D3dxIniPath = settings.D3dxIniPath;
        HuntingMode = settings.HuntingMode;
        FrameAnalysisKey = settings.FrameAnalysisKey;
        ReloadKey = settings.ReloadKey;
        BackupKeepCount = settings.BackupKeepCount;
    }
}
