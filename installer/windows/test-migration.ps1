# Production migration helpers with a simulated WSL boundary; no network/elevation required.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
. (Join-Path $PSScriptRoot 'bootstrap-migration.ps1')
$checks = 0
function Assert-Test([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw "Migration check failed: $Message" }
    $script:checks++
}
function Assert-Rejected([scriptblock] $Action, [string] $Message) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-Test $rejected $Message
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('newpat-migration-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temporary) | Out-Null
$registrations = @{}
$calls = New-Object 'Collections.Generic.List[object]'
$interruptImport = $false
$failImportBeforeRegistration = $false
$assetReadHook = $null
$testArchive = Join-Path $temporary 'rootfs.tar.gz'
[IO.File]::WriteAllText($testArchive, 'verified fixture')
function Get-NewPatAsset($Asset, [string] $CacheDirectory, [string] $AssetDirectory) {
    if ($null -ne $script:assetReadHook) { & $script:assetReadHook }
    return $script:testArchive
}
function Get-NewPatWslNames { return @($script:registrations.Keys) }
function Assert-NewPatDistroLocation([string] $Distro, [string] $ExpectedDirectory) {
    if (-not $script:registrations.ContainsKey($Distro) -or
        $script:registrations[$Distro].directory -cne $ExpectedDirectory) { throw 'Unexpected WSL location.' }
}
function Invoke-NewPatWsl([string[]] $Arguments, [switch] $AllowFailure, [int] $TimeoutSeconds = 1800) {
    $script:calls.Add($Arguments)
    if ($Arguments[0] -ceq '--import') {
        if ($script:registrations.ContainsKey($Arguments[1])) { throw 'Duplicate import.' }
        if ($script:failImportBeforeRegistration) { throw 'Simulated failure before WSL registration.' }
        [IO.Directory]::CreateDirectory($Arguments[2]) | Out-Null
        [IO.File]::WriteAllText((Join-Path $Arguments[2] 'ext4.vhdx'), 'fixture disk')
        $script:registrations[$Arguments[1]] = @{ directory = $Arguments[2]; product = 'newpat-runtime-v1'; owner = '' }
        if ($script:interruptImport) { throw 'Simulated interruption after import.' }
        return [pscustomobject]@{ ExitCode = 0; Text = ''; ErrorText = '' }
    }
    if ($Arguments[0] -cne '--distribution' -or -not $script:registrations.ContainsKey($Arguments[1])) {
        throw 'Unexpected WSL operation.'
    }
    $entry = $script:registrations[$Arguments[1]]
    if ($Arguments[5] -ceq '/usr/bin/cat') {
        if ($Arguments[6] -ceq '/etc/newpat-runtime-id') { return [pscustomobject]@{ ExitCode = 0; Text = $entry.product; ErrorText = '' } }
        if ($Arguments[6] -ceq '/var/lib/newpat/owner-id') {
            if (-not $entry.owner) { return [pscustomobject]@{ ExitCode = 1; Text = ''; ErrorText = 'absent' } }
            return [pscustomobject]@{ ExitCode = 0; Text = $entry.owner; ErrorText = '' }
        }
    }
    if ($Arguments[5] -ceq '/usr/bin/install') { return [pscustomobject]@{ ExitCode = 0; Text = ''; ErrorText = '' } }
    if ($Arguments[5] -ceq '/bin/sh' -and $Arguments[8] -ceq 'newpat-owner') {
        $entry.owner = $Arguments[9]
        return [pscustomobject]@{ ExitCode = 0; Text = ''; ErrorText = '' }
    }
    throw 'Unexpected WSL operation; destructive commands are never allowed by this fixture.'
}
function New-Ownership([string] $Distro, [string] $Hash, [string] $Status = 'owned') {
    return [pscustomobject]@{ schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; distro = $Distro; owner_id = ('a' * 32); rootfs_sha256 = $Hash; status = $Status }
}
try {
    $hash = 'b' * 64
    $asset = [pscustomobject]@{ sha256 = $hash }
    $wsl = Join-Path $temporary 'wsl'
    [IO.Directory]::CreateDirectory($wsl) | Out-Null
    $target = Get-NewPatRuntimeTarget $wsl $hash @()
    Assert-Test ($target.Distro -ceq (Get-NewPatRuntimeDistroName $hash $wsl) -and $target.Distro.Length -le 64) 'fresh install binds the WSL name to both rootfs and runtime directory'
    Initialize-NewPatRuntimeTarget $target $asset '' ''
    Assert-Test ($registrations.Count -eq 1 -and $target.Ownership.status -ceq 'owned') 'fresh import verifies owner before marking owned'
    $receipt = Get-Content -LiteralPath $target.OwnershipPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($receipt.rootfs_sha256 -ceq $hash -and $receipt.owner_id -ceq $registrations[$target.Distro].owner) 'full rootfs identity and random owner persisted'
    $imports = @($calls | Where-Object { $_[0] -ceq '--import' }).Count
    $again = Get-NewPatRuntimeTarget $wsl $hash @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $again $asset '' ''
    Assert-Test (@($calls | Where-Object { $_[0] -ceq '--import' }).Count -eq $imports) 'same rootfs retry reuses verified distro without another import'

    $targetReceiptBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($target.OwnershipPath))
    $relocatedWsl = Join-Path $temporary ('other runtime & ' + [char]0x00E8)
    $relocated = Get-NewPatRuntimeTarget $relocatedWsl $hash @($registrations.Keys)
    Assert-Test ($relocated.Distro -cne $target.Distro -and -not $relocated.Registered) 'a new runtime directory gets a new namespace for the identical scientific filesystem'
    Initialize-NewPatRuntimeTarget $relocated $asset '' ''
    Assert-Test ($registrations.ContainsKey($target.Distro) -and
        $registrations[$target.Distro].directory -ceq $target.Directory) 'preparing another destination retains the earlier registration and disk location'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($target.OwnershipPath)) -ceq $targetReceiptBefore) 'preparing another destination preserves the earlier ownership receipt'
    Assert-Rejected { Assert-NewPatRuntimeNamespace $relocated.Distro $hash $wsl } 'a location-bound name cannot authorize another runtime directory'

    $previousDesktopHash = '7' * 64
    $previousDesktopName = (Get-NewPatInstallationProfile).distro_prefix + $previousDesktopHash.Substring(0, 40)
    $previousDesktopReceipt = Join-Path (Join-Path $wsl 'registrations') ($previousDesktopName + '.json')
    $previousDesktopOwner = New-Ownership $previousDesktopName $previousDesktopHash
    Write-NewPatJsonAtomic $previousDesktopReceipt $previousDesktopOwner
    $registrations[$previousDesktopName] = @{ directory = (Join-Path $wsl $previousDesktopName); product = 'newpat-runtime-v1'; owner = $previousDesktopOwner.owner_id }
    $previousDesktopBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($previousDesktopReceipt))
    $existingDesktop = Get-NewPatRuntimeTarget $wsl $previousDesktopHash @($registrations.Keys)
    Assert-Test ($existingDesktop.Distro -cne $previousDesktopName -and -not $existingDesktop.Registered) 'an unbound registration is ignored'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($previousDesktopReceipt)) -ceq $previousDesktopBefore) 'an unrelated receipt remains untouched'
    $differentLegacyLocation = Get-NewPatRuntimeTarget $relocatedWsl $previousDesktopHash @($registrations.Keys)
    Assert-Test ($differentLegacyLocation.Distro -cne $previousDesktopName -and -not $differentLegacyLocation.Registered) 'a legacy Desktop elsewhere is not adopted when its receipt is absent from the selected directory'

    $legacyPath = Join-Path $wsl 'ownership.json'
    $oldHash = 'c' * 64
    $legacy = New-Ownership 'NewPat-Runtime' $oldHash
    $legacy.PSObject.Properties.Remove('installation_channel')
    Write-NewPatJsonAtomic $legacyPath $legacy
    $legacyBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($legacyPath))
    $registrations['NewPat-Runtime'] = @{ directory = (Join-Path $wsl 'NewPat-Runtime'); product = 'newpat-runtime-v1'; owner = $legacy.owner_id }
    $calls.Clear()
    $different = Get-NewPatRuntimeTarget $wsl ('d' * 64) @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $different ([pscustomobject]@{ sha256 = ('d' * 64) }) '' ''
    Assert-Test ($different.Distro -cne 'NewPat-Runtime' -and $registrations.ContainsKey('NewPat-Runtime')) 'different legacy rootfs is retained alongside new target'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($legacyPath)) -ceq $legacyBefore) 'legacy ownership bytes remain unchanged'
    Assert-Test (@($calls | Where-Object { $_[0] -ceq '--distribution' -and $_[1] -ceq 'NewPat-Runtime' }).Count -eq 0) 'migration does not execute commands inside old runtime'
    $sameLegacy = Get-NewPatRuntimeTarget $wsl $oldHash @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $sameLegacy ([pscustomobject]@{ sha256 = $oldHash }) '' ''
    Assert-Test ($sameLegacy.Distro -cne 'NewPat-Runtime') 'same-hash stable runtime is not reused by the candidate'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($legacyPath)) -ceq $legacyBefore) 'candidate preparation does not rewrite stable ownership record'
    Assert-Test (@($calls | Where-Object { $_[0] -ceq '--distribution' -and $_[1] -ceq 'NewPat-Runtime' }).Count -eq 0) 'identical rootfs does not execute any command in stable distro'
    $stableQualified = 'NewPat-Runtime-' + ('9' * 40)
    $registrations[$stableQualified] = @{ directory = (Join-Path $wsl $stableQualified); product = 'newpat-runtime-v1'; owner = 'stable owner' }
    $stableQualifiedTarget = Get-NewPatRuntimeTarget $wsl ('9' * 64) @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $stableQualifiedTarget ([pscustomobject]@{ sha256 = ('9' * 64) }) '' ''
    Assert-Test ($stableQualifiedTarget.Distro -cne $stableQualified -and $registrations[$stableQualified].owner -ceq 'stable owner') 'digest-qualified stable name is isolated even for identical rootfs'
    $previewQualified = 'NewPat-05-Preview-' + ('9' * 40)
    $previewOwnership = New-Ownership $previewQualified ('9' * 64)
    $previewOwnership.installation_channel = 'preview-0.5'
    $previewReceipt = Join-Path (Join-Path $wsl 'registrations') ($previewQualified + '.json')
    Write-NewPatJsonAtomic $previewReceipt $previewOwnership
    $previewReceiptBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($previewReceipt))
    $registrations[$previewQualified] = @{ directory = (Join-Path $wsl $previewQualified); product = 'newpat-runtime-v1'; owner = $previewOwnership.owner_id }
    $calls.Clear()
    $previewQualifiedTarget = Get-NewPatRuntimeTarget $wsl ('9' * 64) @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $previewQualifiedTarget ([pscustomobject]@{ sha256 = ('9' * 64) }) '' ''
    Assert-Test ($previewQualifiedTarget.Distro -cne $previewQualified -and
        $registrations[$previewQualified].owner -ceq $previewOwnership.owner_id -and
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($previewReceipt)) -ceq $previewReceiptBefore) 'Desktop preparation preserves the Preview registration and receipt with an identical rootfs'
    Assert-Test (@($calls | Where-Object { $_[0] -ceq '--distribution' -and $_[1] -ceq $previewQualified }).Count -eq 0) 'Desktop preparation never executes commands in the Preview runtime'
    $badOwnership = $sameLegacy.Ownership | ConvertTo-Json | ConvertFrom-Json
    $badOwnership.installation_channel = 'stable'
    Write-NewPatJsonAtomic $sameLegacy.OwnershipPath $badOwnership
    Assert-Rejected { Get-NewPatRuntimeTarget $wsl $oldHash @($registrations.Keys) } 'candidate cannot adopt foreign ownership record'
    Write-NewPatJsonAtomic $sameLegacy.OwnershipPath $sameLegacy.Ownership

    $unknownHash = 'e' * 64
    $unknown = Get-NewPatRuntimeTarget $wsl $unknownHash @($registrations.Keys)
    $registrations[$unknown.Distro] = @{ directory = $unknown.Directory; product = 'newpat-runtime-v1'; owner = '' }
    Assert-Rejected { Get-NewPatRuntimeTarget $wsl $unknownHash @($registrations.Keys) } 'registered target without ownership is rejected'
    $registrations.Remove($unknown.Distro)
    Write-NewPatJsonAtomic $unknown.OwnershipPath (New-Ownership $unknown.Distro ($unknownHash.Substring(0, 63) + 'f'))
    Assert-Rejected { Get-NewPatRuntimeTarget $wsl $unknownHash @($registrations.Keys) } 'full digest prevents prefix-name collisions'

    $interruptHash = 'f' * 64
    $interrupted = Get-NewPatRuntimeTarget $wsl $interruptHash @($registrations.Keys)
    $interruptImport = $true
    Assert-Rejected { Initialize-NewPatRuntimeTarget $interrupted ([pscustomobject]@{ sha256 = $interruptHash }) '' '' } 'interrupted import reports failure'
    $interruptImport = $false
    $resume = Get-NewPatRuntimeTarget $wsl $interruptHash @($registrations.Keys)
    Assert-Test ($resume.Registered -and $resume.Ownership.status -ceq 'importing') 'resume finds recorded incomplete import'
    Initialize-NewPatRuntimeTarget $resume ([pscustomobject]@{ sha256 = $interruptHash }) '' ''
    Assert-Test ($resume.Ownership.status -ceq 'owned') 'resume finishes owner initialization without deleting the disk'
    $originalDirectory = $registrations[$resume.Distro].directory
    $registrations[$resume.Distro].directory = Join-Path $temporary 'foreign'
    Assert-Rejected { Initialize-NewPatRuntimeTarget $resume ([pscustomobject]@{ sha256 = $interruptHash }) '' '' } 'reject target registered at another location'
    $registrations[$resume.Distro].directory = $originalDirectory
    $registrations[$resume.Distro].product = 'foreign-product'
    Assert-Rejected { Initialize-NewPatRuntimeTarget $resume ([pscustomobject]@{ sha256 = $interruptHash }) '' '' } 'reject different product before initializing owner'
    $registrations[$resume.Distro].product = 'newpat-runtime-v1'
    $registrations[$resume.Distro].owner = 'wrong-owner'
    Assert-Rejected { Initialize-NewPatRuntimeTarget $resume ([pscustomobject]@{ sha256 = $interruptHash }) '' '' } 'owned marker cannot be replaced on retry'

    $occupiedHash = '1' * 64
    $occupied = Get-NewPatRuntimeTarget $wsl $occupiedHash @($registrations.Keys)
    [IO.Directory]::CreateDirectory($occupied.Directory) | Out-Null
    [IO.File]::WriteAllText((Join-Path $occupied.Directory 'keep.txt'), 'preserve')
    Assert-Rejected { Initialize-NewPatRuntimeTarget $occupied ([pscustomobject]@{ sha256 = $occupiedHash }) '' '' } 'unregistered nonempty directory is never overwritten'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $occupied.Directory 'keep.txt')) -ceq 'preserve') 'existing directory content preserved'

    # Reinstallation after a user manually unregisters an owned Desktop is safe
    # only when its disk directory is absent or empty. Keep the previous receipt.
    $repairHash = '2' * 64
    $repairAsset = [pscustomobject]@{ sha256 = $repairHash }
    $repair = Get-NewPatRuntimeTarget $wsl $repairHash @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $repair $repairAsset '' ''
    $oldRepairOwner = $repair.Ownership.owner_id
    $oldRepairReceipt = [Convert]::ToBase64String([IO.File]::ReadAllBytes($repair.OwnershipPath))
    $registrations.Remove($repair.Distro)
    Remove-Item -LiteralPath $repair.Directory -Recurse -Force
    $missingOwned = Get-NewPatRuntimeTarget $wsl $repairHash @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $missingOwned $repairAsset '' ''
    $receiptHistory = Join-Path $wsl 'registration-history'
    $repairBackups = @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($repair.Distro + '-*.json') -File)
    Assert-Test ($repairBackups.Count -eq 1 -and
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($repairBackups[0].FullName)) -ceq $oldRepairReceipt) 'recreation preserves exact old ownership bytes outside active receipts'
    Assert-Test ($missingOwned.Ownership.owner_id -cne $oldRepairOwner -and $missingOwned.Ownership.status -ceq 'owned' -and
        $registrations[$missingOwned.Distro].owner -ceq $missingOwned.Ownership.owner_id) 'recreation imports and verifies a fresh owner instead of reusing the removed instance identity'

    $registrations.Remove($missingOwned.Distro)
    $missingWithDisk = Get-NewPatRuntimeTarget $wsl $repairHash @($registrations.Keys)
    $receiptBeforeRefusal = [Convert]::ToBase64String([IO.File]::ReadAllBytes($missingWithDisk.OwnershipPath))
    $diskBeforeRefusal = [IO.File]::ReadAllText((Join-Path $missingWithDisk.Directory 'ext4.vhdx'))
    $importsBeforeRefusal = @($calls | Where-Object { $_[0] -ceq '--import' }).Count
    Assert-Rejected { Initialize-NewPatRuntimeTarget $missingWithDisk $repairAsset '' '' } 'an owned but unregistered disk is never overwritten by repair'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($missingWithDisk.OwnershipPath)) -ceq $receiptBeforeRefusal -and
        [IO.File]::ReadAllText((Join-Path $missingWithDisk.Directory 'ext4.vhdx')) -ceq $diskBeforeRefusal -and
        @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($repair.Distro + '-*.json') -File).Count -eq 1 -and
        @($calls | Where-Object { $_[0] -ceq '--import' }).Count -eq $importsBeforeRefusal) 'nonempty-destination refusal leaves receipt, disk, history and registrations untouched'

    # Leave the destination empty and simulate an import failure before WSL has
    # registered anything. The new importing receipt makes the next retry resumable.
    [IO.File]::Delete((Join-Path $missingWithDisk.Directory 'ext4.vhdx'))
    $failImportBeforeRegistration = $true
    try {
        Assert-Rejected { Initialize-NewPatRuntimeTarget $missingWithDisk $repairAsset '' '' } 'a failed repaired import remains visible as a setup failure'
    } finally { $failImportBeforeRegistration = $false }
    $pendingRepair = Get-NewPatRuntimeTarget $wsl $repairHash @($registrations.Keys)
    $pendingOwner = $pendingRepair.Ownership.owner_id
    $repairBackups = @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($repair.Distro + '-*.json') -File)
    Assert-Test (-not $pendingRepair.Registered -and $pendingRepair.Ownership.status -ceq 'importing' -and
        $pendingOwner -cne $missingOwned.Ownership.owner_id -and $repairBackups.Count -eq 2) 'failed recreation preserves the prior receipt and records a fresh pending import'
    Initialize-NewPatRuntimeTarget $pendingRepair $repairAsset '' ''
    Assert-Test ($pendingRepair.Ownership.status -ceq 'owned' -and $pendingRepair.Ownership.owner_id -ceq $pendingOwner -and
        @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($repair.Distro + '-*.json') -File).Count -eq 2) 'retry completes the pending import without replacing its owner or duplicating recovery history'

    # An unbound receipt remains unrelated even after its WSL registration disappears.
    $registrations.Remove($previousDesktopName)
    $newDesktop = Get-NewPatRuntimeTarget $wsl $previousDesktopHash @($registrations.Keys)
    Initialize-NewPatRuntimeTarget $newDesktop ([pscustomobject]@{ sha256 = $previousDesktopHash }) '' ''
    $unboundBackups = @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($previousDesktopName + '-*.json') -File)
    Assert-Test ($newDesktop.Distro -ceq (Get-NewPatRuntimeDistroName $previousDesktopHash $wsl) -and
        $registrations.ContainsKey($newDesktop.Distro) -and -not $registrations.ContainsKey($previousDesktopName) -and
        $newDesktop.Ownership.owner_id -cne $previousDesktopOwner.owner_id) 'fresh import uses the location-bound registration and a new owner'
    Assert-Test ($unboundBackups.Count -eq 0 -and
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($previousDesktopReceipt)) -ceq $previousDesktopBefore) 'fresh import leaves the unrelated ownership receipt in place'

    foreach ($foreignName in @('NewPat-Runtime', 'NewPat-Unknown', ('NewPat-05-Preview-' + ('6' * 40)))) {
        $foreignReceiptPath = Join-Path (Join-Path $wsl 'registrations') ($foreignName + '.json')
        $foreignReceipt = New-Ownership $foreignName ('6' * 64)
        Write-NewPatJsonAtomic $foreignReceiptPath $foreignReceipt
        $foreignTarget = [pscustomobject]@{
            Distro = $foreignName; Directory = (Join-Path $wsl $foreignName); OwnershipPath = $foreignReceiptPath
            Ownership = $foreignReceipt; Registered = $false; RootfsSha256 = ('6' * 64)
        }
        $foreignBytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($foreignReceiptPath))
        $beforeForeignImports = @($calls | Where-Object { $_[0] -ceq '--import' }).Count
        Assert-Rejected { Initialize-NewPatRuntimeTarget $foreignTarget ([pscustomobject]@{ sha256 = ('6' * 64) }) '' '' } 'repair rejects stable and unknown namespaces despite a forged Desktop channel field'
        Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($foreignReceiptPath)) -ceq $foreignBytes -and
            @($calls | Where-Object { $_[0] -ceq '--import' }).Count -eq $beforeForeignImports) 'foreign namespaces remain unchanged before any import'
    }

    $linkedHash = '4' * 64
    $linked = Get-NewPatRuntimeTarget $wsl $linkedHash @($registrations.Keys)
    Write-NewPatJsonAtomic $linked.OwnershipPath (New-Ownership $linked.Distro $linkedHash)
    $linked = Get-NewPatRuntimeTarget $wsl $linkedHash @($registrations.Keys)
    $outsideRuntime = Join-Path $temporary 'unrelated empty folder'
    [IO.Directory]::CreateDirectory($outsideRuntime) | Out-Null
    New-Item -ItemType Junction -Path $linked.Directory -Target $outsideRuntime -ErrorAction Stop | Out-Null
    try {
        $linkedReceiptBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($linked.OwnershipPath))
        Assert-Rejected { Initialize-NewPatRuntimeTarget $linked ([pscustomobject]@{ sha256 = $linkedHash }) '' '' } 'repair refuses even an empty destination reached through a junction'
        Assert-Test (@(Get-ChildItem -LiteralPath $outsideRuntime -Force).Count -eq 0 -and
            [Convert]::ToBase64String([IO.File]::ReadAllBytes($linked.OwnershipPath)) -ceq $linkedReceiptBefore -and
            @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($linked.Distro + '-*.json') -File).Count -eq 0) 'junction rejection preserves the outside folder and the ownership evidence'
    } finally { [IO.Directory]::Delete($linked.Directory, $false) }

    $raceHash = '5' * 64
    $race = Get-NewPatRuntimeTarget $wsl $raceHash @($registrations.Keys)
    Write-NewPatJsonAtomic $race.OwnershipPath (New-Ownership $race.Distro $raceHash)
    $race = Get-NewPatRuntimeTarget $wsl $raceHash @($registrations.Keys)
    $raceReceiptBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($race.OwnershipPath))
    $assetReadHook = {
        $script:registrations[$script:race.Distro] = @{ directory = (Join-Path $script:temporary 'new foreign registration'); product = 'newpat-runtime-v1'; owner = 'foreign owner' }
    }
    try {
        Assert-Rejected { Initialize-NewPatRuntimeTarget $race ([pscustomobject]@{ sha256 = $raceHash }) '' '' } 'registration appearing during asset preparation blocks repair'
    } finally { $assetReadHook = $null }
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($race.OwnershipPath)) -ceq $raceReceiptBefore -and
        $registrations[$race.Distro].owner -ceq 'foreign owner' -and
        @(Get-ChildItem -LiteralPath $receiptHistory -Filter ($race.Distro + '-*.json') -File).Count -eq 0) 'late registration leaves the existing distribution and receipt untouched'

    $project = Join-Path $temporary 'app'
    $backendPath = Join-Path $project '.runtime/backend.json'
    $statePath = Join-Path $project '.runtime/installer/state.json'
    $runtimeImagePath = Join-Path $project '.runtime/runtime-image.txt'
    $data = Join-Path $temporary 'custom-data'
    $runs = Join-Path $temporary 'custom-runs'
    [IO.Directory]::CreateDirectory($data) | Out-Null
    [IO.Directory]::CreateDirectory($runs) | Out-Null
    [IO.File]::WriteAllText((Join-Path $data 'input.txt'), 'input sentinel')
    [IO.File]::WriteAllText((Join-Path $runs 'result.txt'), 'result sentinel')
    $previous = [pscustomobject]@{ schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; backend = 'wsl'; wsl_distro = $target.Distro; rootfs_sha256 = $hash; runtime_dir = $wsl; runtime_image = ('sha256:' + ('2' * 64)); data_dir = $data; runs_dir = $runs }
    Write-NewPatJsonAtomic $backendPath $previous
    [IO.File]::WriteAllText($runtimeImagePath, $previous.runtime_image)
    Write-NewPatJsonAtomic $statePath ([ordered]@{ schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; phase = 'ready'; source_commit = ('3' * 40) })
    $manifest = [pscustomobject]@{ source_commit = ('4' * 40); assets = [pscustomobject]@{ rootfs = [pscustomobject]@{ sha256 = $hash } } }
    $snapshotPath = Save-NewPatRecoverySnapshot $project $manifest
    $snapshotBytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($snapshotPath))
    $snapshot = Get-Content -LiteralPath $snapshotPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $savedBackend = $snapshot.previous_files.PSObject.Properties['.runtime/backend.json'].Value
    Assert-Test ($savedBackend.content_base64 -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath))) 'snapshot preserves previous backend bytes'
    $state = [ordered]@{ schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; phase = 'verifying_installation'; updated_utc = ''; wsl_distro = $target.Distro; rootfs_sha256 = $hash; runtime_dir = $wsl }
    Write-NewPatJsonAtomic $statePath $state
    Save-NewPatRecoverySnapshot $project $manifest | Out-Null
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($snapshotPath)) -ceq $snapshotBytes) 'retry never overwrites first recovery evidence'
    $snapshotLayout = [pscustomobject]@{ app_dir = $project; runtime_dir = $wsl; cache_dir = (Join-Path $temporary 'cache'); data_dir = $data; runs_dir = $runs }
    $layoutSnapshot = Save-NewPatRecoverySnapshot $project $manifest $snapshotLayout
    $snapshotLayout.runtime_dir = $relocatedWsl
    $relocatedSnapshot = Save-NewPatRecoverySnapshot $project $manifest $snapshotLayout
    Assert-Test ($layoutSnapshot -cne $relocatedSnapshot -and (Test-Path -LiteralPath $layoutSnapshot)) 'changing destinations within the same build retains distinct recovery evidence'
    $foreign = $previous | ConvertTo-Json | ConvertFrom-Json
    $foreign.PSObject.Properties.Remove('installation_channel')
    Write-NewPatJsonAtomic $backendPath $foreign
    $beforeForeignCheck = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath))
    Assert-Rejected { Get-NewPatPreviousDataRoots $project $temporary } 'legacy backend is not adopted without channel'
    Assert-Rejected { Save-NewPatRecoverySnapshot $project $manifest } 'foreign backend rejected before recovery writes'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath)) -ceq $beforeForeignCheck) 'foreign backend bytes remain untouched'
    $foreign | Add-Member -NotePropertyName installation_channel -NotePropertyValue 'stable'
    Write-NewPatJsonAtomic $backendPath $foreign
    Assert-Rejected { Get-NewPatPreviousDataRoots $project $temporary } 'backend from another channel is rejected'
    Write-NewPatJsonAtomic $backendPath $previous
    $roots = Get-NewPatPreviousDataRoots $project (Join-Path $temporary 'default')
    Assert-Test ($roots.data_dir -ceq $data -and $roots.runs_dir -ceq $runs) 'custom data and result roots survive update'
    $earlierMetadata = $previous | ConvertTo-Json | ConvertFrom-Json
    $earlierMetadata.wsl_distro = $previousDesktopName
    $earlierMetadata.PSObject.Properties.Remove('rootfs_sha256')
    $earlierMetadata.PSObject.Properties.Remove('runtime_dir')
    Write-NewPatJsonAtomic $backendPath $earlierMetadata
    Assert-Rejected { Get-NewPatPreviousDataRoots $project (Join-Path $temporary 'default') } 'metadata without runtime identity is rejected'
    Write-NewPatJsonAtomic $backendPath $previous
    $configuration = [ordered]@{ schema_version = 1; installation_channel = (Get-NewPatInstallationProfile).channel; backend = 'wsl'; wsl_distro = $target.Distro; rootfs_sha256 = $hash; runtime_dir = $wsl; runtime_image = ('sha256:' + ('5' * 64)); data_dir = $roots.data_dir; runs_dir = $roots.runs_dir }
    $foreignConfiguration = [pscustomobject]@{
        installation_channel = (Get-NewPatInstallationProfile).channel
        wsl_distro = 'NewPat-Runtime'; rootfs_sha256 = $hash
    }
    $foreignVerify = @{ called = $false }
    Assert-Rejected { Complete-NewPatRuntimeActivation $project $statePath $state $foreignConfiguration { $foreignVerify.called = $true } } 'activation rejects stable distro even if channel field was copied'
    Assert-Test (-not $foreignVerify.called) 'foreign runtime is rejected before any verification command'
    $mismatchedState = $state | ConvertTo-Json | ConvertFrom-Json
    $mismatchedState.runtime_dir = $relocatedWsl
    $mismatchedState.wsl_distro = $relocated.Distro
    Assert-Rejected { Complete-NewPatRuntimeActivation $project $statePath $mismatchedState $configuration { $foreignVerify.called = $true } } 'two individually valid runtimes cannot be mixed across preparation state and configuration'
    Assert-Test (-not $foreignVerify.called) 'a destination mismatch is rejected before candidate tests or activation'
    $backendBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath))
    $runtimeImageBefore = [IO.File]::ReadAllText($runtimeImagePath)
    $envBefore = [Environment]::GetEnvironmentVariable('NEWPAT_WSL_DISTRO', 'Process')
    $observedCandidate = @{}
    Assert-Rejected {
        Complete-NewPatRuntimeActivation $project $statePath $state $configuration {
            $observedCandidate.distro = $env:NEWPAT_WSL_DISTRO
            $observedCandidate.image = $env:NEWPAT_RUNTIME_IMAGE
            $observedCandidate.backend = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath))
            throw 'Simulated self-test failure.'
        }
    } 'failed self-test prevents activation'
    Assert-Test ($observedCandidate.distro -ceq $target.Distro -and $observedCandidate.image -ceq $configuration.runtime_image) 'validation uses candidate distro and image'
    Assert-Test ($observedCandidate.backend -ceq $backendBefore) 'previous selection remains published during validation'
    Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath)) -ceq $backendBefore) 'failed validation preserves previous backend'
    Assert-Test ([IO.File]::ReadAllText($runtimeImagePath) -ceq $runtimeImageBefore) 'failed validation preserves previous runtime image file'
    $savedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($savedState.phase -cne 'ready') 'failed validation never publishes ready state'
    Assert-Test ([Environment]::GetEnvironmentVariable('NEWPAT_WSL_DISTRO', 'Process') -ceq $envBefore) 'candidate environment restored after failure'
    # Inject only the persistence boundary; activation and verification use production helpers.
    $originalJsonWriter = (Get-Command Write-NewPatJsonAtomic).ScriptBlock
    $failedWritePath = $backendPath
    function Write-NewPatJsonAtomic([string] $Path, $Value) {
        if ([IO.Path]::GetFullPath($Path) -ceq [IO.Path]::GetFullPath($script:failedWritePath)) {
            throw 'Simulated persistence failure.'
        }
        & $script:originalJsonWriter $Path $Value
    }
    try {
        Assert-Rejected { Complete-NewPatRuntimeActivation $project $statePath $state $configuration {} } 'failed backend publication rejects activation'
        Assert-Test ([Convert]::ToBase64String([IO.File]::ReadAllBytes($backendPath)) -ceq $backendBefore -and
            [IO.File]::ReadAllText($runtimeImagePath) -ceq $runtimeImageBefore) 'failed backend write preserves old selection files'
        $savedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Test ($savedState.phase -cne 'ready') 'failed backend write cannot publish ready'
        $failedWritePath = $statePath
        Assert-Rejected { Complete-NewPatRuntimeActivation $project $statePath $state $configuration {} } 'failed ready publication rejects activation'
        $savedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $pendingBackend = Get-Content -LiteralPath $backendPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Test ($savedState.phase -cne 'ready' -and $pendingBackend.wsl_distro -ceq $target.Distro) 'interrupted activation leaves app blocked despite prepared selection'
        $retryRoots = Get-NewPatPreviousDataRoots $project (Join-Path $temporary 'default')
        Assert-Test ($retryRoots.data_dir -ceq $data -and $retryRoots.runs_dir -ceq $runs) 'retry after interrupted publication preserves custom roots'
    } finally {
        Set-Item -Path Function:Write-NewPatJsonAtomic -Value $originalJsonWriter
    }
    $state = $savedState
    Complete-NewPatRuntimeActivation $project $statePath $state $configuration {
        Assert-Test ($env:NEWPAT_DATA_DIR -ceq $data -and $env:NEWPAT_RUNS_DIR -ceq $runs) 'candidate checks use preserved data roots'
        $notReady = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Test ($notReady.phase -cne 'ready') 'ready marker remains unset until checks finish'
    }
    $selected = Get-Content -LiteralPath $backendPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $ready = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($selected.wsl_distro -ceq $target.Distro -and $ready.phase -ceq 'ready') 'successful retry selects candidate and publishes ready state'
    Assert-Test ($selected.rootfs_sha256 -ceq $hash -and $ready.rootfs_sha256 -ceq $hash) 'selected rootfs is bound in state and configuration'
    Assert-Test ([Environment]::GetEnvironmentVariable('NEWPAT_WSL_DISTRO', 'Process') -ceq $envBefore) 'candidate environment restored after successful activation'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $data 'input.txt')) -ceq 'input sentinel' -and [IO.File]::ReadAllText((Join-Path $runs 'result.txt')) -ceq 'result sentinel') 'data and existing results remain unchanged'
    $selected.data_dir = 'relative-data'
    Write-NewPatJsonAtomic $backendPath $selected
    Assert-Rejected { Get-NewPatPreviousDataRoots $project $temporary } 'invalid previous data root is rejected rather than reset'
    Assert-Test (@($calls | Where-Object { $_[0] -in @('--unregister', '--terminate', '--shutdown') }).Count -eq 0) 'migration never deletes or stops another runtime'
    Write-Host "PASS: $checks migration assertions."
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
