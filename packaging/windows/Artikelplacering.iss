#define MyAppName "Artikelplacering"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppExeName "Artikelplacering.exe"

[Setup]
AppId={{9FB26325-9A9D-40E8-B7A5-8D5B9261F474}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Dole Nordic AB
AppPublisherURL=https://github.com/EmirKadr/Artikelplacering
AppSupportURL=https://github.com/EmirKadr/Artikelplacering/issues
AppUpdatesURL=https://github.com/EmirKadr/Artikelplacering/releases
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#MyAppName}

[Languages]
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\release\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
