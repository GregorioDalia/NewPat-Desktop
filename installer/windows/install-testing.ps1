param([string]$Destination = '', [switch]$UseSetup, [switch]$LibraryOnly)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Assert-PlainPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "La destinazione contiene un collegamento: $current"
            }
        }
        $parent = Split-Path -Parent $current
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Get-VerifiedAsset($Record, [string]$Directory, [string]$ReleasePath) {
    if ($Record.file -notmatch '\A[A-Za-z0-9][A-Za-z0-9._-]+\z' -or
        $Record.sha256 -notmatch '\A[a-f0-9]{64}\z' -or [long]$Record.size -le 0) {
        throw 'Identita del download non valida.'
    }
    $target = Join-Path $Directory $Record.file
    Assert-PlainPath $target
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        Write-Host ('Download: ' + $Record.file)
        $temporary = $target + '.download-' + [Guid]::NewGuid().ToString('N')
        try {
            . (Join-Path $PSScriptRoot 'install-profile.ps1')
            $baseUrl = (Get-NipatOnlineRepository) + $ReleasePath
            $client = New-Object Net.WebClient
            $client.Headers.Add('User-Agent', 'NIPAT-Testing-Installer')
            try { $client.DownloadFile(($BaseUrl + $Record.file), $temporary) }
            finally { $client.Dispose() }
            if ((Get-Item -LiteralPath $temporary).Length -ne [long]$Record.size -or
                (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Record.sha256) {
                throw ('Download non integro: ' + $Record.file)
            }
            [IO.File]::Move($temporary, $target)
        } finally {
            if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        }
    }
    if ((Get-Item -LiteralPath $target).Length -ne [long]$Record.size -or
        (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Record.sha256) {
        throw ('Il file presente non coincide con la versione selezionata: ' + $target)
    }
    return $target
}

function Assert-TestingBundle([string]$Archive, [string]$Bundle) {
    # A previous extraction may have been edited. Verify all executable source
    # against the already hash-checked ZIP before running its installer again.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    $hash = [Security.Cryptography.SHA256]::Create()
    $seen = @{}
    $verified = 0
    $verifiedWorker = $false
    $verifiedManifest = $false
    try {
        foreach ($entry in $zip.Entries) {
            # .NET Framework ZIP writers use backslashes, while the release
            # packager uses forward slashes. Both address the same Windows
            # extraction; validate a single normalized identity before hashing.
            $relative = $entry.FullName.Replace('\', '/')
            if (-not $relative -or $relative.StartsWith('/') -or $relative.Contains(':') -or
                $relative -match '(^|/)(\.|\.\.)(/|$)' -or $relative.Contains('//') -or $seen.ContainsKey($relative)) {
                throw 'Percorso del pacchetto non valido o duplicato.'
            }
            $seen[$relative] = $true
            if (-not $relative.StartsWith('app/', [StringComparison]::Ordinal) -or $relative.EndsWith('/')) { continue }
            $path = [IO.Path]::GetFullPath((Join-Path $Bundle $relative.Replace('/', '\')))
            if (-not $path.StartsWith(($Bundle.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Percorso del pacchetto non valido.' }
            Assert-PlainPath $path
            if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -ne $entry.Length) {
                throw ('Estrazione incompleta: ' + $entry.FullName + '. Estrarre nuovamente il pacchetto senza modificare la cartella NIPAT.')
            }
            $source = $entry.Open()
            try { $expected = [Convert]::ToBase64String($hash.ComputeHash($source)) } finally { $source.Dispose() }
            $actualFile = [IO.File]::OpenRead($path)
            try { $actual = [Convert]::ToBase64String($hash.ComputeHash($actualFile)) } finally { $actualFile.Dispose() }
            if ($actual -cne $expected) { throw ('File estratto modificato: ' + $entry.FullName + '. Nessun file viene eseguito.') }
            $verified++
            if ($relative -ceq 'app/installer/windows/install-zip.ps1') { $verifiedWorker = $true }
            if ($relative -ceq 'app/.distribution/installer-manifest.json') { $verifiedManifest = $true }
        }
        if ($verified -eq 0 -or -not $verifiedWorker -or -not $verifiedManifest) {
            throw 'Il pacchetto non contiene il sorgente NewPat, il suo installer e il manifest verificati.'
        }
    } finally { $hash.Dispose(); $zip.Dispose() }
}

function Assert-TestingRoot([string]$Root) {
    Assert-PlainPath $Root
    $marker = Join-Path $Root 'installation.json'
    if (-not (Test-Path -LiteralPath $Root)) { return }
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        if (@(Get-ChildItem -LiteralPath $Root -Force).Count -eq 0) { return }
        throw 'La cartella Testing contiene file senza identita NewPat. Nessun file viene adottato.'
    }
    Assert-PlainPath $marker
    $owner = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($owner.PSObject.Properties).Count -ne 3 -or $owner.schema_version -ne 1 -or
        $owner.product -cne 'nipat-desktop' -or $owner.installation_method -cne 'zip') {
        throw 'La destinazione non appartiene a un installazione ZIP NewPat Testing.'
    }
    foreach ($name in @('current.json', 'pending.json')) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        Assert-PlainPath $path
        $pointer = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($pointer.PSObject.Properties).Count -ne 4 -or $pointer.schema_version -ne 1 -or
            $pointer.version -cnotmatch '\A0\.9\.[0-9]+\z' -or $pointer.source_commit -cnotmatch '\A[a-f0-9]{40}\z') {
            throw 'La cartella selezionata non contiene una versione NewPat Testing valida.'
        }
        $expected = Join-Path (Join-Path $Root 'versions') ($pointer.version + '-' + $pointer.source_commit)
        if ($pointer.app_dir -ine $expected) { throw 'Il puntatore Testing esce dalla cartella registrata.' }
        Assert-PlainPath $expected
        $manifest = Get-Content -LiteralPath (Join-Path $expected '.distribution\installer-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.version -cne $pointer.version -or $manifest.source_commit -cne $pointer.source_commit) {
            throw 'La versione Testing installata non coincide con il suo manifest.'
        }
    }
}

function Get-TestingInstallRoot([string]$DownloadDirectory, [bool]$DefaultDestination,
        [string]$ExpectedVersion = '', [string]$ExpectedSource = '') {
    if ($DefaultDestination) {
        $base = Join-Path $env:LOCALAPPDATA 'NIPAT-Testing'
        $root = Join-Path $base 'NIPAT'
        $legacy = Join-Path $base '0.9.0\pacchetto\NIPAT'
        # Upgrade the previously published preview in place, keeping experiments,
        # preferences and scientific runtime. Never discover/adopt the stable app.
        if (-not (Test-Path -LiteralPath $root) -and (Test-Path -LiteralPath $legacy)) { $root = $legacy }
    } else {
        $root = Join-Path $DownloadDirectory 'NIPAT'
        $legacy = Join-Path $DownloadDirectory 'pacchetto\NIPAT'
        if (-not (Test-Path -LiteralPath $root) -and (Test-Path -LiteralPath $legacy)) { $root = $legacy }
    }
    Assert-TestingRoot $root
    $testingMarker = Join-Path $root 'testing.json'
    if (Test-Path -LiteralPath $testingMarker) {
        Assert-PlainPath $testingMarker
        $testing = Get-Content -LiteralPath $testingMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        if (@($testing.PSObject.Properties).Count -ne 2 -or $testing.schema_version -ne 1 -or $testing.channel -cne 'testing') {
            throw 'Identita Testing della destinazione non valida.'
        }
    } else {
        foreach ($name in @('current.json', 'pending.json')) {
            $path = Join-Path $root $name
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
            $pointer = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
            # The original 0.9.0 Testing installer used this unmarked layout.
            # A newer first installation can stop before its marker is written.
            if (($root -ieq $legacy -and $pointer.version -ceq '0.9.0') -or
                ($ExpectedVersion -and $pointer.version -ceq $ExpectedVersion -and $pointer.source_commit -ceq $ExpectedSource)) { continue }
            throw 'La destinazione contiene una installazione ZIP diversa. Scegliere una cartella separata per NewPat Testing.'
        }
    }
    return $root
}

function Set-TestingAppShortcuts([string]$Root, [string]$Project) {
    Assert-TestingRoot $Root
    . (Join-Path $Project 'installer\windows\zip-common.ps1')
    Assert-NipatZipRoot $Root
    Write-NipatJsonAtomic (Join-Path $Root 'testing.json') ([ordered]@{ schema_version = 1; channel = 'testing' })
    Set-NipatZipShortcuts $Root $Project
}

function Open-TestingApp([string]$Root, [string]$Project) {
    Set-TestingAppShortcuts $Root $Project
    Write-Host 'Avvio NewPat Testing. Per i prossimi avvii usa NewPat Testing sul Desktop o nel menu Start.'
    & (Join-Path $Project 'scripts\windows\run.ps1') gui
    if ($LASTEXITCODE -ne 0) { throw 'Avvio grafico non riuscito. Consulta il messaggio della finestra NewPat.' }
}

if ($LibraryOnly) { return }

try {
    $metadata = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'testing-release.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($metadata.schema_version -ne 1 -or $metadata.channel -cne 'testing' -or
        $metadata.version -notmatch '\A0\.9\.[0-9]+(?:(?:a|b|rc)[0-9]+)?\z' -or
        $metadata.source_commit -notmatch '\A[a-f0-9]{40}\z') {
        throw 'Questo avvio e riservato alle versioni sperimentali NewPat 0.9.'
    }
    $version = $metadata.version
    $releasePath = '/releases/download/v' + $version + '/'
    $defaultDestination = -not $Destination
    if ($defaultDestination) { $Destination = Join-Path $env:LOCALAPPDATA ('NIPAT-Testing\' + $version) }
    $destination = [IO.Path]::GetFullPath($Destination)
    Assert-PlainPath $destination
    [IO.Directory]::CreateDirectory($destination) | Out-Null
    Write-Host ('NewPat ' + $version + ' - VERSIONE SPERIMENTALE')
    if ($UseSetup) {
        Write-Host 'Questa modalita aggiorna l installazione desktop esistente con la versione sperimentale.'
        $payload = Get-VerifiedAsset $metadata.payload $destination $releasePath
        $setup = Get-VerifiedAsset $metadata.setup $destination $releasePath
        $arguments = @(
            ('/NIPATPACKAGE="' + $payload + '"'), ('/NIPATVERSION=' + $version),
            ('/NIPATSOURCE=' + $metadata.source_commit), ('/NIPATSHA256=' + $metadata.payload.sha256),
            ('/NIPATSIZE=' + $metadata.payload.size)
        )
        $process = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
        exit $process.ExitCode
    }
    $root = Get-TestingInstallRoot $destination $defaultDestination $version $metadata.source_commit
    $currentPath = Join-Path $root 'current.json'
    $pendingPath = Join-Path $root 'pending.json'
    if ((Test-Path -LiteralPath $currentPath) -and -not (Test-Path -LiteralPath $pendingPath)) {
        $current = Get-Content -LiteralPath $currentPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($current.version -ceq $version -and $current.source_commit -cne $metadata.source_commit) {
            throw 'La stessa versione identifica un commit differente. Nessun file viene sostituito.'
        }
        if ([version]$current.version -ge [version]$version) {
            Open-TestingApp $root $current.app_dir
            exit 0
        }
    }
    $resumeProject = ''
    if (Test-Path -LiteralPath $pendingPath) {
        $pending = Get-Content -LiteralPath $pendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($pending.version -ceq $version -and $pending.source_commit -ceq $metadata.source_commit) { $resumeProject = $pending.app_dir }
    }
    $bundle = Join-Path $destination 'bundle'
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if ($resumeProject) {
        Write-Host 'Ripresa automatica della preparazione gia iniziata...'
        & $powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $resumeProject 'installer\windows\install-zip.ps1') -Resume
        $code = $LASTEXITCODE
    } else {
        $archive = Get-VerifiedAsset $metadata.complete_zip $destination $releasePath
        if (-not (Test-Path -LiteralPath $bundle)) {
            # Extraction is atomic: interrupted extraction does not leave a
            # partial bundle that prevents running the same entrypoint again.
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $staging = $bundle + '.extract-' + [Guid]::NewGuid().ToString('N')
            try {
                [IO.Compression.ZipFile]::ExtractToDirectory($archive, $staging)
                [IO.Directory]::Move($staging, $bundle)
            } finally {
                if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
            }
        }
        Assert-PlainPath $bundle
        Assert-TestingBundle $archive $bundle
        $worker = Join-Path $bundle 'app\installer\windows\install-zip.ps1'
        # The production installer verifies every source and bundled asset, and
        # its activity lease blocks replacement while an analysis is running.
        & $powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $worker -BundleDirectory $bundle -InstallRoot $root
        $code = $LASTEXITCODE
    }
    $pointerPath = if (Test-Path -LiteralPath $pendingPath) { $pendingPath } else { $currentPath }
    if (Test-Path -LiteralPath $pointerPath) {
        $installed = Get-Content -LiteralPath $pointerPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Set-TestingAppShortcuts $root $installed.app_dir
    }
    if ($code -eq 0) {
        $current = Get-Content -LiteralPath $currentPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Open-TestingApp $root $current.app_dir
    } elseif ($code -eq 3010) {
        Write-Host 'Riavvia Windows, poi apri NewPat Testing dal Desktop/menu Start oppure riapri questo stesso file.'
    } else {
        throw 'Preparazione non completata. Riapri questo stesso file per riprovare; conserva il messaggio e setup.log.'
    }
    exit $code
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
