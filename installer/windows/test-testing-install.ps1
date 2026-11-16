# Test the real release entrypoint. Only WSL preparation, Desktop registration
# and the graphical child are fixture boundaries; no network or real data.
. (Join-Path $PSScriptRoot 'install-testing.ps1') -LibraryOnly
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('NIPAT Testing & ' + [char]0x00e8 + '-' + [Guid]::NewGuid().ToString('N'))
$oldLocal = $env:LOCALAPPDATA
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
function Assert-Test([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "PASS: $Message"
}
function Assert-Rejected([scriptblock]$Action, [string]$Message) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-Test $rejected $Message
}
function Write-Json([string]$Path, $Value) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
}
function New-InstalledFixture([string]$Root, [string]$Version = '0.9.0') {
    $source = 'a' * 40
    $project = Join-Path (Join-Path $Root 'versions') ($Version + '-' + $source)
    Write-Json (Join-Path $Root 'installation.json') @{ schema_version=1; product='nipat-desktop'; installation_method='zip' }
    Write-Json (Join-Path $Root 'current.json') @{ schema_version=1; version=$Version; source_commit=$source; app_dir=$project }
    Write-Json (Join-Path $project '.distribution\installer-manifest.json') @{ version=$Version; source_commit=$source }
    [IO.Directory]::CreateDirectory((Join-Path $Root 'runs\Testgrafico1')) | Out-Null
    [IO.File]::WriteAllText((Join-Path $Root 'runs\Testgrafico1\run.json'), '{"status":"running"}')
    [IO.File]::WriteAllText((Join-Path $Root 'preferences.json'), '{"language":"it"}')
    return $project
}
function Prepare-Download([string]$Directory) {
    [IO.Directory]::CreateDirectory($Directory) | Out-Null
    $archive = Join-Path $Directory 'NIPAT-0.9.1-Windows-completo.zip'
    [IO.Compression.ZipFile]::CreateFromDirectory($script:FixtureBundle, $archive)
    return @{ file=(Split-Path -Leaf $archive); size=(Get-Item -LiteralPath $archive).Length;
        sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() }
}
try {
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    $env:LOCALAPPDATA = Join-Path $temporary 'Local app data'
    $metadataDirectory = Join-Path $temporary 'entry & source'
    [IO.Directory]::CreateDirectory($metadataDirectory) | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-testing.ps1') -Destination $metadataDirectory
    $entry = Join-Path $metadataDirectory 'install-testing.ps1'
    $fixtureBundle = Join-Path $temporary 'fixture'
    $fixtureApp = Join-Path $fixtureBundle 'app'
    [IO.Directory]::CreateDirectory((Join-Path $fixtureApp 'installer\windows')) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $fixtureApp 'scripts\windows')) | Out-Null
    Write-Json (Join-Path $fixtureApp '.distribution\installer-manifest.json') @{ version='0.9.1'; source_commit=('b' * 40) }
    @'
param([string]$BundleDirectory, [string]$InstallRoot, [switch]$Resume)
$ErrorActionPreference = 'Stop'
function Save-Json($Path, $Value) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}
if ($Resume) {
    $project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $root = (Get-Content -LiteralPath (Join-Path $project '.runtime\zip-install.json') -Raw | ConvertFrom-Json).root
} else {
    $root = $InstallRoot
    $project = Join-Path (Join-Path $root 'versions') ('0.9.1-' + ('b' * 40))
    [IO.Directory]::CreateDirectory($project) | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $BundleDirectory 'app') -Force | Copy-Item -Destination $project -Recurse -Force
}
Save-Json (Join-Path $root 'installation.json') @{ schema_version=1; product='nipat-desktop'; installation_method='zip' }
Save-Json (Join-Path $project '.runtime\zip-install.json') @{ schema_version=1; installation_method='zip'; root=$root }
$pointer = @{ schema_version=1; version='0.9.1'; source_commit=('b' * 40); app_dir=$project }
if ($env:NIPAT_TESTING_FIXTURE_PHASE -eq 'reboot') {
    Save-Json (Join-Path $root 'pending.json') $pointer
    exit 3010
}
Save-Json (Join-Path $root 'current.json') $pointer
Remove-Item -LiteralPath (Join-Path $root 'pending.json') -ErrorAction SilentlyContinue
exit 0
'@ | Set-Content -LiteralPath (Join-Path $fixtureApp 'installer\windows\install-zip.ps1') -Encoding UTF8
    @'
function Assert-NipatZipRoot([string]$Root) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'installation.json'))) { throw 'Missing root ownership' }
}
function Write-NipatJsonAtomic([string]$Path, $Value) { $Value | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding UTF8 }
function Set-NipatZipShortcuts([string]$Root, [string]$Project) {
    $Project | Set-Content -LiteralPath (Join-Path $Root 'NewPat.lnk') -Encoding UTF8
}
'@ | Set-Content -LiteralPath (Join-Path $fixtureApp 'installer\windows\zip-common.ps1') -Encoding UTF8
    @'
