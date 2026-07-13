using System.Text.Json;
using GakumasModManager.Models;
using GakumasModManager.Services;

var root = Path.Combine(Path.GetTempPath(), "gkms-mm-scanner-" + Guid.NewGuid().ToString("N"));
try
{
    var game = Path.Combine(root, "Game");
    var mods = Path.Combine(game, "Mods");
    Directory.CreateDirectory(mods);
    File.WriteAllText(
        Path.Combine(game, "d3dx.ini"),
        """
        [Hunting]
        hunting=1
        reload_fixes = no_modifiers VK_F10
        reload_config = no_modifiers VK_F10
        analyse_frame = no_modifiers VK_F8
        """);

    var gakumasMi = Path.Combine(mods, "Saki Stage Costume - Orange");
    Directory.CreateDirectory(gakumasMi);
    File.WriteAllText(Path.Combine(gakumasMi, "mod.ini"), "; mod ini");
    File.WriteAllText(Path.Combine(gakumasMi, "cover.png"), "");
    Directory.CreateDirectory(Path.Combine(gakumasMi, "Textures"));
    File.WriteAllBytes(Path.Combine(gakumasMi, "Textures", "Body.BaseColor.dds"), [(byte)'D', (byte)'D', (byte)'S', (byte)' ']);
    File.WriteAllText(
        Path.Combine(gakumasMi, "manifest.json"),
        JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            id = "starbobis.saki.orange",
            name = "Saki Stage Costume - Orange",
            version = "1.0.1",
            author = "StarBobis",
            targets = new[] { "body.weightedMesh" },
            components = new[] { "hair", "hairprop" },
            conflicts = new[] { "hski.cstm-0000.body.mesh" },
            cover = "cover.png",
            materials = new
            {
                body_baseColor = new
                {
                    slot = "ps-t0",
                    hash = "base",
                    file = "Textures/Body.BaseColor.dds",
                },
            },
        }));

    var duplicate = Path.Combine(mods, "Duplicate Costume");
    Directory.CreateDirectory(duplicate);
    File.WriteAllText(Path.Combine(duplicate, "mod.ini"), "; mod ini");
    File.WriteAllText(
        Path.Combine(duplicate, "manifest.json"),
        JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            id = "duplicate.costume",
            name = "Duplicate Costume",
            version = "1.0.0",
            author = "Tester",
            targets = new[] { "body.weightedMesh" },
            conflicts = new[] { "hski.cstm-0000.body.mesh" },
            materials = new
            {
                body_baseColor = new
                {
                    slot = "ps-t0",
                    hash = "base",
                    file = "Textures/Missing.dds",
                },
            },
        }));

    var generic = Path.Combine(mods, "Generic Shader Fix");
    Directory.CreateDirectory(generic);
    File.WriteAllText(Path.Combine(generic, "fix.ini"), "; generic");

    var disabled = Path.Combine(mods, "DISABLED Old Hair");
    Directory.CreateDirectory(disabled);
    File.WriteAllText(Path.Combine(disabled, "hair.ini"), "; disabled");

    var broken = Path.Combine(mods, "Broken GakumasMI");
    Directory.CreateDirectory(broken);
    File.WriteAllText(Path.Combine(broken, "manifest.json"), "{ broken json");

    // 只含 Windows desktop.ini 的目录不是 mod（游戏也 exclude_recursive = desktop.ini）
    var desktopOnly = Path.Combine(mods, "Not A Mod");
    Directory.CreateDirectory(desktopOnly);
    File.WriteAllText(Path.Combine(desktopOnly, "desktop.ini"), "[.ShellClassInfo]");

    var scanner = new ScannerService();
    var result = scanner.ScanGameDirectory(game);

    Assert(result.Packages.Count == 5, "expected five packages");
    Assert(!result.Packages.Any(package => package.Name == "Not A Mod"), "expected desktop.ini-only directory to be ignored");
    Assert(result.Packages.Any(package => package.Name == "Saki Stage Costume - Orange"
        && package.Type == PackageType.GakumasMi
        && package.Status == PackageStatus.Conflict
        && package.IsEnabled
        && package.ComponentsLabel == "发型 + 发饰"
        && package.TargetDisplay == "body.weightedMesh (发型 + 发饰)"), "expected enabled GakumasMI conflict package");
    Assert(result.Packages.Any(package => package.Name == "Duplicate Costume"
        && package.Status == PackageStatus.Broken
        && package.MissingFileCount == 1), "expected duplicate package with missing file to be broken");
    Assert(result.Packages.Any(package => package.Name == "Generic Shader Fix"
        && package.Type == PackageType.Generic3Dmigoto), "expected generic package");
    Assert(result.Packages.Any(package => package.Name == "Old Hair"
        && package.Status == PackageStatus.Disabled
        && !package.IsEnabled), "expected disabled prefix package");
    Assert(result.Packages.Any(package => package.Name == "Broken GakumasMI"
        && package.Status == PackageStatus.Broken), "expected broken manifest package");

    Assert(result.Packages.Single(package => package.Name == "Saki Stage Costume - Orange").CharacterName == "花海咲季",
        "expected hski conflict key to map to 花海咲季");
    Assert(result.Packages.Single(package => package.Name == "Generic Shader Fix").CharacterName == CharacterCatalog.Other,
        "expected package with no character code to fall into 其他");
    Assert(CharacterCatalog.OrderIndex("花海咲季") < CharacterCatalog.OrderIndex("月村手毬"),
        "expected 花海咲季 to sort before 月村手毬");
    Assert(CharacterCatalog.OrderIndex(CharacterCatalog.Other) == CharacterCatalog.OrderedNames.Count - 1,
        "expected 其他 to sort last");

    var actions = new PackageActionsService();
    var genericPackage = result.Packages.Single(package => package.Name == "Generic Shader Fix");
    var disableResult = actions.SetEnabled(genericPackage, enabled: false);
    Assert(disableResult.Ok, "expected disable to succeed");
    Assert(Directory.Exists(Path.Combine(mods, "DISABLED Generic Shader Fix")), "expected disabled directory");
    Assert(!Directory.Exists(generic), "expected original generic directory to be moved");

    var afterDisable = scanner.ScanGameDirectory(game);
    var disabledGeneric = afterDisable.Packages.Single(package => package.Name == "Generic Shader Fix");
    Assert(!disabledGeneric.IsEnabled && disabledGeneric.Status == PackageStatus.Disabled, "expected generic package disabled after rename");

    var enableResult = actions.SetEnabled(disabledGeneric, enabled: true);
    Assert(enableResult.Ok, "expected enable to succeed");
    Assert(Directory.Exists(generic), "expected generic directory restored");
    Assert(!Directory.Exists(Path.Combine(mods, "DISABLED Generic Shader Fix")), "expected disabled directory gone");

    Directory.CreateDirectory(Path.Combine(mods, "DISABLED Generic Shader Fix"));
    var collisionResult = actions.SetEnabled(genericPackage with { DirectoryPath = generic, IsEnabled = true }, enabled: false);
    Assert(!collisionResult.Ok, "expected disable collision to fail");
    Assert(Directory.Exists(generic), "expected source directory preserved on collision");

    var reloadFix = new D3dxReloadService();
    Assert(reloadFix.EnsureForegroundReloadEnabled(game).Ok, "expected check_foreground_window ensure to succeed");
    var d3dxAfter = File.ReadAllText(Path.Combine(game, "d3dx.ini"));
    Assert(d3dxAfter.Contains("check_foreground_window = 0") || d3dxAfter.Contains("check_foreground_window=0"),
        "expected check_foreground_window set to 0");
    Assert(d3dxAfter.Contains("reload_fixes"), "expected unrelated d3dx keys preserved by ensure");
    Assert(reloadFix.EnsureForegroundReloadEnabled(game).Ok, "expected idempotent ensure on second call");

    var installer = new PackageInstallService();
    var installMods = Path.Combine(root, "InstallMods");
    Directory.CreateDirectory(installMods);

    var srcFolder = Path.Combine(root, "src", "Cool Hair Mod");
    Directory.CreateDirectory(srcFolder);
    File.WriteAllText(Path.Combine(srcFolder, "mod.ini"), "; hair");
    Assert(installer.Install(installMods, [srcFolder]).Ok, "expected folder install to succeed");
    Assert(File.Exists(Path.Combine(installMods, "Cool Hair Mod", "mod.ini")), "expected folder mod copied into Mods");
    Assert(!installer.Install(installMods, [srcFolder]).Ok, "expected collision install to fail (no overwrite)");

    var zipTopDir = Path.Combine(root, "zipsrc");
    Directory.CreateDirectory(Path.Combine(zipTopDir, "Zipped Costume"));
    File.WriteAllText(Path.Combine(zipTopDir, "Zipped Costume", "mod.ini"), "; z");
    var zipTop = Path.Combine(root, "Zipped Costume.zip");
    System.IO.Compression.ZipFile.CreateFromDirectory(zipTopDir, zipTop);
    Assert(installer.Install(installMods, [zipTop]).Ok, "expected zip-with-top-folder install to succeed");
    Assert(File.Exists(Path.Combine(installMods, "Zipped Costume", "mod.ini")), "expected zip installed under its top-folder name");

    var flatDir = Path.Combine(root, "flatzip");
    Directory.CreateDirectory(flatDir);
    File.WriteAllText(Path.Combine(flatDir, "fix.ini"), "; flat");
    var zipFlat = Path.Combine(root, "Flat Fix.zip");
    System.IO.Compression.ZipFile.CreateFromDirectory(flatDir, zipFlat);
    Assert(installer.Install(installMods, [zipFlat]).Ok, "expected flat zip install to succeed");
    Assert(File.Exists(Path.Combine(installMods, "Flat Fix", "fix.ini")), "expected flat zip installed under zip name");

    File.WriteAllText(Path.Combine(root, "readme.txt"), "not a mod");
    Assert(!installer.Install(installMods, [Path.Combine(root, "readme.txt")]).Ok, "expected non-mod drop to be rejected");
    Assert(!installer.Install("", [srcFolder]).Ok, "expected install with no Mods path to fail");

    Console.WriteLine("GAKUMAS_MM_SCANNER_SMOKE_OK");
}
finally
{
    if (Directory.Exists(root))
    {
        Directory.Delete(root, recursive: true);
    }
}

static void Assert(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}
