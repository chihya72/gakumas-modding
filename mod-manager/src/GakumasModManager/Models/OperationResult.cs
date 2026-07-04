namespace GakumasModManager.Models;

public sealed record OperationResult(
    bool Ok,
    string Message,
    string? NewDirectoryPath = null,
    string Severity = "Info");

