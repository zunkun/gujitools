#ifndef VERSION
#define VERSION "1.0.0"
#endif
#ifndef BUILD_TIMESTAMP
#define BUILD_TIMESTAMP "dev"
#endif
[Setup]
AppName=guji古籍工具
AppVersion={#VERSION}
DefaultDirName={localappdata}\Software\guji
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=guji_setup_{#VERSION}_{#BUILD_TIMESTAMP}
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\guji\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\guji"; Filename: "{app}\guji.exe"
Name: "{group}\guji"; Filename: "{app}\guji.exe"
Name: "{group}\卸载"; Filename: "{uninstallexe}"

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
  Msg := '安装完成！guji.exe 已注册到当前用户 PATH。请关闭并重新打开终端后使用 guji 命令。';
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
