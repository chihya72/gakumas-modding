; Inno Setup 脚本：把 3DMigoto 加载器安装到游戏根目录，并附带 Mod 管理器 + 桌面快捷方式。
; 编译前需设置环境变量：
;   GKMM_STAGE   已装配好的 staging 目录（加载器平铺 + GakumasModManager\ 子目录）
;   GKMM_VERSION 版本号（可选，默认 0.0.0-local）
; 编译：ISCC.exe mod-manager\installer\GakumasModManager.iss

#define StageDir GetEnv("GKMM_STAGE")
#define AppVersion GetEnv("GKMM_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0-local"
#endif
#if StageDir == ""
  #error 请先设置 GKMM_STAGE 环境变量指向 staging 目录
#endif
#define OutDir GetEnv("GKMM_OUT")
#if OutDir == ""
  #define OutDir "."
#endif

[Setup]
AppName=Gakumas 3DMigoto + Mod Manager
AppVersion={#AppVersion}
AppPublisher=chihya72
DefaultDirName={autopf}\gakumas
; 关闭浏览时自动追加末段目录名：否则选 xxx\gakumas 会变成 xxx\gakumas\gakumas。
AppendDefaultDirName=no
DisableProgramGroupPage=yes
DisableDirPage=no
DirExistsWarning=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename=GakumasModManager-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\src\GakumasModManager\app.ico
UninstallDisplayIcon={app}\GakumasModManager\GakumasModManager.exe

; 未引入中文语言包（非官方、CI 不一定带）：用默认英文向导 + 下方关键中文提示。
[Messages]
SelectDirDesc=请选择游戏根目录（gakumas.exe 所在的文件夹）。
SelectDirLabel3=加载器（d3d11.dll 等）会装到该目录，Mod 管理器装到其下的 GakumasModManager 子文件夹。

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式（Mod 管理器）"; GroupDescription: "附加任务："

[Files]
; 3DMigoto 加载器：平铺进游戏根目录（{app}）
Source: "{#StageDir}\d3d11.dll";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\nvapi64.dll";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\d3dcompiler_47.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\ShaderFixes\*";      DestDir: "{app}\ShaderFixes"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\键位说明.txt";       DestDir: "{app}"; Flags: ignoreversion
; d3dx.ini / Mods 内容属于用户配置：已存在则不覆盖，避免抹掉用户改动与已装 mod
Source: "{#StageDir}\d3dx.ini";           DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#StageDir}\Mods\*";             DestDir: "{app}\Mods"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs
; Mod 管理器：独立子目录
Source: "{#StageDir}\GakumasModManager\*"; DestDir: "{app}\GakumasModManager"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Gakumas Mod Manager"; Filename: "{app}\GakumasModManager\GakumasModManager.exe"; Tasks: desktopicon

[Run]
; shellexec：管理器 exe 是 requireAdministrator，用 ShellExecute 才会走 UAC 提权。
; 默认的 CreateProcess（且 postinstall 会降到非提权用户）拉起它会抛 740「需要提升」。
Filename: "{app}\GakumasModManager\GakumasModManager.exe"; Description: "启动 Mod 管理器"; Flags: nowait postinstall skipifsilent shellexec

[Code]
var
  ErrorCode: Integer;

function IsDotNet8DesktopInstalled(): Boolean;
var
  FindRec: TFindRec;
begin
  Result := False;
  if FindFirst(ExpandConstant('{commonpf}\dotnet\shared\Microsoft.WindowsDesktop.App\8.*'), FindRec) then
  try
    Result := True;
  finally
    FindClose(FindRec);
  end;
end;

// 目录页校验：所选目录必须是游戏根目录（含 gakumas.exe 和 gakumas_Data 文件夹），否则拦住。
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Dir := WizardDirValue;
    if not (FileExists(Dir + '\gakumas.exe') and DirExists(Dir + '\gakumas_Data')) then
    begin
      MsgBox('所选目录不是游戏根目录，请选择同时包含 gakumas.exe 与 gakumas_Data 文件夹的目录',
             mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not IsDotNet8DesktopInstalled()) then
  begin
    if MsgBox('未检测到 .NET 8 Desktop Runtime，Mod 管理器可能无法启动。' + #13#10 +
              '是否现在打开官方下载页？（下载 "Desktop Runtime" 的 Windows x64 版）',
              mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://dotnet.microsoft.com/download/dotnet/8.0',
                '', '', SW_SHOW, ewNoWait, ErrorCode);
  end;
end;
