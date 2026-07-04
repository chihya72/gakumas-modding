namespace GakumasModManager.Models;

public enum PackageType
{
    GakumasMi,
    Generic3Dmigoto
}

public enum PackageStatus
{
    Enabled,
    Disabled,
    Conflict,
    Broken
}

public sealed record ValidationIssue(string Text, string Severity = "Info");

public sealed record ModPackage
{
    public string? Id { get; init; }
    public required string Name { get; init; }
    public string? Author { get; init; }
    public string? Version { get; init; }
    public required PackageType Type { get; init; }
    public required PackageStatus Status { get; init; }
    public required bool IsEnabled { get; init; }
    public string? Target { get; init; }
    public string? DirectoryPath { get; init; }
    public string? ManifestPath { get; init; }
    public string? CoverPath { get; init; }
    public IReadOnlyList<string> IniFiles { get; init; } = [];
    public int MissingFileCount { get; init; }
    public int InvalidDdsCount { get; init; }
    public IReadOnlyList<ValidationIssue> Checks { get; init; } = [];
    public IReadOnlyList<string> Conflicts { get; init; } = [];

    public string TypeLabel => Type switch
    {
        PackageType.GakumasMi => "GakumasMI 包",
        PackageType.Generic3Dmigoto => "通用 3DMigoto",
        _ => "未知"
    };

    public string StatusLabel => Status switch
    {
        PackageStatus.Enabled => "已启用",
        PackageStatus.Disabled => "已禁用",
        PackageStatus.Conflict => "有冲突",
        PackageStatus.Broken => "损坏",
        _ => "未知"
    };
}

public sealed record ScanResult(
    string GamePath,
    string ModsPath,
    IReadOnlyList<ModPackage> Packages,
    IReadOnlyList<ValidationIssue> Issues);
