#ifndef VERSION
#define VERSION "1.0.0"
#endif
#ifndef BUILD_TIMESTAMP
#define BUILD_TIMESTAMP "dev"
#endif

[Setup]
AppName=古籍重製
AppVersion={#VERSION}
AppVerName=古籍重製 {#VERSION}
; ⚠️ 安装目录：**用户级程序目录**，不装到 C:\Software 下面。
;   {localappdata}\Programs\guji
;   = C:\Users\<你>\AppData\Local\Programs\guji
; 为什么是这里：PrivilegesRequired=lowest（纯用户级安装、免 UAC）下，
; Windows 的惯例就是装到 Programs（Chrome / VS Code 的用户级安装同款）；
; 不要往系统盘根的公共 C:\Software 里塞，那是"谁装的都说不清"的位置。
;
; ⚠️ 安装目录一旦改动，PATH 注册必须跟着动 —— [Code] 里一律用 {app}
; （= 用户实际选定的安装目录）拼路径，**不写死任何绝对路径**。
DefaultDirName={localappdata}\Programs\guji
; ⚠️ 必须 no：旧版默认目录是 {localappdata}\Software\guji，而 Inno 默认
; (UsePreviousAppDir=yes) 会记住上次的目录 —— 老用户升级时会被"粘"在
; 旧目录里，永远迁不到新位置。代价是用户自定义的安装目录不再被记住。
UsePreviousAppDir=no
DefaultGroupName=古籍重製
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=guji_setup_{#VERSION}_{#BUILD_TIMESTAMP}
Compression=lzma2
SolidCompression=yes
; 程序显示图标（EXE 内嵌的 .ico 由 PyInstaller icon= 写入）
#ifdef ICON_FILE
SetupIconFile={#ICON_FILE}
#endif
UninstallDisplayName=古籍重製 {#VERSION}
UninstallDisplayIcon={app}\guji-desktop.exe

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\guji\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
; 开始菜单：GUI 主程序 + 卸载入口
Name: "{autoprograms}\古籍重製"; Filename: "{app}\guji-desktop.exe"; IconFilename: "{app}\guji-desktop.exe"
Name: "{autoprograms}\卸载 古籍重製"; Filename: "{uninstallexe}"
; 桌面快捷方式（可选安装，默认不勾选）
Name: "{autodesktop}\古籍重製"; Filename: "{app}\guji-desktop.exe"; IconFilename: "{app}\guji-desktop.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[InstallDelete]
; 程序改名遗留：旧版本快捷方式名为「guji古籍工具」，升级后不会自动消失，
; 安装时显式清掉，避免开始菜单出现新旧两套快捷方式。
Type: files; Name: "{autoprograms}\guji古籍工具.lnk"
Type: files; Name: "{autoprograms}\卸载 guji古籍工具.lnk"
Type: files; Name: "{autodesktop}\guji古籍工具.lnk"
; GUI 可执行文件改名过：guji-gui.exe → guji-desktop.exe。
; 它已经不在 [Files] 的载荷里，Inno 不会替你删，于是旧版升级后
; {app} 里会永久留着一个旧 EXE，旧快捷方式还照样能启动它（跑的是老版本）。
Type: files; Name: "{app}\guji-gui.exe"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  UserEnvironmentKey = 'Environment';
  BroadcastWindow = $FFFF;
  EnvironmentChangedMessage = $001A;
  AbortIfHung = $0002;

function SendMessageTimeout(hWnd, Msg, wParam: Integer; lParam: string; fuFlags, uTimeout: Integer; var lpdwResult: Integer): Integer;
  external 'SendMessageTimeoutW@user32.dll stdcall';

function PathContains(const PathValue, Entry: string): Boolean;
var
  Remaining, CurrentEntry: string;
  SeparatorPosition: Integer;
begin
  Result := False;
  Remaining := PathValue;
  while Remaining <> '' do
  begin
    SeparatorPosition := Pos(';', Remaining);
    if SeparatorPosition = 0 then
    begin
      CurrentEntry := Remaining;
      Remaining := '';
    end
    else
    begin
      CurrentEntry := Copy(Remaining, 1, SeparatorPosition - 1);
      Delete(Remaining, 1, SeparatorPosition);
    end;
    if CompareText(Trim(CurrentEntry), Entry) = 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function RemovePathEntry(const PathValue, Entry: string): string;
var
  Remaining, CurrentEntry: string;
  SeparatorPosition: Integer;
begin
  Result := '';
  Remaining := PathValue;
  while Remaining <> '' do
  begin
    SeparatorPosition := Pos(';', Remaining);
    if SeparatorPosition = 0 then
    begin
      CurrentEntry := Remaining;
      Remaining := '';
    end
    else
    begin
      CurrentEntry := Copy(Remaining, 1, SeparatorPosition - 1);
      Delete(Remaining, 1, SeparatorPosition);
    end;
    if (Trim(CurrentEntry) <> '') and (CompareText(Trim(CurrentEntry), Entry) <> 0) then
    begin
      if Result <> '' then
        Result := Result + ';';
      Result := Result + Trim(CurrentEntry);
    end;
  end;
end;

procedure NotifyEnvironmentChanged;
var
  SendResult: Integer;
begin
  SendMessageTimeout(BroadcastWindow, EnvironmentChangedMessage, 0,
    'Environment', AbortIfHung, 5000, SendResult);
end;

// ---- 历史安装目录的清理 ----------------------------------------------
// 下面几个目录都不该再出现在用户 PATH 里（都是曾经的 {app}，PATH 就是
// 按它注册的；目录搬了，PATH 里的旧条目就成了死路径）：
//
//   0) {localappdata}\Software\guji —— 上一版默认目录。带
//      UsePreviousAppDir=no 升级时 Inno 会先跑旧卸载程序，通常已把这条
//      清掉；这里再兜一次底。
//   1) {sd}\Software\guji —— **最早的默认目录**，即 C:\Software\guji。
//      当年 build.py 还会把产物「部署」复制到那里（安装包之外的野路子），
//      那个行为已删除（构建只出安装包），但 PATH 里可能还留着旧条目。
//
// 注意顺序：先清历史、再加 {app}。若用户恰好把 {app} 选在历史目录上，
// 这样也能保证最终 PATH 里留下的是它。
//
// ⚠️ 本段用 // 注释而不是 { }：{ } 注释里只要出现 {app} 就会被提前闭合。
function LegacyDir(Index: Integer): string;
begin
  if Index = 0 then
    Result := ExpandConstant('{localappdata}\Software\guji')
  else if Index = 1 then
    Result := ExpandConstant('{sd}\Software\guji')
  else
    Result := '';
end;

procedure RemoveLegacyPathEntries;
var
  Index: Integer;
  Dir, PathValue, UpdatedPathValue: string;
begin
  if not RegQueryStringValue(HKCU, UserEnvironmentKey, 'Path', PathValue) then
    Exit;
  UpdatedPathValue := PathValue;
  for Index := 0 to 1 do
  begin
    Dir := LegacyDir(Index);
    if Dir <> '' then
      UpdatedPathValue := RemovePathEntry(UpdatedPathValue, Dir);
  end;
  if UpdatedPathValue <> PathValue then
  begin
    RegWriteExpandStringValue(HKCU, UserEnvironmentKey, 'Path', UpdatedPathValue);
    NotifyEnvironmentChanged;
  end;
end;

// 把「实际安装目录」（{app}）加进用户 PATH：命令行的 guji.exe 就在 {app}
// 里，所以 PATH 条目必须跟着安装目录走，不能写死某个绝对路径。
procedure AddToUserPath;
var
  PathValue: string;
begin
  if not RegQueryStringValue(HKCU, UserEnvironmentKey, 'Path', PathValue) then
    PathValue := '';
  if not PathContains(PathValue, ExpandConstant('{app}')) then
  begin
    if PathValue <> '' then
      PathValue := PathValue + ';';
    RegWriteExpandStringValue(HKCU, UserEnvironmentKey, 'Path',
      PathValue + ExpandConstant('{app}'));
    NotifyEnvironmentChanged;
  end;
end;

procedure RemoveFromUserPath;
var
  PathValue, UpdatedPathValue: string;
begin
  if RegQueryStringValue(HKCU, UserEnvironmentKey, 'Path', PathValue) then
  begin
    UpdatedPathValue := RemovePathEntry(PathValue, ExpandConstant('{app}'));
    if UpdatedPathValue <> PathValue then
    begin
      RegWriteExpandStringValue(HKCU, UserEnvironmentKey, 'Path', UpdatedPathValue);
      NotifyEnvironmentChanged;
    end;
  end;
end;

procedure RefreshEnvironment;
var
  Msg, AppDir, OldDir: string;
begin
  AppDir := ExpandConstant('{app}');
  OldDir := ExpandConstant('{localappdata}\Software\guji');
  { 提示要短句多行：MsgBox 不给中文断行，一行太长会横向溢出被截。 }
  { 安装目录不写出来——用户不关心装在哪，只关心怎么用。 }
  Msg := '古籍重製 安装完成！' + #13#10 + #13#10 +
         '• 命令行：guji 命令已加入当前用户 PATH。' + #13#10 +
         '  关闭所有终端窗口重新打开后，即可直接运行 guji。' + #13#10 +
         '• 图形界面：已创建「古籍重製」开始菜单项，可直接启动。';
  { 旧目录若还在（没被旧卸载程序带走），提示一句——不代删，避免误删。 }
  { ⚠️ #13#10 不可写成行首：ISPP 会把行首的 # 当成预处理指令报
    "Unknown preprocessor directive"（真踩过）。续行必须以字符串开头。 }
  if DirExists(OldDir)
     and (CompareText(AppDir, OldDir) <> 0) then
    Msg := Msg + #13#10 + #13#10 +
           '提示：检测到旧版本目录仍在（已不再使用，可手动删除）：' + #13#10 +
           OldDir + #13#10 +
           '删除它可释放约 650 MB 空间。';
  MsgBox(Msg, mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RemoveLegacyPathEntries;
    AddToUserPath;
    RefreshEnvironment;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveFromUserPath;
    RemoveLegacyPathEntries;
  end;
end;
