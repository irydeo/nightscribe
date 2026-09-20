; NightScribe - Inno Setup script (Windows installer)
;
; Built by the "Windows preview" GitHub Actions workflow:
;   ISCC.exe /DAppVersion=<version> /DAppSuffix=-preview.<sha> installer\nightscribe.iss
; Input:  ..\dist\nightscribe\  (PyInstaller onedir output)
; Output: ..\dist\NightScribeSetup-<version><suffix>.exe
;         (suffix is empty for manual builds, "-preview.<sha>" in CI)
;
; Per-user install under %LOCALAPPDATA%\Programs: no admin rights needed.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#ifndef AppSuffix
  #define AppSuffix ""
#endif

[Setup]
; Stable identifier of the app (upgrades and uninstall hang from it; never change it)
AppId={{5b057088-ce5c-4bb3-b0e6-80aa959848f8}
AppName=NightScribe
AppVersion={#AppVersion}
AppPublisher=Francisco José Calvo Fernández (Irydeo Observatory, MPC Z41)
AppPublisherURL=https://www.irydeo.com
AppSupportURL=https://github.com/irydeo/nightscribe/issues
DefaultDirName={localappdata}\Programs\NightScribe
DefaultGroupName=NightScribe
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NightScribeSetup-{#AppVersion}{#AppSuffix}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=NightScribe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\nightscribe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NightScribe"; Filename: "{app}\nightscribe.exe"; Parameters: "gui"
Name: "{autodesktop}\NightScribe"; Filename: "{app}\nightscribe.exe"; Parameters: "gui"; Tasks: desktopicon

[Run]
Filename: "{app}\nightscribe.exe"; Parameters: "gui"; Description: "{cm:LaunchProgram,NightScribe}"; Flags: nowait postinstall skipifsilent
