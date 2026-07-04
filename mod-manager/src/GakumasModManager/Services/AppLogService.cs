using System.Diagnostics;
using System.IO;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface IAppLogService
{
    string LogDirectory { get; }

    string LogFilePath { get; }

    void Append(LogEntry entry);

    OperationResult OpenLogDirectory();
}

public sealed class AppLogService : IAppLogService
{
    public AppLogService()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        LogDirectory = Path.Combine(localAppData, "GakumasModManager", "logs");
        Directory.CreateDirectory(LogDirectory);
        LogFilePath = Path.Combine(LogDirectory, $"gakumas-mm-{DateTime.Now:yyyyMMdd}.log");
    }

    public string LogDirectory { get; }

    public string LogFilePath { get; }

    public void Append(LogEntry entry)
    {
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}\t{entry.Level}\t{entry.Message}";
        File.AppendAllLines(LogFilePath, [line]);
    }

    public OperationResult OpenLogDirectory()
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = LogDirectory,
                UseShellExecute = true,
            });
            return new OperationResult(true, $"已打开日志目录：{LogDirectory}");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new OperationResult(false, $"打开日志目录失败：{ex.Message}", Severity: "Error");
        }
    }
}

