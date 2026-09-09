; SONIC AI — Inno Setup Installer Script
; Build: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" sonic_setup.iss

#define MyAppName "SONIC AI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SONIC AI"
#define MyAppExeName "SONIC-AI.exe"
#define MyAppUpdaterExe "SONIC-Updater.exe"
#define MyAppAssocName "SONIC AI File"
#define MyAppAssocExt ".sonic"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
AppId={{B1E2F3A4-C5D6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=SONIC-AI-Setup-{#MyAppVersion}
SetupIconFile=config\sonic.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableWelcomePage=no
LicenseFile=LICENSE.txt
WizardImageFile=
WizardSmallImageFile=
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "Create Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyAppUpdaterExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "config\sonic.ico"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "config\sonic.png"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "auth\firebase_config.json"; DestDir: "{app}\auth"; Flags: ignoreversion
Source: "core\prompt.txt"; DestDir: "{app}\core"; Flags: ignoreversion
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}\redist"; Flags: ignoreversion deleteafterinstall

[Dirs]
Name: "{app}\config"
Name: "{app}\auth"
Name: "{app}\core"
Name: "{localappdata}\SONIC AI"
Name: "{localappdata}\SONIC AI\memory"
Name: "{localappdata}\SONIC AI\Updater"
Name: "{localappdata}\SONIC AI\Updater\backup"
Name: "{localappdata}\SONIC AI\Updater\downloads"
Name: "{localappdata}\SONIC AI\updates"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Install VC++ Runtime silently if not already installed
Filename: "{tmp}\redist\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Visual C++ Runtime..."; Flags: waituntilterminated skipifnotsilent
Filename: "{tmp}\redist\vc_redist.x64.exe"; Parameters: "/install /passive /norestart"; StatusMsg: "Installing Visual C++ Runtime..."; Flags: waituntilterminated skipifsilent
; Launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; File association
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocKey}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{localappdata}\SONIC AI\Updater"
Type: filesandordirs; Name: "{localappdata}\SONIC AI\updates"

[Code]
// Auto-delete old version before installing new one
procedure CurStepChanged(CurStep: TSetupStep);
var
  OldExe: String;
begin
  if CurStep = ssInstall then
  begin
    // Delete old EXE if it exists
    OldExe := ExpandConstant('{app}\{#MyAppExeName}');
    if FileExists(OldExe) then
    begin
      DelTree(OldExe, False, True, False);
    end;
    
    // Delete old .old files from previous updates
    DelTree(ExpandConstant('{app}\*.exe.old'), False, True, False);
  end;
  
  if CurStep = ssPostInstall then
  begin
    CreateDir(ExpandConstant('{localappdata}\SONIC AI'));
    CreateDir(ExpandConstant('{localappdata}\SONIC AI\memory'));
    CreateDir(ExpandConstant('{localappdata}\SONIC AI\Updater'));
    CreateDir(ExpandConstant('{localappdata}\SONIC AI\Updater\backup'));
    CreateDir(ExpandConstant('{localappdata}\SONIC AI\Updater\downloads'));
    CreateDir(ExpandConstant('{localappdata}\SONIC AI\updates'));
  end;
end;
