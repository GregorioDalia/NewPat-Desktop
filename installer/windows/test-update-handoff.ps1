# Integration check: real worker processes and a recording executable, no WSL installation.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('nipat handoff & ' + [char]0x03A9 + '-' + [Guid]::NewGuid().ToString('N'))
$oldLocal = $env:LOCALAPPDATA
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$script:Children = @()
$primaryFailure = $null

function Assert-Test([bool] $Condition, [string] $Description) {
    if (-not $Condition) { throw ('FAIL: ' + $Description) }
    Write-Host ('PASS: ' + $Description)
}
function Quote-Test([string] $Value) {
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}
function Wait-TestFile([string] $File) {
    $limit = [DateTime]::UtcNow.AddSeconds(20)
    while (-not (Test-Path -LiteralPath $File)) {
        if ([DateTime]::UtcNow -gt $limit) { throw "Timed out waiting for $File" }
        Start-Sleep -Milliseconds 50
    }
}
function Write-TestJson([string] $File, $Object) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $File)) | Out-Null
    [IO.File]::WriteAllText($File, ($Object | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
}
function Start-TestProcess([string] $Arguments, $Environment = @{}) {
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $powershell
    $start.Arguments = $Arguments
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    foreach ($key in $Environment.Keys) { $start.EnvironmentVariables[$key] = $Environment[$key] }
    $process = [Diagnostics.Process]::Start($start)
    $script:Children += $process
    return $process
}

function Wait-TestRelaunch([string] $Root) {
    $recordFile = Join-Path $Root 'reopened-process.json'
    Wait-TestFile $recordFile
    $record = Get-Content -LiteralPath $recordFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $process = [Diagnostics.Process]::GetProcessById([int]$record.pid)
    # The fixture waits for acknowledgement. Pin its handle while it is alive:
    # GetProcessById alone does not retain ExitCode after a fast process exits.
    # Never attach cleanup to an unrelated process that has reused its PID.
    $null = $process.Handle
    $started = $process.StartTime
    if ($null -eq $started -or $started.ToUniversalTime().Ticks -ne [long]$record.started_ticks) {
        $process.Dispose()
        throw 'Reopened fixture process identity does not match.'
    }
    $script:Children += $process
    [IO.File]::WriteAllText((Join-Path $Root 'reopened-observed'), 'handle retained')
    Assert-Test ($process.WaitForExit(20000)) 'reopened fixture entry point finishes before directory cleanup'
    $exitCode = $process.ExitCode
    Assert-Test ($null -ne $exitCode -and $exitCode -eq 0) "reopened fixture entry point exits successfully (exit $exitCode)"
}

try {
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    $env:LOCALAPPDATA = Join-Path $temporary 'user-local'
    [IO.Directory]::CreateDirectory((Join-Path $env:LOCALAPPDATA 'NIPAT-Desktop')) | Out-Null
    $fixture = Join-Path $temporary 'recording-installer.exe'
    Add-Type -TypeDefinition @'
using System;
using System.IO;
class RecordingInstaller {
  static int Main(string[] args) {
    string root = Environment.GetEnvironmentVariable("NIPAT_HANDOFF_FIXTURE");
    if (args.Length > 1 && args[1] == "extract-update") {
      File.WriteAllLines(Path.Combine(root,"extracted.txt"),args);
      string destination = args[Array.IndexOf(args,"--destination")+1];
      string scripts = Path.Combine(destination,"app","installer","windows");
      Directory.CreateDirectory(scripts);
      File.Copy(Path.Combine(root,"zip-worker.ps1"),Path.Combine(scripts,"install-zip.ps1"));
      return 0;
    }
    if (args.Length > 0 && args[0] == "-m") {
      File.WriteAllLines(Path.Combine(root,"reopened.txt"), args);
      return 0;
    }
    File.WriteAllLines(Path.Combine(root,"invoked.txt"), args);
    File.WriteAllText(Path.Combine(root,"invoked-location.txt"),System.Reflection.Assembly.GetExecutingAssembly().Location);
    string[] behavior = File.ReadAllLines(Path.Combine(root,"behavior.txt"));
    if (behavior[1] != "keep") {
      string app = Path.Combine(root,"app & space");
      string commit = new string('b',40);
      string runtime = "sha256:" + new string('c',64);
      string state = "{\"schema_version\":1,\"installation_channel\":\"desktop\",\"phase\":\""+behavior[1]+"\",\"version\":\"0.6.1\",\"source_commit\":\""+commit+"\",\"runtime_image\":\""+runtime+"\"}";
      File.WriteAllText(Path.Combine(app,".runtime","installer","state.json"),state);
      File.WriteAllText(Path.Combine(app,".distribution","installer-manifest.json"),state);
    }
    return Int32.Parse(behavior[0]);
  }
}
'@ -Language CSharp -OutputAssembly $fixture -OutputType ConsoleApplication
    $holder = Join-Path $temporary 'parent-holder.ps1'
    [IO.File]::WriteAllText($holder, @'
param([string]$Release,[int]$Code=85)
$limit=[DateTime]::UtcNow.AddMinutes(2)
while(-not(Test-Path -LiteralPath $Release)){if([DateTime]::UtcNow -gt $limit){exit 1};Start-Sleep -Milliseconds 50}
exit $Code
'@)
    foreach ($case in @('success', 'busy', 'tampered', 'canceled', 'unconfirmed', 'pending', 'reboot', 'failed', 'old-ready', 'bootstrap', 'bootstrap-tampered', 'zip', 'zip-failed')) {
        $root = Join-Path $temporary $case
        $zipCase = $case.StartsWith('zip')
        $app = if ($zipCase) { Join-Path $root ('NIPAT\versions\0.8.99-' + ('a'*40)) } else { Join-Path $root 'app & space' }
        $targetVersion = if ($zipCase) { '0.8.100' } else { '0.6.1' }
        $work = Join-Path $root 'outside app worker'
        $data = Join-Path $root 'research data'
        foreach ($dir in @($work,$data,(Join-Path $app 'scripts\windows'),(Join-Path $app 'installer\windows'),
            (Join-Path $app '.runtime\installer'),(Join-Path $app '.distribution'))) {
            [IO.Directory]::CreateDirectory($dir) | Out-Null
        }
        $sentinel = Join-Path $data 'preserve.txt'
        [IO.File]::WriteAllText($sentinel,'research data stays unchanged')
        $preference = Join-Path $env:LOCALAPPDATA 'NIPAT-Desktop\preferences.json'
        [IO.File]::WriteAllText($preference,'{"schema_version":1,"language":"en"}')
        $sentinelHash = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
        $preferenceHash = (Get-FileHash -LiteralPath $preference -Algorithm SHA256).Hash
        Copy-Item -LiteralPath (Join-Path $projectRoot 'scripts\windows\run.ps1') -Destination (Join-Path $app 'scripts\windows\run.ps1')
        Copy-Item -LiteralPath $fixture -Destination (Join-Path $app 'python-fixture.exe')
        [IO.File]::WriteAllText((Join-Path $app 'scripts\windows\common.ps1'), @'
$fixtureRoot = $env:NIPAT_HANDOFF_FIXTURE
$fixtureProcess = [Diagnostics.Process]::GetCurrentProcess()
$fixtureRecord = @{pid=$PID;started_ticks=$fixtureProcess.StartTime.ToUniversalTime().Ticks} | ConvertTo-Json
$fixtureTemporary = Join-Path $fixtureRoot 'reopened-process.tmp'
[IO.File]::WriteAllText($fixtureTemporary,$fixtureRecord,(New-Object Text.UTF8Encoding($false)))
[IO.File]::Move($fixtureTemporary,(Join-Path $fixtureRoot 'reopened-process.json'))
$fixtureProcess.Dispose()
$fixtureDeadline = [DateTime]::UtcNow.AddSeconds(20)
while (-not (Test-Path -LiteralPath (Join-Path $fixtureRoot 'reopened-observed'))) {
    if ([DateTime]::UtcNow -gt $fixtureDeadline) { throw 'Relaunch observer did not acknowledge the process.' }
    Start-Sleep -Milliseconds 20
}
function Get-NipatProject { return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) }
function Set-NipatEnvironment([string]$Project) {}
function Get-NipatPython([string]$Project) { return (Join-Path $Project 'python-fixture.exe') }
'@)
        [IO.File]::WriteAllText((Join-Path $app 'installer\windows\bootstrap-common.ps1'), @'
function Read-NipatInstallerManifest([string]$Path) { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
function Assert-NipatRuntimeBinding($Manifest,$State,$Configuration) {
 if($Manifest.source_commit -cne $State.source_commit){throw 'binding mismatch'}
}
function Resolve-NipatInstallPath([string]$Path) { return [IO.Path]::GetFullPath($Path) }
function Assert-NipatInstallPathWithoutLinks([string]$Path) { Assert-LocalPath $Path | Out-Null }
'@)
        $state = [ordered]@{schema_version=1;installation_channel='desktop';phase='ready';version='0.6.0';source_commit=('a'*40);runtime_image=('sha256:'+('c'*64))}
        Write-TestJson (Join-Path $app '.runtime\installer\state.json') $state
        Write-TestJson (Join-Path $app '.distribution\installer-manifest.json') $state
        Write-TestJson (Join-Path $app '.runtime\backend.json') @{schema_version=1}
        $code = if($case -eq 'reboot'){3010}elseif($case -eq 'failed'){1}else{0}
        $phase = if($case -eq 'pending'){'verifying_installation'}elseif($case -eq 'old-ready'){'keep'}else{'ready'}
        [IO.File]::WriteAllLines((Join-Path $root 'behavior.txt'),[string[]]@([string]$code,$phase))
        $bootstrapCase = $case.StartsWith('bootstrap')
        $packageName = if ($bootstrapCase) { 'NIPAT-0.6.1-Windows-payload.zip' } elseif ($zipCase) { 'NIPAT-0.8.100-Windows-completo.zip' } else { 'NIPAT-Setup.exe' }
        $package = Join-Path $root $packageName
        if ($bootstrapCase) {
            # This executable records argv; payload parsing is exercised by the
            # downloader/package tests. Here use non-executable payload bytes to
            # prove the worker runs the retained bootstrap, not the ZIP.
            [IO.File]::WriteAllText($package,'verified payload fixture')
            $retained = Join-Path $app '.runtime\setup\NIPAT-Setup.exe'
            [IO.Directory]::CreateDirectory((Split-Path -Parent $retained)) | Out-Null
            Copy-Item -LiteralPath $fixture -Destination $retained
            $setupHash = (Get-FileHash -LiteralPath $retained -Algorithm SHA256).Hash.ToLowerInvariant()
            Write-TestJson (Join-Path $app '.runtime\bootstrap-install.json') @{
                schema_version=1;installation_method='bootstrap';setup_sha256=$setupHash
            }
        } elseif ($zipCase) {
            [IO.File]::WriteAllText($package,'verified ZIP fixture')
            $zipRoot = Join-Path $root 'NIPAT'
            Write-TestJson (Join-Path $zipRoot 'installation.json') @{
                schema_version=1;product='nipat-desktop';installation_method='zip'
            }
            Write-TestJson (Join-Path $zipRoot 'current.json') @{
                schema_version=1;version='0.8.99';source_commit=('a'*40);app_dir=$app
            }
            Write-TestJson (Join-Path $app '.runtime\zip-install.json') @{
                schema_version=1;installation_method='zip';root=$zipRoot
            }
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'zip-common.ps1') -Destination (Join-Path $app 'installer\windows\zip-common.ps1')
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'activity-lock.ps1') -Destination (Join-Path $app 'installer\windows\activity-lock.ps1')
            [IO.Directory]::CreateDirectory((Join-Path $app '.runtime\python')) | Out-Null
            Copy-Item -LiteralPath $fixture -Destination (Join-Path $app '.runtime\python\python.exe')
            [IO.File]::WriteAllText((Join-Path $app 'installer\windows\zip_package.py'),'# extraction is recorded; archive verification has dedicated round-trip tests')
            [IO.File]::WriteAllText((Join-Path $root 'zip-worker.ps1'), @'
param([string]$BundleDirectory,[string]$InstallRoot)
$ErrorActionPreference='Stop'
$root=$env:NIPAT_HANDOFF_FIXTURE
try {
if($InstallRoot -ine (Join-Path $root 'NIPAT')) { throw 'ZIP update did not preserve the selected installation root' }
[IO.File]::WriteAllLines((Join-Path $root 'invoked.txt'),[string[]]@($BundleDirectory,$InstallRoot))
if((Split-Path -Leaf $root) -ceq 'zip-failed') { exit 1 }
$previous=Get-Content -LiteralPath (Join-Path $InstallRoot 'current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$app=Join-Path $InstallRoot ('versions\0.8.100-'+('b'*40))
[IO.Directory]::CreateDirectory($app)|Out-Null
Copy-Item -LiteralPath (Join-Path $previous.app_dir 'scripts') -Destination $app -Recurse
Copy-Item -LiteralPath (Join-Path $previous.app_dir 'installer') -Destination $app -Recurse
Copy-Item -LiteralPath (Join-Path $previous.app_dir 'python-fixture.exe') -Destination $app
[IO.Directory]::CreateDirectory((Join-Path $app '.runtime\installer'))|Out-Null
[IO.Directory]::CreateDirectory((Join-Path $app '.distribution'))|Out-Null
$state=@{schema_version=1;installation_channel='desktop';phase='ready';version='0.8.100';source_commit=('b'*40);runtime_image=('sha256:'+('c'*64))}|ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $app '.runtime\installer\state.json'),$state)
[IO.File]::WriteAllText((Join-Path $app '.distribution\installer-manifest.json'),$state)
[IO.File]::WriteAllText((Join-Path $app '.runtime\backend.json'),'{"schema_version":1}')
$pointer=@{schema_version=1;version='0.8.100';source_commit=('b'*40);app_dir=$app}|ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $InstallRoot 'current.json'),$pointer)
exit 0
} catch {
    [IO.File]::WriteAllText((Join-Path $root 'zip-worker-error.txt'), ($_ | Out-String), (New-Object Text.UTF8Encoding($false)))
    throw
}
'@)
        } else { Copy-Item -LiteralPath $fixture -Destination $package }
        $release = Join-Path $root 'release-parent'
        $parentCode = if ($case -eq 'unconfirmed') { 0 } else { 85 }
        $parent = Start-TestProcess ('-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' + (Quote-Test $holder) + ' -Release ' + (Quote-Test $release) + ' -Code ' + $parentCode)
        $descriptor = Join-Path $work 'handoff.json'
        $handoffRecord = [ordered]@{
            schema_version=1;installation_channel='desktop';parent_pid=$parent.Id;project_dir=$app;package=$package
            sha256=(Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant();size=(Get-Item -LiteralPath $package).Length
            version=$targetVersion;source_commit=('b'*40);data_dir=$data
        }
        if ($bootstrapCase) { $handoffRecord.installation_method = 'bootstrap'; $handoffRecord.setup_sha256 = $setupHash }
        if ($zipCase) { $handoffRecord.installation_method = 'zip' }
        Write-TestJson $descriptor $handoffRecord
        $workerPath = Join-Path $work 'update-handoff.ps1'
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'update-handoff.ps1') -Destination $workerPath
        # The bundled worker sets only its own process policy, also when the
        # launching process has the default Restricted policy. No machine policy changes.
        $worker = Start-TestProcess ('-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' + (Quote-Test $workerPath) + ' -Descriptor ' + (Quote-Test $descriptor) + ' -NoPause') @{
            NIPAT_HANDOFF_FIXTURE=$root; PSExecutionPolicyPreference='Restricted'
        }
        Wait-TestFile (Join-Path $work 'ready.json')
        Assert-Test (-not (Test-Path -LiteralPath (Join-Path $root 'invoked.txt'))) "$case waits for the current CLI to exit"
        $shared = $null
        try {
            if($case -eq 'busy') {
                $shared=[IO.File]::Open((Join-Path $env:LOCALAPPDATA 'NIPAT-Desktop\activity.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
            }
            if($case -eq 'tampered'){[IO.File]::AppendAllText($package,'modified after download')}
            if($case -eq 'bootstrap-tampered'){[IO.File]::AppendAllText($retained,'modified after offer')}
            if($case -eq 'canceled'){[IO.File]::WriteAllText((Join-Path $work 'cancel'),'cancel')}
            [IO.File]::WriteAllText($release,'exit')
            Assert-Test ($worker.WaitForExit(30000)) "$case worker completes"
        } finally {if($null -ne $shared){$shared.Dispose()}}
        if($case -in @('success','bootstrap','zip')) {
            if ($worker.ExitCode -ne 0) {
                foreach ($diagnostic in @('handoff.log','error.txt')) {
                    $file = Join-Path $work $diagnostic
                    if (Test-Path -LiteralPath $file) {
                        Write-Host ($diagnostic + ':')
                        Write-Host (Get-Content -LiteralPath $file -Raw -Encoding UTF8)
                    }
                }
                $zipError = Join-Path $root 'zip-worker-error.txt'
                if (Test-Path -LiteralPath $zipError) { Write-Host (Get-Content -LiteralPath $zipError -Raw -Encoding UTF8) }
                throw "The $case worker failed with exit $($worker.ExitCode); no relaunch is expected."
            }
            Wait-TestRelaunch $root
            Wait-TestFile (Join-Path $root 'reopened.txt')
        }
        if($case -in @('busy','tampered','canceled','unconfirmed','bootstrap-tampered')) {
            Assert-Test (-not(Test-Path -LiteralPath (Join-Path $root 'invoked.txt'))) "$case never starts an installer"
        } else {
            Assert-Test (Test-Path -LiteralPath (Join-Path $root 'invoked.txt')) "$case invokes the verified executable"
            $arguments=Get-Content -LiteralPath (Join-Path $root 'invoked.txt') -Encoding UTF8
            if ($zipCase) {
                Assert-Test ($arguments.Count -eq 2 -and $arguments[0] -ieq (Join-Path $work 'verified-zip') -and
                    $arguments[1] -ieq $zipRoot) 'ZIP worker receives separate bundle and persistent install roots'
                Assert-Test (-not (Test-Path -LiteralPath (Join-Path $work 'verified-zip\NIPAT'))) 'ZIP update never installs under its temporary extraction directory'
                $pointer = Get-Content -LiteralPath (Join-Path $zipRoot 'current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
                $expectedVersion = if ($case -ceq 'zip') { '0.8.100' } else { '0.8.99' }
                Assert-Test ($pointer.version -ceq $expectedVersion) 'ZIP success selects the new version; a failed preparation keeps the existing version'
            } else {
                Assert-Test ($arguments -ccontains ('/DIR='+$app) -and $arguments -ccontains '/NIPATUPDATE=1') "$case preserves the application path as one argv value"
            }
            if ($bootstrapCase) {
                Assert-Test ($arguments -ccontains ('/NIPATPACKAGE='+$package) -and
                    $arguments -ccontains '/NIPATVERSION=0.6.1' -and
                    $arguments -ccontains ('/NIPATSOURCE='+('b'*40)) -and
                    $arguments -ccontains ('/NIPATSHA256='+$handoffRecord.sha256) -and
                    $arguments -ccontains ('/NIPATSIZE='+$handoffRecord.size)) 'bootstrap receives the exact accepted payload identity without latest lookup'
                $executed = [IO.File]::ReadAllText((Join-Path $root 'invoked-location.txt'))
                Assert-Test ($executed -ieq (Join-Path $work 'NIPAT-Setup.exe')) 'bootstrap executes outside application before replacement'
                Assert-Test ((Get-FileHash -LiteralPath $executed -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $setupHash) 'bootstrap executable bytes remain unchanged'
            }
        }
        if($case -in @('success','bootstrap','zip')) {
            Assert-Test ($worker.ExitCode -eq 0) 'two-version ready update reopens through production run.ps1'
        } else {
            Assert-Test (-not(Test-Path -LiteralPath (Join-Path $root 'reopened.txt'))) "$case does not reopen NIPAT"
            Assert-Test ($worker.ExitCode -ne 0) "$case reports an incomplete handoff"
        }
        Assert-Test ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ceq $sentinelHash -and
            (Get-FileHash -LiteralPath $preference -Algorithm SHA256).Hash -ceq $preferenceHash) "$case preserves research data and user preferences"
    }
} catch {
    $primaryFailure = $_
    throw
} finally {
    # Stop only test-owned processes, in reverse start order so releasing the
    # parent cannot race a still-live worker into launching another fixture.
    for($index=$script:Children.Count-1;$index -ge 0;$index--) {
        $child=$script:Children[$index]
        try{if(-not $child.HasExited){$child.Kill();$child.WaitForExit(5000)|Out-Null};$child.Dispose()}catch{}
    }
    $env:LOCALAPPDATA=$oldLocal
    try {
        if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary -Recurse -Force}
    } catch {
        if ($null -eq $primaryFailure) { throw }
        Write-Warning ('Cleanup after the original test failure also failed: ' + $_.Exception.Message)
    }
}
