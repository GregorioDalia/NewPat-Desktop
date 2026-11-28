param(
    [Parameter(Mandatory = $true)][string] $Descriptor,
    [switch] $NoPause
)

# Standalone worker copied outside the application before the current CLI exits.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$directory = Split-Path -Parent ([IO.Path]::GetFullPath($Descriptor))
$cancelFile = Join-Path $directory 'cancel'
$logFile = Join-Path $directory 'handoff.log'
$packageStream = $null
$bootstrapStream = $null
$activity = $null
$parent = $null
$result = 1

function Write-HandoffLog([string] $Message) {
    [IO.File]::AppendAllText($logFile, ([DateTime]::UtcNow.ToString('o') + ' ' + $Message + "`r`n"),
        (New-Object Text.UTF8Encoding($false)))
    Write-Host $Message
}

function Assert-NotCanceled {
    if (Test-Path -LiteralPath $cancelFile) { throw 'Aggiornamento annullato: nessun installer viene avviato.' }
}

function Assert-LocalPath([string] $Path) {
    if ($Path -cnotmatch '^[A-Za-z]:\\' -or $Path.Substring(2) -match '[<>:"|?*\x00-\x1f]') {
        throw 'Il passaggio all installer richiede percorsi assoluti su dischi locali.'
    }
    $full = [IO.Path]::GetFullPath($Path)
    $drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($full))
    if (-not $drive.IsReady -or $drive.DriveType -ne [IO.DriveType]::Fixed) { throw 'Disco locale non disponibile.' }
    $current = $full
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Il percorso del componente di aggiornamento contiene un collegamento.'
            }
        }
        $next = [IO.Path]::GetDirectoryName($current.TrimEnd('\'))
        if ($next -eq $current) { break }
        $current = $next
    }
    return $full
}

