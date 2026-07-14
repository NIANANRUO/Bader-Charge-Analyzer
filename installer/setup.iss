; Inno Setup script for Bader Charge Analyzer.
; Build: ISCC.exe installer/setup.iss
; Output: dist/BaderChargeAnalyzer_Setup_v<version>.exe

#define AppName       "Bader Charge Analyzer"
#define AppVersion    "0.2.0"
#define AppPublisher  "NIANANRUO"
#define AppURL        "https://github.com/NIANANRUO/Bader-Charge-Analyzer"
#define AppExeName    "BaderChargeAnalyzer.exe"
#define SourceDir     "..\dist\BaderChargeAnalyzer"
#define AppIcon       "BaderChargeAnalyzer.ico"

[Setup]
AppId={{7D37C8E8-60F7-4E37-8E6E-95D99BC4DFA2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=BaderChargeAnalyzer_Setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile={#AppIcon}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
