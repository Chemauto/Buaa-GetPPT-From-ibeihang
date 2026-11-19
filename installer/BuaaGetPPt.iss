; BuaaGetPPt 安装包脚本（Inno Setup 6/7）
; 编译：ISCC.exe installer\BuaaGetPPt.iss  （需先完成 PyInstaller 构建 dist\BuaaGetPPt.exe）

#define MyAppName "BuaaGetPPt"
#define MyAppVersion "1.2.0"
#define MyAppExeName "BuaaGetPPt.exe"

[Setup]
AppId={{7A4C21E8-5D93-4B6F-8A10-C2E5F8D3B714}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
AppPublisherURL=https://github.com/Chemauto/Buaa-GetPPT-From-ibeihang
DefaultDirName={autopf}\{#MyAppName}
PrivilegesRequired=lowest
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=BuaaGetPPt-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
CloseApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\BuaaGetPPt.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
