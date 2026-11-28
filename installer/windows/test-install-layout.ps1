# Exercise actual path validation and persistence on an isolated local directory.
# No elevation, WSL distribution, network connection or user data is required.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
$checks = 0
function Assert-Test([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw "Installation layout check failed: $Message" }
    $script:checks++
}
function Assert-Rejected([scriptblock] $Action, [string] $Message) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-Test $rejected $Message
}
function Copy-Layout($Layout) { return ($Layout | ConvertTo-Json -Depth 8 | ConvertFrom-Json) }
function Write-StorageMarker([string] $Path, [string] $Role, [string] $Channel = 'desktop') {
    [IO.Directory]::CreateDirectory($Path) | Out-Null
    $markerName = if ($Role -ceq 'application') { '.newpat-app.ini' } else { '.newpat-storage.ini' }
    @('[NewPat]', 'schema_version=1', ('installation_channel=' + $Channel), ('role=' + $Role)) |
        Set-Content -LiteralPath (Join-Path $Path $markerName) -Encoding ASCII
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('newpat-layout-' + [Guid]::NewGuid().ToString('N'))
$oldLocalAppData = $env:LOCALAPPDATA
$junctions = New-Object 'Collections.Generic.List[string]'
try {
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    $env:LOCALAPPDATA = Join-Path $temporary 'isolated user profile'
    $layout = [pscustomobject]@{
        schema_version = 1; installation_channel = 'desktop'
        app_dir = (Join-Path $temporary ('application & [literal] ' + [char]0x00E8))
        runtime_dir = (Join-Path $temporary 'runtime on selected volume')
        cache_dir = (Join-Path $temporary 'selected cache')
        data_dir = (Join-Path $temporary 'existing research inputs')
        runs_dir = (Join-Path $temporary 'existing research results')
    }
    foreach ($name in @('app_dir', 'runtime_dir', 'cache_dir', 'data_dir', 'runs_dir')) {
        [IO.Directory]::CreateDirectory($layout.$name) | Out-Null
    }
    Write-StorageMarker $layout.runtime_dir 'runtime'
    Write-StorageMarker $layout.cache_dir 'cache'
    Write-StorageMarker $layout.app_dir 'application'
    $inputPath = Join-Path $layout.data_dir 'input.txt'
    $resultPath = Join-Path $layout.runs_dir 'result.txt'
    [IO.File]::WriteAllText($inputPath, 'existing input sentinel')
    [IO.File]::WriteAllText($resultPath, 'existing result sentinel')
    $inputHash = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash
    $resultHash = (Get-FileHash -LiteralPath $resultPath -Algorithm SHA256).Hash
    Assert-NewPatInstallLayout $layout
    Assert-NewPatInstallLayout $layout -CheckExisting
    Assert-Test (Test-NewPatStorageMarker $layout.runtime_dir 'runtime') 'runtime storage marker is recognized'
    Assert-Test (Test-NewPatStorageMarker $layout.cache_dir 'cache') 'cache storage marker is recognized'
    $layoutPath = Join-Path $layout.app_dir '.runtime\install-layout.json'
    Write-NewPatJsonAtomic $layoutPath $layout
    $loaded = Read-NewPatInstallLayout $layout.app_dir
    foreach ($name in @('app_dir', 'runtime_dir', 'cache_dir', 'data_dir', 'runs_dir')) {
        Assert-Test ([IO.Path]::GetFullPath($loaded.$name).TrimEnd('\') -ieq
            [IO.Path]::GetFullPath($layout.$name).TrimEnd('\')) ("saved $name is loaded without resetting to AppData")
    }
    Assert-NewPatInstallationLocation $layout.app_dir
    $otherApp = Join-Path $temporary 'another application'
    Write-NewPatJsonAtomic (Join-Path $otherApp '.runtime\install-layout.json') $layout
    Assert-Rejected { Read-NewPatInstallLayout $otherApp } 'a copied layout cannot authorize a different application directory'

    foreach ($badSchema in @('1', $true, 2)) {
        $invalid = Copy-Layout $layout
        $invalid.schema_version = $badSchema
        Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'schema version is validated without coercion'
    }
    foreach ($foreignChannel in @('stable', 'preview-0.5', 'experimental08')) {
        $invalid = Copy-Layout $layout
        $invalid.installation_channel = $foreignChannel
        Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'another channel cannot authorize Desktop storage'
    }
    $invalid = Copy-Layout $layout
    $invalid.PSObject.Properties.Remove('cache_dir')
    Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'a missing destination is not silently replaced'
    $invalid = Copy-Layout $layout
    $invalid | Add-Member -NotePropertyName unknown_destination -NotePropertyValue $temporary
    Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'unknown layout fields are rejected'
    $invalid = Copy-Layout $layout
    $invalid.data_dir = $false
    Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'non-string destinations are rejected'

    $driveRoot = [IO.Path]::GetPathRoot($temporary)
    foreach ($badPath in @('relative\research', $driveRoot, '\\server\share\NewPat',
        (Join-Path $temporary 'unsafe*directory'), (Join-Path $temporary 'trailing-space '))) {
        $invalid = Copy-Layout $layout
        $invalid.data_dir = $badPath
        Assert-Rejected { Assert-NewPatInstallLayout $invalid } ("unsafe or unsupported destination is rejected: $badPath")
    }
    foreach ($protected in @(
        (Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\preferences.json'),
        (Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\installations'),
        $env:WINDIR,
        $env:ProgramFiles
    )) {
        $invalid = Copy-Layout $layout
        $invalid.app_dir = $protected
        Assert-Rejected { Assert-NewPatInstallLayout $invalid } ("protected system or stable installation location is rejected: $protected")
    }
    foreach ($badPair in @(
        @('data_dir', 'app_dir'), @('runs_dir', 'data_dir'), @('runtime_dir', 'cache_dir')
    )) {
        $invalid = Copy-Layout $layout
        $invalid.($badPair[0]) = $invalid.($badPair[1])
        Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'equal roots cannot mix application, runtime, cache or research data'
    }
    $invalid = Copy-Layout $layout
    $invalid.runs_dir = Join-Path $layout.runtime_dir 'analysis-results'
    Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'research results cannot be nested inside removable runtime storage'
    $invalid = Copy-Layout $layout
    $invalid.runtime_dir = $temporary
    Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'a runtime root cannot contain the other selected destinations'

    $unownedCache = Join-Path $temporary 'unowned cache'
    [IO.Directory]::CreateDirectory($unownedCache) | Out-Null
    $unownedSentinel = Join-Path $unownedCache 'keep.txt'
    [IO.File]::WriteAllText($unownedSentinel, 'unrelated contents')
    $invalid = Copy-Layout $layout
    $invalid.cache_dir = $unownedCache
    Assert-Rejected { Assert-NewPatInstallLayout $invalid -CheckExisting } 'a nonempty custom managed folder requires an ownership marker'
    Write-StorageMarker $unownedCache 'runtime'
    Assert-Rejected { Assert-NewPatInstallLayout $invalid -CheckExisting } 'a runtime marker cannot authorize a cache directory'
    foreach ($foreignChannel in @('stable', 'preview-0.5', 'experimental08')) {
        Write-StorageMarker $unownedCache 'cache' $foreignChannel
        Assert-Rejected { Assert-NewPatInstallLayout $invalid -CheckExisting } 'another channel storage marker is not adopted'
    }
    Assert-Test ([IO.File]::ReadAllText($unownedSentinel) -ceq 'unrelated contents') 'rejected managed locations preserve unrelated contents'
    $defaults = Get-NewPatDefaultInstallLayout
    foreach ($field in @('runtime_dir', 'cache_dir')) {
        $defaultPath = $defaults.$field
        [IO.Directory]::CreateDirectory($defaultPath) | Out-Null
        $defaultSentinel = Join-Path $defaultPath 'keep.txt'
        [IO.File]::WriteAllText($defaultSentinel, 'unowned default location')
        try {
            $invalid = Copy-Layout $layout
            $invalid.$field = $defaultPath
            Assert-Rejected { Assert-NewPatInstallLayout $invalid -CheckExisting } 'a nonempty default managed folder also requires its ownership marker'
            Assert-Test ([IO.File]::ReadAllText($defaultSentinel) -ceq 'unowned default location') 'rejection preserves unowned files in the default destination'
        } finally {
            [IO.File]::Delete($defaultSentinel)
            [IO.Directory]::Delete($defaultPath)
        }
    }
    $unownedApp = Join-Path $temporary 'nonempty unrelated application'
    [IO.Directory]::CreateDirectory($unownedApp) | Out-Null
    [IO.File]::WriteAllText((Join-Path $unownedApp 'keep.txt'), 'application sentinel')
    $invalid = Copy-Layout $layout
    $invalid.app_dir = $unownedApp
    Assert-Rejected { Assert-NewPatInstallLayout $invalid -CheckExisting } 'an unrelated nonempty application directory is not overwritten'
    $gitDirectory = Join-Path $layout.app_dir '.git'
    [IO.Directory]::CreateDirectory($gitDirectory) | Out-Null
    Assert-Rejected { Assert-NewPatInstallLayout $layout -CheckExisting } 'an application marker cannot authorize overwriting a source checkout'
    [IO.Directory]::Delete($gitDirectory)

    $target = Join-Path $temporary 'junction target'
    [IO.Directory]::CreateDirectory($target) | Out-Null
    $link = Join-Path $temporary 'junction parent'
    New-Item -ItemType Junction -Path $link -Target $target -ErrorAction Stop | Out-Null
    $junctions.Add($link)
    $invalid = Copy-Layout $layout
    $invalid.data_dir = Join-Path $link 'new research inputs'
    Assert-Rejected { Assert-NewPatInstallLayout $invalid } 'a nonexistent destination below a junction is rejected before any writes'
    $nestedLink = Join-Path $layout.cache_dir 'nested junction'
    New-Item -ItemType Junction -Path $nestedLink -Target $target -ErrorAction Stop | Out-Null
    $junctions.Add($nestedLink)
    Assert-Rejected { Assert-NewPatInstallLayout $layout } 'managed storage with a nested junction is rejected'
    [IO.Directory]::Delete($nestedLink)
    $junctions.Remove($nestedLink) | Out-Null

    $rootfsHash = 'a' * 64
    $distro = Get-NewPatRuntimeDistroName $rootfsHash $layout.runtime_dir
    $sameDistro = Get-NewPatRuntimeDistroName $rootfsHash ($layout.runtime_dir.ToUpperInvariant() + '\')
    $otherDistro = Get-NewPatRuntimeDistroName $rootfsHash (Join-Path $temporary 'second runtime')
    Assert-Test ($distro.Length -le 64 -and $distro -ceq $sameDistro -and $distro -cne $otherDistro) 'runtime identity is case-insensitive, ignores a trailing separator and distinguishes destinations'
    Assert-NewPatRuntimeNamespace $distro $rootfsHash $layout.runtime_dir
    Assert-Rejected { Assert-NewPatRuntimeNamespace $distro $rootfsHash (Join-Path $temporary 'second runtime') } 'runtime binding rejects a valid name assigned to another destination'
    $legacyDistro = (Get-NewPatInstallationProfile).distro_prefix + $rootfsHash.Substring(0, 40)
    Assert-Rejected { Assert-NewPatRuntimeNamespace $legacyDistro $rootfsHash } 'a name without a directory binding is rejected'

    Save-NewPatInstallLayoutHistory $layout | Out-Null
    Save-NewPatInstallLayoutHistory $layout | Out-Null
    $historyDirectory = Join-Path $env:LOCALAPPDATA 'NewPat-Desktop\installations'
    $absentDrive = @(65..90 | ForEach-Object { ('{0}:\' -f [char]$_) } |
        Where-Object { -not (Test-Path -LiteralPath $_) })[0]
    $offlineLayout = Copy-Layout $layout
    foreach ($field in @('app_dir', 'runtime_dir', 'cache_dir', 'data_dir', 'runs_dir')) {
        $offlineLayout.$field = $absentDrive + 'previous NewPat\' + $field
    }
    $offlineRecord = Join-Path $historyDirectory 'offline-history.json'
    Write-NewPatJsonAtomic $offlineRecord $offlineLayout
    Assert-NewPatInstallLayout $offlineLayout -Historical
    Assert-Rejected { Assert-NewPatInstallLayout $offlineLayout } 'currently selected destinations still require an available local fixed drive'
    Assert-NewPatInstallLayout $layout -CheckExisting
    Assert-Test (@(Get-NewPatKnownInstallLayouts $layout.app_dir | Where-Object {
        $_.runtime_dir -ieq $offlineLayout.runtime_dir
    }).Count -eq 1) 'an unavailable historical disk is retained without blocking an unrelated valid new selection'
    Remove-Item -LiteralPath $offlineRecord -Force
    $known = @(Get-NewPatKnownInstallLayouts $layout.app_dir)
    $same = @($known | Where-Object { $_.app_dir -ieq $layout.app_dir -and $_.runtime_dir -ieq $layout.runtime_dir })
    Assert-Test ($same.Count -ge 1 -and @(Get-ChildItem -LiteralPath $historyDirectory -Filter '*.json' -File).Count -eq 1) 'saving the same layout twice retains one history record and can be read back'
    $historyFile = @(Get-ChildItem -LiteralPath $historyDirectory -Filter '*.json' -File)[0].FullName
    $retainedFiles = @($historyFile, $layoutPath, $inputPath, $resultPath,
        (Join-Path $layout.runtime_dir '.newpat-storage.ini'), (Join-Path $layout.cache_dir '.newpat-storage.ini'))
    $retainedHashes = @{}
    foreach ($file in $retainedFiles) { $retainedHashes[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash }
    foreach ($case in @(
        @{ managed = 'cache_dir'; previous = 'runtime_dir' },
        @{ managed = 'runtime_dir'; previous = 'cache_dir' },
        @{ managed = 'runtime_dir'; previous = 'app_dir' }
    )) {
        $candidate = Copy-Layout $layout
        # Move the corresponding current root away first. The candidate is
        # internally disjoint; only its intersection with retained history is invalid.
        $replacement = Join-Path $temporary ('new-' + $case.previous + '-for-' + $case.managed)
        $nested = Join-Path ([string]$layout.($case.previous)) ('nested-' + $case.managed)
        $candidate.($case.previous) = $replacement
        $candidate.($case.managed) = $nested
        Assert-NewPatInstallLayout $candidate
        Assert-Rejected { Assert-NewPatInstallLayout $candidate -CheckExisting } ("selected $($case.managed) cannot occupy retained $($case.previous) storage")
        Assert-Test (-not (Test-Path -LiteralPath $replacement) -and -not (Test-Path -LiteralPath $nested)) 'historical-role rejection creates neither selected destination'
    }
    foreach ($file in $retainedFiles) {
        Assert-Test ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ceq $retainedHashes[$file]) 'historical-role checks preserve saved destinations and existing files'
    }
    $secondLayout = Copy-Layout $layout
    $secondLayout.runtime_dir = Join-Path $temporary 'second runtime'
    Save-NewPatInstallLayoutHistory $secondLayout | Out-Null
    $known = @(Get-NewPatKnownInstallLayouts $layout.app_dir)
    Assert-Test (@($known | Where-Object { $_.runtime_dir -ieq $secondLayout.runtime_dir }).Count -ge 1 -and
        @($known | Where-Object { $_.runtime_dir -ieq $layout.runtime_dir }).Count -ge 1 -and
        @(Get-ChildItem -LiteralPath $historyDirectory -Filter '*.json' -File).Count -eq 2) 'a changed runtime destination is remembered without losing the earlier one'

    Assert-Test ((Get-NewPatApplicationKind $unownedApp) -ceq 'unknown') 'unrelated nonempty destinations remain unrecognized'
    Assert-Test ((Get-NewPatApplicationKind (Join-Path $temporary 'not created yet')) -ceq 'empty') 'a new destination is classified without creating it'
    $customResidual = Join-Path $temporary 'custom residual application'
    $customLayout = Copy-Layout $layout
    $customLayout.app_dir = $customResidual
    Write-NewPatJsonAtomic (Join-Path $customResidual '.runtime\install-layout.json') $customLayout
    [IO.File]::WriteAllText((Join-Path $customResidual 'notes.txt'), 'preserve notes')
    Assert-Test ((Get-NewPatApplicationKind $customResidual) -ceq 'unknown') 'layout metadata alone never authorizes an application folder'
    Assert-Rejected { Assert-NewPatInstallationLocation (Join-Path $temporary 'unconfigured application') } 'a custom application location requires a recorded layout'
    Remove-Item -LiteralPath $layout.app_dir -Recurse -Force
    $knownAfterAppRemoval = @(Get-NewPatKnownInstallLayouts $layout.app_dir)
    Assert-Test (@($knownAfterAppRemoval | Where-Object { $_.runtime_dir -ieq $layout.runtime_dir }).Count -ge 1 -and
        @($knownAfterAppRemoval | Where-Object { $_.runtime_dir -ieq $secondLayout.runtime_dir }).Count -ge 1) 'remembered runtime destinations remain available after application removal'
    Assert-Test ((Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash -ceq $inputHash -and
        (Get-FileHash -LiteralPath $resultPath -Algorithm SHA256).Hash -ceq $resultHash) 'layout validation and persistence preserve existing research files'
    Write-Host "PASS: $checks installation layout assertions."
} finally {
    foreach ($junction in $junctions) {
        if (Test-Path -LiteralPath $junction) { [IO.Directory]::Delete($junction) }
    }
    $env:LOCALAPPDATA = $oldLocalAppData
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
