# No Pester, elevation, WSL, Docker or network access required. Windows uses Python 3.
# Runs on Windows PowerShell 5.1 and PowerShell 7.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('newpat-bootstrap-test-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temporary) | Out-Null
$assertions = 0
function Assert-Test([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    $script:assertions += 1
}
function Assert-Rejected([scriptblock] $Action, [string] $Message) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-Test $rejected $Message
}
$candidateVersion = Get-NewPatApplicationVersion
function New-TestManifest([string] $Version = $candidateVersion) {
    $assets = [ordered]@{}
    foreach ($name in @('rootfs', 'scientific_image')) {
        $file = $name + '-' + $Version + '.tar.gz'
        $assets[$name] = [ordered]@{
            file = $file; sha256 = ('b' * 64); size = 123
            url = ('https://github.com/GregorioDalia/NewPat-Desktop/releases/download/v' + $Version + '/' + $file)
        }
    }
    return [ordered]@{
        schema_version = 1; version = $Version; release_tag = ('v' + $Version)
        installation_profile = (Get-NewPatInstallationProfile)
        source_commit = ('a' * 40); runtime_image = ('sha256:' + ('c' * 64)); assets = $assets
    }
}
try {
    $manifestPath = Join-Path $temporary 'installer-manifest.json'
    $manifest = New-TestManifest
    Write-NewPatJsonAtomic $manifestPath $manifest
    $parsed = Read-NewPatInstallerManifest $manifestPath
    Assert-Test ($parsed.release_tag -ceq ('v' + $candidateVersion)) 'accept valid release manifest'
    function Invoke-RestMethod {
        param($Method, $Uri, $Headers, $TimeoutSec, $MaximumRedirection)
        if ($Uri -cne 'https://api.github.com/repositories/1307623649') { throw 'Unexpected repository lookup.' }
        return $script:fixtureRepo
    }
    try {
        foreach ($slug in (Get-NewPatOfficialRepositories)) {
            $script:fixtureRepo = @{id = 1307623649; full_name = $slug}
            Assert-Test ((Get-NewPatOnlineRepository) -ceq ('https://github.com/' + $slug)) 'resolve the official repository by ID'
        }
        $script:fixtureRepo = @{id = 1; full_name = 'GregorioDalia/NewPat-Desktop'}
        Assert-Rejected { Get-NewPatOnlineRepository } 'reject a reused repository slug'
        $script:fixtureRepo = @{id = 1307623649; full_name = 'another/NewPat-Desktop'}
        Assert-Rejected { Get-NewPatOnlineRepository } 'reject a foreign repository name'
    } finally {
        Remove-Item Function:Invoke-RestMethod
    }
    $profile = Get-NewPatInstallationProfile
    Assert-Test ($profile.display_name -ceq 'NewPat') 'new install display uses NewPat'
    $legacyProfile = $profile | ConvertTo-Json | ConvertFrom-Json
    $legacyProfile.display_name = 'NewPat Desktop'
    Assert-Rejected { Assert-NewPatInstallationProfile $legacyProfile } 'reject other product names'
    $legacyProfile.app_id = 'foreign-app'
    Assert-Rejected { Assert-NewPatInstallationProfile $legacyProfile } 'legacy brand does not waive ownership identity'
    Assert-Test ($profile.channel -ceq 'desktop' -and $profile.app_dir_name -ceq 'NewPat-Desktop' -and
        $profile.app_id -ceq 'B870A3DA-56E8-4F27-A571-86FCEDD83F25') 'official identity preserves supported Desktop upgrades'
    Assert-Test ($profile.app_dir_name -cne 'NewPat' -and $profile.data_dir_name -cne 'NewPat' -and
        $profile.resume_key -cne 'NewPat-ResumeSetup' -and $profile.distro_prefix -cne 'NewPat-Runtime-') 'candidate identities differ from stable'
    Assert-Test ($profile.app_dir_name -cne 'NewPat-0.5-Preview' -and $profile.data_dir_name -cne 'NewPat-0.5-Preview' -and
        $profile.resume_key -cne 'NewPat-05-Preview-ResumeSetup' -and $profile.distro_prefix -cne 'NewPat-05-Preview-' -and
        $profile.app_id -cne '9E27D451-67B5-4D28-B388-A41CFE2F7D05') 'Desktop identities differ from the retained 0.5 Preview'
    foreach ($field in @('channel', 'app_dir_name', 'data_dir_name', 'distro_prefix', 'resume_key', 'mutex_prefix', 'app_id')) {
        $manifest = New-TestManifest
        $manifest.installation_profile.$field = 'stable'
        Write-NewPatJsonAtomic $manifestPath $manifest
        Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } "reject foreign installation profile $field"
    }
    foreach ($badSchema in @('1', $true)) {
        $manifest = New-TestManifest
        $manifest.installation_profile.schema_version = $badSchema
        Write-NewPatJsonAtomic $manifestPath $manifest
        Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject coerced profile schema version'
    }
    $manifest = New-TestManifest
    $manifest.Remove('installation_profile')
    Write-NewPatJsonAtomic $manifestPath $manifest
    Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject old manifest with no installation channel'

    # Only the registry boundary is simulated; command generation and the keys are production code.
    $resumeValues = @{
        'NewPat-ResumeSetup' = 'stable resume sentinel'
        'NewPat-05-Preview-ResumeSetup' = 'preview resume sentinel'
        'NewPat-Experimental08-ResumeSetup' = 'experimental resume sentinel'
    }
    $registryKey = New-Object PSObject
    $registryKey | Add-Member -MemberType ScriptMethod -Name SetValue -Value {
        param($Name, $Value, $Kind)
        $script:resumeValues[$Name] = $Value
    }
    $registryKey | Add-Member -MemberType ScriptMethod -Name DeleteValue -Value {
        param($Name, $ThrowOnMissing)
        $script:resumeValues.Remove($Name)
    }
    $registryKey | Add-Member -MemberType ScriptMethod -Name Dispose -Value {}
    $openRegistry = (Get-Command Open-NewPatResumeRegistry).ScriptBlock
    function Open-NewPatResumeRegistry([switch] $Create) { return $script:registryKey }
    $oldLocalAppData = $env:LOCALAPPDATA
    try {
        # A short nonexistent location keeps RunOnce below its Windows length limit. No files are written there.
        $env:LOCALAPPDATA = 'C:\NewPatResumeTest'
        $candidateProject = Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') $profile.app_dir_name
        Assert-NewPatInstallationLocation $candidateProject
        Assert-Rejected { Assert-NewPatInstallationLocation (Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') 'NewPat') } 'bootstrap rejects stable app folder before writes'
        Assert-Rejected { Assert-NewPatInstallationLocation (Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') 'NewPat-Experimental08') } 'bootstrap rejects experimental app folder before writes'
        Assert-Rejected { Assert-NewPatInstallationLocation (Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') 'NewPat-0.5-Preview') } 'bootstrap rejects the Preview app folder before writes'
        Assert-Test (Register-NewPatResume $candidateProject) 'candidate resume registration succeeds'
        Assert-Test ($resumeValues[$profile.resume_key].Contains($candidateProject)) 'candidate resume points to candidate app'
        Assert-Test ($resumeValues['NewPat-ResumeSetup'] -ceq 'stable resume sentinel') 'register preserves stable pending resume'
        Assert-Test ($resumeValues['NewPat-05-Preview-ResumeSetup'] -ceq 'preview resume sentinel') 'register preserves Preview pending resume'
        Assert-Test ($resumeValues['NewPat-Experimental08-ResumeSetup'] -ceq 'experimental resume sentinel') 'register preserves experimental pending resume'
        Unregister-NewPatResume
        Assert-Test ($resumeValues['NewPat-Experimental08-ResumeSetup'] -ceq 'experimental resume sentinel') 'unregister preserves experimental pending resume'
        Assert-Test (-not $resumeValues.ContainsKey($profile.resume_key) -and
            $resumeValues['NewPat-ResumeSetup'] -ceq 'stable resume sentinel' -and
            $resumeValues['NewPat-05-Preview-ResumeSetup'] -ceq 'preview resume sentinel') 'unregister removes only candidate pending resume'
    } finally {
        $env:LOCALAPPDATA = $oldLocalAppData
        Set-Item -Path Function:Open-NewPatResumeRegistry -Value $openRegistry
    }
    $otherPatch = '0.8.' + (1 + [int]($candidateVersion.Split('.')[-1]))
    foreach ($unsupportedVersion in @('0.3.0a1', '0.7.2', ($candidateVersion + 'rc1'), $otherPatch)) {
        $manifest = New-TestManifest $unsupportedVersion
        Write-NewPatJsonAtomic $manifestPath $manifest
        Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject unsupported version even with consistent tag and asset URLs'
    }
    foreach ($url in @('https://example.org/rootfs.tar.gz',
        ("https://github.com/GregorioDalia/NewPat-Desktop/releases/download/v$candidateVersion/rootfs-$candidateVersion.tar.gz?redirect=1"),
        "https://github.com/other/repo/releases/download/v$candidateVersion/rootfs-$candidateVersion.tar.gz")) {
        $manifest = New-TestManifest
        $manifest.assets.rootfs.url = $url
        Write-NewPatJsonAtomic $manifestPath $manifest
        Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject foreign/query/repo URL'
    }
    foreach ($file in @('../rootfs.tar.gz', 'C:\rootfs.tar.gz', 'folder/rootfs.tar.gz', '..\rootfs.tar.gz')) {
        $manifest = New-TestManifest
        $manifest.assets.rootfs.file = $file
        Write-NewPatJsonAtomic $manifestPath $manifest
        Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject path traversal/absolute asset file'
    }
    $manifest = New-TestManifest
    $manifest.assets.rootfs.size = -1
    Write-NewPatJsonAtomic $manifestPath $manifest
    Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject negative asset size'
    $manifest = New-TestManifest
    $manifest.runtime_image = 'latest'
    Write-NewPatJsonAtomic $manifestPath $manifest
    Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject mutable runtime image tag'
    $manifest = New-TestManifest
    $manifest.assets.rootfs.sha256 = 'bad'
    Write-NewPatJsonAtomic $manifestPath $manifest
    Assert-Rejected { Read-NewPatInstallerManifest $manifestPath } 'reject invalid asset checksum'

    $assetPath = Join-Path $temporary 'asset.tar.gz'
    [IO.File]::WriteAllBytes($assetPath, [byte[]]@(1, 2, 3, 4))
    $asset = [pscustomobject]@{ file = 'asset.tar.gz'; size = 4; sha256 = (Get-FileHash $assetPath -Algorithm SHA256).Hash.ToLowerInvariant() }
    Assert-Test (Test-NewPatAsset $assetPath $asset) 'accept verified asset'
    [IO.File]::WriteAllBytes($assetPath, [byte[]]@(4, 3, 2, 1))
    Assert-Test (-not (Test-NewPatAsset $assetPath $asset)) 'reject altered asset with same size'
    [IO.File]::WriteAllBytes($assetPath, [byte[]]@(1, 2, 3))
    Assert-Test (-not (Test-NewPatAsset $assetPath $asset)) 'reject wrong asset size'
    Assert-Test (-not (Test-NewPatAsset (Join-Path $temporary 'missing') $asset)) 'reject missing asset'
    $assetDirectory = Join-Path $temporary 'offline'
    $cacheDirectory = Join-Path $temporary 'cache'
    [IO.Directory]::CreateDirectory($assetDirectory) | Out-Null
    [IO.Directory]::CreateDirectory($cacheDirectory) | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $assetDirectory $asset.file), [byte[]]@(1, 2, 3, 4))
    $cached = Get-NewPatAsset $asset $cacheDirectory $assetDirectory
    Assert-Test (Test-NewPatAsset $cached $asset) 'offline asset copied and reverified in cache'
    # Inno installs directly to this same hash-addressed cache before bootstrap starts.
    # No original extraction medium, URL or download is needed after installation/reboot.
    Remove-Item -LiteralPath $assetDirectory -Recurse -Force
    function Invoke-WebRequest { throw 'Unexpected download while embedded cache is valid.' }
    try {
        $cacheOnly = Get-NewPatAsset $asset $cacheDirectory ''
        Assert-Test ($cacheOnly -ceq $cached) 'embedded cache works with no asset directory or download'
        $afterRemoval = Get-NewPatAsset $asset $cacheDirectory $assetDirectory
        Assert-Test ($afterRemoval -ceq $cached) 'cached archive remains usable after installer media is removed'
        Assert-Test (@(Get-ChildItem -LiteralPath $cacheDirectory -File).Count -eq 1) 'cache retrieval never creates a second permanent archive'
    } finally {
        Remove-Item Function:Invoke-WebRequest
    }
    [IO.Directory]::CreateDirectory($assetDirectory) | Out-Null
    [IO.File]::WriteAllBytes($cached, [byte[]]@(0, 0, 0, 0))
    [IO.File]::WriteAllBytes((Join-Path $assetDirectory $asset.file), [byte[]]@(9, 9, 9, 9))
    Assert-Rejected { Get-NewPatAsset $asset $cacheDirectory $assetDirectory } 'reject altered cache and offline file without execution'

    $statePath = Join-Path $temporary 'state.json'
    Write-NewPatJsonAtomic $statePath ([ordered]@{ schema_version = 1; phase = 'starting' })
    $unicodePath = 'C:\Users\Jos' + [char]0x00E9 + '\Dati ' + [char]0x6D4B + [char]0x8BD5
    Write-NewPatJsonAtomic $statePath ([ordered]@{ schema_version = 1; phase = 'ready'; data_dir = $unicodePath })
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($state.phase -eq 'ready') 'atomic state replacement retains complete JSON'
    Assert-Test ($state.data_dir -ceq $unicodePath) 'UTF-8 state preserves Unicode user paths on Windows PowerShell 5.1'
    Assert-Test (@(Get-ChildItem -LiteralPath $temporary -Filter '.write-*').Count -eq 0) 'atomic state leaves no temporary files'

    Assert-Test ((ConvertTo-NewPatNativeArgument 'plain') -ceq 'plain') 'native plain argument'
    Assert-Test ((ConvertTo-NewPatNativeArgument '') -ceq '""') 'native empty argument'
    Assert-Test ((ConvertTo-NewPatNativeArgument 'C:\a b\') -ceq '"C:\a b\\"') 'native path space and trailing slash'
    Assert-Test ((ConvertTo-NewPatNativeArgument 'a"b') -ceq '"a\"b"') 'native embedded quote'
    $checkLogs = Join-Path $temporary 'setup checks with spaces'
    $checkExecutable = (Get-Process -Id $PID).Path
    $supervisorParameters = @{}
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $supervisorParameters.SupervisorPython = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
    }
    $checkScript = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Console]::WriteLine('before'); [Console]::Error.WriteLine('warning'); [Console]::WriteLine([char]0x00E9); [Console]::WriteLine('after'); exit 0"
    Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', $checkScript) $checkLogs 'doctor' @supervisorParameters 6> $null
    $checkOutput = [IO.File]::ReadAllText((Join-Path $checkLogs 'doctor.stdout.log'))
    Assert-Test ($checkOutput.Contains('before') -and $checkOutput.Contains('after')) 'setup stdout is retained through completion'
    Assert-Test ($checkOutput.Contains([string][char]0x00E9)) 'setup diagnostics preserve Unicode output'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'doctor.stderr.log')).Trim() -ceq 'warning') 'setup stderr is retained even on success'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'doctor.exit-code.txt')).Trim() -ceq '0') 'stderr alone does not fail a successful setup check'
    # Both streams exceed a pipe buffer: sequential draining would deadlock.
    $checkScript = "[Console]::Out.Write(('o' * 70000)); [Console]::Error.Write(('e' * 70000)); exit 7"
    $checkError = ''
    try {
        Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', $checkScript) $checkLogs 'self-test' @supervisorParameters 6> $null
    } catch { $checkError = $_.Exception.Message }
    Assert-Test ($checkError.Contains('codice 7') -and $checkError.Contains('self-test.stderr.log')) 'setup failure preserves its native exit code and diagnostic path'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'self-test.stdout.log')) -ceq ('o' * 70000)) 'failed setup check retains all stdout'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'self-test.stderr.log')) -ceq ('e' * 70000)) 'failed setup check retains all stderr'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'self-test.exit-code.txt')).Trim() -ceq '7') 'failed setup exit code is saved separately'
    # The child waits for its own partial diagnostics to reach disk. Buffering
    # until exit makes this fail even though the process itself never blocks.
    $livePath = (Join-Path $checkLogs 'doctor.stdout.log').Replace("'", "''")
    $checkScript = @"
