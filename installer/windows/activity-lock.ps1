# Exclusive process-lifetime lease for setup/resume/removal. Dot-sourcing has no side effects.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-NipatActivityRuntime([string] $Directory = $PSScriptRoot,
    [ValidateSet('src/nipat/windows_install_activity.py', 'src/nipat/windows_wsl_prerequisites.py')]
    [string] $HelperRelativePath = 'src/nipat/windows_install_activity.py') {
    $project = Split-Path -Parent (Split-Path -Parent $Directory)
    $helper = Join-Path $project $HelperRelativePath
    Assert-NipatActivityPathWithoutLinks $helper
    if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
        throw 'Componente di coordinamento Python assente. Ripristinare il pacchetto NewPat.'
    }
    $manifestPath = Join-Path $project '.distribution\installer-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        # Developer/CI checkouts only. Installed applications never select a
        # Python from PATH and never download an interpreter before acquiring a lease.
        $python = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
        return [pscustomobject]@{ Python = $python; Helper = $helper; Temporary = $null }
    }
    $inventoryPath = Join-Path $project '.distribution\application-files.json'
    if (-not (Test-Path -LiteralPath $inventoryPath -PathType Leaf)) {
        throw 'Inventario del pacchetto NewPat mancante. Ripristinare il pacchetto.'
    }
    $inventory = Get-Content -LiteralPath $inventoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $entries = @($inventory.files | Where-Object { $_.path -ceq $HelperRelativePath })
    if ($inventory.schema_version -ne 1 -or $inventory.installation_channel -cne 'desktop' -or
        $inventory.source_commit -cne $manifest.source_commit -or $entries.Count -ne 1 -or
        $entries[0].sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entries[0].sha256) {
        throw 'Il componente di coordinamento Python non corrisponde al pacchetto verificato.'
    }
    $archive = Join-Path $project '.distribution\python-3.12.10-embed-amd64.zip'
    Assert-NipatActivityPathWithoutLinks $archive
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf) -or
        (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -cne
            '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3') {
        throw 'Archivio Python del pacchetto assente o non integro. Ripristinare NewPat.'
    }
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ('nipat-activity-python-' + [Guid]::NewGuid().ToString('N'))
    Assert-NipatActivityPathWithoutLinks $temporary
    try {
        # The installed Python may be repaired while setup owns the lease. Use
        # a private copy, leaving every installed byte untouched before locking.
        Expand-Archive -LiteralPath $archive -DestinationPath $temporary
        return [pscustomobject]@{ Python = (Join-Path $temporary 'python.exe'); Helper = $helper; Temporary = $temporary }
    } catch {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
        throw
    }
}

function Test-NipatInheritedActivity {
    $token = [Environment]::GetEnvironmentVariable('NIPAT_SETUP_ACTIVITY_TOKEN', 'Process')
    if ($token -cnotmatch '^[1-9][0-9]{0,9}:[a-f0-9]{32}$') { return $false }
    $runtime = $null
    $process = $null
    try {
        $runtime = Get-NipatActivityRuntime
        $start = New-Object Diagnostics.ProcessStartInfo
        $start.FileName = $runtime.Python
        # Windows paths cannot contain double quotes; no shell interprets these arguments.
        $start.Arguments = '-B -X utf8 "' + $runtime.Helper + '" ' + [string]$PID
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $process = [Diagnostics.Process]::Start($start)
        if (-not $process.WaitForExit(30000)) {
            $process.Kill()
            [void]$process.WaitForExit(5000)
            throw 'Il controllo del coordinamento NewPat ha superato il tempo disponibile.'
        }
        if ($process.ExitCode -notin @(0, 1)) { throw 'Impossibile verificare il coordinamento della preparazione NewPat.' }
        return $process.ExitCode -eq 0
    } finally {
        if ($null -ne $process) { $process.Dispose() }
        if ($null -ne $runtime -and $runtime.Temporary -and (Test-Path -LiteralPath $runtime.Temporary)) {
            Remove-Item -LiteralPath $runtime.Temporary -Recurse -Force
        }
    }
}

function Assert-NipatActivityPathWithoutLinks([string] $Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'La cartella di coordinamento NewPat non puo attraversare collegamenti o junction.'
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd('\'))
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
}

function Get-NipatActivityLockPath {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA) -or $env:LOCALAPPDATA -notmatch '^[A-Za-z]:[\\/]') {
        throw 'LOCALAPPDATA non disponibile per coordinare le sessioni NewPat.'
    }
    $path = Join-Path (Join-Path $env:LOCALAPPDATA 'NIPAT-Desktop') 'activity.lock'
    Assert-NipatActivityPathWithoutLinks $path
    [IO.Directory]::CreateDirectory((Split-Path -Parent $path)) | Out-Null
    Assert-NipatActivityPathWithoutLinks $path
    return $path
}

function Enter-NipatInstallationActivity {
    $previousToken = [Environment]::GetEnvironmentVariable('NIPAT_SETUP_ACTIVITY_TOKEN', 'Process')
    if (Test-NipatInheritedActivity) {
        # The actual ancestor keeps both the exclusive file handle and event alive.
        return [pscustomobject]@{ Borrowed = $true; Handle = $null; Event = $null; Token = $previousToken }
    }
    $handle = $null
    $event = $null
    try {
        $path = Get-NipatActivityLockPath
        try { $handle = [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
        catch {
            throw 'NewPat non e disponibile per la preparazione: attendere il termine delle analisi e chiudere tutte le finestre NewPat, quindi riprovare. Nessuna sessione viene interrotta.'
        }
        $nonce = [Guid]::NewGuid().ToString('N')
        $created = $false
        $event = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset,
            ('Local\NIPAT-Desktop-SetupLease-' + $nonce), [ref] $created)
        if (-not $created) { throw 'Il coordinamento temporaneo NewPat non e stato creato; riprovare.' }
        $token = "$PID`:$nonce"
        [Environment]::SetEnvironmentVariable('NIPAT_SETUP_ACTIVITY_TOKEN', $token, 'Process')
        return [pscustomobject]@{ Borrowed = $false; Handle = $handle; Event = $event; Token = $token }
    } catch {
        [Environment]::SetEnvironmentVariable('NIPAT_SETUP_ACTIVITY_TOKEN', $null, 'Process')
        if ($null -ne $event) { $event.Dispose() }
        if ($null -ne $handle) { $handle.Dispose() }
        throw
    }
}

function Exit-NipatInstallationActivity($Lease) {
    if ($null -eq $Lease -or $Lease.Borrowed) { return }
    try {
        [Environment]::SetEnvironmentVariable('NIPAT_SETUP_ACTIVITY_TOKEN', $null, 'Process')
        if ($null -ne $Lease.Event) { $Lease.Event.Dispose() }
    } finally {
        if ($null -ne $Lease.Handle) { $Lease.Handle.Dispose() }
    }
}