if ($args.Count -ne 1 -or $args[0] -cne 'gui') { throw 'GUI argument missing' }
Add-Content -LiteralPath $env:NIPAT_TESTING_FIXTURE_LAUNCHES -Value 'gui'
exit 0
'@ | Set-Content -LiteralPath (Join-Path $fixtureApp 'scripts\windows\run.ps1') -Encoding UTF8
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $destination = Join-Path $temporary ('Explicit install & ' + [char]0x00e8)
    $record = Prepare-Download $destination
    $metadata = @{ schema_version=1; channel='testing'; version='0.9.1'; source_commit=('b' * 40); complete_zip=$record }
    Write-Json (Join-Path $metadataDirectory 'testing-release.json') $metadata
    $env:NIPAT_TESTING_FIXTURE_LAUNCHES = Join-Path $temporary 'launches.txt'
    $env:NIPAT_TESTING_FIXTURE_PHASE = 'reboot'
    & $powershell -NoProfile -ExecutionPolicy Bypass -File $entry -Destination $destination
    Assert-Test ($LASTEXITCODE -eq 3010) 'first entry reports required reboot'
    $root = Join-Path $destination 'NIPAT'
    Assert-Test (Test-Path -LiteralPath (Join-Path $root 'pending.json')) 'reboot retains pending installation'
    Assert-Test (Test-Path -LiteralPath (Join-Path $root 'NewPat.lnk')) 'same app entry available before reboot'
    Assert-Test (-not (Test-Path -LiteralPath $env:NIPAT_TESTING_FIXTURE_LAUNCHES)) 'GUI not started before ready'
    Remove-Item -LiteralPath (Join-Path $destination 'pacchetto') -Recurse -Force
    Remove-Item -LiteralPath (Join-Path $destination $record.file)
    $env:NIPAT_TESTING_FIXTURE_PHASE = 'ready'
    & $powershell -NoProfile -ExecutionPolicy Bypass -File $entry -Destination $destination
    Assert-Test ($LASTEXITCODE -eq 0) 'same entry resumes without original bundle or archive'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $root 'pending.json'))) 'resume activates ready version'
    Assert-Test (@(Get-Content -LiteralPath $env:NIPAT_TESTING_FIXTURE_LAUNCHES).Count -eq 1) 'resume opens GUI once'
    & $powershell -NoProfile -ExecutionPolicy Bypass -File $entry -Destination $destination
    Assert-Test ($LASTEXITCODE -eq 0) 'same entry reopens ready app without download'
    Assert-Test (@(Get-Content -LiteralPath $env:NIPAT_TESTING_FIXTURE_LAUNCHES).Count -eq 2) 'ready relaunch opens GUI once'

    $legacy = Join-Path $env:LOCALAPPDATA 'NIPAT-Testing\0.9.0\pacchetto\NIPAT'
    New-InstalledFixture $legacy | Out-Null
    $download = Join-Path $env:LOCALAPPDATA 'NIPAT-Testing\0.9.1'
    Assert-Test ((Get-TestingInstallRoot $download $true) -ceq $legacy) 'default preview upgrade retains legacy root'
    $stable = Join-Path $env:LOCALAPPDATA 'NIPAT Desktop'
    New-InstalledFixture $stable '0.8.99' | Out-Null
    Assert-Rejected { Assert-TestingRoot $stable } 'stable application cannot be adopted as Testing'
    $metadata.complete_zip = Prepare-Download $download
    Write-Json (Join-Path $metadataDirectory 'testing-release.json') $metadata
    & $powershell -NoProfile -ExecutionPolicy Bypass -File $entry
    Assert-Test ($LASTEXITCODE -eq 0) 'default entry upgrades legacy Testing installation'
    Assert-Test ((Get-Content -LiteralPath (Join-Path $legacy 'current.json') -Raw | ConvertFrom-Json).version -ceq '0.9.1') 'preview upgrade selects0.9.1'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $legacy 'runs\Testgrafico1\run.json')) -ceq '{"status":"running"}') 'preview experiment files preserved exactly'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $legacy 'preferences.json')) -ceq '{"language":"it"}') 'preview preferences preserved exactly'
    Assert-Test ((Get-Content -LiteralPath (Join-Path $stable 'current.json') -Raw | ConvertFrom-Json).version -ceq '0.8.99') 'stable application remains selected and untouched'
    $pointer = Get-Content -LiteralPath (Join-Path $legacy 'current.json') -Raw | ConvertFrom-Json
    $pointer.app_dir = $stable
    Write-Json (Join-Path $legacy 'current.json') $pointer
    Assert-Rejected { Get-TestingInstallRoot $download $true } 'foreign current pointer is rejected before executing any worker'
    $foreign = Join-Path $temporary 'unowned\NIPAT'
    [IO.Directory]::CreateDirectory($foreign) | Out-Null
    [IO.File]::WriteAllText((Join-Path $foreign 'keep.txt'), 'keep')
    Assert-Rejected { Get-TestingInstallRoot (Split-Path -Parent $foreign) $false } 'foreign custom destination is not adopted'

    $bundle = Join-Path $download 'pacchetto'
    $archive = Join-Path $download $metadata.complete_zip.file
    Assert-TestingBundle $archive $bundle
    Add-Content -LiteralPath (Join-Path $bundle 'app\installer\windows\install-zip.ps1') -Value '# changed'
    Assert-Rejected { Assert-TestingBundle $archive $bundle } 'modified extracted installer rejected before execution'
    $emptyArchive = Join-Path $temporary 'empty.zip'
    $empty = [IO.Compression.ZipFile]::Open($emptyArchive, [IO.Compression.ZipArchiveMode]::Create)
    $empty.Dispose()
    Assert-Rejected { Assert-TestingBundle $emptyArchive $bundle } 'archive without verified executable source cannot pass vacuously'
    $unsafeArchive = Join-Path $temporary 'unsafe.zip'
    $unsafe = [IO.Compression.ZipFile]::Open($unsafeArchive, [IO.Compression.ZipArchiveMode]::Create)
    try { $unsafe.CreateEntry('app/../outside.ps1') | Out-Null } finally { $unsafe.Dispose() }
    Assert-Rejected { Assert-TestingBundle $unsafeArchive $bundle } 'source traversal rejected before file access'
} finally {
    $env:LOCALAPPDATA = $oldLocal
    Remove-Item Env:NIPAT_TESTING_FIXTURE_PHASE, Env:NIPAT_TESTING_FIXTURE_LAUNCHES -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