[Console]::Out.Write('live diagnostic'); [Console]::Out.Flush()
`$watch = [Diagnostics.Stopwatch]::StartNew()
`$seen = `$false
while (`$watch.Elapsed.TotalSeconds -lt 5) {
    `$stream = [IO.FileStream]::new('$livePath', [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    `$reader = [IO.StreamReader]::new(`$stream)
    try { `$seen = `$reader.ReadToEnd().Contains('live diagnostic') } finally { `$reader.Dispose() }
    if (`$seen) { break }
    Start-Sleep -Milliseconds 20
}
if (-not `$seen) { exit 8 }; exit 0
"@
    Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', $checkScript) $checkLogs 'doctor' -TimeoutSeconds 10 @supervisorParameters 6> $null
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'doctor.stdout.log')) -ceq 'live diagnostic') 'setup diagnostics are visible before exit without a newline'
    $other = [Diagnostics.Process]::Start($checkExecutable, '-NoLogo -NoProfile -Command "Start-Sleep -Seconds 30"')
    try {
        $checkScript = "[Console]::WriteLine('before deadline'); Start-Sleep -Seconds 30; [Console]::WriteLine('too late')"
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $checkError = ''
        try {
            Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', $checkScript) $checkLogs 'self-test' -TimeoutSeconds 2 @supervisorParameters 6> $null
        } catch { $checkError = $_.Exception.Message }
        Assert-Test ($checkError.Contains('scaduto') -and $checkError.Contains('self-test.stderr.log')) 'blocked setup reports a deadline and diagnostic paths'
        Assert-Test ($watch.Elapsed.TotalSeconds -lt 15) 'setup deadline returns after bounded cleanup'
        Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'self-test.exit-code.txt')).Trim() -ceq '124') 'timed-out setup cannot reuse success evidence'
        Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'self-test.stdout.log')).Trim() -ceq 'before deadline') 'partial diagnostics survive timeout'
        Assert-Test (-not $other.HasExited) 'setup timeout does not stop another session'
    } finally {
        if (-not $other.HasExited) { $other.Kill(); $other.WaitForExit() }
        $other.Dispose()
    }
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        # The immediate child exits, but its descendant inherits the output
        # pipe. The job must still be able to stop that descendant by ownership.
        $pidPath = Join-Path $temporary 'setup-descendant.pid'
        $childCode = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes('Start-Sleep -Seconds 30'))
        $exeLiteral = $checkExecutable.Replace("'", "''")
        $pidLiteral = $pidPath.Replace("'", "''")
        $checkScript = @"
