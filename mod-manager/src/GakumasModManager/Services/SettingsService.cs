using System.IO;
using System.Text.Json;

namespace GakumasModManager.Services;

public interface ISettingsService
{
    string? LoadGamePath();

    void SaveGamePath(string gamePath);
}

public sealed class SettingsService : ISettingsService
{
    private readonly string _settingsPath;

    public SettingsService()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var directory = Path.Combine(localAppData, "GakumasModManager");
        Directory.CreateDirectory(directory);
        _settingsPath = Path.Combine(directory, "settings.json");
    }

    public string? LoadGamePath()
    {
        try
        {
            if (!File.Exists(_settingsPath))
            {
                return null;
            }

            using var stream = File.OpenRead(_settingsPath);
            using var document = JsonDocument.Parse(stream);
            return document.RootElement.TryGetProperty("gamePath", out var value)
                && value.ValueKind == JsonValueKind.String
                ? value.GetString()
                : null;
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    public void SaveGamePath(string gamePath)
    {
        try
        {
            File.WriteAllText(_settingsPath, JsonSerializer.Serialize(new { gamePath }));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // ponytail: best-effort persistence — a failed write must not crash the app.
        }
    }
}
