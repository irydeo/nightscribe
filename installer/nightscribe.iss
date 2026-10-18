; NightScribe - Inno Setup script (Windows installer)
;
; Built by the GitHub Actions workflows (preview.yml for the rolling
; pre-release, release.yml for a tagged stable release):
;   ISCC.exe /DAppVersion=<version> /DAppSuffix=-preview.<sha> installer\nightscribe.iss
; Input:  ..\dist\nightscribe\  (PyInstaller onedir output)
; Output: ..\dist\NightScribeSetup-<version><suffix>.exe
;         (the suffix is "-preview.<sha>" in the preview workflow, and empty in
;          the release workflow and in manual builds)
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
SetupIconFile=..\nightscribe\assets\appicon.ico
DefaultDirName={localappdata}\Programs\NightScribe
DefaultGroupName=NightScribe
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NightScribeSetup-{#AppVersion}{#AppSuffix}
; Code signing, OPTIONAL and inert by default (ADR-087). The workflow passes
; /DSignToolName=<name> and /S<name>=<command> when a certificate is
; configured, and passes nothing when there is none, so this recipe builds
; unsigned exactly as before.
;
; It is here, wired and unused, because of Windows Smart App Control: it
; BLOCKS unsigned installers outright, with no "run anyway" (that is
; SmartScreen, a different gate, and it does have one). Nothing else fixes it:
; SAC evaluates at run time, so the Mark of the Internet, unzipping or a
; self-signed certificate change nothing, and the signature has to come from a
; certificate authority Windows trusts.
#ifdef SignToolName
SignTool={#SignToolName}
; The uninstaller is compiled INTO the setup, so this is the only moment it can
; be signed. Without it, uninstalling is unsigned code too, and SAC can block
; the uninstall as well.
SignedUninstaller=yes
#endif
LicenseFile=..\LICENSE
; Find_Orb travels inside the app folder (dist\nightscribe\findorb). This
; note tells the observer what it is, its licence and where its source is:
; GPLv2 with a no-commercial clause, shipped as a separate program by this
; non-commercial GPLv3 app (ADR-079).
InfoBeforeFile=..\installer\findorb-notice.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; If NightScribe is somehow still running when Setup copies the files, close
; it (and do not relaunch it: the [Run] entry below already offers that). The
; [Code] below closes it too, before the uninstall, which is where it matters.
CloseApplications=yes
RestartApplications=no
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

[Code]
// Inno Setup, with the same AppId, does NOT uninstall the previous version: it
// installs over it and APPENDS to the same uninstall log (see "Appending to
// Existing Uninstall Logs" in its help). Files the new build no longer ships,
// and a PyInstaller onedir tree changes a lot between versions (renamed DLLs,
// packages that come and go), would stay in the app folder until the final
// uninstall, so the install would not be clean. We run the previous
// uninstaller ourselves, silently, before copying. Settings and data live in
// the platformdirs folders (%APPDATA%/%LOCALAPPDATA%), never in the app
// folder, so they survive untouched.

function PreviousUninstallString(): String;
var
  Key, Cmd: String;
begin
  Result := '';
  { The uninstall registry key is the AppId plus "_is1". Our AppId is written
    with a doubled opening brace (an escaped literal), so ExpandConstant turns
    it back into a single one. The install is per-user, so the key lives under
    HKCU; HKLM is checked as a fallback. }
  Key := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
  if not RegQueryStringValue(HKCU, Key, 'UninstallString', Cmd) then
    RegQueryStringValue(HKLM, Key, 'UninstallString', Cmd);
  Result := Cmd;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Cmd: String;
  ResultCode: Integer;
begin
  Result := '';
  Cmd := PreviousUninstallString();
  if Cmd = '' then
    Exit;                          { nothing installed: this is a first install }
  { The uninstaller cannot delete nightscribe.exe while the app is running, and
    a locked file would be left behind (and the copy below would fail). }
  Exec('taskkill.exe', '/F /IM nightscribe.exe', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  Cmd := RemoveQuotes(Cmd);        { the path may carry spaces }
  if (not Exec(Cmd, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE,
               ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    Result := 'The previous version of NightScribe could not be uninstalled. ' +
              'Uninstall it from Settings > Apps, then run this installer again.';
end;
