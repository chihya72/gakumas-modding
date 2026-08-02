; Inno Setup 脚本：把 3DMigoto 抓帧环境安装到游戏根目录。
;
; 0.7.0 起本安装包**只装加载器**，不再附带 Mod 管理器：换模已转 AB bundle 路线，
; 由 gakumas-mod-runtime 的 xinput1_3.dll 加载，游戏内管理 UI 由 xinput9_1_0.dll 提供。
; 本加载器留下的唯一职责是给 mod 作者抓帧（F8 Frame Analysis）做配置档。
;
; 编译前需设置环境变量：
;   GKMS_STAGE   已装配好的 staging 目录（加载器平铺）
;   GKMS_VERSION 版本号（可选，默认 0.0.0-local）
;   GKMS_OUT     输出目录（可选，默认当前目录）
; 编译：ISCC.exe 3dmigoto-gkms\installer\Gakumas3DMigotoCapture.iss

#define StageDir GetEnv("GKMS_STAGE")
#define AppVersion GetEnv("GKMS_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0-local"
#endif
#if StageDir == ""
  #error 请先设置 GKMS_STAGE 环境变量指向 staging 目录
#endif
#define OutDir GetEnv("GKMS_OUT")
#if OutDir == ""
  #define OutDir "."
#endif

[Setup]
AppName=Gakumas 3DMigoto 抓帧环境
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
OutputBaseFilename=Gakumas3DMigotoCapture-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; 未引入中文语言包（非官方、CI 不一定带）：用默认英文向导 + 下方关键中文提示。
[Messages]
SelectDirDesc=请选择游戏根目录（gakumas.exe 所在的文件夹）。
SelectDirLabel3=加载器（d3d11.dll 等）会平铺装到该目录。本包只装抓帧用的加载器，不含 Mod 管理器。

[Files]
; 3DMigoto 加载器：平铺进游戏根目录（{app}）
Source: "{#StageDir}\d3d11.dll";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\nvapi64.dll";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\d3dcompiler_47.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\ShaderFixes\*";      DestDir: "{app}\ShaderFixes"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\键位说明.txt";       DestDir: "{app}"; Flags: ignoreversion
; d3dx.ini 属于用户配置：已存在则不覆盖，避免抹掉用户改动
Source: "{#StageDir}\d3dx.ini";           DestDir: "{app}"; Flags: onlyifdoesntexist

[Code]
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
