param(
    [string] $Project = '',
    [switch] $LibraryOnly
)

# Optional removal of this installation's owned compute environments. Analysis data
# and unknown files are never removal targets. Inno calls this before removing
# the application, only after the user explicitly chooses runtime cleanup.
. (Join-Path $PSScriptRoot 'bootstrap-common.ps1')
. (Join-Path $PSScriptRoot 'bootstrap-migration.ps1')
. (Join-Path $PSScriptRoot 'activity-lock.ps1')
if (-not (Get-Command Get-NewPatKnownInstallLayouts -ErrorAction SilentlyContinue)) {
    . (Join-Path $PSScriptRoot 'install-layout.ps1')
}

function Get-NewPatRemovalPath([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]') {
        throw "Percorso di rimozione non locale o non assoluto: $Path."
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($full.Length -le 3) { throw 'La radice di un disco non puo essere una destinazione di rimozione.' }
    return $full
}

function Test-NewPatRemovalPathsOverlap([string] $First, [string] $Second) {
    $firstPath = Get-NewPatRemovalPath $First
    $secondPath = Get-NewPatRemovalPath $Second
    return $firstPath -ieq $secondPath -or
        $firstPath.StartsWith($secondPath + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $secondPath.StartsWith($firstPath + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NewPatRemovalTree([string] $Path) {
    $current = Get-NewPatRemovalPath $Path
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (Test-Path -LiteralPath $current) {
            $entry = Get-Item -LiteralPath $current -Force
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "La rimozione non attraversa collegamenti o junction: $current."
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -ieq $current) { break }
        $current = $parent
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return }
    $pending = New-Object 'Collections.Generic.Stack[string]'
    $pending.Push($Path)
    while ($pending.Count -gt 0) {
        foreach ($entry in @(Get-ChildItem -LiteralPath $pending.Pop() -Force)) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "La rimozione non attraversa collegamenti o junction: $($entry.FullName)."
            }
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
        }
    }
}

function Get-NewPatRemovalRegistrations {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (-not (Test-Path -LiteralPath $key)) { return @() }
    return @(Get-ChildItem -LiteralPath $key | ForEach-Object {
        $entry = Get-ItemProperty -LiteralPath $_.PSPath
        if ($null -ne $entry.PSObject.Properties['DistributionName'] -and
            $null -ne $entry.PSObject.Properties['BasePath']) {
            [pscustomobject]@{
                DistributionName = [string] $entry.DistributionName
                BasePath = [string] $entry.BasePath
                Version = if ($null -ne $entry.PSObject.Properties['Version']) { $entry.Version } else { $null }
            }
        }
    })
}

