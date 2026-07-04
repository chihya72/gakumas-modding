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

    var scanner = new ScannerService();
    var result = scanner.ScanGameDirectory(game);

    Assert(result.Packages.Count == 5, "expected five packages");
    Assert(result.Packages.Any(package => package.Name == "Saki Stage Costume - Orange"
        && package.Type == PackageType.GakumasMi
        && package.Status == PackageStatus.Conflict
        && package.IsEnabled), "expected enabled GakumasMI conflict package");
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

    var d3dx = new D3dxConfigService();
    var settings = d3dx.LoadSettings(game);
    Assert(settings.HuntingMode == "1", "expected hunting mode read");
    Assert(settings.ReloadKey == "F10", "expected reload key read");
    Assert(settings.FrameAnalysisKey == "F8", "expected frame analysis key read");

    var backup1 = d3dx.BackupD3dxIni(game, keepCount: 2);
    var backup2 = d3dx.BackupD3dxIni(game, keepCount: 2);
    var backup3 = d3dx.BackupD3dxIni(game, keepCount: 2);
    Assert(backup1.Ok && backup2.Ok && backup3.Ok, "expected d3dx backups to succeed");
    Assert(Directory.EnumerateFiles(game, "d3dx.ini.bak.*").Count() == 2, "expected backup retention cleanup");

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