function Quote-HandoffArgument([string] $Value) {
    # Windows argv quoting, without interpreting any value as PowerShell or cmd source.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Write-HandoffJson([string] $Name, $Value) {
    $file = Join-Path $directory $Name
    $temporary = Join-Path $directory ([Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
        [IO.File]::Move($temporary, $file)
    } finally { if (Test-Path -LiteralPath $temporary) { [IO.File]::Delete($temporary) } }
}

try {
    Assert-NotCanceled
    Assert-LocalPath $Descriptor | Out-Null
    $record = Get-Content -LiteralPath $Descriptor -Raw -Encoding UTF8 | ConvertFrom-Json
    $method = $record.installation_method
    $zipInstall = $method -ceq 'zip'
    $bootstrapInstall = $method -ceq 'bootstrap'
    $fieldCount = if ($bootstrapInstall) { 12 } else { 11 }
    if ($method -cnotin @('zip', 'bootstrap') -or
        @($record.PSObject.Properties).Count -ne $fieldCount -or $record.schema_version -ne 1 -or
        $record.installation_channel -cne 'desktop' -or $record.parent_pid -le 0 -or
        $record.sha256 -cnotmatch '^[a-f0-9]{64}$' -or $record.size -le 0 -or
        $record.source_commit -cnotmatch '^[a-f0-9]{40}$' -or
        $record.version -cnotmatch '^\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?$') {
        throw 'Richiesta di aggiornamento non valida.'
    }
    $project = Assert-LocalPath $record.project_dir
    $package = Assert-LocalPath $record.package
    $data = Assert-LocalPath $record.data_dir
    if (-not (Test-Path -LiteralPath $project -PathType Container) -or
        -not (Test-Path -LiteralPath $package -PathType Leaf) -or [IO.Path]::GetExtension($package) -ine '.zip') {
        throw 'Installer o applicazione non disponibili.'
    }
    if ($zipInstall) {
        . (Join-Path $project 'installer\windows\zip-common.ps1')
        $zipRoot = Get-NewPatZipRoot $project
        $zipMarker = Get-Content -LiteralPath (Join-Path $project '.runtime\zip-install.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($zipMarker.PSObject.Properties).Count -ne 3 -or $zipMarker.schema_version -ne 1 -or
            $zipMarker.installation_method -cne 'zip' -or $zipMarker.root -ine $zipRoot -or
            (Read-NewPatZipPointer $zipRoot).app_dir -ine $project) { throw 'Installazione ZIP attiva non valida.' }
    }
    if ($bootstrapInstall) {
        $setupMarkerPath = Assert-LocalPath (Join-Path $project '.runtime\bootstrap-install.json')
        $setupMarker = Get-Content -LiteralPath $setupMarkerPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($setupMarker.PSObject.Properties).Count -ne 3 -or $setupMarker.schema_version -ne 1 -or
            $setupMarker.installation_method -cne 'bootstrap' -or $record.setup_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
            $setupMarker.setup_sha256 -cne $record.setup_sha256 -or
            (Test-Path -LiteralPath (Join-Path $project '.runtime\zip-install.json'))) {
            throw 'Installazione con setup stabile non valida. Nessun installer viene avviato.'
        }
        $setupSource = Assert-LocalPath (Join-Path $project '.runtime\setup\NewPat-Setup.exe')
        if (-not (Test-Path -LiteralPath $setupSource -PathType Leaf)) { throw 'Setup stabile mancante. Riparare l installazione.' }
    }
    $parent = [Diagnostics.Process]::GetProcessById([int] $record.parent_pid)
    # Opening the process handle before acknowledgement avoids a reused PID.
    $null = $parent.Handle
    Assert-NotCanceled
    Write-HandoffJson 'ready.json' ([ordered]@{ schema_version = 1; worker_pid = $PID; parent_pid = [int]$record.parent_pid })
    Write-HandoffLog 'Chiusura della sessione NewPat in corso...'
    $deadline = [DateTime]::UtcNow.AddMinutes(2)
    while (-not $parent.WaitForExit(100)) {
        Assert-NotCanceled
        if ([DateTime]::UtcNow -gt $deadline) { throw 'La sessione NewPat non si e chiusa. Ripetere l aggiornamento dal menu.' }
    }
    Assert-NotCanceled
    if ($parent.ExitCode -ne 85) {
        throw 'La sessione non ha confermato il passaggio all installer. Nessun aggiornamento viene avviato.'
    }
    $lockPath = Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\activity.lock'
    Assert-LocalPath $lockPath | Out-Null
    try { $activity = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
    catch { throw 'Sono aperte altre sessioni o analisi NewPat. Chiuderle al termine del lavoro e ripetere l aggiornamento. Nessuna analisi e stata interrotta.' }
    $packageStream = [IO.File]::Open($package, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    if ($packageStream.Length -ne $record.size) { throw 'Dimensione dell installer modificata. Ripetere il download.' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($sha.ComputeHash($packageStream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($digest -cne $record.sha256) { throw 'SHA-256 dell installer modificato. Nessun file viene eseguito.' }
    Assert-NotCanceled
    if ($bootstrapInstall) {
        # Keep the installed bootstrap immutable while checking/copying it, then
        # release it before Inno replaces application files. The independent copy
        # lets every future update reuse the SAME reviewed executable.
        $bootstrapStream = [IO.File]::Open($setupSource, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $setupDigest = [BitConverter]::ToString($sha.ComputeHash($bootstrapStream)).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        if ($setupDigest -cne $record.setup_sha256) { throw 'SHA-256 del setup stabile modificato. Nessun file viene eseguito.' }
        $copiedSetup = Join-Path $directory 'NewPat-Setup.exe'
        $bootstrapStream.Position = 0
        $output = [IO.File]::Open($copiedSetup, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $bootstrapStream.CopyTo($output) } finally { $output.Dispose() }
        $bootstrapStream.Dispose(); $bootstrapStream = $null
        $bootstrapStream = [IO.File]::Open($copiedSetup, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $copiedDigest = [BitConverter]::ToString($sha.ComputeHash($bootstrapStream)).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        if ($copiedDigest -cne $record.setup_sha256) { throw 'Copia del setup stabile modificata. Nessun file viene eseguito.' }
    }
    $zipDirectory = Join-Path $directory 'verified-zip'
    if ($zipInstall) {
        $python = Join-Path $project '.runtime\python\python.exe'
        $extractor = Join-Path $project 'installer\windows\zip_package.py'
        Write-HandoffLog 'Verifica ed estrazione dello ZIP completo...'
        & $python $extractor extract-update --package $package --destination $zipDirectory --version $record.version --source $record.source_commit --sha256 $record.sha256
        if ($LASTEXITCODE -ne 0) { throw 'Verifica dello ZIP non riuscita. Nessun aggiornamento avviato.' }
    }
    # Inno repeats this exclusive acquisition before modifying any application file.
    $activity.Dispose(); $activity = $null
    $start = New-Object Diagnostics.ProcessStartInfo
    if ($zipInstall) {
        $start.FileName = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $zipWorker = Join-Path $zipDirectory 'app\installer\windows\install-zip.ps1'
        $start.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' + (Quote-HandoffArgument $zipWorker) +
            ' -BundleDirectory ' + (Quote-HandoffArgument $zipDirectory) + ' -InstallRoot ' + (Quote-HandoffArgument $zipRoot)
    } else {
        $start.FileName = $copiedSetup
        $start.Arguments = '/NEWPATUPDATE=1 /NORESTART /RESTARTEXITCODE=3010 /DIR=' + (Quote-HandoffArgument $project) +
            ' /NEWPATPACKAGE=' + (Quote-HandoffArgument $package) +
            ' /NEWPATVERSION=' + (Quote-HandoffArgument $record.version) +
            ' /NEWPATSOURCE=' + (Quote-HandoffArgument $record.source_commit) +
            ' /NEWPATSHA256=' + (Quote-HandoffArgument $record.sha256) +
            ' /NEWPATSIZE=' + (Quote-HandoffArgument ([string]$record.size))
    }
    $start.WorkingDirectory = $directory
    $start.UseShellExecute = $false
    Assert-NotCanceled
    Write-HandoffLog ('Avvio installer NewPat ' + $record.version + '...')
    $installer = [Diagnostics.Process]::Start($start)
    try { $installer.WaitForExit(); $code = $installer.ExitCode } finally { $installer.Dispose() }
    $packageStream.Dispose(); $packageStream = $null
    if ($code -eq 3010) {
        if ($zipInstall) { Write-HandoffLog ('Riavvio di Windows richiesto. Riprendere la preparazione dal collegamento locale in ' + $zipRoot) }
        else { Write-HandoffLog 'Riavvio di Windows richiesto. Riavviare il PC e completare la preparazione dal menu Start.' }
        $result = 3010
    } elseif ($code -ne 0) {
        $resume = if ($zipInstall) { 'dal collegamento locale in ' + $zipRoot } else { 'dal menu Start' }
        throw "Installazione non completata (codice $code). Consultare il setup e riprendere la preparazione $resume."
    } else {
        if ($zipInstall) { $project = (Read-NewPatZipPointer $zipRoot).app_dir }
        # The existing entry point performs the full ready/manifest/runtime binding check.
        $runner = Join-Path $project 'scripts\windows\run.ps1'
        $stateFile = Join-Path $project '.runtime\installer\state.json'
        $state = Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($state.phase -cne 'ready' -or $state.installation_channel -cne 'desktop' -or
            $state.version -cne $record.version -or $state.source_commit -cne $record.source_commit) {
            throw 'Preparazione non conclusa. Completare NewPat tramite il collegamento di preparazione della propria installazione prima di avviare analisi.'
        }
        $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $launch = New-Object Diagnostics.ProcessStartInfo
        $launch.FileName = $powershell
        $launch.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' + (Quote-HandoffArgument $runner) + ' gui'
        $launch.WorkingDirectory = $data
        $launch.UseShellExecute = $false
        $launch.EnvironmentVariables.Remove('NEWPAT_SETUP_ACTIVITY_TOKEN')
        $opened = [Diagnostics.Process]::Start($launch)
        $opened.Dispose()
        Write-HandoffLog 'Installer completato. Avvio di NewPat tramite il controllo dell installazione.'
        $result = 0
    }
} catch {
    $message = $_.Exception.Message
    [IO.File]::WriteAllText((Join-Path $directory 'error.txt'), $message, (New-Object Text.UTF8Encoding($false)))
    Write-HandoffLog ('ERRORE: ' + $message)
} finally {
    if ($null -ne $packageStream) { $packageStream.Dispose() }
    if ($null -ne $bootstrapStream) { $bootstrapStream.Dispose() }
    if ($null -ne $activity) { $activity.Dispose() }
    if ($null -ne $parent) { $parent.Dispose() }
}
if ($result -ne 0 -and -not $NoPause) {
    Write-Host ('Diagnostica: ' + $directory)
    Read-Host 'Premere Invio per chiudere questa finestra' | Out-Null
}
exit $result
