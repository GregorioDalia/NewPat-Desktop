# Lifecycle guards with real local files; no WSL, registry or menu modifications.
. (Join-Path $PSScriptRoot 'zip-common.ps1')
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('NIPAT ZIP lifecycle & ' + [char]0x00e8 + '-' + [Guid]::NewGuid().ToString('N'))
$oldLocal = $env:LOCALAPPDATA
function Assert-Test([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "PASS: $Message"
}
function Assert-Rejected([scriptblock] $Action, [string] $Message) {
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert-Test $failed $Message
}
function Set-FixtureFunction([string] $Path, [string] $Name, [string] $Body) {
    $source = [IO.File]::ReadAllText($Path)
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
    $node = $ast.Find({ param($item) $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $item.Name -ceq $Name }, $true)
    if ($null -eq $node) { throw "Missing fixture boundary $Name" }
    $source = $source.Substring(0, $node.Extent.StartOffset) + $Body + $source.Substring($node.Extent.EndOffset)
    [IO.File]::WriteAllText($Path, $source, (New-Object Text.UTF8Encoding($false)))
}
function Write-FixtureManifest([string] $App, [string] $Assets, [string] $Version, [string] $Commit) {
    [IO.File]::WriteAllText((Join-Path $App 'src\nipat\__init__.py'), ('__version__ = "' + $Version + '"'))
    $distribution = Join-Path $App '.distribution'
    if (Test-Path -LiteralPath $distribution) { Remove-Item -LiteralPath $distribution -Recurse -Force }
    $sourceHashes = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $App -Recurse -Force -File) {
        $sourceHashes[$file.FullName.Substring($App.Length + 1).Replace('\', '/')] = (Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    }
    $assetsRecord = [ordered]@{}
    foreach ($key in @('rootfs', 'scientific_image')) {
        $path = Join-Path $Assets ($key + '.tar.gz')
        [IO.File]::WriteAllText($path, "fixture bytes for $key")
        $assetsRecord[$key] = [ordered]@{ file = ($key + '.tar.gz'); size = (Get-Item -LiteralPath $path).Length
            sha256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
            url = ('https://github.com/GregorioDalia/nipat-desktop/releases/download/v' + $Version + '/' + $key + '.tar.gz') }
    }
    Write-NipatJsonAtomic (Join-Path $distribution 'installer-manifest.json') ([ordered]@{
        schema_version = 1; version = $Version; release_tag = ('v' + $Version); source_commit = $Commit
        runtime_image = ('sha256:' + ('d' * 64)); installation_profile = (Get-NipatInstallationProfile)
        assets = $assetsRecord; source_sha256 = $sourceHashes
    })
    $files = @()
    foreach ($file in Get-ChildItem -LiteralPath $App -Recurse -Force -File) {
        $files += [ordered]@{ path = $file.FullName.Substring($App.Length + 1).Replace('\', '/'); sha256 = (Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant() }
    }
    Write-NipatJsonAtomic (Join-Path $distribution 'application-files.json') ([ordered]@{ schema_version = 1; installation_channel = 'desktop'; source_commit = $Commit; files = $files })
}
try {
    $env:LOCALAPPDATA = $temporary
    $root = Join-Path $temporary "Cartella estratta & locale\NIPAT"
    [IO.Directory]::CreateDirectory($root) | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'foreign.txt'), 'keep')
    Assert-Rejected { Assert-NipatZipRoot $root -Create } 'nonempty unowned directory rejected'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $root 'foreign.txt')) -ceq 'keep') 'foreign file retained'
    Remove-Item -LiteralPath (Join-Path $root 'foreign.txt')
    Assert-NipatZipRoot $root -Create
    Assert-NipatZipRoot $root
    $old = [pscustomobject]@{ schema_version = 1; version = '0.8.99'; source_commit = ('a' * 40); app_dir = (Get-NipatZipProject $root '0.8.99' ('a' * 40)) }
    $next = [pscustomobject]@{ schema_version = 1; version = '0.9.0'; source_commit = ('b' * 40); app_dir = (Get-NipatZipProject $root '0.9.0' ('b' * 40)) }
    Write-NipatJsonAtomic (Join-Path $old.app_dir '.runtime\zip-install.json') ([ordered]@{ schema_version = 1; installation_method = 'zip'; root = $root })
    Assert-Test ((Get-NipatZipRoot $old.app_dir) -ceq $root) 'installed ZIP resolves its local root'
    $foreignRoot = Join-Path $temporary 'foreign-owned-root'
    Assert-NipatZipRoot $foreignRoot -Create
    Write-NipatJsonAtomic (Join-Path $old.app_dir '.runtime\zip-install.json') ([ordered]@{ schema_version = 1; installation_method = 'zip'; root = $foreignRoot })
    Assert-Rejected { Get-NipatZipRoot $old.app_dir } 'ZIP marker cannot select another owned root'
    Write-NipatJsonAtomic (Join-Path $old.app_dir '.runtime\zip-install.json') ([ordered]@{ schema_version = 1; installation_method = 'zip'; root = $root })
    Write-NipatJsonAtomic (Join-Path $root 'current.json') $old
    Assert-Test ((Get-NipatZipInstallRoot (Join-Path $temporary 'new extraction') '') -ceq (Join-Path $temporary 'new extraction\NIPAT')) 'fresh extraction chooses adjacent NIPAT directory'
    Assert-Test ((Get-NipatZipInstallRoot (Join-Path $temporary 'download') $root) -ceq $root) 'explicit update retains installed root'
    Assert-Rejected { Get-NipatZipInstallRoot (Join-Path $temporary 'download') (Join-Path $temporary 'unowned') } 'explicit update rejects unowned destination'
    Write-NipatJsonAtomic (Join-Path $root 'pending.json') $next
    $stateFile = Join-Path $next.app_dir '.runtime\installer\state.json'
    foreach ($phase in @('starting', 'awaiting_reboot', 'failed')) {
        Write-NipatJsonAtomic $stateFile ([ordered]@{ phase = $phase; version = $next.version; source_commit = $next.source_commit; installation_channel = 'desktop' })
        Assert-Rejected { Complete-NipatZipActivation $root $next } "no activation when $phase"
        Assert-Test ((Read-NipatZipPointer $root).app_dir -ceq $old.app_dir) "previous version preserved when $phase"
        Assert-Test ((Read-NipatZipPointer $root 'pending.json').app_dir -ceq $next.app_dir) "resume pointer retained when $phase"
    }
    Write-NipatJsonAtomic $stateFile ([ordered]@{ phase = 'ready'; version = $next.version; source_commit = ('c' * 40); installation_channel = 'desktop' })
    Assert-Rejected { Complete-NipatZipActivation $root $next } 'ready state from another source rejected'
    Write-NipatJsonAtomic $stateFile ([ordered]@{ phase = 'ready'; version = $next.version; source_commit = $next.source_commit; installation_channel = 'desktop' })
    Complete-NipatZipActivation $root $next
    Assert-Test ((Read-NipatZipPointer $root).app_dir -ceq $next.app_dir) 'ready version activated atomically'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $root 'pending.json'))) 'pending pointer removed after activation'
    $bad = [pscustomobject]@{ schema_version = 1; version = $next.version; source_commit = $next.source_commit; app_dir = (Join-Path $temporary 'foreign-app') }
    Write-NipatJsonAtomic (Join-Path $root 'current.json') $bad
    Assert-Rejected { Read-NipatZipPointer $root } 'pointer outside managed versions rejected'
    Assert-Rejected { Get-NipatZipProject $root '../outside' ('a' * 40) } 'version traversal rejected'
    $link = Join-Path $temporary 'linked-root'
    New-Item -ItemType Junction -Path $link -Target $root | Out-Null
    Assert-Rejected { Assert-NipatZipRoot $link } 'junction root rejected'
    [IO.Directory]::Delete($link)

    # Real installer processes and real activity lease. Only OS prerequisites,
    # WSL/bootstrap operations and Python runtime selection are fixture boundaries.
    Remove-Item -LiteralPath $root -Recurse -Force
    $bundle = Join-Path $temporary 'extracted & space'
    $root = Join-Path $bundle 'NIPAT'
    $app = Join-Path $bundle 'app'
    $assets = Join-Path $bundle 'assets'
    [IO.Directory]::CreateDirectory($assets) | Out-Null
    $sourceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $relativeFiles = @('installer/windows/install-zip.ps1', 'installer/windows/zip-common.ps1',
        'installer/windows/bootstrap-common.ps1', 'installer/windows/activity-lock.ps1',
        'installer/windows/repair-installation.ps1', 'installer/windows/install-profile.ps1',
        'installer/windows/install-layout.ps1', 'installer/windows/install-profile.json',
        'src/nipat/windows_install_activity.py', 'scripts/windows/common.ps1', 'src/nipat/__init__.py')
    foreach ($relative in $relativeFiles) {
        $target = Join-Path $app $relative
        [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceRoot $relative) -Destination $target
    }
    Set-FixtureFunction (Join-Path $app 'installer/windows/bootstrap-common.ps1') 'Assert-NipatWindowsUser' 'function Assert-NipatWindowsUser { }'
    Set-FixtureFunction (Join-Path $app 'installer/windows/activity-lock.ps1') 'Get-NipatActivityRuntime' @'
