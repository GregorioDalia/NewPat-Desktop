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
try {
    $env:LOCALAPPDATA = $temporary
    $root = Get-NipatZipRoot
    [IO.Directory]::CreateDirectory($root) | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'foreign.txt'), 'keep')
    Assert-Rejected { Assert-NipatZipRoot $root -Create } 'nonempty unowned directory rejected'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $root 'foreign.txt')) -ceq 'keep') 'foreign file retained'
    Remove-Item -LiteralPath (Join-Path $root 'foreign.txt')
    Assert-NipatZipRoot $root -Create
    Assert-NipatZipRoot $root
    $old = [pscustomobject]@{ schema_version = 1; version = '0.8.95'; source_commit = ('a' * 40); app_dir = (Get-NipatZipProject $root '0.8.95' ('a' * 40)) }
    $next = [pscustomobject]@{ schema_version = 1; version = '0.8.96'; source_commit = ('b' * 40); app_dir = (Get-NipatZipProject $root '0.8.96' ('b' * 40)) }
    Write-NipatJsonAtomic (Join-Path $root 'current.json') $old
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
} finally {
    $env:LOCALAPPDATA = $oldLocal
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
