namespace GakumasModManager.Models;

public sealed record D3dxSettings(
    string D3dxIniPath,
    string HuntingMode,
    string FrameAnalysisKey,
    string ReloadKey,
    int BackupKeepCount);