function Get-NipatActivityRuntime([string] $Directory = $PSScriptRoot) {
    return [pscustomobject]@{
        Python = (Get-Command python.exe -CommandType Application).Source
        Helper = (Join-Path (Split-Path -Parent (Split-Path -Parent $Directory)) 'src\nipat\windows_install_activity.py')
        Temporary = $null
    }
}
'@
    @'
param([switch] $ManualResume, [switch] $Resume)
. (Join-Path $PSScriptRoot 'zip-common.ps1')
if (-not $ManualResume) { throw 'ZIP must not register or remove the EXE RunOnce key.' }
$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$manifest = Read-NipatInstallerManifest (Join-Path $project '.distribution\installer-manifest.json')
$lease = Enter-NipatInstallationActivity
try {
    if (-not $lease.Borrowed) { throw 'Bootstrap must inherit the live installer lease.' }
    Write-NipatJsonAtomic (Join-Path $project '.runtime\installer\state.json') ([ordered]@{
        phase = $env:NIPAT_ZIP_FIXTURE_PHASE; version = $manifest.version; source_commit = $manifest.source_commit; installation_channel = 'desktop'
    })
} finally { Exit-NipatInstallationActivity $lease }
if ($env:NIPAT_ZIP_FIXTURE_PHASE -ceq 'ready') { exit 0 }
if ($env:NIPAT_ZIP_FIXTURE_PHASE -ceq 'awaiting_reboot') { exit 3010 }
exit 1
'@ | Set-Content -LiteralPath (Join-Path $app 'installer/windows/bootstrap.ps1') -Encoding UTF8
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    Write-FixtureManifest $app $assets '0.8.99' ('a' * 40)
    $env:NIPAT_ZIP_FIXTURE_PHASE = 'awaiting_reboot'
    & $powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'installer/windows/install-zip.ps1') -BundleDirectory $bundle
    Assert-Test ($LASTEXITCODE -eq 3010) 'first ZIP installation returns reboot code'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $root 'current.json'))) 'reboot does not activate incomplete installation'
    Assert-Test (@(Get-ChildItem -LiteralPath (Join-Path $root 'cache') -Filter '*.tar.gz').Count -eq 2) 'both scientific archives cached before reboot'
    $pending = Read-NipatZipPointer $root 'pending.json'
    $env:NIPAT_ZIP_FIXTURE_PHASE = 'ready'
    [IO.Directory]::Move($app, ($app + '-removed'))
    [IO.Directory]::Move($assets, ($assets + '-removed'))
    & $powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $pending.app_dir 'installer/windows/install-zip.ps1') -Resume
    Assert-Test ($LASTEXITCODE -eq 0) 'installed resume completes without extracted bundle'
    [IO.Directory]::Move(($app + '-removed'), $app)
    [IO.Directory]::Move(($assets + '-removed'), $assets)
    Assert-Test ((Read-NipatZipPointer $root).version -ceq '0.8.99') 'first ready installation activated'
    Assert-Test ((Get-NipatZipRoot (Read-NipatZipPointer $root).app_dir) -ceq $root) 'local root persisted in installed marker'
    foreach ($launcher in @('2_AVVIA.cmd', '1_COMPLETA_PREPARAZIONE.cmd', 'NIPAT.lnk')) {
        Assert-Test (Test-Path -LiteralPath (Join-Path $root $launcher)) ("local launcher created: $launcher")
    }
    $appShortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $root 'NIPAT.lnk'))
    Assert-Test ($appShortcut.TargetPath -ieq $powershell) 'normal shortcut uses the system PowerShell interpreter'
    Assert-Test ($appShortcut.Arguments.Contains('-WindowStyle Hidden') -and $appShortcut.Arguments.EndsWith('-Mode auto')) 'normal shortcut hides the bridge and selects automatic setup/launch'
    [IO.Directory]::CreateDirectory((Join-Path $root 'data')) | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'data\preserve.txt'), 'research data')
    $bundle = Join-Path $temporary 'next separate extraction'
    [IO.Directory]::CreateDirectory($bundle) | Out-Null
    Copy-Item -LiteralPath $app -Destination (Join-Path $bundle 'app') -Recurse
    Copy-Item -LiteralPath $assets -Destination (Join-Path $bundle 'assets') -Recurse
    $app = Join-Path $bundle 'app'
    $assets = Join-Path $bundle 'assets'
    Write-FixtureManifest $app $assets '0.9.0' ('b' * 40)
    $env:NIPAT_ZIP_FIXTURE_PHASE = 'failed'
    & $powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'installer/windows/install-zip.ps1') -BundleDirectory $bundle -InstallRoot $root
    Assert-Test ($LASTEXITCODE -eq 1) 'failed upgrade reported as failure'
    Assert-Test ((Read-NipatZipPointer $root).version -ceq '0.8.99') 'failed upgrade retains previous active version'
    Assert-Test ((Get-Content -LiteralPath (Join-Path $root '2_AVVIA.cmd') -Raw).Contains('0.8.99-' + ('a' * 40))) 'failed upgrade launcher retains previous worker'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $bundle 'NIPAT'))) 'update extraction does not create another installation'
    $pending = Read-NipatZipPointer $root 'pending.json'
    $env:NIPAT_ZIP_FIXTURE_PHASE = 'ready'
    & $powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $pending.app_dir 'installer/windows/install-zip.ps1') -Resume
    Assert-Test ($LASTEXITCODE -eq 0 -and (Read-NipatZipPointer $root).version -ceq '0.9.0') 'successful upgrade activates the new app directory'
    Assert-Test ((Get-Content -LiteralPath (Join-Path $root '2_AVVIA.cmd') -Raw).Contains('0.9.0-' + ('b' * 40))) 'successful upgrade refreshes local launcher'
    $appShortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $root 'NIPAT.lnk'))
    Assert-Test ($appShortcut.Arguments.Contains('0.9.0-' + ('b' * 40))) 'app shortcut follows the activated version'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $root 'data\preserve.txt')) -ceq 'research data') 'update retains research data'
} finally {
    $env:LOCALAPPDATA = $oldLocal
    Remove-Item Env:NIPAT_ZIP_FIXTURE_PHASE -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
