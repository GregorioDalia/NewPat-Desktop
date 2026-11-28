# Helpers for resumable runtime preparation. No distribution is removed or replaced.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-NewPatOwnership([string] $Path, [string] $Distro) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $record = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-NewPatInstallationChannel $record 'Il registro di proprieta'
    if ($record.schema_version -ne 1 -or $record.distro -cne $Distro -or
        $record.owner_id -cnotmatch '^[a-f0-9]{32}$' -or
        $record.rootfs_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        $record.status -notin @('importing', 'owned')) {
        throw "Registro di proprieta non valido: $Path. Nessuna distribuzione viene modificata."
    }
    return $record
}

function Get-NewPatRuntimeTarget([string] $WslDirectory, [string] $RootfsSha256, [string[]] $Names) {
    if ($RootfsSha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Identita rootfs non valida.' }
    $distro = Get-NewPatRuntimeDistroName $RootfsSha256 $WslDirectory
    $recordPath = Join-Path (Join-Path $WslDirectory 'registrations') ($distro + '.json')
    $ownership = Read-NewPatOwnership $recordPath $distro
    if ($null -ne $ownership -and $ownership.rootfs_sha256 -cne $RootfsSha256) {
        throw 'Conflitto tra nome della distribuzione e identita completa del rootfs. Nessuna sostituzione viene eseguita.'
    }
    $registered = $Names -contains $distro
    if ($registered -and $null -eq $ownership) {
        throw "La distribuzione $distro esiste senza il registro di proprieta NewPat. Nessuna modifica viene eseguita."
    }
    return [pscustomobject]@{
        Distro = $distro; Directory = (Join-Path $WslDirectory $distro)
        OwnershipPath = $recordPath; Ownership = $ownership
        Registered = $registered; RootfsSha256 = $RootfsSha256
    }
}

function Assert-NewPatRuntimeOwner($Target, [switch] $AllowInitialize) {
    Assert-NewPatDistroLocation $Target.Distro $Target.Directory
    $prefix = @('--distribution', $Target.Distro, '--user', 'root', '--exec')
    $product = Invoke-NewPatWsl ($prefix + @('/usr/bin/cat', '/etc/newpat-runtime-id'))
    if ($product.Text -cne 'newpat-runtime-v1') { throw 'Il contenuto della distribuzione non e un runtime NewPat riconosciuto.' }
    $owner = Invoke-NewPatWsl ($prefix + @('/usr/bin/cat', '/var/lib/newpat/owner-id')) -AllowFailure
    if ($owner.ExitCode -ne 0 -and $AllowInitialize -and
        $Target.Ownership.status -ceq 'importing') {
        Invoke-NewPatWsl ($prefix + @('/usr/bin/install', '-d', '-m', '0700', '/var/lib/newpat')) | Out-Null
        # Only a validated hexadecimal ownership token crosses this fixed shell script as argv.
        Invoke-NewPatWsl ($prefix + @('/bin/sh', '-c', 'printf "%s\n" "$1" > /var/lib/newpat/owner-id',
            'newpat-owner', $Target.Ownership.owner_id)) | Out-Null
        $owner = Invoke-NewPatWsl ($prefix + @('/usr/bin/cat', '/var/lib/newpat/owner-id'))
    }
    if ($owner.ExitCode -ne 0 -or $owner.Text -cne $Target.Ownership.owner_id) {
        throw 'Il marcatore di proprieta della distribuzione non corrisponde. Nessuna selezione del runtime viene applicata.'
    }
}

function Assert-NewPatRuntimeTargetReceipt($Target, $RootfsAsset) {
    $directory = Resolve-NewPatInstallPath $Target.Directory
    $runtimeDirectory = Split-Path -Parent $directory
    Assert-NewPatRuntimeNamespace $Target.Distro $Target.RootfsSha256 $runtimeDirectory
    if ($RootfsAsset.sha256 -cne $Target.RootfsSha256 -or
        $directory -ine (Join-Path $runtimeDirectory $Target.Distro)) {
        throw 'La destinazione del runtime non corrisponde al namespace e al rootfs richiesti.'
    }
    $receiptDirectory = Join-Path $runtimeDirectory 'registrations'
    $expectedReceipt = Join-Path $receiptDirectory ($Target.Distro + '.json')
    if ([IO.Path]::GetFullPath($Target.OwnershipPath) -ine $expectedReceipt) {
        throw 'Il registro di proprieta non appartiene alla destinazione del runtime.'
    }
    Assert-NewPatInstallPathWithoutLinks $directory
    Assert-NewPatInstallPathWithoutLinks $receiptDirectory
    if ((Test-Path -LiteralPath $expectedReceipt) -and
        ((Get-Item -LiteralPath $expectedReceipt -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Il registro di proprieta del runtime non puo essere un collegamento.'
    }
    $current = Read-NewPatOwnership $expectedReceipt $Target.Distro
    if (($null -eq $current) -ne ($null -eq $Target.Ownership)) {
        throw 'Il registro di proprieta e cambiato durante la preparazione. Riprovare il setup.'
    }
    if ($Target.Registered -and $null -eq $current) {
        throw 'La distribuzione registrata non dispone di un registro di proprieta NewPat verificato.'
    }
    if ($null -ne $current) {
        if ($current.rootfs_sha256 -cne $Target.RootfsSha256 -or
            $current.owner_id -cne $Target.Ownership.owner_id -or
            $current.status -cne $Target.Ownership.status) {
            throw 'Il registro di proprieta non corrisponde al runtime selezionato. Nessun file viene modificato.'
        }
    }
}

function Assert-NewPatEmptyRuntimeDestination([string] $Directory) {
    Assert-NewPatInstallPathWithoutLinks $Directory
    if ((Test-Path -LiteralPath $Directory) -and
        @(Get-ChildItem -LiteralPath $Directory -Force).Count -gt 0) {
        throw "La cartella $Directory contiene gia file senza una registrazione WSL. Nessun file viene sovrascritto."
    }
}

function Initialize-NewPatRuntimeTarget($Target, $RootfsAsset, [string] $CacheDirectory, [string] $AssetDirectory) {
    Assert-NewPatRuntimeTargetReceipt $Target $RootfsAsset
    if (-not $Target.Registered) {
        Assert-NewPatEmptyRuntimeDestination $Target.Directory
        if (@(Get-NewPatWslNames) -contains $Target.Distro) {
            throw 'La distribuzione e stata registrata durante la preparazione. Nessuna registrazione viene sostituita; riprovare il setup.'
        }
        $rootfs = Get-NewPatAsset $RootfsAsset $CacheDirectory $AssetDirectory
        # Asset preparation can take several minutes. Recheck the registration,
        # destination and receipt immediately before writing recovery metadata.
        Assert-NewPatRuntimeTargetReceipt $Target $RootfsAsset
        Assert-NewPatEmptyRuntimeDestination $Target.Directory
        if (@(Get-NewPatWslNames) -contains $Target.Distro) {
            throw 'La distribuzione e stata registrata durante la preparazione. Nessuna registrazione viene sostituita; riprovare il setup.'
        }
        $ownership = $Target.Ownership
        if ($null -ne $ownership -and $ownership.status -ceq 'owned') {
            # A user may have unregistered this owned Desktop runtime manually. Only an
            # absent registration plus an empty destination permits recreation.
            # Preserve the exact old receipt outside the active registrations.
            $history = Join-Path (Split-Path -Parent $Target.Directory) 'registration-history'
            Assert-NewPatInstallPathWithoutLinks $history
            [IO.Directory]::CreateDirectory($history) | Out-Null
            $backup = Join-Path $history ($Target.Distro + '-' + [Guid]::NewGuid().ToString('N') + '.json')
            [IO.File]::Copy($Target.OwnershipPath, $backup, $false)
            $saved = Read-NewPatOwnership $backup $Target.Distro
            if ($saved.owner_id -cne $ownership.owner_id -or $saved.status -cne 'owned' -or
                $saved.rootfs_sha256 -cne $Target.RootfsSha256 -or
                (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash -cne
                (Get-FileHash -LiteralPath $Target.OwnershipPath -Algorithm SHA256).Hash) {
                throw 'Il registro precedente e cambiato durante il recupero. Nessuna nuova importazione viene eseguita.'
            }
            Write-Host "Ripristino della distribuzione NewPat assente. Registro precedente conservato: $backup"
            $ownership = $null
        }
        if ($null -eq $ownership) {
            $ownership = [pscustomobject]@{
                schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; distro = $Target.Distro; owner_id = [Guid]::NewGuid().ToString('N')
                rootfs_sha256 = $Target.RootfsSha256; status = 'importing'
            }
        }
        Write-NewPatJsonAtomic $Target.OwnershipPath $ownership
        $Target.Ownership = $ownership
        Invoke-NewPatWsl @('--import', $Target.Distro, $Target.Directory, $rootfs, '--version', '2') | Out-Null
        $Target.Registered = $true
    }
    Assert-NewPatRuntimeOwner $Target -AllowInitialize
    if ($Target.Ownership.status -ne 'owned') {
        $Target.Ownership.status = 'owned'
        Write-NewPatJsonAtomic $Target.OwnershipPath $Target.Ownership
    }
}

function Save-NewPatRecoverySnapshot([string] $Project, $Manifest, $Layout = $null) {
    foreach ($relative in @('.runtime/installer/state.json', '.runtime/backend.json')) {
        $existing = Join-Path $Project $relative
        if (Test-Path -LiteralPath $existing -PathType Leaf) {
            Assert-NewPatInstallationChannel (Get-Content -LiteralPath $existing -Raw -Encoding UTF8 | ConvertFrom-Json) $relative
        }
    }
    $layoutDigest = ''
    if ($null -ne $Layout) {
        $paths = @('app_dir', 'runtime_dir', 'cache_dir', 'data_dir', 'runs_dir') | ForEach-Object {
            [IO.Path]::GetFullPath([string]$Layout.$_).TrimEnd('\').ToLowerInvariant()
        }
        $hasher = [Security.Cryptography.SHA256]::Create()
        try {
            $layoutDigest = ([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($paths -join "`n"))))).Replace('-', '').ToLowerInvariant()
        } finally { $hasher.Dispose() }
    }
    $name = $Manifest.source_commit + '-' + $Manifest.assets.rootfs.sha256.Substring(0, 16)
    if ($layoutDigest) { $name += '-' + $layoutDigest.Substring(0, 16) }
    $name += '.json'
    $path = Join-Path (Join-Path $Project '.runtime\installer\recovery') $name
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $snapshot = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-NewPatInstallationChannel $snapshot 'Il registro di recupero'
        if ($snapshot.schema_version -ne 1 -or $snapshot.target_source_commit -cne $Manifest.source_commit -or
            $snapshot.target_rootfs_sha256 -cne $Manifest.assets.rootfs.sha256) {
            throw 'Il registro di recupero esistente non corrisponde alla preparazione richiesta.'
        }
        if ($layoutDigest -and ($null -eq $snapshot.PSObject.Properties['target_layout_sha256'] -or
            $snapshot.target_layout_sha256 -cne $layoutDigest)) {
            throw 'Il registro di recupero esistente non corrisponde alle cartelle selezionate.'
        }
        return $path
    }
    $files = [ordered]@{}
    foreach ($relative in @('.runtime/installer/state.json', '.runtime/backend.json', '.runtime/runtime-image.txt')) {
        $original = Join-Path $Project $relative
        if (Test-Path -LiteralPath $original -PathType Leaf) {
            $files[$relative] = [ordered]@{
                sha256 = (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant()
                content_base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($original))
            }
        }
    }
    Write-NewPatJsonAtomic $path ([ordered]@{
        schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; target_source_commit = $Manifest.source_commit
        target_rootfs_sha256 = $Manifest.assets.rootfs.sha256
        target_layout_sha256 = $layoutDigest
        created_utc = [DateTime]::UtcNow.ToString('o'); previous_files = $files
    })
    return $path
}

function Get-NewPatPreviousDataRoots([string] $Project, [string] $BaseDirectory) {
    $path = Join-Path $Project '.runtime\backend.json'
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $configuration = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-NewPatInstallationChannel $configuration 'La configurazione precedente'
        if ($configuration.schema_version -ne 1 -or $configuration.backend -cne 'wsl' -or
            $configuration.runtime_image -cnotmatch '^sha256:[a-f0-9]{64}$' -or
            [string]::IsNullOrWhiteSpace($configuration.data_dir) -or
            [string]::IsNullOrWhiteSpace($configuration.runs_dir) -or
            -not [IO.Path]::IsPathRooted($configuration.data_dir) -or
            -not [IO.Path]::IsPathRooted($configuration.runs_dir)) {
            throw 'La configurazione precedente non e valida. Conservare backend.json e contattare il supporto.'
        }
        $runtimeDirectory = ''
        if ($null -ne $configuration.PSObject.Properties['runtime_dir']) { $runtimeDirectory = [string]$configuration.runtime_dir }
        Assert-NewPatRuntimeNamespace $configuration.wsl_distro $configuration.rootfs_sha256 $runtimeDirectory
        return [pscustomobject]@{ data_dir = $configuration.data_dir; runs_dir = $configuration.runs_dir }
    }
    return [pscustomobject]@{
        data_dir = (Join-Path $BaseDirectory 'data'); runs_dir = (Join-Path $BaseDirectory 'runs')
    }
}

function Complete-NewPatRuntimeActivation([string] $Project, [string] $StatePath, $State, $Configuration, [scriptblock] $Verify) {
    Assert-NewPatInstallationChannel $State 'Lo stato candidato'
    Assert-NewPatInstallationChannel $Configuration 'La configurazione candidata'
    $runtimeDirectory = ''
    if ($Configuration -is [Collections.IDictionary]) {
        if ($Configuration.Contains('runtime_dir')) { $runtimeDirectory = [string]$Configuration.runtime_dir }
    } elseif ($null -ne $Configuration.PSObject.Properties['runtime_dir']) {
        $runtimeDirectory = [string]$Configuration.runtime_dir
    }
    $stateRuntimeDirectory = ''
    if ($State -is [Collections.IDictionary]) {
        if ($State.Contains('runtime_dir')) { $stateRuntimeDirectory = [string]$State.runtime_dir }
    } elseif ($null -ne $State.PSObject.Properties['runtime_dir']) {
        $stateRuntimeDirectory = [string]$State.runtime_dir
    }
    Assert-NewPatRuntimeNamespace $Configuration.wsl_distro $Configuration.rootfs_sha256 $runtimeDirectory
    Assert-NewPatRuntimeNamespace $State.wsl_distro $State.rootfs_sha256 $stateRuntimeDirectory
    if ($State.wsl_distro -cne $Configuration.wsl_distro -or $State.rootfs_sha256 -cne $Configuration.rootfs_sha256) {
        throw 'Lo stato di preparazione e la configurazione candidata selezionano runtime diversi.'
    }
    if ($runtimeDirectory -or $stateRuntimeDirectory) {
        if ([string]::IsNullOrWhiteSpace($runtimeDirectory) -or [string]::IsNullOrWhiteSpace($stateRuntimeDirectory) -or
            [IO.Path]::GetFullPath($runtimeDirectory).TrimEnd('\') -ine [IO.Path]::GetFullPath($stateRuntimeDirectory).TrimEnd('\')) {
            throw 'La cartella del runtime candidato non corrisponde allo stato di preparazione.'
        }
    }
    # Tests run with a candidate environment while backend.json still selects the old runtime.
    # Ready state is the final activation gate; an interrupted commit remains blocked and resumable.
    $candidate = [ordered]@{
        NEWPAT_PROJECT_DIR = $Project; NEWPAT_BACKEND = 'wsl'; NEWPAT_WSL_DISTRO = $Configuration.wsl_distro
        NEWPAT_RUNTIME_IMAGE = $Configuration.runtime_image; NEWPAT_DATA_DIR = $Configuration.data_dir
        NEWPAT_RUNS_DIR = $Configuration.runs_dir; NEWPAT_WORKSPACE_DIR = (Split-Path -Parent $Configuration.data_dir)
    }
    $previousEnvironment = @{}
    try {
        foreach ($name in $candidate.Keys) {
            $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, $candidate[$name], 'Process')
        }
        & $Verify
        Write-NewPatJsonAtomic (Join-Path $Project '.runtime\backend.json') $Configuration
        $Configuration.runtime_image | Set-Content -LiteralPath (Join-Path $Project '.runtime\runtime-image.txt') -Encoding ASCII
        $State.phase = 'ready'
        $State.updated_utc = [DateTime]::UtcNow.ToString('o')
        Write-NewPatJsonAtomic $StatePath $State
        Write-Host 'NewPat: ready'
    } finally {
        foreach ($name in $previousEnvironment.Keys) {
            if ($null -eq $previousEnvironment[$name]) {
                Remove-Item -LiteralPath ('Env:' + $name) -ErrorAction SilentlyContinue
            } else {
                [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
            }
        }
    }
}
