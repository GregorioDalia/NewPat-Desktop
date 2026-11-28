# Official desktop identity: never infer it from another installation.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-NewPatOfficialRepositories {
    return 'GregorioDalia/NewPat-Desktop'
}

function Get-NewPatOnlineRepository {
    $identity = Invoke-RestMethod -Method Get -Uri 'https://api.github.com/repositories/1307623649' `
        -Headers @{'User-Agent' = 'NewPat-Installer'} -TimeoutSec 30 -MaximumRedirection 0
    if ((($identity.id -isnot [int]) -and ($identity.id -isnot [long])) -or
        $identity.id -ne 1307623649 -or (Get-NewPatOfficialRepositories) -cnotcontains $identity.full_name) {
        throw 'Identita del repository GitHub non valida.'
    }
    return ('https://github.com/' + $identity.full_name)
}

function Assert-NewPatInstallationProfile($Profile) {
    $expected = [ordered]@{
        schema_version = 1; channel = 'desktop'; display_name = 'NewPat'
        app_dir_name = 'NewPat-Desktop'; data_dir_name = 'NewPat-Desktop'
        distro_prefix = 'NewPat-Desktop-'; resume_key = 'NewPat-Desktop-ResumeSetup'
        mutex_prefix = 'Local\NewPat-Desktop-Setup-'; app_id = 'B870A3DA-56E8-4F27-A571-86FCEDD83F25'
    }
    if ($null -eq $Profile -or @($Profile.PSObject.Properties).Count -ne $expected.Count) {
        throw 'Profilo di installazione NewPat mancante o non valido.'
    }
    foreach ($name in $expected.Keys) {
        $typeMatches = $false
        if ($null -ne $Profile.PSObject.Properties[$name]) {
            if ($name -ceq 'schema_version') {
                $typeMatches = ($Profile.$name -is [int]) -or ($Profile.$name -is [long])
            } else { $typeMatches = $Profile.$name -is [string] }
        }
        if (-not $typeMatches -or $Profile.$name -cne $expected[$name]) {
            throw "Identita di installazione non supportata: $name. Le altre installazioni non vengono modificate."
        }
    }
}

function Get-NewPatInstallationProfile {
    $profile = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'install-profile.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-NewPatInstallationProfile $profile
    return $profile
}

function Assert-NewPatInstallationChannel($Value, [string] $Description) {
    $present = $false
    if ($null -ne $Value) {
        if ($Value -is [Collections.IDictionary]) { $present = $Value.Contains('installation_channel') }
        else { $present = $null -ne $Value.PSObject.Properties['installation_channel'] }
    }
    if (-not $present -or $Value.installation_channel -cne (Get-NewPatInstallationProfile).channel) {
        throw "$Description appartiene a un altro canale di installazione. NewPat non adotta configurazioni sperimentali o di altre installazioni."
    }
}

function Assert-NewPatRuntimeNamespace([string] $Distro, [string] $RootfsSha256, [string] $RuntimeDirectory = '') {
    if ($RootfsSha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Identita rootfs non valida.' }
    if (-not $RuntimeDirectory) { $RuntimeDirectory = (Get-NewPatDefaultInstallLayout).runtime_dir }
    if ($Distro -cne (Get-NewPatRuntimeDistroName $RootfsSha256 $RuntimeDirectory)) {
        throw 'La distribuzione richiesta non appartiene a questa installazione NewPat.'
    }
}

function Assert-NewPatInstallationLocation([string] $Project) {
    $profile = Get-NewPatInstallationProfile
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA non disponibile.' }
    $expected = Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') $profile.app_dir_name
    if (Test-Path -LiteralPath (Join-Path $Project '.runtime\install-layout.json') -PathType Leaf) {
        Read-NewPatInstallLayout $Project | Out-Null
        return
    }
    if ([IO.Path]::GetFullPath($Project).TrimEnd('\') -ine [IO.Path]::GetFullPath($expected).TrimEnd('\')) {
        throw 'NewPat deve essere installato nella propria cartella dedicata. Avviare il relativo installer normalmente.'
    }
    # Reject junctions/symlinks in existing installation-specific paths before writes.
    $base = Join-Path $env:LOCALAPPDATA $profile.data_dir_name
    $paths = @($Project, $base)
    foreach ($relative in @('.runtime', '.runtime\installer', '.runtime\installer\recovery', '.distribution')) {
        $paths += Join-Path $Project $relative
    }
    foreach ($relative in @('cache', 'wsl', 'wsl\registrations', 'data', 'runs')) {
        $paths += Join-Path $base $relative
    }
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path) {
            if (((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "La cartella dedicata non puo essere un collegamento: $path. Nessun file viene modificato."
            }
        }
    }
}

. (Join-Path $PSScriptRoot 'install-layout.ps1')
