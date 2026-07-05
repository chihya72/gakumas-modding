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

    public string CharacterName => CharacterCatalog.ResolveName(this);

    public int CharacterOrderIndex => CharacterCatalog.OrderIndex(CharacterName);

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

// 角色代号 → 中文名，顺序即 UI 分类/排序顺序；"其他" 永远排最后
public static class CharacterCatalog
{
    public const string Other = "其他";

    private static readonly (string Code, string Name)[] Ordered =
    [
        ("hski", "花海咲季"),
        ("ttmr", "月村手毬"),
        ("fktn", "藤田琴音"),
        ("amao", "有村麻央"),
        ("kllj", "葛城莉莉娅"),
        ("kcna", "仓本千奈"),
        ("ssmk", "紫云清夏"),
        ("shro", "筱泽广"),
        ("hrnm", "姬崎莉波"),
        ("hume", "花海佑芽"),
        ("hmsz", "秦谷美铃"),
        ("jsna", "十王星南"),
        ("atbm", "雨夜燕"),
        ("nasr", "根绪亚纱里"),
    ];

    private static readonly Dictionary<string, string> ByCode =
        Ordered.ToDictionary(x => x.Code, x => x.Name);

    private static readonly List<string> OrderIndexer =
        Ordered.Select(x => x.Name).Append(Other).ToList();

    public static IReadOnlyList<string> OrderedNames => OrderIndexer;

    public static string ResolveName(ModPackage package)
    {
        var code = ExtractCode(package);
        return code is not null && ByCode.TryGetValue(code, out var name) ? name : Other;
    }

    public static int OrderIndex(string characterName)
    {
        var index = OrderIndexer.IndexOf(characterName);
        return index < 0 ? int.MaxValue : index;
    }

    // 优先从 conflicts 键（"hmsz.cstm-0119.body.mesh"）取前缀，回退到 target（"mdl_chr_hmsz-cstm-0119_body"）
    private static string? ExtractCode(ModPackage package)
    {
        var key = package.Conflicts.FirstOrDefault();
        if (!string.IsNullOrEmpty(key))
        {
            return key.Split('.')[0].ToLowerInvariant();
        }

        var target = package.Target;
        if (!string.IsNullOrEmpty(target))
        {
            var chr = target.Split('_').FirstOrDefault(part => part.Contains('-'));
            if (chr is not null)
            {
                return chr.Split('-')[0].ToLowerInvariant();
            }
        }

        return null;
    }
}

public sealed record ScanResult(
    string GamePath,
    string ModsPath,
    IReadOnlyList<ModPackage> Packages,
    IReadOnlyList<ValidationIssue> Issues);
