# Shared lifecycle for the additive, managed Windows ZIP installation.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
. (Join-Path $PSScriptRoot 'activity-lock.ps1')

function Get-NewPatZipRoot([string] $Project = '') {
    if (-not $Project) { $Project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
    $projectPath = Resolve-NewPatInstallPath $Project
    Assert-NewPatInstallPathWithoutLinks $projectPath
    $marker = Join-Path $projectPath '.runtime\zip-install.json'
    Assert-NewPatActivityPathWithoutLinks $marker
    $value = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($value.PSObject.Properties).Count -ne 3 -or $value.schema_version -ne 1 -or
        $value.installation_method -cne 'zip' -or -not ($value.root -is [string])) {
        throw 'Identita dell installazione ZIP non valida.'
    }
    $root = Resolve-NewPatInstallPath $value.root
    Assert-NewPatZipRoot $root
    $folder = Split-Path -Leaf $projectPath
    $match = [regex]::Match($folder, '^((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))-([a-f0-9]{40})$')
    if (-not $match.Success -or $projectPath -ine (Get-NewPatZipProject $root $match.Groups[1].Value $match.Groups[2].Value)) {
        throw 'L applicazione ZIP non appartiene alla cartella registrata.'
    }
    return $root
}

function Get-NewPatZipInstallRoot([string] $Bundle, [string] $RequestedRoot, [switch] $AllowNew) {
    if ($RequestedRoot) {
        $root = Resolve-NewPatInstallPath $RequestedRoot
        Assert-NewPatInstallPathWithoutLinks $root
        if ($AllowNew -and (-not (Test-Path -LiteralPath $root) -or
            @(Get-ChildItem -LiteralPath $root -Force).Count -eq 0)) { return $root }
        Assert-NewPatZipRoot $root
        return $root
    }
    return Resolve-NewPatInstallPath (Join-Path $Bundle 'NewPat')
}

function Assert-NewPatZipRoot([string] $Root, [switch] $Create) {
    if ($Root -ine (Resolve-NewPatInstallPath $Root)) { throw 'Percorso ZIP non canonico.' }
    Assert-NewPatInstallPathWithoutLinks $Root
    $marker = Join-Path $Root 'installation.json'
    if (Test-Path -LiteralPath $marker -PathType Leaf) {
        Assert-NewPatActivityPathWithoutLinks $marker
        $value = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($value.PSObject.Properties).Count -ne 3 -or $value.schema_version -ne 1 -or
            $value.product -cne 'newpat-desktop' -or $value.installation_method -cne 'zip') {
            throw 'La cartella non appartiene all installazione ZIP NewPat.'
        }
    } elseif ($Create) {
        if ((Test-Path -LiteralPath $Root) -and @(Get-ChildItem -LiteralPath $Root -Force).Count -gt 0) {
            throw 'La destinazione ZIP contiene file senza un identificativo NewPat. Nessun file viene adottato.'
        }
        Write-NewPatJsonAtomic $marker ([ordered]@{ schema_version = 1; product = 'newpat-desktop'; installation_method = 'zip' })
    } else { throw 'Installazione ZIP non inizializzata.' }
}

function Get-NewPatZipProject([string] $Root, [string] $Version, [string] $Source) {
    if ($Version -cnotmatch '^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$' -or $Source -cnotmatch '^[a-f0-9]{40}$') {
        throw 'Identita della versione ZIP non valida.'
    }
    return Join-Path (Join-Path $Root 'versions') ($Version + '-' + $Source)
}

function Read-NewPatZipPointer([string] $Root, [string] $Name = 'current.json') {
    if ($Name -cnotin @('current.json', 'pending.json')) { throw 'Puntatore ZIP non riconosciuto.' }
    Assert-NewPatZipRoot $Root
    $file = Join-Path $Root $Name
    Assert-NewPatActivityPathWithoutLinks $file
    $value = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($value.PSObject.Properties).Count -ne 4 -or $value.schema_version -ne 1 -or
        $value.app_dir -ine (Get-NewPatZipProject $Root $value.version $value.source_commit)) {
        throw 'Puntatore della versione ZIP non valido.'
    }
    Assert-NewPatInstallPathWithoutLinks $value.app_dir
    return $value
}

function Assert-NewPatZipApplication([string] $Project, [switch] $Installed) {
    # Scope the library's script parameters locally; maintenance owns ReportFile.
    . (Join-Path $PSScriptRoot 'repair-installation.ps1') -LibraryOnly
    Assert-NewPatInstallPathWithoutLinks $Project -Tree
    $manifest = Read-NewPatInstallerManifest (Join-Path $Project '.distribution\installer-manifest.json')
    $inventoryFile = Join-Path $Project '.distribution\application-files.json'
    $inventory = Get-Content -LiteralPath $inventoryFile -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-NewPatApplicationPayload $inventory
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
        if ($Installed -and ($relative.StartsWith('.runtime/') -or $relative -ceq '.newpat-app.ini')) { continue }
        if (-not $expected.ContainsKey($relative)) { throw "File inatteso nel pacchetto ZIP: $relative" }
    }
    return $manifest
}

