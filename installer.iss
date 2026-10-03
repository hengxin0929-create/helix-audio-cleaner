; HELIX音频清理工具 —— Inno Setup 安装包脚本
; 版本号由 GitHub Actions 通过 iscc /DMyAppVersion=x.y.z 传入
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "HELIX音频清理工具"
#define MyAppExe "HelixAudioCleaner.exe"

[Setup]
AppId={{CCE79097-C455-4E0C-B676-168BE6C6E710}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=HELIX
DefaultDirName={autopf}\HELIX音频清理工具
DefaultGroupName=HELIX音频清理工具
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=HELIX_Audio_Cleaner_Setup_v{#MyAppVersion}
SetupIconFile=horse.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加图标:"

[Dirs]
; 一机一码授权目录：安装时创建并授予普通用户写权限，激活时无需右键管理员运行
Name: "{commonappdata}\HELIX音频拼音"; Permissions: users-modify

[Files]
Source: "dist\HelixAudioCleaner\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
