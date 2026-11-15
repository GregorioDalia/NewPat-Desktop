# Shared lifecycle for the additive, managed Windows ZIP installation.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
. (Join-Path $PSScriptRoot 'activity-lock.ps1')
. (Join-Path $PSScriptRoot 'repair-installation.ps1') -LibraryOnly

function Get-NipatZipRoot {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA non disponibile.' }
    return Resolve-NipatInstallPath (Join-Path $env:LOCALAPPDATA 'NIPAT-Desktop-Zip')
}

function Assert-NipatZipRoot([string] $Root, [switch] $Create) {
    if ($Root -ine (Get-NipatZipRoot)) { throw 'Cartella ZIP diversa dalla destinazione gestita.' }
    Assert-NipatInstallPathWithoutLinks $Root
    $marker = Join-Path $Root 'installation.json'
    if (Test-Path -LiteralPath $marker -PathType Leaf) {
        Assert-NipatActivityPathWithoutLinks $marker
        $value = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($value.PSObject.Properties).Count -ne 3 -or $value.schema_version -ne 1 -or
            $value.product -cne 'nipat-desktop' -or $value.installation_method -cne 'zip') {
            throw 'La cartella non appartiene all installazione ZIP NIPAT.'
        }
    } elseif ($Create) {
        if ((Test-Path -LiteralPath $Root) -and @(Get-ChildItem -LiteralPath $Root -Force).Count -gt 0) {
            throw 'La destinazione ZIP contiene file senza un identificativo NIPAT. Nessun file viene adottato.'
        }
        Write-NipatJsonAtomic $marker ([ordered]@{ schema_version = 1; product = 'nipat-desktop'; installation_method = 'zip' })
    } else { throw 'Installazione ZIP non inizializzata.' }
}

function Get-NipatZipProject([string] $Root, [string] $Version, [string] $Source) {
    if ($Version -cnotmatch '^0\.8\.(0|[1-9][0-9]*)$' -or $Source -cnotmatch '^[a-f0-9]{40}$') {
        throw 'Identita della versione ZIP non valida.'
    }
    return Join-Path (Join-Path $Root 'versions') ($Version + '-' + $Source)
}

function Read-NipatZipPointer([string] $Root, [string] $Name = 'current.json') {
    if ($Name -cnotin @('current.json', 'pending.json')) { throw 'Puntatore ZIP non riconosciuto.' }
    Assert-NipatZipRoot $Root
    $file = Join-Path $Root $Name
    Assert-NipatActivityPathWithoutLinks $file
    $value = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($value.PSObject.Properties).Count -ne 4 -or $value.schema_version -ne 1 -or
        $value.app_dir -ine (Get-NipatZipProject $Root $value.version $value.source_commit)) {
        throw 'Puntatore della versione ZIP non valido.'
    }
    Assert-NipatInstallPathWithoutLinks $value.app_dir
    return $value
}

