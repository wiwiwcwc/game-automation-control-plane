; Inno Setup installer for Hsiesta (休汐).
; The existing PyInstaller onedir directory is the only application payload.
; build_installer.ps1 supplies AppVersion from pyproject.toml.

#ifndef AppVersion
#error AppVersion must be supplied by build_installer.ps1.
#endif

#define HsiestaAppName "休汐 Hsiesta"
#define HsiestaExeName "GameAutomationControlPlane.exe"

[Setup]
AppId={{57c41fc3-082e-4bf2-98ed-c6ac900d7211}
AppName={#HsiestaAppName}
AppVersion={#AppVersion}
AppVerName={#HsiestaAppName} {#AppVersion}
AppPublisher={#HsiestaAppName}
AppPublisherURL=https://github.com/wiwiwcwc/hsiesta
AppSupportURL=https://github.com/wiwiwcwc/hsiesta/issues
DefaultDirName={localappdata}\Programs\Hsiesta
DefaultGroupName={#HsiestaAppName}
; Keep the group page available so silent deployment can explicitly override
; the default with /GROUP. Interactive installs still start with this default.
DisableProgramGroupPage=no
PrivilegesRequired=lowest
CloseApplications=yes
CloseApplicationsFilter={#HsiestaExeName}
RestartApplications=no
OutputDir=..\dist
OutputBaseFilename=Hsiesta-{#AppVersion}-Setup
SetupIconFile=..\src\game_control_plane\assets\app_icon.ico
UninstallDisplayIcon={app}\{#HsiestaExeName}
VersionInfoDescription={#HsiestaAppName} Windows installer
VersionInfoProductName={#HsiestaAppName}
VersionInfoVersion={#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; This exact onedir output is built and checked by packaging/build_windows.ps1.
; No third-party automation tool, runtime, model, or game asset is copied here.
Source: "..\dist\GameAutomationControlPlane\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#HsiestaAppName}"; Filename: "{app}\{#HsiestaExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#HsiestaAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#HsiestaAppName}"; Filename: "{app}\{#HsiestaExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#HsiestaExeName}"; Description: "{cm:LaunchProgram,{#HsiestaAppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete] section: user data lives outside {app} at
; %LOCALAPPDATA%\GameAutomationControlPlane and must survive uninstall.
