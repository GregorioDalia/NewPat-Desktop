param([string] $BundleDirectory = '', [string] $InstallRoot = '', [switch] $Resume, [switch] $VerifyOnly, [switch] $OpenWhenReady)

. (Join-Path $PSScriptRoot 'zip-common.ps1')
. (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'scripts\windows\common.ps1')
$lease = $null
$result = 1
try {
    if ($Resume) {
        $root = Get-NipatZipRoot
        if ($InstallRoot -and (Resolve-NipatInstallPath $InstallRoot) -ine $root) { throw 'La ripresa ZIP richiede la cartella registrata.' }
        $pointer = Read-NipatZipPointer $root 'pending.json'
        $project = $pointer.app_dir
        $manifest = Assert-NipatZipApplication $project -Installed
        if ($manifest.version -cne $pointer.version -or $manifest.source_commit -cne $pointer.source_commit) { throw 'Versione in attesa diversa dal pacchetto installato.' }
        $layout = Read-NipatInstallLayout $project
    } else {
        if (-not $BundleDirectory) { throw 'Estrarre lo ZIP completo e avviare 1_INSTALLA.cmd.' }
        $bundle = Resolve-NipatInstallPath $BundleDirectory
        Assert-NipatInstallPathWithoutLinks $bundle -Tree
        $source = Join-Path $bundle 'app'
        $manifest = Assert-NipatZipApplication $source
        foreach ($key in @('rootfs', 'scientific_image')) {
            $asset = $manifest.assets.$key
            if (-not (Test-NipatAsset (Join-Path (Join-Path $bundle 'assets') $asset.file) $asset)) {
                throw "Asset incluso assente o non integro: $($asset.file). Estrarre nuovamente lo ZIP completo."
            }
        }
        if ($VerifyOnly) { Write-Host 'PASS: ZIP completo verificato; nessuna installazione eseguita.'; exit 0 }
        $root = Get-NipatZipInstallRoot $bundle $InstallRoot -AllowNew
        $project = Get-NipatZipProject $root $manifest.version $manifest.source_commit
        $pointer = [pscustomobject][ordered]@{ schema_version = 1; version = $manifest.version; source_commit = $manifest.source_commit; app_dir = $project }
        $layout = [pscustomobject][ordered]@{
            schema_version = 1; installation_channel = 'desktop'; app_dir = $project
            runtime_dir = (Join-Path $root 'wsl'); cache_dir = (Join-Path $root 'cache')
            data_dir = (Join-Path $root 'data'); runs_dir = (Join-Path $root 'runs')
        }
    }
    Assert-NipatWindowsUser
    $lease = Enter-NipatInstallationActivity
    Assert-NipatZipRoot $root -Create
    foreach ($file in @('current.json', 'pending.json')) { Assert-NipatActivityPathWithoutLinks (Join-Path $root $file) }
    if (Test-Path -LiteralPath (Join-Path $root 'current.json')) {
        $current = Read-NipatZipPointer $root
        if ([version]$current.version -gt [version]$manifest.version) { throw 'Installazione di una versione precedente non consentita. La versione attiva resta disponibile.' }
        if ($current.version -ceq $manifest.version -and $current.source_commit -cne $manifest.source_commit) { throw 'La stessa versione identifica un commit differente.' }
    }
    Assert-NipatInstallPathWithoutLinks $project -Tree
    if (-not $Resume) {
        if (Test-Path -LiteralPath $project) {
            Assert-NipatZipApplication $project -Installed | Out-Null
        } else {
            $staging = Join-Path (Join-Path $root 'versions') ('.staging-' + [Guid]::NewGuid().ToString('N'))
            [IO.Directory]::CreateDirectory($staging) | Out-Null
            Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $staging -Recurse
            Assert-NipatZipApplication $staging | Out-Null
            [IO.Directory]::Move($staging, $project)
        }
        Write-NipatZipOwnership $project 'application'
        foreach ($role in @('runtime', 'cache')) { Write-NipatZipOwnership $layout.($role + '_dir') $role }
        Write-NipatJsonAtomic (Join-Path $project '.runtime\install-layout.json') $layout
        Write-NipatJsonAtomic (Join-Path $project '.runtime\zip-install.json') ([ordered]@{ schema_version = 1; installation_method = 'zip'; root = $root })
    }
    Assert-NipatInstallLayout $layout -CheckExisting
    if (-not $Resume) {
        # Cache BOTH archives before WSL activation can request a reboot.
        foreach ($key in @('rootfs', 'scientific_image')) {
            Get-NipatAsset $manifest.assets.$key $layout.cache_dir (Join-Path $bundle 'assets') | Out-Null
        }
    }
    Write-NipatJsonAtomic (Join-Path $root 'pending.json') $pointer
    Set-NipatZipShortcuts $root $project
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $project 'installer\windows\bootstrap.ps1'), '-ManualResume')
    if ($Resume) { $arguments += '-Resume' }
    & $powershell @arguments
    $result = $LASTEXITCODE
    if ($result -eq 0) {
        Complete-NipatZipActivation $root $pointer
        Set-NipatZipShortcuts $root $project
        Write-Host ('NewPat ZIP pronto. Aprire ' + (Join-Path $root 'NewPat.lnk'))
        Write-Host "Dati e risultati: $root"
    } elseif ($result -eq 3010) {
        Write-Host ('Dopo il riavvio aprire ' + (Join-Path $root 'NewPat.lnk') + ' per completare automaticamente la preparazione.')
    } else {
        throw "Preparazione ZIP non completata (codice $result). La precedente versione attiva resta selezionata. Diagnostica: $project\.runtime\installer\setup.log"
    }
} catch {
    $result = 1
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
} finally { if ($null -ne $lease) { Exit-NipatInstallationActivity $lease } }
if ($result -eq 0 -and $OpenWhenReady) {
    & (Join-Path $project 'scripts\windows\run.ps1') gui
    $result = $LASTEXITCODE
}
exit $result