function Get-NewPatRemovalRegistrationPath([string] $Path) {
    if ($Path.StartsWith('\\?\')) { $Path = $Path.Substring(4) }
    return (Get-NewPatRemovalPath $Path)
}

function Assert-NewPatRemovalTarget($Target, $Registrations, [switch] $SkipOwnerProbe) {
    Assert-NewPatRemovalTree $Target.Directory
    Assert-NewPatRemovalTree $Target.OwnershipPath
    $receipt = Read-NewPatOwnership $Target.OwnershipPath $Target.Distro
    if ($null -eq $receipt -or $receipt.owner_id -cne $Target.Ownership.owner_id -or
        $receipt.rootfs_sha256 -cne $Target.RootfsSha256 -or
        (Get-FileHash -LiteralPath $Target.OwnershipPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Target.ReceiptSha256) {
        throw 'Il registro di proprieta e cambiato durante la verifica; nessuna ulteriore rimozione viene eseguita.'
    }
    Assert-NewPatRuntimeNamespace $Target.Distro $Target.RootfsSha256 $Target.RuntimeDirectory
    $matches = @($Registrations | Where-Object { $_.DistributionName -ieq $Target.Distro })
    if ($Target.Registered) {
        if ($matches.Count -ne 1 -or $matches[0].Version -ne 2 -or
            (Get-NewPatRemovalRegistrationPath $matches[0].BasePath) -ine $Target.Directory) {
            throw "La registrazione WSL non corrisponde al runtime NewPat previsto: $($Target.Distro)."
        }
        # This checks both the product marker and the installation's random owner
        # token. No owner file is initialized or rewritten during removal.
        if (-not $SkipOwnerProbe) { Assert-NewPatRuntimeOwner $Target }
    } else {
        if ($matches.Count -ne 0) { throw 'La registrazione WSL e cambiata durante la verifica.' }
        if ((Test-Path -LiteralPath $Target.Directory) -and
            @(Get-ChildItem -LiteralPath $Target.Directory -Force).Count -gt 0) {
            throw "Runtime non registrato con file ancora presenti: $($Target.Directory). Conservare la cartella per una verifica manuale."
        }
    }
}

function Get-NewPatZipRemovalRoot([string] $Project) {
    # The layout history stores paths, including versions from earlier releases
    # whose files can already have been removed. ZIP projects have an immutable
    # versions/<version>-<commit> path under their own installation root.
    $projectPath = Get-NewPatRemovalPath $Project
    $versions = [IO.Path]::GetDirectoryName($projectPath)
    if ([IO.Path]::GetFileName($versions) -ieq 'versions' -and
        [IO.Path]::GetFileName($projectPath) -cmatch '\A[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{40}\z') {
        return [IO.Path]::GetDirectoryName($versions)
    }
    return ''
}

function Get-NewPatRuntimeRemovalPlan([string] $Project, [switch] $InspectOnly) {
    $layouts = @(Get-NewPatKnownInstallLayouts $Project)
    $profile = Get-NewPatInstallationProfile
    $runtimeRoots = @{}
    $cacheRoots = @{}
    $protectedRoots = @()
    $selectedZipRoot = Get-NewPatZipRemovalRoot $Project
    foreach ($layout in $layouts) {
        Assert-NewPatInstallationChannel $layout 'Le destinazioni di rimozione'
        foreach ($name in @('app_dir', 'data_dir', 'runs_dir')) {
            $protectedRoots += Get-NewPatRemovalPath $layout.$name
        }
        $runtime = Get-NewPatRemovalPath $layout.runtime_dir
        $cache = Get-NewPatRemovalPath $layout.cache_dir
        if ((Get-NewPatZipRemovalRoot $layout.app_dir) -ine $selectedZipRoot) {
            $protectedRoots += @($runtime, $cache)
            continue
        }
        $runtimeRoots[$runtime] = $runtime
        $cacheRoots[$cache] = $cache
    }
    foreach ($path in @($runtimeRoots.Values) + @($cacheRoots.Values)) {
        foreach ($protected in $protectedRoots) {
            if (Test-NewPatRemovalPathsOverlap $path $protected) {
                throw "La destinazione da rimuovere si sovrappone a una cartella protetta di questa o di un altra installazione: $path."
            }
        }
        Assert-NewPatRemovalTree $path
    }
    foreach ($runtime in $runtimeRoots.Values) {
        foreach ($cache in $cacheRoots.Values) {
            if (Test-NewPatRemovalPathsOverlap $runtime $cache) {
                throw 'Ambiente WSL e cache condividono una destinazione; rimozione interrotta.'
            }
        }
    }
    $registrations = @(Get-NewPatRemovalRegistrations)
    $targets = @()
    $knownTargets = @{}
    foreach ($runtime in $runtimeRoots.Values) {
        if ((Test-Path -LiteralPath $runtime -PathType Container) -and
            -not (Test-NewPatStorageMarker $runtime 'runtime')) {
            throw "Ambiente di calcolo privo del marcatore NewPat: $runtime."
        }
        $receiptDirectory = Join-Path $runtime 'registrations'
        if (Test-Path -LiteralPath $receiptDirectory -PathType Container) {
            foreach ($file in @(Get-ChildItem -LiteralPath $receiptDirectory -Filter '*.json' -File)) {
                $distro = [IO.Path]::GetFileNameWithoutExtension($file.Name)
                if (-not $distro.StartsWith($profile.distro_prefix, [StringComparison]::Ordinal)) {
                    throw "Registro di una distribuzione estranea nella cartella NewPat: $($file.FullName)."
                }
                $receipt = Read-NewPatOwnership $file.FullName $distro
                Assert-NewPatRuntimeNamespace $distro $receipt.rootfs_sha256 $runtime
                if ($knownTargets.ContainsKey($distro)) {
                    throw "La distribuzione $distro compare in piu registri; nessuna rimozione viene eseguita."
                }
                $target = [pscustomobject]@{
                    Distro = $distro; Directory = (Get-NewPatRemovalPath (Join-Path $runtime $distro))
                    RuntimeDirectory = $runtime; OwnershipPath = $file.FullName
                    Ownership = $receipt; RootfsSha256 = $receipt.rootfs_sha256
                    Registered = @($registrations | Where-Object { $_.DistributionName -ieq $distro }).Count -gt 0
                    ReceiptSha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                }
                Assert-NewPatRemovalTarget $target $registrations -SkipOwnerProbe:$InspectOnly
                $knownTargets[$distro] = $target
                $targets += $target
            }
        }
    }
    # Resolve all receipts first: historical managed roots can contain a newer
    # runtime destination. An unknown registration in either root still blocks
    # the entire plan, independently of the order of layout discovery.
    foreach ($runtime in $runtimeRoots.Values) {
        foreach ($registration in $registrations) {
            # Unrelated registrations can use a path syntax this application does
            # not support. They are never candidates; selected targets have
            # already undergone the strict location check above.
            try { $registeredPath = Get-NewPatRemovalRegistrationPath $registration.BasePath }
            catch { continue }
            if (Test-NewPatRemovalPathsOverlap $runtime $registeredPath) {
                if (-not $knownTargets.ContainsKey($registration.DistributionName)) {
                    throw "Distribuzione senza un registro NewPat verificato nella destinazione scelta: $($registration.DistributionName)."
                }
            }
        }
    }
    $cacheFiles = @()
    foreach ($cache in $cacheRoots.Values) {
        if (-not (Test-Path -LiteralPath $cache -PathType Container)) { continue }
        $hasMarker = Test-NewPatStorageMarker $cache 'cache'
        if (-not $hasMarker) {
            throw "Cache priva del marcatore NewPat: $cache."
        }
        foreach ($file in @(Get-ChildItem -LiteralPath $cache -File -Force)) {
            if ($file.Name -cnotmatch '^([a-f0-9]{64})-(newpat-wsl-rootfs|newpat-scientific-runtime)-[A-Za-z0-9._-]+\.tar\.gz$') { continue }
            $expected = $Matches[1]
            $actual = if ($InspectOnly) { $expected } else { (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
            if ($actual -cne $expected) {
                throw "Archivio della cache modificato o incompleto: $($file.FullName). Nessuna rimozione viene eseguita."
            }
            $cacheFiles += [pscustomobject]@{ Path = $file.FullName; Sha256 = $expected }
        }
    }
    return [pscustomobject]@{
        Targets = @($targets); CacheFiles = @($cacheFiles)
        RuntimeRoots = @($runtimeRoots.Values); CacheRoots = @($cacheRoots.Values)
        ProtectedRoots = @($protectedRoots)
    }
}

function Remove-NewPatEmptyDirectory([string] $Path) {
    if (Test-Path -LiteralPath $Path -PathType Container) {
        Assert-NewPatRemovalTree $Path
        if (@(Get-ChildItem -LiteralPath $Path -Force).Count -eq 0) {
            [IO.Directory]::Delete($Path, $false)
        }
    }
}

function Invoke-NewPatRuntimeRemoval($Plan) {
    # Revalidate the entire plan immediately before its first destructive action.
    # A failed unregister stops here; successfully removed distributions are not
    # hidden by a broad catch or followed by an unconditional directory deletion.
    $registrations = @(Get-NewPatRemovalRegistrations)
    foreach ($target in $Plan.Targets) { Assert-NewPatRemovalTarget $target $registrations }
    foreach ($file in $Plan.CacheFiles) {
        Assert-NewPatRemovalTree $file.Path
        if (-not (Test-Path -LiteralPath $file.Path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $file.Path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Sha256) {
            throw 'La cache e cambiata durante la verifica; nessuna rimozione viene eseguita.'
        }
    }
    foreach ($target in $Plan.Targets) {
        Assert-NewPatRemovalTarget $target @(Get-NewPatRemovalRegistrations)
        if ($target.Registered) {
            Write-Host "Rimozione ambiente WSL NewPat: $($target.Distro)"
            Invoke-NewPatWsl @('--unregister', $target.Distro) -TimeoutSeconds 240 | Out-Null
            if (@(Get-NewPatRemovalRegistrations | Where-Object { $_.DistributionName -ieq $target.Distro }).Count -ne 0) {
                throw "WSL riporta ancora la distribuzione $($target.Distro); il registro NewPat viene conservato."
            }
        }
        [IO.File]::Delete($target.OwnershipPath)
        Remove-NewPatEmptyDirectory $target.Directory
    }
    foreach ($file in $Plan.CacheFiles) {
        Assert-NewPatRemovalTree $file.Path
        if ((Get-FileHash -LiteralPath $file.Path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Sha256) {
            throw 'Un archivio della cache e cambiato; la rimozione degli archivi rimanenti viene interrotta.'
        }
        Write-Host "Rimozione archivio della cache: $($file.Path)"
        [IO.File]::Delete($file.Path)
    }
    foreach ($runtime in $Plan.RuntimeRoots) { Remove-NewPatEmptyDirectory (Join-Path $runtime 'registrations') }
    foreach ($path in @($Plan.RuntimeRoots) + @($Plan.CacheRoots)) { Remove-NewPatEmptyDirectory $path }
    Write-Host 'Ambienti NewPat verificati e archivi della cache rimossi. Dati, risultati e file non riconosciuti sono conservati.'
}

if (-not $LibraryOnly) {
    $mutex = $null
    $locked = $false
    $activityLease = $null
    $result = 1
    $transcriptStarted = $false
    $logPath = $null
    try {
        Assert-NewPatWindowsUser
        if (-not $Project) { $Project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
        Assert-NewPatInstallationLocation $Project
        $activityLease = Enter-NewPatInstallationActivity
        $profile = Get-NewPatInstallationProfile
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $mutex = New-Object Threading.Mutex($false, ($profile.mutex_prefix + $sid))
        try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
        if (-not $locked) { throw 'La preparazione NewPat e in corso. Attendere prima di disinstallare.' }
        $logDirectory = Join-Path (Get-NewPatInstallLayoutHistoryDirectory) 'logs'
        Assert-NewPatInstallPathWithoutLinks $logDirectory -Tree
        [IO.Directory]::CreateDirectory($logDirectory) | Out-Null
        $logPath = Join-Path $logDirectory ('uninstall-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N') + '.log')
        Start-Transcript -LiteralPath $logPath -ErrorAction Stop | Out-Null
        $transcriptStarted = $true
        $script:NewPatWsl = Join-Path $env:WINDIR 'System32\wsl.exe'
        $plan = Get-NewPatRuntimeRemovalPlan $Project
        Invoke-NewPatRuntimeRemoval $plan
        $result = 0
    } catch {
        Write-Host ('Rimozione del runtime interrotta: ' + $_.Exception.Message) -ForegroundColor Red
        Write-Host 'Gli elementi gia rimossi restano rimossi. Le analisi, Docker Desktop e le altre distribuzioni non vengono cancellati.'
    } finally {
        try {
            if ($transcriptStarted) {
                try { Stop-Transcript -ErrorAction Stop | Out-Null }
                catch { Write-Host ('Impossibile completare il log di rimozione: ' + $_.Exception.Message) -ForegroundColor Yellow }
                Write-Host "Log della rimozione: $logPath"
            }
            if ($locked) { $mutex.ReleaseMutex() }
            if ($null -ne $mutex) { $mutex.Dispose() }
        } finally {
            Exit-NewPatInstallationActivity $activityLease
        }
    }
    exit $result
}
