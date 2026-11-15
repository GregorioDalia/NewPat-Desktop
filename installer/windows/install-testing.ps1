param([string]$Destination = '', [switch]$UseSetup)

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

function Get-VerifiedAsset($Record, [string]$Directory, [string]$BaseUrl) {
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

try {
    $metadata = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'testing-release.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($metadata.schema_version -ne 1 -or $metadata.channel -cne 'testing' -or
        $metadata.version -notmatch '\A0\.9\.[0-9]+(?:(?:a|b|rc)[0-9]+)?\z' -or
        $metadata.source_commit -notmatch '\A[a-f0-9]{40}\z') {
        throw 'Questo avvio e riservato alle versioni sperimentali NIPAT 0.9.'
    }
    $version = $metadata.version
    $baseUrl = 'https://github.com/GregorioDalia/nipat-desktop/releases/download/v' + $version + '/'
    if (-not $Destination) { $Destination = Join-Path $env:LOCALAPPDATA ('NIPAT-Testing\' + $version) }
    $destination = [IO.Path]::GetFullPath($Destination)
    Assert-PlainPath $destination
    [IO.Directory]::CreateDirectory($destination) | Out-Null
    Write-Host ('NIPAT ' + $version + ' - VERSIONE SPERIMENTALE')
    if ($UseSetup) {
        Write-Host 'Questa modalita aggiorna l installazione desktop esistente con la versione sperimentale.'
        $payload = Get-VerifiedAsset $metadata.payload $destination $baseUrl
        $setup = Get-VerifiedAsset $metadata.setup $destination $baseUrl
        $arguments = @(
            ('/NIPATPACKAGE="' + $payload + '"'), ('/NIPATVERSION=' + $version),
            ('/NIPATSOURCE=' + $metadata.source_commit), ('/NIPATSHA256=' + $metadata.payload.sha256),
            ('/NIPATSIZE=' + $metadata.payload.size)
        )
        $process = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
        exit $process.ExitCode
    }
    $archive = Get-VerifiedAsset $metadata.complete_zip $destination $baseUrl
    $bundle = Join-Path $destination 'pacchetto'
    if (Test-Path -LiteralPath $bundle) {
        throw ('La cartella del pacchetto esiste gia. Per continuare aprire 1_INSTALLA.cmd al suo interno: ' + $bundle)
    }
    # The whole archive has been verified against the release-specific digest;
    # its production installer independently verifies every bundled source/asset.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $bundle)
    $worker = Join-Path $bundle 'app\installer\windows\install-zip.ps1'
    $root = Join-Path $bundle 'NIPAT'
    & $worker -BundleDirectory $bundle
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Write-Host ('Installazione completata. Aprire: ' + (Join-Path $root '2_AVVIA.cmd'))
    }
    exit $code
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