`$start = New-Object Diagnostics.ProcessStartInfo
`$start.FileName = '$exeLiteral'
`$start.Arguments = '-NoLogo -NoProfile -EncodedCommand $childCode'
`$start.UseShellExecute = `$false
`$start.CreateNoWindow = `$true
`$child = [Diagnostics.Process]::Start(`$start)
[IO.File]::WriteAllText('$pidLiteral', [string]`$child.Id)
[Console]::WriteLine('parent exited'); exit 0
"@
        $checkError = ''
        try {
            Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', $checkScript) $checkLogs 'doctor' -TimeoutSeconds 3 @supervisorParameters 6> $null
        } catch { $checkError = $_.Exception.Message }
        Assert-Test ($checkError.Contains('scaduto')) 'inherited setup pipes remain bounded after parent exit'
        $descendant = [int][IO.File]::ReadAllText($pidPath)
        $alive = $true
        $watch = [Diagnostics.Stopwatch]::StartNew()
        while ($alive -and $watch.Elapsed.TotalSeconds -lt 5) {
            try {
                $child = [Diagnostics.Process]::GetProcessById($descendant)
                try { $alive = -not $child.HasExited } finally { $child.Dispose() }
            } catch [ArgumentException] { $alive = $false }
            if ($alive) { Start-Sleep -Milliseconds 20 }
        }
        Assert-Test (-not $alive) 'setup job stops owned descendants after their parent exited'
    }
    Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', 'exit 0') $checkLogs 'self-test' -TimeoutSeconds 10 @supervisorParameters 6> $null
    Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'self-test.exit-code.txt')).Trim() -ceq '0') 'setup check can be retried after timeout'
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        Invoke-NewPatSetupCheck $checkExecutable @('-NoLogo', '-NoProfile', '-Command', 'exit 0') $checkLogs 'doctor' -TimeoutSeconds 10 @supervisorParameters 6> $null
        Assert-Test ([IO.File]::ReadAllText((Join-Path $checkLogs 'doctor.exit-code.txt')).Trim() -ceq '0') 'short-lived setup check retains its success code'
    }
    Assert-Rejected {
        Invoke-NewPatSetupCheck (Join-Path $temporary 'missing.exe') @() $checkLogs 'doctor' @supervisorParameters 6> $null
    } 'setup launch failure cannot reuse a successful prior exit code'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $checkLogs 'doctor.exit-code.txt'))) 'launch failure removes stale exit-code evidence'
    $script:NewPatWsl = (Get-Process -Id $PID).Path
    $probe = Invoke-NewPatWsl @('-NoLogo', '-NoProfile', '-Command', "[Console]::Error.WriteLine('warning'); [Console]::WriteLine('marker'); exit 0") -TimeoutSeconds 20
    Assert-Test ($probe.Text -ceq 'marker' -and $probe.ErrorText -ceq 'warning') 'native stderr warning does not corrupt marker output'
    $failure = Invoke-NewPatWsl @('-NoLogo', '-NoProfile', '-Command', 'exit 7') -AllowFailure -TimeoutSeconds 20
    Assert-Test ($failure.ExitCode -eq 7) 'native failure is inspectable'
    $inputEncodingBefore = [Console]::InputEncoding
    $inputEncodingSignature = $inputEncodingBefore.CodePage.ToString() + ':' + [Convert]::ToBase64String($inputEncodingBefore.GetPreamble())
    # Read raw bytes through EOF: Console.ReadLine may hide or reinterpret a BOM.
    $stdinProbe = '$bytes = New-Object IO.MemoryStream; [Console]::OpenStandardInput().CopyTo($bytes); [Console]::WriteLine($bytes.Length); $bytes.Dispose()'
    $stdin = Invoke-NewPatWsl @('-NoLogo', '-NoProfile', '-Command', $stdinProbe) -TimeoutSeconds 20
    Assert-Test ($stdin.Text -ceq '0') ("native stdin reaches EOF with zero bytes; stdout=$($stdin.Text); stderr=$($stdin.ErrorText); exit=$($stdin.ExitCode)")
    $inputEncodingAfter = [Console]::InputEncoding
    $afterSignature = $inputEncodingAfter.CodePage.ToString() + ':' + [Convert]::ToBase64String($inputEncodingAfter.GetPreamble())
    Assert-Test ($afterSignature -ceq $inputEncodingSignature) 'native launch restores original console input encoding'
    Assert-Rejected { Invoke-NewPatWsl @('-NoLogo', '-NoProfile', '-Command', 'Start-Sleep -Seconds 10') -TimeoutSeconds 1 } 'native probe timeout is bounded'
    Write-Host "PASS: $assertions installer assertions."
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
