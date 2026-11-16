# Shared lifecycle for the additive, managed Windows ZIP installation.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
. (Join-Path $PSScriptRoot 'activity-lock.ps1')

function Get-NipatZipRoot([string] $Project = '') {
    if (-not $Project) { $Project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
    $projectPath = Resolve-NipatInstallPath $Project
    Assert-NipatInstallPathWithoutLinks $projectPath
    $marker = Join-Path $projectPath '.runtime\zip-install.json'
    Assert-NipatActivityPathWithoutLinks $marker
    $value = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($value.PSObject.Properties).Count -ne 3 -or $value.schema_version -ne 1 -or
        $value.installation_method -cne 'zip' -or -not ($value.root -is [string])) {
        throw 'Identita dell installazione ZIP non valida.'
    }
    $root = Resolve-NipatInstallPath $value.root
    Assert-NipatZipRoot $root
    $folder = Split-Path -Leaf $projectPath
    $match = [regex]::Match($folder, '^((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))-([a-f0-9]{40})$')
    if (-not $match.Success -or $projectPath -ine (Get-NipatZipProject $root $match.Groups[1].Value $match.Groups[2].Value)) {
        throw 'L applicazione ZIP non appartiene alla cartella registrata.'
    }
    return $root
}

function Get-NipatZipInstallRoot([string] $Bundle, [string] $RequestedRoot, [switch] $AllowNew) {
    if ($RequestedRoot) {
        $root = Resolve-NipatInstallPath $RequestedRoot
        Assert-NipatInstallPathWithoutLinks $root
        if ($AllowNew -and (-not (Test-Path -LiteralPath $root) -or
            @(Get-ChildItem -LiteralPath $root -Force).Count -eq 0)) { return $root }
        Assert-NipatZipRoot $root
        return $root
    }
    return Resolve-NipatInstallPath (Join-Path $Bundle 'NIPAT')
}

function Assert-NipatZipRoot([string] $Root, [switch] $Create) {
    if ($Root -ine (Resolve-NipatInstallPath $Root)) { throw 'Percorso ZIP non canonico.' }
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
    if ($Version -cnotmatch '^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$' -or $Source -cnotmatch '^[a-f0-9]{40}$') {
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
    # Scope the library's script parameters locally; maintenance owns ReportFile.
    . (Join-Path $PSScriptRoot 'repair-installation.ps1') -LibraryOnly
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
    # Keep the diagnostic CMD entrypoints for compatibility. The normal app
    # shortcut hides the bridge and opens the console-free Python host.
    Assert-NipatZipRoot $Root
    $launchProject = $Project
    if (Test-Path -LiteralPath (Join-Path $Root 'current.json')) {
        $launchProject = (Read-NipatZipPointer $Root).app_dir
    }
    foreach ($mode in @('launch', 'resume')) {
        $targetProject = if ($mode -ceq 'launch') { $launchProject } else { $Project }
        $folder = Split-Path -Leaf $targetProject
        if ($folder -cnotmatch '^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-[a-f0-9]{40}$' -or
            (Split-Path -Parent $targetProject) -ine (Join-Path $Root 'versions')) {
            throw 'Destinazione del launcher ZIP non valida.'
        }
        $name = if ($mode -ceq 'launch') { '2_AVVIA.cmd' } else { '1_COMPLETA_PREPARAZIONE.cmd' }
        $path = Join-Path $Root $name
        Assert-NipatActivityPathWithoutLinks $path
        $lines = @('@echo off', 'setlocal DisableDelayedExpansion',
            ('"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0versions\' + $folder + '\installer\windows\zip-entry.ps1" -Mode ' + $mode),
            'exit /b %ERRORLEVEL%')
        $temporary = Join-Path $Root ('.launcher-' + [Guid]::NewGuid().ToString('N') + '.cmd')
        try {
            [IO.File]::WriteAllText($temporary, (($lines -join "`r`n") + "`r`n"), [Text.Encoding]::ASCII)
            if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary, $path, [NullString]::Value) }
            else { [IO.File]::Move($temporary, $path) }
        } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
    }
    $shortcutProject = if (Test-Path -LiteralPath (Join-Path $Root 'pending.json')) { $Project } else { $launchProject }
    $shortcuts = @((Join-Path $Root 'NIPAT.lnk'))
    $testingMarker = Join-Path $Root 'testing.json'
    if (Test-Path -LiteralPath $testingMarker -PathType Leaf) {
        Assert-NipatActivityPathWithoutLinks $testingMarker
        $testing = Get-Content -LiteralPath $testingMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($testing.PSObject.Properties).Count -ne 2 -or $testing.schema_version -ne 1 -or $testing.channel -cne 'testing') {
            throw 'Identita del collegamento Testing non valida.'
        }
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
        $programs = [Environment]::GetFolderPath('Programs')
        foreach ($directory in @($desktop, $programs)) {
            if ($directory) {
                $shortcuts += (Join-Path $directory 'NIPAT Testing.lnk')
            }
        }
    }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($path in $shortcuts) {
        try {
            Assert-NipatActivityPathWithoutLinks $path
            [IO.Directory]::CreateDirectory((Split-Path -Parent $path)) | Out-Null
            $link = $shell.CreateShortcut($path)
            $link.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $link.Arguments = '-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $shortcutProject 'installer\windows\zip-entry.ps1') + '" -Mode auto'
            $link.WorkingDirectory = $Root
            $link.IconLocation = (Join-Path $shortcutProject 'assets\branding\nipat-icon.ico') + ',0'
            $link.Description = 'Apri NIPAT o completa automaticamente la preparazione dopo un riavvio.'
            $link.Save()
        } catch {
            if ($path -ieq (Join-Path $Root 'NIPAT.lnk')) { throw }
            # A redirected/readonly Desktop must not break a ready installation.
            Write-Warning ('Collegamento non creato: ' + $path + '. Usa NIPAT.lnk nella cartella dell app oppure lo stesso file di installazione. ' + $_.Exception.Message)
        }
    }
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