function Write-NewPatZipOwnership([string] $Directory, [string] $Role) {
    if ($Role -cnotin @('application', 'runtime', 'cache')) { throw 'Ruolo cartella ZIP non valido.' }
    Assert-NewPatInstallPathWithoutLinks $Directory -Tree
    [IO.Directory]::CreateDirectory($Directory) | Out-Null
    if (Test-NewPatStorageMarker $Directory $Role) { return }
    if ($Role -cne 'application' -and @(Get-ChildItem -LiteralPath $Directory -Force).Count -gt 0) {
        throw 'La cartella runtime/cache contiene file senza un identificativo NewPat.'
    }
    $name = if ($Role -ceq 'application') { '.newpat-app.ini' } else { '.newpat-storage.ini' }
    [IO.File]::WriteAllText((Join-Path $Directory $name), "[NewPat]`nschema_version=1`ninstallation_channel=desktop`nrole=$Role`n", (New-Object Text.UTF8Encoding($false)))
}

function Set-NewPatZipShortcuts([string] $Root, [string] $Project) {
    # Keep diagnostic CMD entrypoints alongside the app shortcut. The normal app
    # shortcut hides the bridge and opens the console-free Python host.
    Assert-NewPatZipRoot $Root
    $launchProject = $Project
    if (Test-Path -LiteralPath (Join-Path $Root 'current.json')) {
        $launchProject = (Read-NewPatZipPointer $Root).app_dir
    }
    foreach ($mode in @('launch', 'resume')) {
        $targetProject = if ($mode -ceq 'launch') { $launchProject } else { $Project }
        $folder = Split-Path -Leaf $targetProject
        if ($folder -cnotmatch '^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-[a-f0-9]{40}$' -or
            (Split-Path -Parent $targetProject) -ine (Join-Path $Root 'versions')) {
            throw 'Destinazione del launcher ZIP non valida.'
        }
        $name = if ($mode -ceq 'launch') { '2_LAUNCH.cmd' } else { '1_RESUME_SETUP.cmd' }
        $path = Join-Path $Root $name
        Assert-NewPatActivityPathWithoutLinks $path
        $lines = @('@echo off', 'setlocal DisableDelayedExpansion',
            ('"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0versions\' + $folder + '\installer\windows\zip-entry.ps1" -Mode ' + $mode),
            'exit /b %ERRORLEVEL%')
        $contents = ($lines -join "`r`n") + "`r`n"
        $temporary = Join-Path $Root ('.launcher-' + [Guid]::NewGuid().ToString('N') + '.cmd')
        try {
            [IO.File]::WriteAllText($temporary, $contents, [Text.Encoding]::ASCII)
            if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary, $path, [NullString]::Value) }
            else { [IO.File]::Move($temporary, $path) }
        } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
    }
    $shortcutProject = if (Test-Path -LiteralPath (Join-Path $Root 'pending.json')) { $Project } else { $launchProject }
    $shortcuts = @((Join-Path $Root 'NewPat.lnk'))
    $testingMarker = Join-Path $Root 'testing.json'
    if (Test-Path -LiteralPath $testingMarker -PathType Leaf) {
        Assert-NewPatActivityPathWithoutLinks $testingMarker
        $testing = Get-Content -LiteralPath $testingMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($testing.PSObject.Properties).Count -ne 2 -or $testing.schema_version -ne 1 -or $testing.channel -cne 'testing') {
            throw 'Identita del collegamento Testing non valida.'
        }
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
        $programs = [Environment]::GetFolderPath('Programs')
        foreach ($directory in @($desktop, $programs)) {
            if ($directory) {
                $shortcuts += (Join-Path $directory 'NewPat Testing.lnk')
            }
        }
    }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($path in $shortcuts) {
        try {
            Assert-NewPatActivityPathWithoutLinks $path
            [IO.Directory]::CreateDirectory((Split-Path -Parent $path)) | Out-Null
            $link = $shell.CreateShortcut($path)
            $link.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $link.Arguments = '-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $shortcutProject 'installer\windows\zip-entry.ps1') + '" -Mode auto'
            $link.WorkingDirectory = $Root
            $link.IconLocation = (Join-Path $shortcutProject 'assets\branding\newpat-icon.ico') + ',0'
            $link.Description = 'Apri NewPat o completa automaticamente la preparazione dopo un riavvio.'
            $link.Save()
        } catch {
            if ($path -ieq (Join-Path $Root 'NewPat.lnk')) { throw }
            # A redirected/readonly Desktop must not break a ready installation.
            Write-Warning ('Collegamento non creato: ' + $path + '. Usa NewPat.lnk nella cartella dell app oppure lo stesso file di installazione. ' + $_.Exception.Message)
        }
    }
}

function Complete-NewPatZipActivation([string] $Root, $Pointer) {
    Assert-NewPatZipRoot $Root
    if ($Pointer.app_dir -ine (Get-NewPatZipProject $Root $Pointer.version $Pointer.source_commit)) {
        throw 'Destinazione ZIP non valida per l attivazione.'
    }
    Assert-NewPatActivityPathWithoutLinks (Join-Path $Root 'current.json')
    $state = Get-Content -LiteralPath (Join-Path $Pointer.app_dir '.runtime\installer\state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.phase -cne 'ready' -or $state.installation_channel -cne 'desktop' -or
        $state.version -cne $Pointer.version -or $state.source_commit -cne $Pointer.source_commit) {
        throw 'La nuova versione non ha completato la preparazione; la versione corrente resta selezionata.'
    }
    Write-NewPatJsonAtomic (Join-Path $Root 'current.json') $Pointer
    $pending = Join-Path $Root 'pending.json'
    if (Test-Path -LiteralPath $pending) { [IO.File]::Delete($pending) }
}
