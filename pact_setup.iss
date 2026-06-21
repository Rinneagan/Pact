; Inno Setup Script for Pact PDF Application
; Generates a clean, user-level installer (.exe) for Windows

#define MyAppName "Pact"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Namida"
#define MyAppExeName "Pact.exe"

[Setup]
AppId={{5E5868E9-23CE-45FC-93C9-1065114D3C5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DisableDirPage=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=c:\Users\AvaricE\Documents\PDFfetch\dist
OutputBaseFilename=PactSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "c:\Users\AvaricE\Documents\PDFfetch\dist\Pact.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
