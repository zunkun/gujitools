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
DefaultDirName={localappdata}\Software\guji
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
  Msg: string;
begin
  Msg := '古籍重製 安装完成！' + #13#10 + #13#10 +
         '• 命令行：guji 命令已添加至当前用户 PATH，' +
         '关闭所有终端窗口重新打开后即可直接运行 guji。' + #13#10 +
         '• 图形界面：已创建「古籍重製」开始菜单项，可直接启动。';
  MsgBox(Msg, mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    AddToUserPath;
    RefreshEnvironment;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveFromUserPath;
end;
