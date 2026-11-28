param(
    [string] $AssetDirectory = '',
    [switch] $Resume,
    [switch] $ManualResume
)

. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
. (Join-Path $PSScriptRoot 'bootstrap-migration.ps1')
. (Join-Path $PSScriptRoot 'activity-lock.ps1')
$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $project 'scripts\windows\common.ps1')
$transcriptStarted = $false
$mutex = $null
$lockHeld = $false
$activityLease = $null
$result = 1
$state = $null
$statePath = Join-Path $project '.runtime\installer\state.json'
$script:NewPatWsl = Join-Path $env:WINDIR 'System32\wsl.exe'
$distro = $null

function Save-NewPatPhase([string] $Phase) {
    $script:state.phase = $Phase
    $script:state.updated_utc = [DateTime]::UtcNow.ToString('o')
    Write-NewPatJsonAtomic $script:statePath $script:state
    Write-Host "NewPat: $Phase"
}

function Request-NewPatReboot {
    Save-NewPatPhase 'awaiting_reboot'
    if ($ManualResume) {
        Write-Host 'WSL richiede un riavvio. Dopo il riavvio aprire il collegamento locale di ripresa nella cartella NewPat.'
        return
    }
    $automaticResume = Register-NewPatResume $script:project
    Write-Host 'WSL richiede un riavvio di Windows. Salva il lavoro e riavvia quando preferisci.'
    if ($automaticResume) {
        Write-Host ('La preparazione riprendera al prossimo accesso; puoi anche aprire ' + $profile.display_name + ' - Resume Setup dal menu Start.')
    } else {
        Write-Host ('Per riprendere dopo il riavvio, aprire ' + $profile.display_name + ' - Resume Setup dal menu Start.')
    }
}