function Assert-NipatZipApplication([string] $Project, [switch] $Installed) {
    Assert-NipatInstallPathWithoutLinks $Project -Tree
    $manifest = Read-NipatInstallerManifest (Join-Path $Project '.distribution\installer-manifest.json')
    $inventoryFile = Join-Path $Project '.distribution\application-files.json'
    $inventory = Get-Content -LiteralPath $inventoryFile -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-NipatApplicationPayload $inventory
    if ($inventory.schema_version -ne 1 -or $inventory.installation_channel -cne 'desktop' -or
        $inventory.source_commit -cne $manifest.source_commit) { throw 'Inventario ZIP non valido.' }
    $expected = @{}
    foreach ($entry in $inventory.files) {
        $name = [string]$entry.path
        $expected[$name] = $entry.sha256
        $file = Join-Path $Project $name
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256) {
            throw "File ZIP mancante o modificato: $name"
        }
    }
    foreach ($source in $manifest.source_sha256.PSObject.Properties) {
        if (-not $expected.ContainsKey($source.Name) -or $expected[$source.Name] -cne $source.Value) {
            throw "Il file ZIP non corrisponde al sorgente dichiarato: $($source.Name)"
        }
    }
    foreach ($file in Get-ChildItem -LiteralPath $Project -Recurse -Force -File) {
        $relative = $file.FullName.Substring($Project.TrimEnd('\').Length + 1).Replace('\', '/')
        if ($relative -ceq '.distribution/application-files.json') { continue }
        if ($Installed -and ($relative.StartsWith('.runtime/') -or $relative -ceq '.nipat-app.ini')) { continue }
        if (-not $expected.ContainsKey($relative)) { throw "File inatteso nel pacchetto ZIP: $relative" }
    }
    return $manifest
}

function Write-NipatZipOwnership([string] $Directory, [string] $Role) {
    if ($Role -cnotin @('application', 'runtime', 'cache')) { throw 'Ruolo cartella ZIP non valido.' }
    Assert-NipatInstallPathWithoutLinks $Directory -Tree
    [IO.Directory]::CreateDirectory($Directory) | Out-Null
    if (Test-NipatStorageMarker $Directory $Role) { return }
    if ($Role -cne 'application' -and @(Get-ChildItem -LiteralPath $Directory -Force).Count -gt 0) {
        throw 'La cartella runtime/cache contiene file senza un identificativo NIPAT.'
    }
    $name = if ($Role -ceq 'application') { '.nipat-app.ini' } else { '.nipat-storage.ini' }
    [IO.File]::WriteAllText((Join-Path $Directory $name), "[NIPAT]`nschema_version=1`ninstallation_channel=desktop`nrole=$Role`n", (New-Object Text.UTF8Encoding($false)))
}

function Set-NipatZipShortcuts([string] $Root, [string] $Project) {
    $programs = [Environment]::GetFolderPath('Programs')
    if (-not $programs) { throw 'Menu Start del tuo account non disponibile.' }
    $folder = Join-Path $programs 'NIPAT Desktop ZIP'
    Assert-NipatInstallPathWithoutLinks $folder
    [IO.Directory]::CreateDirectory($folder) | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    try {
        foreach ($mode in @('launch', 'resume')) {
            $name = if ($mode -ceq 'launch') { 'NIPAT Desktop ZIP.lnk' } else { 'NIPAT Desktop ZIP - completa preparazione.lnk' }
            $shortcutFile = Join-Path $folder $name
            Assert-NipatActivityPathWithoutLinks $shortcutFile
            $shortcut = $shell.CreateShortcut($shortcutFile)
            $shortcut.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $shortcut.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Project 'installer\windows\zip-entry.ps1') + '" -Mode ' + $mode
            $shortcut.WorkingDirectory = $Root
            $shortcut.IconLocation = (Join-Path $Project 'assets\branding\nipat-icon.ico') + ',0'
            $shortcut.Save()
        }
    } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
}

function Complete-NipatZipActivation([string] $Root, $Pointer) {
    Assert-NipatZipRoot $Root
    if ($Pointer.app_dir -ine (Get-NipatZipProject $Root $Pointer.version $Pointer.source_commit)) {
        throw 'Destinazione ZIP non valida per l attivazione.'
    }
    Assert-NipatActivityPathWithoutLinks (Join-Path $Root 'current.json')
    $state = Get-Content -LiteralPath (Join-Path $Pointer.app_dir '.runtime\installer\state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.phase -cne 'ready' -or $state.installation_channel -cne 'desktop' -or
        $state.version -cne $Pointer.version -or $state.source_commit -cne $Pointer.source_commit) {
        throw 'La nuova versione non ha completato la preparazione; la versione corrente resta selezionata.'
    }
    Write-NipatJsonAtomic (Join-Path $Root 'current.json') $Pointer
    $pending = Join-Path $Root 'pending.json'
    if (Test-Path -LiteralPath $pending) { [IO.File]::Delete($pending) }
}
