namespace GakumasModManager.Models;

public sealed record LogEntry(string Time, string Message, string Level = "Info");