try {
    Assert-NewPatWindowsUser
    Assert-NewPatInstallationLocation $project
    $activityLease = Enter-NewPatInstallationActivity
    $profile = Get-NewPatInstallationProfile
    $manifest = Read-NewPatInstallerManifest (Join-Path $project '.distribution\installer-manifest.json')
    $layout = Read-NewPatInstallLayout $project
    # Inno writes ownership markers before invoking bootstrap. Resume must obey
    # the same destination checks; a missing marker never adopts existing files.
    Assert-NewPatInstallLayout $layout -CheckExisting
    # Reject a foreign state before even creating the log or recovery directory.
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        Assert-NewPatInstallationChannel (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json) 'Lo stato precedente'
    }
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $mutex = New-Object Threading.Mutex($false, ($profile.mutex_prefix + $sid))
    try { $lockHeld = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $lockHeld = $true }
    if (-not $lockHeld) { throw 'Un altra preparazione NewPat e gia in corso. Attendere che termini.' }
    Save-NewPatInstallLayoutHistory $layout
    Initialize-NewPatWritableDirectory (Split-Path -Parent $statePath) 'dello stato installer'
    Start-Transcript -LiteralPath (Join-Path $project '.runtime\installer\setup.log') -Append | Out-Null
    $transcriptStarted = $true
    $recoveryPath = Save-NewPatRecoverySnapshot $project $manifest $layout
    $previous = $null
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $previous = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($previous.schema_version -ne 1) { throw 'Stato installer non riconosciuto. Conservare il log e contattare il supporto.' }
        # A new self-contained setup uses its embedded cache, never a stale path from an older installer.
        if ($Resume -and -not $AssetDirectory -and $previous.PSObject.Properties['asset_directory']) { $AssetDirectory = $previous.asset_directory }
    }
    if ($AssetDirectory) { $AssetDirectory = Resolve-NewPatDirectory $AssetDirectory }
    $state = [ordered]@{
        schema_version = 1; installation_channel = $profile.channel; version = $manifest.version; release_tag = $manifest.release_tag
        source_commit = $manifest.source_commit; runtime_image = $manifest.runtime_image
        resolved_runtime_image = $null; runtime_archive_sha256 = $null
        wsl_distro = $null; rootfs_sha256 = $manifest.assets.rootfs.sha256; recovery_snapshot = $recoveryPath
        app_dir = $layout.app_dir; runtime_dir = $layout.runtime_dir; cache_dir = $layout.cache_dir
        data_dir = $layout.data_dir; runs_dir = $layout.runs_dir
        phase = 'starting'; updated_utc = [DateTime]::UtcNow.ToString('o')
        asset_directory = $AssetDirectory; last_error = $null
    }
    Save-NewPatPhase 'checking_windows'
    $cache = $layout.cache_dir
    $wslDirectory = $layout.runtime_dir
    Initialize-NewPatWritableDirectory $cache 'della cache installer'
    Initialize-NewPatWritableDirectory $wslDirectory 'della distribuzione Linux'
    $wsl = Get-NewPatWslReadiness
    $ready = $wsl.Ready
    Write-Host ("WSL: " + $wsl.Kind + $(if ($wsl.Version) { " (" + $wsl.Version + ")" } else { '' }))
    if (-not $ready) {
        $computer = Get-CimInstance -ClassName Win32_ComputerSystem
        $processors = @(Get-CimInstance -ClassName Win32_Processor)
        if (-not $computer.HypervisorPresent -and
            @($processors | Where-Object { $_.VirtualizationFirmwareEnabled -eq $false }).Count -gt 0) {
            throw 'La virtualizzazione hardware risulta disabilitata. Abilitarla nel BIOS/UEFI o chiedere al reparto IT di abilitarla nella macchina virtuale, quindi riaprire il setup.'
        }
        Save-NewPatPhase 'enabling_wsl'
        Write-Host 'Windows richiedera UAC per abilitare o aggiornare WSL2 da Microsoft. Solo i comandi Windows DISM/WSL vengono elevati; NewPat resta nell account normale. Possono essere richieste piu conferme UAC.'
        $prerequisites = $null
        try {
            $prerequisites = Get-NewPatActivityRuntime -HelperRelativePath 'src/newpat/windows_wsl_prerequisites.py'
            & $prerequisites.Python -B -X utf8 -u $prerequisites.Helper
            $prerequisiteCode = $LASTEXITCODE
        } finally {
            if ($null -ne $prerequisites -and $prerequisites.Temporary -and (Test-Path -LiteralPath $prerequisites.Temporary)) {
                Remove-Item -LiteralPath $prerequisites.Temporary -Recurse -Force
            }
        }
        if ($prerequisiteCode -in @(3010, 1641)) {
            Request-NewPatReboot
            $result = 3010
        } elseif ($prerequisiteCode -eq 50) {
            throw 'Questa installazione Windows/WSL non espone ancora le opzioni richieste. Installare gli aggiornamenti Windows e la versione WSL distribuita da Microsoft, quindi riaprire il setup. Istruzioni: https://learn.microsoft.com/windows/wsl/install'
        } elseif ($prerequisiteCode -eq 1460) {
            throw 'La configurazione WSL ha superato il tempo disponibile. Controllare la connessione e attendere la conclusione delle operazioni Windows prima di riaprire il setup.'
        } elseif ($prerequisiteCode -ne 0) {
            throw "Attivazione WSL non completata (codice $($prerequisiteCode)). Verificare autorizzazioni/policy aziendali con il reparto IT e riprovare."
        } else {
            $wsl = Get-NewPatWslReadiness
            $ready = $wsl.Ready
            if (-not $ready) {
                if ($wsl.Kind -in @('missing', 'legacy')) { throw "WSL non risulta aggiornato. Installare gli aggiornamenti Windows e WSL Microsoft, quindi riaprire il setup. $($wsl.Detail)" }
                if ($Resume) { throw "WSL non e pronto anche dopo la ripresa. Verificare virtualizzazione e policy con il reparto IT. $($wsl.Detail)" }
                Request-NewPatReboot
                $result = 3010
            }
        }
    }
    if ($ready) {
        Save-NewPatPhase 'preparing_runtime'
        $target = Get-NewPatRuntimeTarget $wslDirectory $manifest.assets.rootfs.sha256 @(Get-NewPatWslNames)
        $distro = $target.Distro
        $state.wsl_distro = $distro
        if (-not $target.Registered) { Save-NewPatPhase 'importing_distribution' }
        Initialize-NewPatRuntimeTarget $target $manifest.assets.rootfs $cache $AssetDirectory
        Save-NewPatPhase 'loading_scientific_image'
        Invoke-NewPatWsl @('--distribution', $distro, '--user', 'root', '--exec', '/usr/local/bin/newpat-engine', 'ensure') -TimeoutSeconds 240 | Out-Null
        $runtimeImage = Install-NewPatScientificImage $manifest $cache $AssetDirectory $distro
        $state.resolved_runtime_image = $runtimeImage
        $state.runtime_archive_sha256 = $manifest.assets.scientific_image.sha256
        $configuration = [ordered]@{
            schema_version = 1; installation_channel = $profile.channel; backend = 'wsl'; wsl_distro = $distro
            rootfs_sha256 = $manifest.assets.rootfs.sha256
            runtime_image = $runtimeImage; source_runtime_image = $manifest.runtime_image
            runtime_archive_sha256 = $manifest.assets.scientific_image.sha256
            app_dir = $layout.app_dir; runtime_dir = $layout.runtime_dir; cache_dir = $layout.cache_dir
            data_dir = $layout.data_dir; runs_dir = $layout.runs_dir
            release_tag = $manifest.release_tag; source_commit = $manifest.source_commit
        }
        if (-not (Test-Path -LiteralPath $configuration.data_dir -PathType Container)) {
            [IO.Directory]::CreateDirectory($configuration.data_dir) | Out-Null
        }
        Initialize-NewPatWritableDirectory $configuration.runs_dir 'dei risultati'
        $python = Install-NewPatPython $project
        Save-NewPatPhase 'verifying_installation'
        Complete-NewPatRuntimeActivation $project $statePath $state $configuration {
            $checkLogs = Split-Path -Parent $statePath
            Invoke-NewPatSetupCheck $python @('-X', 'utf8', '-u', '-m', 'newpat', 'doctor', '--runtime') $checkLogs 'doctor'
            Invoke-NewPatSetupCheck $python @('-X', 'utf8', '-u', '-m', 'newpat', 'self-test') $checkLogs 'self-test'
        }
        if (-not $ManualResume) { Unregister-NewPatResume }
        if ($ManualResume) { Write-Host 'Preparazione del runtime ZIP completata.' }
        else { Write-Host ($profile.display_name + ' e pronto. Apri ' + $profile.display_name + ' dal menu Start per scegliere un analisi.') }
        Write-Host "Applicazione: $($configuration.app_dir)"
        Write-Host "Ambiente WSL: $($configuration.runtime_dir)"
        Write-Host "Cache installazione: $($configuration.cache_dir)"
        Write-Host "Dati: $($configuration.data_dir)"
        Write-Host "Risultati: $($configuration.runs_dir)"
        $result = 0
    }
} catch {
    $message = $_.Exception.Message
    Write-Host ("ERRORE: " + $message) -ForegroundColor Red
    if ($null -ne $state -and $lockHeld) {
        $state.last_error = $message
        try { Save-NewPatPhase 'failed' } catch { Write-Host 'Impossibile aggiornare lo stato installer.' }
    }
} finally {
    try {
        if ($transcriptStarted) { Stop-Transcript | Out-Null }
    } finally {
        try {
            if ($lockHeld) { $mutex.ReleaseMutex() }
        } finally {
            try { if ($null -ne $mutex) { $mutex.Dispose() } }
            finally { Exit-NewPatInstallationActivity $activityLease }
        }
    }
}
exit $result
