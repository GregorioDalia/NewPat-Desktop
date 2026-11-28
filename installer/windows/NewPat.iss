#ifndef StageDir
  #error StageDir must identify a staged, verified installer directory
#endif
#ifndef BootstrapDir
  #define BootstrapDir StageDir + "\bootstrap"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\build\output"
#endif
#include BootstrapDir + "\bootstrap-profile.iss"

[Setup]
AppId={#NewPatAppId}
AppName={#NewPatDisplayName}
AppVersion={#NewPatBootstrapVersion}
AppVerName={#NewPatDisplayName}
AppPublisher=NewPat contributors
AppPublisherURL=https://github.com/GregorioDalia
LicenseFile={#StageDir}\app\LICENSE
DefaultDirName={code:GetNewPatDefaultAppDir}
DisableDirPage=no
UsePreviousAppDir=yes
SetupMutex=Local\NewPat-Desktop-Installer
DefaultGroupName={#NewPatDisplayName}
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.19045
OutputDir={#OutputDir}
OutputBaseFilename=NewPat-Setup
Compression=lzma2
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
SetupIconFile={#StageDir}\app\assets\branding\newpat-icon.ico
UninstallDisplayName={#NewPatDisplayName}
UninstallDisplayIcon={app}\assets\branding\newpat-icon.ico
CloseApplications=no
RestartApplications=no

[Files]
; Only this independently versioned bootstrap and official Python are embedded.
Source: "{#BootstrapDir}\python\*"; DestDir: "{tmp}\newpat-bootstrap-python"; Flags: dontcopy noencryption recursesubdirs createallsubdirs
Source: "{#BootstrapDir}\bootstrap_download.py"; DestDir: "{tmp}"; Flags: dontcopy noencryption
; Downloaded members are inventoried and hashed before the wizard opens.
Source: "{tmp}\newpat-payload\app\*"; DestDir: "{app}"; Flags: external ignoreversion recursesubdirs createallsubdirs
; Both archives survive reboot in the verified cache, with content-addressed names.
Source: "{tmp}\newpat-payload\runtime-cache\*"; DestDir: "{code:GetNewPatCacheDir}"; Flags: external ignoreversion uninsneveruninstall
; Reuse these exact setup bytes for later guided payload updates.
Source: "{srcexe}"; DestDir: "{app}\.runtime\setup"; DestName: "NewPat-Setup.exe"; Flags: external ignoreversion

[Dirs]
; Shortcuts have a valid working directory even before WSL setup/reboot completes.
Name: "{code:GetNewPatDataDir}"; Flags: uninsneveruninstall
Name: "{code:GetNewPatRunsDir}"; Flags: uninsneveruninstall
Name: "{code:GetNewPatRuntimeDir}"; Flags: uninsneveruninstall
Name: "{code:GetNewPatCacheDir}"; Flags: uninsneveruninstall

[INI]
; Ownership markers persist so a later setup can reuse deliberately retained directories.
Filename: "{app}\.newpat-app.ini"; Section: "NewPat"; Key: "schema_version"; String: "1"
Filename: "{app}\.newpat-app.ini"; Section: "NewPat"; Key: "installation_channel"; String: "desktop"
Filename: "{app}\.newpat-app.ini"; Section: "NewPat"; Key: "role"; String: "application"
Filename: "{code:GetNewPatRuntimeDir}\.newpat-storage.ini"; Section: "NewPat"; Key: "schema_version"; String: "1"
Filename: "{code:GetNewPatRuntimeDir}\.newpat-storage.ini"; Section: "NewPat"; Key: "installation_channel"; String: "desktop"
Filename: "{code:GetNewPatRuntimeDir}\.newpat-storage.ini"; Section: "NewPat"; Key: "role"; String: "runtime"
Filename: "{code:GetNewPatCacheDir}\.newpat-storage.ini"; Section: "NewPat"; Key: "schema_version"; String: "1"
Filename: "{code:GetNewPatCacheDir}\.newpat-storage.ini"; Section: "NewPat"; Key: "installation_channel"; String: "desktop"
Filename: "{code:GetNewPatCacheDir}\.newpat-storage.ini"; Section: "NewPat"; Key: "role"; String: "cache"

[Registry]
; Preferences survive app removal; no analysis directory is deleted by Uninstall.
Root: HKCU; Subkey: "Software\NewPat\desktop"; ValueType: string; ValueName: "app_dir"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\NewPat\desktop"; ValueType: string; ValueName: "runtime_dir"; ValueData: "{code:GetNewPatRuntimeDir}"
Root: HKCU; Subkey: "Software\NewPat\desktop"; ValueType: string; ValueName: "cache_dir"; ValueData: "{code:GetNewPatCacheDir}"
Root: HKCU; Subkey: "Software\NewPat\desktop"; ValueType: string; ValueName: "data_dir"; ValueData: "{code:GetNewPatDataDir}"
Root: HKCU; Subkey: "Software\NewPat\desktop"; ValueType: string; ValueName: "runs_dir"; ValueData: "{code:GetNewPatRunsDir}"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento {#NewPatDisplayName} sul desktop"

[Icons]
Name: "{autodesktop}\{#NewPatDisplayName}"; Filename: "{app}\2_LAUNCH.cmd"; WorkingDir: "{code:GetNewPatDataDir}"; IconFilename: "{app}\assets\branding\newpat-icon.ico"; Tasks: desktopicon
Name: "{group}\{#NewPatDisplayName}"; Filename: "{app}\2_LAUNCH.cmd"; WorkingDir: "{code:GetNewPatDataDir}"; IconFilename: "{app}\assets\branding\newpat-icon.ico"
Name: "{group}\{#NewPatDisplayName} - Resume Setup"; Filename: "{app}\1_SETUP.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\assets\branding\newpat-icon.ico"
Name: "{group}\{#NewPatDisplayName} Folder"; Filename: "{app}"
Name: "{group}\{#NewPatDisplayName} User Guide"; Filename: "{app}\docs\USER_GUIDE.md"
Name: "{group}\Uninstall {#NewPatDisplayName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\2_LAUNCH.cmd"; Description: "Avvia {#NewPatDisplayName}"; WorkingDir: "{code:GetNewPatDataDir}"; Flags: postinstall nowait skipifsilent; Check: CanLaunchNewPat

[Code]
var
  BootstrapResult: Integer;
  BootstrapCompleted: Boolean;
  WslRebootRequired: Boolean;
  StoragePage: TInputDirWizardPage;
  LayoutHelpersExtracted: Boolean;
  ApplicationKind: String;
  ProposedParent: String;
  ActivityLock: THandle;
  SetupLeaseEvent: THandle;
  SetupNonce: String;
  GuidedUpdateProject: String;
  PayloadVersion: String;
  PayloadSource: String;
  PayloadHash: String;
  PayloadSize: String;
  PayloadPackage: String;
  PayloadHandles: array of THandle;

function NewPatGetDriveType(RootPath: String): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

{ Inno Setup 6.7.3 uses a 32-bit process, also in 64-bit install mode.
  UINT_PTR is its pointer-width unsigned type; BOOL maps to WinAPI LongBool. }
function NewPatCreateFile(FileName: String; DesiredAccess, ShareMode: Cardinal;
  SecurityAttributes: UINT_PTR; CreationDisposition, Flags: Cardinal;
  TemplateFile: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';

function NewPatCloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

function NewPatCreateEvent(SecurityAttributes: UINT_PTR; ManualReset, InitialState: BOOL;
  Name: String): THandle;
  external 'CreateEventW@kernel32.dll stdcall';

function NewPatGetLastError(): Cardinal;
  external 'GetLastError@kernel32.dll stdcall';

function NewPatGetCurrentProcessId(): Cardinal;
  external 'GetCurrentProcessId@kernel32.dll stdcall';

function NewPatSetEnvironmentVariable(Name, Value: String): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function NewPatDeleteEnvironmentVariable(Name: String; Value: UINT_PTR): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function NewPatRememberedPath(Name, DefaultPath: String): String;
begin
  Result := DefaultPath;
  RegQueryStringValue(HKCU, 'Software\NewPat\desktop', Name, Result);
  if Trim(Result) = '' then Result := DefaultPath;
end;

function GetNewPatDefaultAppDir(Param: String): String;
begin
  Result := NewPatRememberedPath('app_dir',
    ExpandConstant('{localappdata}\Programs\{#NewPatAppDirectory}'));
end;

function GetNewPatRuntimeDir(Param: String): String;
begin
  Result := StoragePage.Values[0];
end;

function GetNewPatCacheDir(Param: String): String;
begin
  Result := StoragePage.Values[1];
end;

function GetNewPatDataDir(Param: String): String;
begin
  Result := StoragePage.Values[2];
end;

function GetNewPatRunsDir(Param: String): String;
begin
  Result := StoragePage.Values[3];
end;

function CanLaunchNewPat(): Boolean;
begin
  Result := BootstrapCompleted and (BootstrapResult = 0) and not WslRebootRequired and
    (ExpandConstant('{param:NEWPATUPDATE|}') <> '1');
end;

function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := (Version.ProductType = VER_NT_WORKSTATION) and
    ((Version.Build = 19045) or (Version.Build >= 22000));
  if not Result then begin
    MsgBox('NewPat richiede Windows 10 22H2 x64 (build 19045) oppure Windows 11 x64. ' +
      'Windows Server e le versioni precedenti non sono supportati.', mbError, MB_OK);
    Exit;
  end;
  Result := not IsAdmin;
  if not Result then
    MsgBox('Avvia NewPat-Setup.exe normalmente, senza "Esegui come amministratore". ' +
      'Solo il componente che abilita WSL chiedera'' l''autorizzazione UAC. ' +
      'Applicazione e distribuzione Linux appartengono al tuo utente Windows.', mbError, MB_OK);
end;

function NewPatPathHasReparsePoint(Path: String): Boolean;
var
  Parent: String;
  Entry: TFindRec;
begin
  Result := False;
  Path := RemoveBackslashUnlessRoot(Path);
  while Path <> '' do begin
    if FindFirst(Path, Entry) then begin
      try
        Result := (Entry.Attributes and FILE_ATTRIBUTE_REPARSE_POINT) <> 0;
      finally
        FindClose(Entry);
      end;
      if Result then Exit;
    end;
    Parent := ExtractFileDir(Path);
    if CompareText(Parent, Path) = 0 then Exit;
    Path := Parent;
  end;
end;

procedure ReleaseNewPatChildLease;
begin
  NewPatDeleteEnvironmentVariable('NEWPAT_SETUP_ACTIVITY_TOKEN', 0);
  if SetupLeaseEvent <> 0 then begin
    NewPatCloseHandle(SetupLeaseEvent);
    SetupLeaseEvent := 0;
  end;
  SetupNonce := '';
end;

procedure ReleaseNewPatActivityLock;
begin
  ReleaseNewPatChildLease;
  if ActivityLock <> 0 then begin
    NewPatCloseHandle(ActivityLock);
    ActivityLock := 0;
  end;
end;

procedure ReleaseNewPatPayloadLocks;
var
  I: Integer;
begin
  for I := 0 to GetArrayLength(PayloadHandles) - 1 do
    NewPatCloseHandle(PayloadHandles[I]);
  SetArrayLength(PayloadHandles, 0);
end;

procedure LockNewPatPayloadFile(Path: String);
var
  Handle: THandle;
  Count: Integer;
begin
  if NewPatPathHasReparsePoint(Path) then
    RaiseException('Il pacchetto temporaneo contiene un collegamento. Nessun file viene installato.');
  { Read sharing only: source files cannot be changed/deleted between verification and copy. }
  Handle := NewPatCreateFile(Path, $80000000, 1, 0, 3, $80, 0);
  if Handle = UINT_PTR(-1) then
    RaiseException('Impossibile proteggere il pacchetto temporaneo da modifiche: ' + Path);
  Count := GetArrayLength(PayloadHandles);
  SetArrayLength(PayloadHandles, Count + 1);
  PayloadHandles[Count] := Handle;
end;

procedure LockNewPatPayloadTree(Path: String);
var
  Entry: TFindRec;
begin
  if not FindFirst(AddBackslash(Path) + '*', Entry) then
    RaiseException('Cartella del pacchetto temporaneo non disponibile.');
  try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
        if (Entry.Attributes and FILE_ATTRIBUTE_REPARSE_POINT) <> 0 then
          RaiseException('Collegamento non consentito nel pacchetto temporaneo.');
        if (Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          LockNewPatPayloadTree(AddBackslash(Path) + Entry.Name)
        else LockNewPatPayloadFile(AddBackslash(Path) + Entry.Name);
      end;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

function AcquireNewPatActivityLock(): String;
var
  LockPath, LockDirectory: String;
  ErrorCode: Cardinal;
begin
  Result := '';
  if ActivityLock <> 0 then Exit;
  LockPath := ExpandConstant('{localappdata}\NewPat-Desktop\activity.lock');
  LockDirectory := ExtractFileDir(LockPath);
  if NewPatPathHasReparsePoint(LockPath) or not ForceDirectories(LockDirectory) or
    NewPatPathHasReparsePoint(LockPath) then begin
    Result := 'Impossibile verificare le sessioni NewPat: la cartella di coordinamento non e accessibile o attraversa un collegamento.';
    Exit;
  end;
  { No sharing and no inheritable handle: sessions hold compatible shared read handles. }
  ActivityLock := NewPatCreateFile(LockPath, $80000000, 0, 0, 4, $80, 0);
  ErrorCode := NewPatGetLastError;
  if ActivityLock = UINT_PTR(-1) then begin
    ActivityLock := 0;
    if (ErrorCode = 32) or (ErrorCode = 33) then
      Result := 'NewPat e ancora in uso. Attendere il termine delle analisi e chiudere tutte le finestre NewPat, quindi riprovare. Nessuna sessione viene interrotta.'
    else
      Result := 'Impossibile ottenere l''accesso esclusivo a NewPat (errore Windows ' + IntToStr(ErrorCode) + '). Nessun file viene modificato.';
  end;
end;

function CreateNewPatSetupLease(): String;
var
  I: Integer;
  ErrorCode: Cardinal;
begin
  Result := '';
  if ActivityLock = 0 then begin
    Result := 'Il coordinamento delle sessioni NewPat non e attivo.';
    Exit;
  end;
  if SetupLeaseEvent <> 0 then begin
    NewPatCloseHandle(SetupLeaseEvent);
    SetupLeaseEvent := 0;
  end;
  if Length(SetupNonce) <> 32 then begin
    Result := 'Identificativo temporaneo della preparazione non valido.';
    Exit;
  end;
  for I := 1 to Length(SetupNonce) do
    if Pos(SetupNonce[I], '0123456789abcdef') = 0 then begin
      Result := 'Identificativo temporaneo della preparazione non valido.';
      Exit;
    end;
  SetupLeaseEvent := NewPatCreateEvent(0, True, False,
    'Local\NewPat-Desktop-SetupLease-' + SetupNonce);
  ErrorCode := NewPatGetLastError;
  if (SetupLeaseEvent = 0) or (ErrorCode = 183) then begin
    if SetupLeaseEvent <> 0 then NewPatCloseHandle(SetupLeaseEvent);
    SetupLeaseEvent := 0;
    Result := 'Impossibile creare il coordinamento temporaneo della preparazione NewPat. Riprovare.';
  end;
end;

procedure DeinitializeSetup;
begin
  ReleaseNewPatActivityLock;
  ReleaseNewPatPayloadLocks;
end;

procedure DeinitializeUninstall;
begin
  ReleaseNewPatActivityLock;
end;

function NewPatTreeHasReparsePoint(Path: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := False;
  if not FindFirst(AddBackslash(Path) + '*', Entry) then Exit;
  try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
        if (Entry.Attributes and FILE_ATTRIBUTE_REPARSE_POINT) <> 0 then begin
          Result := True;
          Exit;
        end;
        if (Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          if NewPatTreeHasReparsePoint(AddBackslash(Path) + Entry.Name) then begin
            Result := True;
            Exit;
          end;
      end;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

function NewPatPathsOverlap(LeftPath, RightPath: String): Boolean;
begin
  LeftPath := AddBackslash(RemoveBackslashUnlessRoot(LeftPath));
  RightPath := AddBackslash(RemoveBackslashUnlessRoot(RightPath));
  Result := (CompareText(Copy(LeftPath, 1, Length(RightPath)), RightPath) = 0) or
    (CompareText(Copy(RightPath, 1, Length(LeftPath)), LeftPath) = 0);
end;

function NewPatValidatePath(var Path: String; LabelText: String): String;
var
  I: Integer;
  Letter: String;
begin
  Result := '';
  Path := Trim(Path);
  StringChangeEx(Path, '/', '\', True);
  if Length(Path) < 4 then begin
    Result := LabelText + ': scegliere una sottocartella su un disco locale, non la radice del disco.';
    Exit;
  end;
  Letter := Uppercase(Copy(Path, 1, 1));
  if (Letter < 'A') or (Letter > 'Z') or (Copy(Path, 2, 2) <> ':\') then begin
    Result := LabelText + ': inserire un percorso completo su un disco locale fisso, per esempio D:\NewPat\dati.';
    Exit;
  end;
  for I := 4 to Length(Path) do
    if (Ord(Path[I]) < 32) or (Pos(Path[I], ':*?"<>|') > 0) then begin
      Result := LabelText + ': il percorso contiene caratteri non validi.';
      Exit;
    end;
  Path := RemoveBackslashUnlessRoot(ExpandFileName(Path));
  if Length(Path) < 4 then begin
    Result := LabelText + ': la radice del disco non e una cartella dedicata.';
    Exit;
  end;
  if NewPatGetDriveType(Copy(Path, 1, 3)) <> 3 then begin
    Result := LabelText + ': scegliere un disco locale fisso disponibile. Unita di rete e rimovibili non sono supportate.';
    Exit;
  end;
  if FileExists(Path) then begin
    Result := LabelText + ': il percorso identifica un file, non una cartella.';
    Exit;
  end;
  if NewPatPathsOverlap(Path, ExpandConstant('{win}')) or
     NewPatPathsOverlap(Path, ExpandConstant('{commonpf32}')) or
     NewPatPathsOverlap(Path, ExpandConstant('{commonpf64}')) or
     NewPatPathsOverlap(Path, ExpandConstant('{localappdata}\NewPat-Desktop\preferences.json')) or
     NewPatPathsOverlap(Path, ExpandConstant('{localappdata}\NewPat-Desktop\activity.lock')) then begin
    Result := LabelText + ': scegliere una cartella separata da Windows, Program Files e dalle altre installazioni NewPat.';
    Exit;
  end;
  if NewPatPathHasReparsePoint(Path) then
    Result := LabelText + ': il percorso attraversa un collegamento o una junction. Scegliere la cartella fisica.';
end;

function NewPatValidateSelection(): String;
var
  Paths: TArrayOfString;
  Labels: TArrayOfString;
  I, J: Integer;
begin
  Result := '';
  if (GuidedUpdateProject <> '') and
    (CompareText(RemoveBackslashUnlessRoot(ExpandFileName(WizardDirValue)), GuidedUpdateProject) <> 0) then begin
    Result := 'L''aggiornamento deve mantenere la cartella dell''applicazione da cui e stato avviato: ' + GuidedUpdateProject;
    Exit;
  end;
  SetArrayLength(Paths, 5);
  SetArrayLength(Labels, 5);
  Paths[0] := WizardDirValue;
  Labels[0] := 'Applicazione';
  Labels[1] := 'Ambiente WSL';
  Labels[2] := 'Cache';
  Labels[3] := 'Dati';
  Labels[4] := 'Risultati';
  for I := 1 to 4 do Paths[I] := StoragePage.Values[I - 1];
  for I := 0 to 4 do begin
    Result := NewPatValidatePath(Paths[I], Labels[I]);
    if Result <> '' then Exit;
    for J := 0 to I - 1 do
      if NewPatPathsOverlap(Paths[I], Paths[J]) then begin
        Result := Labels[I] + ' e ' + Labels[J] + ': scegliere cartelle distinte, senza includerne una dentro l''altra.';
        Exit;
      end;
  end;
  for I := 0 to 2 do
    if NewPatTreeHasReparsePoint(Paths[I]) then begin
      Result := Labels[I] + ': la cartella contiene collegamenti o junction. Nessun file viene copiato.';
      Exit;
    end;
  if FileOrDirExists(AddBackslash(Paths[0]) + '.git') then begin
    Result := 'La cartella applicativa contiene un progetto Git. Scegliere una cartella dedicata all''installazione.';
    Exit;
  end;
  WizardForm.DirEdit.Text := Paths[0];
  for I := 1 to 4 do StoragePage.Values[I - 1] := Paths[I];
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  ModeText, PreservationText: String;
begin
  ModeText := 'Installazione';
  PreservationText := 'Dati e risultati gia presenti vengono conservati.';
  if ApplicationKind = 'installed' then begin
    ModeText := 'Aggiornamento e riparazione';
    PreservationText := PreservationText + ' Prima della copia viene salvato un backup dei file applicativi ' +
      'che saranno sostituiti. Gli altri file presenti restano nella cartella. ' +
      'Il backup non comporta un ripristino automatico.';
  end;
  Result := 'NewPat ' + PayloadVersion + NewLine + 'Operazione: ' + ModeText + NewLine + NewLine + PreservationText + NewLine + NewLine +
    MemoDirInfo + NewLine + NewLine +
    'Ambiente di calcolo WSL:' + NewLine + Space + GetNewPatRuntimeDir('') + NewLine + NewLine +
    'Cache dei componenti:' + NewLine + Space + GetNewPatCacheDir('') + NewLine + NewLine +
    'Dati predefiniti:' + NewLine + Space + GetNewPatDataDir('') + NewLine + NewLine +
    'Risultati predefiniti:' + NewLine + Space + GetNewPatRunsDir('') + NewLine + NewLine +
    MemoGroupInfo + NewLine + MemoTasksInfo;
end;

function NewPatJsonString(Value: String): String;
var
  I: Integer;
begin
  Result := '"';
  for I := 1 to Length(Value) do begin
    if Value[I] = '\' then Result := Result + '\\'
    else if Value[I] = '"' then Result := Result + '\"'
    else Result := Result + Value[I];
  end;
  Result := Result + '"';
end;

procedure WriteNewPatInstallLayoutAt(LayoutPath: String);
var
  Lines: TArrayOfString;
  LayoutDir: String;
begin
  LayoutDir := ExtractFileDir(LayoutPath);
  if not ForceDirectories(LayoutDir) then
    RaiseException('Impossibile creare la cartella di configurazione: ' + LayoutDir);
  SetArrayLength(Lines, 9);
  Lines[0] := '{';
  Lines[1] := '  "schema_version": 1,';
  Lines[2] := '  "installation_channel": "desktop",';
  Lines[3] := '  "app_dir": ' + NewPatJsonString(ExpandConstant('{app}')) + ',';
  Lines[4] := '  "runtime_dir": ' + NewPatJsonString(GetNewPatRuntimeDir('')) + ',';
  Lines[5] := '  "cache_dir": ' + NewPatJsonString(GetNewPatCacheDir('')) + ',';
  Lines[6] := '  "data_dir": ' + NewPatJsonString(GetNewPatDataDir('')) + ',';
  Lines[7] := '  "runs_dir": ' + NewPatJsonString(GetNewPatRunsDir(''));
  Lines[8] := '}';
  if not SaveStringsToUTF8File(LayoutPath, Lines, False) then
    RaiseException('Impossibile salvare le cartelle selezionate: ' + LayoutPath);
end;

function QuoteNewPatArgument(Value: String): String;
var
  I, J, Backslashes: Integer;
begin
  { Windows argv quoting: backslashes before quotes and at the end are doubled. }
  Result := '"';
  Backslashes := 0;
  for I := 1 to Length(Value) do begin
    if Value[I] = '\' then
      Backslashes := Backslashes + 1
    else begin
      if Value[I] = '"' then begin
        for J := 1 to (Backslashes * 2 + 1) do Result := Result + '\';
      end else begin
        for J := 1 to Backslashes do Result := Result + '\';
      end;
      Result := Result + Value[I];
      Backslashes := 0;
    end;
  end;
  for J := 1 to (Backslashes * 2) do Result := Result + '\';
  Result := Result + '"';
end;

procedure ExtractNewPatLayoutHelpers;
begin
  if LayoutHelpersExtracted then Exit;
  { Invoke the verified, read-locked helpers in place; do not create unlocked copies. }
  if not FileExists(ExpandConstant('{tmp}\newpat-payload\app\installer\windows\validate-install-layout.ps1')) then
    RaiseException('Componente del pacchetto verificato non disponibile.');
  LayoutHelpersExtracted := True;
end;

function NewPatReadValidationError(ErrorFile, Fallback: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if LoadStringsFromFile(ErrorFile, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      Result := Result + Lines[I] + #13#10;
  if Trim(Result) = '' then Result := Fallback;
end;

function NewPatValidateWithSharedRules(): String;
var
  LayoutFile, ErrorFile, InfoFile, Parameters: String;
  ValidationResult: Integer;
begin
  Result := '';
  ApplicationKind := '';
  SetupNonce := '';
  LayoutFile := ExpandConstant('{tmp}\newpat-layout-selection.json');
  ErrorFile := ExpandConstant('{tmp}\newpat-layout-error.txt');
  InfoFile := ExpandConstant('{tmp}\newpat-layout-info.ini');
  try
    ExtractNewPatLayoutHelpers;
    WriteNewPatInstallLayoutAt(LayoutFile);
    DeleteFile(ErrorFile);
    DeleteFile(InfoFile);
    Parameters := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
      QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload\app\installer\windows\validate-install-layout.ps1')) +
      ' -LayoutFile ' + QuoteNewPatArgument(LayoutFile) +
      ' -InfoFile ' + QuoteNewPatArgument(InfoFile) +
      ' -ErrorFile ' + QuoteNewPatArgument(ErrorFile);
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      Parameters, ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ValidationResult) then
      ValidationResult := 1;
    ApplicationKind := GetIniString('NewPat', 'kind', '', InfoFile);
    if ValidationResult = 0 then
      SetupNonce := GetIniString('NewPat', 'setup_nonce', '', InfoFile);
    if ValidationResult <> 0 then
      Result := NewPatReadValidationError(ErrorFile,
        'Impossibile verificare le cartelle selezionate. Nessun file viene copiato. ' +
        'Verificare che Windows consenta l''esecuzione di PowerShell e riprovare.')
    else if (ApplicationKind <> 'empty') and (ApplicationKind <> 'installed') then
      Result := 'La verifica non ha riconosciuto la destinazione applicativa. Nessun file viene copiato.';
  except
    Result := 'Verifica delle cartelle non completata: ' + GetExceptionMessage;
  end;
end;

function NewPatDirectoryIsEmpty(Path: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := not FileExists(Path);
  if not Result or not DirExists(Path) then Exit;
  if not FindFirst(AddBackslash(Path) + '*', Entry) then begin
    Result := False;
    Exit;
  end;
  try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
        Result := False;
        Exit;
      end;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  MessageText, ParentPath, ChildPath: String;
begin
  Result := True;
  if CurPageID <> StoragePage.ID then Exit;
  ApplicationKind := '';
  MessageText := NewPatValidateSelection;
  if MessageText = '' then MessageText := NewPatValidateWithSharedRules;
  if (GuidedUpdateProject = '') and (MessageText <> '') and
    (ApplicationKind = 'unknown') and not WizardSilent then begin
    ParentPath := WizardDirValue;
    ChildPath := AddBackslash(ParentPath) + '{#NewPatAppDirectory}';
    if (CompareText(ProposedParent, ParentPath) <> 0) and
      (CompareText(ExtractFileName(ParentPath), '{#NewPatAppDirectory}') <> 0) and
      NewPatDirectoryIsEmpty(ChildPath) then begin
      ProposedParent := ParentPath;
      if MsgBox('La cartella selezionata contiene file che non identificano un''installazione NewPat. ' +
        'Vuoi usare questa sottocartella dedicata e vuota?' + #13#10#13#10 + ChildPath + #13#10#13#10 +
        'Nessun file esistente verra spostato o eliminato. Scegli No per tornare indietro e indicare un''altra destinazione.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then begin
        WizardForm.DirEdit.Text := ChildPath;
        MessageText := NewPatValidateSelection;
        if MessageText = '' then MessageText := NewPatValidateWithSharedRules;
      end;
    end;
  end;
  if MessageText <> '' then begin
    MsgBox(MessageText + #13#10#13#10 + 'Usa Indietro per modificare la cartella applicativa.', mbError, MB_OK);
    Result := False;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { The updater reopens this exact application after setup; it cannot relocate the app. }
  Result := (GuidedUpdateProject <> '') and (PageID = wpSelectDir);
end;

function NewPatPrepareApplication(): String;
var
  LayoutFile, ErrorFile, ReportFile, Parameters, Mode, BackupDir: String;
  RepairResult: Integer;
begin
  Result := '';
  LayoutFile := ExpandConstant('{tmp}\newpat-layout-selection.json');
  ErrorFile := ExpandConstant('{tmp}\newpat-repair-error.txt');
  ReportFile := ExpandConstant('{tmp}\newpat-repair-report.ini');
  try
    ExtractNewPatLayoutHelpers;
    WriteNewPatInstallLayoutAt(LayoutFile);
    DeleteFile(ErrorFile);
    DeleteFile(ReportFile);
    Parameters := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
      QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload\app\installer\windows\repair-installation.ps1')) +
      ' -LayoutFile ' + QuoteNewPatArgument(LayoutFile) +
      ' -PayloadFile ' + QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload\app\.distribution\application-files.json')) +
      ' -ReportFile ' + QuoteNewPatArgument(ReportFile) +
      ' -ErrorFile ' + QuoteNewPatArgument(ErrorFile);
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      Parameters, ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, RepairResult) then
      RepairResult := 1;
    if RepairResult <> 0 then begin
      Result := NewPatReadValidationError(ErrorFile,
        'Preparazione o backup dell''applicazione non completati. Nessun file applicativo viene copiato.');
      Exit;
    end;
    Mode := GetIniString('NewPat', 'mode', '', ReportFile);
    BackupDir := GetIniString('NewPat', 'backup_dir', '', ReportFile);
    if (Mode <> 'install') and (Mode <> 'repair') then
      Result := 'Rapporto di preparazione non valido. Nessun file applicativo viene copiato.'
    else if (Mode = 'repair') and ((BackupDir = '') or not DirExists(BackupDir)) then
      Result := 'Backup della riparazione non disponibile. Nessun file applicativo viene copiato.'
    else if Mode = 'repair' then
      Log('Backup prima della riparazione: ' + BackupDir);
  except
    Result := 'Preparazione dell''applicazione non completata: ' + GetExceptionMessage;
  end;
end;

function VerifyNewPatExtractedPayload(): String;
var
  Parameters, ErrorFile: String;
  VerifyResult: Integer;
begin
  ErrorFile := ExpandConstant('{tmp}\newpat-payload-error.txt');
  DeleteFile(ErrorFile);
  Parameters := '-I ' + QuoteNewPatArgument(ExpandConstant('{tmp}\bootstrap_download.py')) +
    ' --check-extracted ' + QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload')) +
    ' --package ' + QuoteNewPatArgument(PayloadPackage) +
    ' --version ' + QuoteNewPatArgument(PayloadVersion) +
    ' --source ' + QuoteNewPatArgument(PayloadSource) +
    ' --sha256 ' + QuoteNewPatArgument(PayloadHash) +
    ' --size ' + QuoteNewPatArgument(PayloadSize) +
    ' --error-file ' + QuoteNewPatArgument(ErrorFile);
  if not Exec(ExpandConstant('{tmp}\newpat-bootstrap-python\python.exe'), Parameters,
    ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, VerifyResult) then VerifyResult := 1;
  Result := '';
  if VerifyResult <> 0 then
    Result := NewPatReadValidationError(ErrorFile,
      'Il contenuto temporaneo e cambiato. Nessun file applicativo viene modificato.');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  CheckResult: Integer;
  Parameters, ErrorFile: String;
begin
  Result := AcquireNewPatActivityLock;
  if Result <> '' then Exit;
  try
    { Recheck membership after time spent in the wizard, immediately before any backup/copy. }
    Result := VerifyNewPatExtractedPayload;
    if Result = '' then Result := NewPatValidateSelection;
    if Result = '' then begin
      ErrorFile := ExpandConstant('{tmp}\newpat-version-error.txt');
      DeleteFile(ErrorFile);
      Parameters := '-I ' + QuoteNewPatArgument(ExpandConstant('{tmp}\bootstrap_download.py')) +
        ' --check-installed ' + QuoteNewPatArgument(ExpandConstant('{app}')) +
        ' --version ' + QuoteNewPatArgument(PayloadVersion) +
        ' --source ' + QuoteNewPatArgument(PayloadSource) +
        ' --error-file ' + QuoteNewPatArgument(ErrorFile);
      if not Exec(ExpandConstant('{tmp}\newpat-bootstrap-python\python.exe'), Parameters,
        ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, CheckResult) then CheckResult := 1;
      if CheckResult <> 0 then Result := NewPatReadValidationError(ErrorFile,
        'Impossibile verificare la versione installata. Nessun file viene sostituito.');
    end;
    if (Result = '') and (CompareText(WizardGroupValue, '{#NewPatDisplayName}') <> 0) then
      Result := 'Il gruppo Start di NewPat deve restare separato dalle altre installazioni. Riavviare senza /GROUP.';
    if Result = '' then Result := NewPatValidateWithSharedRules;
    if Result = '' then Result := CreateNewPatSetupLease;
    if Result = '' then Result := NewPatPrepareApplication;
  except
    Result := 'Preparazione NewPat non completata: ' + GetExceptionMessage;
  end;
  if Result <> '' then ReleaseNewPatActivityLock;
end;

procedure ReadNewPatPreviousDefaults(Project, DefaultsFile: String);
var
  Parameters, ErrorFile: String;
  ValidationResult: Integer;
begin
  ExtractNewPatLayoutHelpers;
  ErrorFile := ExpandConstant('{tmp}\newpat-defaults-error.txt');
  DeleteFile(ErrorFile);
  Parameters := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
    QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload\app\installer\windows\validate-install-layout.ps1')) +
    ' -Project ' + QuoteNewPatArgument(Project) +
    ' -DefaultsFile ' + QuoteNewPatArgument(DefaultsFile) +
    ' -ErrorFile ' + QuoteNewPatArgument(ErrorFile);
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Parameters, ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ValidationResult) then
    ValidationResult := 1;
  if ValidationResult <> 0 then
    RaiseException(NewPatReadValidationError(ErrorFile,
      'Impossibile leggere le cartelle della precedente installazione. ' +
      'Conservare la configurazione esistente e verificare che Windows consenta PowerShell.'));
end;

procedure PrepareNewPatPayload;
var
  Parameters, ErrorFile, ReportFile: String;
  DownloadResult: Integer;
begin
  if (ExpandConstant('{param:NEWPATUPDATE|}') = '1') and
    (ExpandConstant('{param:NEWPATVERSION|}') = '') then
    RaiseException('Questo aggiornamento non specifica la versione del pacchetto. ' +
      'Chiudi NewPat e avvia manualmente NewPat-Setup.exe. Nessun file e stato modificato.');
  ExtractTemporaryFiles('{tmp}\newpat-bootstrap-python\*');
  ExtractTemporaryFile('bootstrap_download.py');
  LockNewPatPayloadTree(ExpandConstant('{tmp}\newpat-bootstrap-python'));
  LockNewPatPayloadFile(ExpandConstant('{tmp}\bootstrap_download.py'));
  ErrorFile := ExpandConstant('{tmp}\newpat-download-error.txt');
  ReportFile := ExpandConstant('{tmp}\newpat-payload.ini');
  Parameters := '-I ' + QuoteNewPatArgument(ExpandConstant('{tmp}\bootstrap_download.py')) +
    ' --destination ' + QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload')) +
    ' --error-file ' + QuoteNewPatArgument(ErrorFile) +
    ' --report-file ' + QuoteNewPatArgument(ReportFile);
  if ExpandConstant('{param:NEWPATPACKAGE|}') <> '' then
    Parameters := Parameters + ' --package ' + QuoteNewPatArgument(ExpandConstant('{param:NEWPATPACKAGE|}'));
  if ExpandConstant('{param:NEWPATVERSION|}') <> '' then
    Parameters := Parameters + ' --version ' + QuoteNewPatArgument(ExpandConstant('{param:NEWPATVERSION|}'));
  if ExpandConstant('{param:NEWPATSOURCE|}') <> '' then
    Parameters := Parameters + ' --source ' + QuoteNewPatArgument(ExpandConstant('{param:NEWPATSOURCE|}'));
  if ExpandConstant('{param:NEWPATSHA256|}') <> '' then
    Parameters := Parameters + ' --sha256 ' + QuoteNewPatArgument(ExpandConstant('{param:NEWPATSHA256|}'));
  if ExpandConstant('{param:NEWPATSIZE|}') <> '' then
    Parameters := Parameters + ' --size ' + QuoteNewPatArgument(ExpandConstant('{param:NEWPATSIZE|}'));
  if not Exec(ExpandConstant('{tmp}\newpat-bootstrap-python\python.exe'), Parameters,
    ExpandConstant('{tmp}'), SW_SHOW, ewWaitUntilTerminated, DownloadResult) then DownloadResult := 1;
  if DownloadResult <> 0 then
    RaiseException(NewPatReadValidationError(ErrorFile,
      'Download o verifica del pacchetto non riusciti. Verifica la connessione e riprova. Nessun file applicativo e stato modificato.'));
  PayloadVersion := GetIniString('NewPat', 'version', '', ReportFile);
  PayloadSource := GetIniString('NewPat', 'source_commit', '', ReportFile);
  PayloadHash := GetIniString('NewPat', 'sha256', '', ReportFile);
  PayloadSize := GetIniString('NewPat', 'size', '', ReportFile);
  if (PayloadVersion = '') or (Length(PayloadSource) <> 40) then
    RaiseException('Il pacchetto verificato non contiene una versione valida.');
  PayloadPackage := ExpandConstant('{param:NEWPATPACKAGE|}');
  if PayloadPackage = '' then PayloadPackage := ExpandConstant('{tmp}\newpat-payload-download.zip');
  LockNewPatPayloadFile(PayloadPackage);
  LockNewPatPayloadTree(ExpandConstant('{tmp}\newpat-payload'));
  Parameters := '-I ' + QuoteNewPatArgument(ExpandConstant('{tmp}\bootstrap_download.py')) +
    ' --check-extracted ' + QuoteNewPatArgument(ExpandConstant('{tmp}\newpat-payload')) +
    ' --package ' + QuoteNewPatArgument(PayloadPackage) +
    ' --version ' + QuoteNewPatArgument(PayloadVersion) +
    ' --source ' + QuoteNewPatArgument(PayloadSource) +
    ' --sha256 ' + QuoteNewPatArgument(PayloadHash) +
    ' --size ' + QuoteNewPatArgument(PayloadSize) +
    ' --error-file ' + QuoteNewPatArgument(ErrorFile);
  if not Exec(ExpandConstant('{tmp}\newpat-bootstrap-python\python.exe'), Parameters,
    ExpandConstant('{tmp}'), SW_SHOW, ewWaitUntilTerminated, DownloadResult) then DownloadResult := 1;
  if DownloadResult <> 0 then
    RaiseException(NewPatReadValidationError(ErrorFile,
      'Il contenuto temporaneo e cambiato. Nessun file applicativo e stato modificato.'));
end;

procedure InitializeWizard();
var
  Base, Project, DefaultsFile, Stored: String;
  Names, Defaults: TArrayOfString;
  I: Integer;
  NeedPrevious, GuidedUpdate: Boolean;
begin
  PrepareNewPatPayload;
  Base := ExpandConstant('{localappdata}\{#NewPatDataDirectory}');
  SetArrayLength(Names, 4);
  SetArrayLength(Defaults, 4);
  Names[0] := 'runtime_dir'; Defaults[0] := AddBackslash(Base) + 'wsl';
  Names[1] := 'cache_dir'; Defaults[1] := AddBackslash(Base) + 'cache';
  Names[2] := 'data_dir'; Defaults[2] := AddBackslash(Base) + 'data';
  Names[3] := 'runs_dir'; Defaults[3] := AddBackslash(Base) + 'runs';
  GuidedUpdate := ExpandConstant('{param:NEWPATUPDATE|}') = '1';
  Project := WizardDirValue;
  if GuidedUpdate then begin
    GuidedUpdateProject := RemoveBackslashUnlessRoot(ExpandFileName(Project));
    WizardForm.DirEdit.Enabled := False;
  end;
  if GuidedUpdate and not FileExists(AddBackslash(Project) + '.runtime\install-layout.json') then
    RaiseException('Il layout dell''applicazione da aggiornare non e disponibile. Riaprire il setup NewPat per riparare l''installazione.');
  NeedPrevious := False;
  for I := 0 to 3 do
    if not RegQueryStringValue(HKCU, 'Software\NewPat\desktop', Names[I], Stored) then
      NeedPrevious := True
    else if Trim(Stored) = '' then NeedPrevious := True;
  if GuidedUpdate or (NeedPrevious and
    (FileExists(AddBackslash(Project) + '.runtime\install-layout.json') or
     FileExists(AddBackslash(Project) + '.runtime\backend.json'))) then begin
    DefaultsFile := ExpandConstant('{tmp}\newpat-previous-paths.ini');
    ReadNewPatPreviousDefaults(Project, DefaultsFile);
    for I := 0 to 3 do begin
      Defaults[I] := GetIniString('NewPat', Names[I], '', DefaultsFile);
      if Trim(Defaults[I]) = '' then
        RaiseException('La configurazione precedente non contiene tutte le destinazioni. Nessun aggiornamento e stato applicato.');
    end;
  end;
  StoragePage := CreateInputDirPage(wpSelectDir,
    'Cartelle di NewPat', 'Scegli dove conservare ambiente di calcolo e analisi.',
    'Puoi mantenere le destinazioni proposte oppure scegliere cartelle distinte, anche su altri dischi locali. ' +
    'I file gia presenti non vengono spostati; un nuovo ambiente WSL viene preparato nella destinazione scelta.',
    False, SetupMessage(msgNewFolderName));
  StoragePage.Add('Ambiente di calcolo WSL:');
  StoragePage.Add('Cache dei componenti di installazione:');
  StoragePage.Add('Cartella dati predefinita:');
  StoragePage.Add('Cartella risultati predefinita:');
  for I := 0 to 3 do
    if GuidedUpdate then
      StoragePage.Values[I] := Defaults[I]
    else
      StoragePage.Values[I] := NewPatRememberedPath(Names[I], Defaults[I]);
end;

function InitializeUninstall(): Boolean;
var
  MessageText: String;
begin
  Result := not IsAdmin;
  if not Result then
    MsgBox('Eseguire la disinstallazione dal proprio account senza elevazione. ' +
      'L''ambiente WSL appartiene all''utente che ha installato NewPat.', mbError, MB_OK);
  if Result then begin
    MessageText := AcquireNewPatActivityLock;
    Result := MessageText = '';
    if not Result then MsgBox(MessageText, mbError, MB_OK);
  end;
end;

procedure RemoveNewPatRuntimeBeforeUninstall;
var
  CleanupResult, NonceResult: Integer;
  Parameters, MessageText: String;
  NonceOutput: TExecOutput;
begin
  try
    { Cleanup borrows this uninstaller's live exclusive lease rather than acquiring it twice. }
    if not ExecAndCaptureOutput(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoLogo -NoProfile -Command "[Guid]::NewGuid().ToString(''N'')"', ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, NonceResult, NonceOutput) then
      RaiseException('Impossibile preparare il coordinamento della rimozione NewPat.');
    if (NonceResult <> 0) or NonceOutput.Error or (GetArrayLength(NonceOutput.StdOut) <> 1) then
      RaiseException('Impossibile ottenere l''identificativo temporaneo della rimozione NewPat.');
    SetupNonce := Trim(NonceOutput.StdOut[0]);
    MessageText := CreateNewPatSetupLease;
    if MessageText <> '' then RaiseException(MessageText);
    if not NewPatSetEnvironmentVariable('NEWPAT_SETUP_ACTIVITY_TOKEN',
      IntToStr(NewPatGetCurrentProcessId) + ':' + SetupNonce) then
      RaiseException('Impossibile autorizzare la rimozione del runtime NewPat.');
    Parameters := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
      QuoteNewPatArgument(ExpandConstant('{app}\installer\windows\uninstall-runtime.ps1')) +
      ' -Project ' + QuoteNewPatArgument(ExpandConstant('{app}'));
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      Parameters, ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, CleanupResult) then
      CleanupResult := 1;
  finally
    ReleaseNewPatChildLease;
  end;
  if CleanupResult <> 0 then
    RaiseException('La pulizia dell''ambiente non e stata completata. L''applicazione non viene rimossa, ' +
      'Consulta i log in ' + ExpandConstant('{localappdata}\{#NewPatDataDirectory}\installations\logs') + '. ' +
      'Per rimuovere soltanto l''applicazione, ' +
      'riapri la disinstallazione e scegli No alla pulizia dell''ambiente.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AssetDir, Parameters, Marker: String;
  Started: Boolean;
begin
  if CurStep = ssPostInstall then begin
    BootstrapResult := 1;
    try
      WriteNewPatInstallLayoutAt(ExpandConstant('{app}\.runtime\install-layout.json'));
      Marker := '{"schema_version":1,"installation_method":"bootstrap","setup_sha256":' +
        NewPatJsonString(Lowercase(GetSHA256OfFile(ExpandConstant('{app}\.runtime\setup\NewPat-Setup.exe')))) + '}';
      if not SaveStringToFile(ExpandConstant('{app}\.runtime\bootstrap-install.json'), Marker, False) then
        RaiseException('Impossibile registrare il canale di aggiornamento del setup.');
      { Windows lists the installed application version, independently of the frozen setup. }
      if not RegWriteStringValue(HKCU,
        'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + ExpandConstant('{#NewPatAppId}_is1'),
        'DisplayVersion', PayloadVersion) then
        RaiseException('Impossibile registrare la versione installata di NewPat.');
      AssetDir := ExpandConstant('{param:ASSETDIR|}');
      Parameters := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
        QuoteNewPatArgument(ExpandConstant('{app}\installer\windows\bootstrap.ps1'));
      if AssetDir <> '' then
        Parameters := Parameters + ' -AssetDirectory ' + QuoteNewPatArgument(AssetDir);
      if (ActivityLock = 0) or (SetupLeaseEvent = 0) then
        RaiseException('Coordinamento della preparazione NewPat non disponibile.');
      if not NewPatSetEnvironmentVariable('NEWPAT_SETUP_ACTIVITY_TOKEN',
        IntToStr(NewPatGetCurrentProcessId) + ':' + SetupNonce) then
        RaiseException('Impossibile autorizzare gli autotest della preparazione NewPat.');
      { Setup is non-elevated; Exec preserves the lease owner's environment and ancestry. }
      Started := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
        Parameters, ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, BootstrapResult);
      if not Started then BootstrapResult := 1;
      BootstrapCompleted := True;
      WslRebootRequired := BootstrapResult = 3010;
    finally
      ReleaseNewPatActivityLock;
    end;
    if (BootstrapResult <> 0) and not WslRebootRequired then
      MsgBox('I file NewPat sono installati, ma la preparazione non e'' completata. ' +
        'Apri "{#NewPatDisplayName} - Resume Setup" dal menu Start. ' +
        'Dettagli nel file .runtime\installer\setup.log della cartella NewPat.', mbError, MB_OK);
  end;
end;

function NeedRestart(): Boolean;
begin
  Result := WslRebootRequired;
end;

function GetCustomSetupExitCode(): Integer;
begin
  Result := 0;
  { An older updater may pass /NORESTART without an explicit reboot code. }
  if WslRebootRequired and (ExpandConstant('{param:NEWPATUPDATE|}') = '1') then
    Result := 3010
  else if (BootstrapResult <> 0) and not WslRebootRequired then Result := 1;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Choice: Integer;
begin
  if CurUninstallStep = usUninstall then begin
    { This point is after Inno's confirmation and before any installed file is removed. }
    { Silent removal conserves runtime and data; interactive cleanup is opt-in. }
    if not UninstallSilent then begin
      Choice := MsgBox('Rimuovere anche gli ambienti WSL e la cache appartenenti a NewPat?'#13#10#13#10 +
        'Si: elimina definitivamente le distribuzioni NewPat riconosciute, tutti i file al loro interno e gli archivi della cache.'#13#10 +
        'No: conserva questi componenti per una reinstallazione.'#13#10#13#10 +
        'Dati e risultati delle analisi su Windows, Docker Desktop e altre distribuzioni Linux vengono conservati.',
        mbConfirmation, MB_YESNOCANCEL or MB_DEFBUTTON2);
      if Choice = IDCANCEL then Abort;
      if Choice = IDYES then RemoveNewPatRuntimeBeforeUninstall;
    end;
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\RunOnce', '{#NewPatResumeKey}');
  end;
end;
