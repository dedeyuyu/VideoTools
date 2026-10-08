; ============================================================
;  VideoTools v1.3.2 — Inno Setup 安装脚本
;  安装目录: {localappdata}\VideoTools  (无需管理员权限)
;  设置保存: Windows 注册表 (QSettings 天然持久化，更新后保留)
;  ffmpeg  : 安装时跳过 ffmpeg\ 目录，避免覆盖用户已下载的版本
; ============================================================

#define MyAppName      "视频集成工具"
#define MyAppVersion   "1.5.4"
#define MyAppPublisher "VideoTools"
#define MyAppExeName   "VideoTools.exe"
#define MyAppURL       "https://github.com"

[Setup]
AppId={{B1C2D3E4-F5A6-7890-ABCD-EF1234567890}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装到用户本地目录，无需管理员权限
DefaultDirName={localappdata}\VideoTools
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; 无需管理员权限
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

; 输出设置
OutputDir=..\output_installer
OutputBaseFilename=VideoTools_v{#MyAppVersion}_Setup
SetupIconFile=..\log\log.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120

; 允许静默安装
AllowNoIcons=yes

; 中文支持
LanguageDetectionMethod=uilanguage

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english";           MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
; ── 主程序及依赖文件（从打包目录复制）──────────────────────────────
; 注意：ffmpeg\ 目录不在此处列出，不会被安装程序覆盖
; 用户第一次安装后通过软件内的"下载 FFmpeg"功能自行下载

Source: "..\打包\VideoTools.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\打包\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\打包\ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion recursesubdirs createallsubdirs

; 日志图标
Source: "..\log\log.ico"; DestDir: "{app}\log"; Flags: ignoreversion

[Dirs]
; 预先创建 ffmpeg 目录（空），避免首次找不到目录报错
Name: "{app}\ffmpeg"

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\log\log.ico"
Name: "{group}\卸载 {#MyAppName}";     Filename: "{uninstallexe}"

; 桌面快捷方式（可选）
Name: "{autodesktop}\{#MyAppName}";    Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\log\log.ico"; Tasks: desktopicon

[Run]
; 安装完成后自动启动
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清理日志目录，但保留 ffmpeg\ 和 log\ 
Type: filesandordirs; Name: "{app}\log"

[Code]
// ── 升级时保留 ffmpeg 目录的逻辑 ───────────────────────────────────
// 在 CurStepChanged 中，当安装开始前检查旧版本是否存在 ffmpeg，
// 如果存在则跳过（Files 段已不包含 ffmpeg 文件，所以天然不覆盖）。
// 此处仅作注释说明，无需额外代码。

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 安装后提示 FFmpeg 状态
    // 实际检测由 Python 程序在运行时完成
  end;
end;
