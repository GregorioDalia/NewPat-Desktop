# Per-user Windows destinations. This module performs no work when imported.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-NewPatInstallPath([string] $Path, [switch] $AllowUnavailable) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -cnotmatch '^[A-Za-z]:[\\/]' -or
        $Path.Substring(2) -match '[<>:"|?*\x00-\x1f]') {
        throw "Usare un percorso assoluto su un disco locale: $Path"
    }
    $value = [IO.Path]::GetFullPath($Path.Replace('/', '\')).TrimEnd('\')
    if ($value.Length -le 2) { throw 'Selezionare una sottocartella, non la radice del disco.' }
    foreach ($part in $value.Substring(3).Split('\')) {
        if ($part -match '[. ]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw "Nome di cartella non supportato da Windows: $Path"
        }
    }
    if (-not $AllowUnavailable) {
        $drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($value))
        if (-not $drive.IsReady -or $drive.DriveType -ne [IO.DriveType]::Fixed) {
            throw "La destinazione deve essere su un disco locale fisso disponibile: $Path"
        }
    }
    return $value
}

function Test-NewPatInstallPathOverlap([string] $First, [string] $Second) {
    $a = [IO.Path]::GetFullPath($First).TrimEnd('\')
    $b = [IO.Path]::GetFullPath($Second).TrimEnd('\')
    return $a.Equals($b, [StringComparison]::OrdinalIgnoreCase) -or
        $a.StartsWith($b + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $b.StartsWith($a + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NewPatInstallPathWithoutLinks([string] $Path, [switch] $Tree) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "La destinazione contiene un collegamento o junction: $current"
            }
            if (-not $item.PSIsContainer) { throw "La destinazione contiene un file al posto di una cartella: $current" }
        }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd('\'))
        if ($parent -eq $current) { break }
        $current = $parent
    }
    if ($Tree -and (Test-Path -LiteralPath $Path -PathType Container)) {
        # Inspect one level at a time, rejecting links before any traversal.
        foreach ($item in Get-ChildItem -LiteralPath $Path -Force) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "La cartella gestita contiene un collegamento o junction: $($item.FullName)"
            }
            if ($item.PSIsContainer) { Assert-NewPatInstallPathWithoutLinks $item.FullName -Tree }
        }
    }
}

function Test-NewPatStorageMarker([string] $Path, [string] $Role) {
    $name = if ($Role -ceq 'application') { '.newpat-app.ini' } else { '.newpat-storage.ini' }
    $marker = Join-Path $Path $name
    if (-not (Test-Path -LiteralPath $marker)) { return $false }
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf) -or
        ((Get-Item -LiteralPath $marker -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Marcatore NewPat non valido: $marker"
    }
    $lines = @(Get-Content -LiteralPath $marker -Encoding UTF8 | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($lines.Count -ne 4 -or $lines[0] -cne '[NewPat]') { throw "Marcatore NewPat non valido: $marker" }
    $values = @{}
    foreach ($line in $lines[1..3]) {
        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2 -or $parts[0] -cnotin @('schema_version', 'installation_channel', 'role') -or
            $values.ContainsKey($parts[0])) { throw "Marcatore NewPat non valido: $marker" }
        $values[$parts[0]] = $parts[1]
    }
    if ($values.Count -ne 3 -or $values['schema_version'] -cne '1' -or
        $values['installation_channel'] -cne (Get-NewPatInstallationProfile).channel -or
        $values['role'] -cne $Role) { throw "Cartella appartenente a un altro ambiente: $Path" }
    return $true
}

function Get-NewPatDefaultInstallLayout([string] $Project = '') {
    $profile = Get-NewPatInstallationProfile
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA non disponibile.' }
    $base = Join-Path $env:LOCALAPPDATA $profile.data_dir_name
    if (-not $Project) { $Project = Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') $profile.app_dir_name }
    return [pscustomobject][ordered]@{
        schema_version = 1; installation_channel = $profile.channel; app_dir = $Project
        runtime_dir = (Join-Path $base 'wsl'); cache_dir = (Join-Path $base 'cache')
        data_dir = (Join-Path $base 'data'); runs_dir = (Join-Path $base 'runs')
    }
}

function Assert-NewPatInstallWritableParent([string] $Path) {
    $parent = $Path
    while (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        $parent = [IO.Path]::GetDirectoryName($parent)
        if (-not $parent) { throw "Destinazione non disponibile: $Path" }
    }
    $probe = Join-Path $parent ('.newpat-install-check-' + [Guid]::NewGuid().ToString('N'))
    $created = $false
    try {
        $stream = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true
        $stream.Dispose()
    } catch { throw "Il tuo account non puo scrivere nella destinazione: $Path. $($_.Exception.Message)" }
    finally { if ($created) { [IO.File]::Delete($probe) } }
}

function Get-NewPatApplicationKind([string] $Path) {
    $Path = Resolve-NewPatInstallPath $Path
    Assert-NewPatInstallPathWithoutLinks $Path -Tree
    if (-not (Test-Path -LiteralPath $Path) -or @(Get-ChildItem -LiteralPath $Path -Force).Count -eq 0) { return 'empty' }
    if (Test-Path -LiteralPath (Join-Path $Path '.git')) { throw 'Selezionare una cartella di installazione, non il checkout del progetto.' }
    if (Test-NewPatStorageMarker $Path 'application') { return 'installed' }
    $profileFile = Join-Path $Path 'installer\windows\install-profile.json'
    if (Test-Path -LiteralPath $profileFile -PathType Leaf) {
        Assert-NewPatInstallationProfile (Get-Content -LiteralPath $profileFile -Raw -Encoding UTF8 | ConvertFrom-Json)
        return 'installed'
    }
    return 'unknown'
}

function Assert-NewPatExistingApplication([string] $Path) {
    if ((Get-NewPatApplicationKind $Path) -ceq 'unknown') {
        throw "La cartella applicativa contiene file non riconosciuti. Scegliere una cartella vuota: $Path"
    }
}

function Assert-NewPatInstallLayout($Layout, [switch] $CheckExisting, [switch] $Historical) {
    if ($Historical -and $CheckExisting) { throw 'Le destinazioni storiche non possono autorizzare una nuova installazione.' }
    if ($Layout -is [Collections.IDictionary]) { $Layout = [pscustomobject]$Layout }
    $fields = @('app_dir', 'runtime_dir', 'cache_dir', 'data_dir', 'runs_dir')
    if ($null -eq $Layout -or @($Layout.PSObject.Properties).Count -ne 7 -or
        -not (($Layout.schema_version -is [int]) -or ($Layout.schema_version -is [long])) -or
        $Layout.schema_version -ne 1) { throw 'Configurazione delle cartelle NewPat non valida.' }
    Assert-NewPatInstallationChannel $Layout 'Le cartelle selezionate'
    $protected = @((Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\installations'),
        (Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\preferences.json'),
        (Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\activity.lock'))
    foreach ($name in @('WINDIR', 'ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) { $protected += $value }
    }
    foreach ($field in $fields) {
        if ($null -eq $Layout.PSObject.Properties[$field] -or -not ($Layout.$field -is [string])) {
            throw "Destinazione NewPat mancante: $field"
        }
        $resolved = Resolve-NewPatInstallPath $Layout.$field -AllowUnavailable:$Historical
        if ($resolved -ine $Layout.$field.TrimEnd('\')) { throw "Usare un percorso completo senza componenti relativi: $($Layout.$field)" }
        foreach ($path in $protected) {
            if (Test-NewPatInstallPathOverlap $resolved $path) { throw "Destinazione riservata al sistema o a un altro ambiente NewPat: $resolved" }
        }
        if (-not $Historical) {
            Assert-NewPatInstallPathWithoutLinks $resolved -Tree:($field -in @('app_dir', 'runtime_dir', 'cache_dir'))
        }
    }
    for ($i = 0; $i -lt $fields.Count; $i++) {
        for ($j = $i + 1; $j -lt $fields.Count; $j++) {
            if (Test-NewPatInstallPathOverlap $Layout.($fields[$i]) $Layout.($fields[$j])) {
                throw "Le cartelle $($fields[$i]) e $($fields[$j]) devono essere separate e non contenersi a vicenda."
            }
        }
    }
    if ($CheckExisting) {
        Assert-NewPatExistingApplication $Layout.app_dir
        # Retained analysis folders remain protected when the user changes the
        # destinations of an installation or reinstalls after removing the app.
        foreach ($known in @(Get-NewPatKnownInstallLayouts '')) {
            foreach ($managed in @('app_dir', 'runtime_dir', 'cache_dir')) {
                foreach ($previousManaged in @('app_dir', 'runtime_dir', 'cache_dir')) {
                    if ($managed -cne $previousManaged -and
                        (Test-NewPatInstallPathOverlap $Layout.$managed $known.$previousManaged)) {
                        throw 'Una destinazione si sovrappone a componenti conservati con un altro ruolo. Scegliere cartelle separate per applicazione, runtime e cache.'
                    }
                }
                foreach ($research in @('data_dir', 'runs_dir')) {
                    if ((Test-NewPatInstallPathOverlap $Layout.$managed $known.$research) -or
                        (Test-NewPatInstallPathOverlap $Layout.$research $known.$managed)) {
                        throw 'Una destinazione si sovrappone a cartelle di analisi o componenti conservati da una precedente installazione. Scegliere cartelle separate.'
                    }
                }
            }
        }
        foreach ($field in @('runtime_dir', 'cache_dir')) {
            $path = $Layout.$field
            $role = if ($field -ceq 'runtime_dir') { 'runtime' } else { 'cache' }
            if (Test-Path -LiteralPath $path -PathType Container) {
                $marked = Test-NewPatStorageMarker $path $role
                if (-not $marked -and @(Get-ChildItem -LiteralPath $path -Force).Count -gt 0) {
                    throw "La cartella $role contiene file non riconosciuti. Scegliere una cartella vuota: $path"
                }
            }
        }
        foreach ($field in $fields) { Assert-NewPatInstallWritableParent $Layout.$field }
    }
}

function Read-NewPatInstallLayout([string] $Project, [switch] $Historical) {
    $file = Join-Path $Project '.runtime\install-layout.json'
    if (Test-Path -LiteralPath $file -PathType Leaf) {
        $layout = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        $layout = Get-NewPatDefaultInstallLayout $Project
    }
    Assert-NewPatInstallLayout $layout -Historical:$Historical
    if ((Resolve-NewPatInstallPath $Project -AllowUnavailable:$Historical) -ine $layout.app_dir) {
        throw 'La cartella dell applicazione non corrisponde alla configurazione. Reinstallare nella destinazione scelta.'
    }
    return $layout
}

function Get-NewPatRuntimeDistroName([string] $RootfsSha256, [string] $RuntimeDirectory) {
    if ($RootfsSha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Identita rootfs non valida.' }
    $canonical = (Resolve-NewPatInstallPath $RuntimeDirectory).ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    # Bind each runtime to its rootfs bytes and storage destination.
    return (Get-NewPatInstallationProfile).distro_prefix + $RootfsSha256.Substring(0, 32) + '-' + $digest.Substring(0, 12)
}

function Get-NewPatInstallLayoutHistoryDirectory {
    return Join-Path (Join-Path $env:LOCALAPPDATA (Get-NewPatInstallationProfile).data_dir_name) 'installations'
}

function Save-NewPatInstallLayoutHistory($Layout) {
    Assert-NewPatInstallLayout $Layout
    $directory = Get-NewPatInstallLayoutHistoryDirectory
    Assert-NewPatInstallPathWithoutLinks $directory -Tree
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $json = $Layout | ConvertTo-Json -Depth 4
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($json))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    Write-NewPatJsonAtomic (Join-Path $directory ($digest + '.json')) $Layout
}

function Get-NewPatKnownInstallLayouts([string] $Project) {
    $layouts = @()
    $directory = Get-NewPatInstallLayoutHistoryDirectory
    Assert-NewPatInstallPathWithoutLinks $directory -Tree
    if (Test-Path -LiteralPath $directory -PathType Container) {
        foreach ($file in Get-ChildItem -LiteralPath $directory -Filter '*.json' -File) {
            $layout = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            Assert-NewPatInstallLayout $layout -Historical
            $layouts += $layout
        }
    }
    $defaults = Get-NewPatDefaultInstallLayout
    Assert-NewPatInstallLayout $defaults -Historical
    $layouts += $defaults
    if (Test-Path -LiteralPath (Join-Path $defaults.app_dir '.runtime\backend.json') -PathType Leaf) {
        $layouts += Read-NewPatInstallLayout $defaults.app_dir -Historical
    }
    if ($Project -and (Test-Path -LiteralPath $Project -PathType Container)) { $layouts += Read-NewPatInstallLayout $Project -Historical }
    return $layouts
}
