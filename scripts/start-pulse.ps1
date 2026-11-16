param([ValidateSet('production', 'dev', 'check', 'clipboard', 'stop', 'health', 'probe')][string]$Mode = 'production')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'pulse-launch-config.ps1')
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$next = Join-Path $root 'node_modules\next\dist\bin\next'
$credentials = [ordered]@{
    BLUEPULSE_ADMIN_PASSWORD = 12
    BLUEPULSE_ADMIN_SESSION_SECRET = 32
    BLUEPULSE_MEDIA_SECRET = 1
}

function Get-LocalPort($Name, [int]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) { return $Default }
    if ($value -notmatch '^[0-9]{1,5}$' -or [int]$value -lt 1 -or [int]$value -gt 65535) {
        throw "Invalid TCP port in $Name."
    }
    return [int]$value
}

function Set-Default($Name, $Value) {
    if (-not [Environment]::GetEnvironmentVariable($Name)) {
        [Environment]::SetEnvironmentVariable($Name, $Value)
    }
}

function Open-LaunchLock($Path) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        try { return [IO.File]::Open($Path, 'OpenOrCreate', 'ReadWrite', 'None') }
        catch [IO.IOException] {
            if (($_.Exception.HResult -band 0xffff) -ne 32) { throw }
            Start-Sleep -Milliseconds 500
        }
    } while ($timer.Elapsed.TotalSeconds -lt 300)
    throw 'Another Pulse startup or shutdown is still in progress.'
}

function Get-LocalCredentials([switch]$ReadOnly) {
    Add-Type -AssemblyName System.Security
    $scope = [Security.Cryptography.DataProtectionScope]::CurrentUser
    $stored = @{}
    if (Test-Path -LiteralPath $credentialFile) {
        try {
            $protected = [Convert]::FromBase64String([IO.File]::ReadAllText($credentialFile))
            $bytes = [Security.Cryptography.ProtectedData]::Unprotect($protected, $null, $scope)
            $decoded = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
            foreach ($name in $credentials.Keys) { $stored[$name] = $decoded.$name }
        } catch { throw 'The Windows account could not decrypt the local Pulse credentials.' }
    }
    $changed = $false
    $effective = @{}
    foreach ($name in $credentials.Keys) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value -and $value.Length -lt $credentials[$name]) {
            throw "Configured $name is too short."
        }
        if (-not $value) {
            $value = $stored[$name]
            if (-not $value -and -not $ReadOnly) {
                $bytes = New-Object byte[] 32
                $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
                try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
                $value = [Convert]::ToBase64String($bytes)
                $stored[$name] = $value
                $changed = $true
            }
        }
        if ($value) { $effective[$name] = $value }
    }
    if ($changed) {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($stored | ConvertTo-Json -Compress))
        $protected = [Security.Cryptography.ProtectedData]::Protect($bytes, $null, $scope)
        [IO.File]::WriteAllText("$credentialFile.tmp", [Convert]::ToBase64String($protected))
        Move-Item -LiteralPath "$credentialFile.tmp" -Destination $credentialFile -Force
    }
    return $effective
}

function Invoke-Backend($Module, $Argument) {
    Push-Location $backend
    try {
        & $python -m $Module $Argument @args
        if ($LASTEXITCODE -ne 0) { throw "$Module $Argument failed (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
}

function Get-RecordedProcess($record) {
    if (-not $record) { return }
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToFileTimeUtc() -eq $record.started) { return $process }
}

function Get-OwnedProcess($Role) { Get-RecordedProcess $services[$Role] }

function Assert-PortOwner($Role, $Port) {
    $process = Get-OwnedProcess $Role
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object LocalPort -eq $Port | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($owner in $listeners) {
        $current = $owner
        $before = [datetime]::MaxValue
        # Next dev and the Windows Python virtualenv can each use a child listener.
        while ($process -and $current -and $current -ne $process.Id) {
            $child = Get-CimInstance Win32_Process -Filter "ProcessId=$current"
            if (-not $child -or $child.CreationDate -lt $process.StartTime -or $child.CreationDate -ge $before) { break }
            $before = $child.CreationDate
            $current = $child.ParentProcessId
        }
        if (-not $process -or $current -ne $process.Id) {
            throw "Port $Port is occupied by PID $owner, outside this Pulse launch. Stop that instance before retrying."
        }
    }
    return ($listeners.Count -gt 0)
}

function Stop-OwnedService($Role, $Seconds) {
    $process = Get-OwnedProcess $Role
    if (-not $process) { return }
    Write-Host "Stopping Pulse $Role (PID $($process.Id))..."
    & $python (Join-Path $PSScriptRoot 'signal-pulse-console.py') $process.Id $services[$Role].started
    if ($LASTEXITCODE -ne 0 -or -not $process.WaitForExit($Seconds * 1000)) {
        throw "Pulse $Role did not stop. See its logs in $runDir. Remaining services were left running."
    }
}

function Save-Services {
    @{ signature = $signature; services = $services } | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath "$stateFile.tmp" -Encoding UTF8
    Move-Item -LiteralPath "$stateFile.tmp" -Destination $stateFile -Force
}

function Start-ServiceProcess($Role, $Executable, $Arguments, $Directory) {
    Write-Host "Starting Pulse $Role..."
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $Directory `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDir "$stamp-$Role.out.log") `
        -RedirectStandardError (Join-Path $runDir "$stamp-$Role.err.log")
    $services[$Role] = @{ pid = $process.Id; started = $process.StartTime.ToFileTimeUtc() }
    Save-Services
}

function Wait-Http($Role, $Port, $Path, $ExpectedProperty, $Seconds) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $Seconds) {
        if (-not (Get-OwnedProcess $Role)) { throw "Pulse $Role exited. See its logs in $runDir." }
        if (Assert-PortOwner $Role $Port) {
            try {
                $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port$Path" -TimeoutSec 3
                if ($ExpectedProperty -eq 'status' -and $response.status -eq 'ready') { return $response }
                if ($ExpectedProperty -eq 'sources' -and $null -ne $response.sources) { return $response }
            } catch { }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Pulse $Role did not become ready. See its logs in $runDir."
}

try {
    $apiPort = Get-LocalPort BLUEPULSE_LOCAL_API_PORT 8000
    $webPort = Get-LocalPort BLUEPULSE_LOCAL_WEB_PORT 3000
    if ($apiPort -eq $webPort) { throw 'Pulse API and Web require different ports.' }
    $apiOrigin = "http://127.0.0.1:$apiPort"
    $webOrigin = "http://127.0.0.1:$webPort"
    $launcherDir = Join-Path $backend 'data\launcher'
    $runDir = Join-Path $launcherDir "$webPort-$apiPort"
    $stateFile = Join-Path $runDir 'services.json'
    $credentialFile = Join-Path $runDir 'credentials.dpapi'
    if ($Mode -eq 'clipboard') {
        $effective = Get-LocalCredentials -ReadOnly
        if (-not $effective.BLUEPULSE_ADMIN_PASSWORD) { throw 'Start Pulse first to configure its admin password.' }
        Set-Clipboard -Value $effective.BLUEPULSE_ADMIN_PASSWORD
        Write-Host 'Pulse admin password copied to the Windows clipboard.'
        exit 0
    }

    if (-not (Test-Path -LiteralPath $python)) { throw 'Install the backend virtualenv as described in backend/README.md.' }
    Set-Default BLUEPULSE_QUICK_TUNNEL '0'
    Set-Default BLUEPULSE_SITE_ORIGIN $webOrigin
    Set-Default BLUEPULSE_API_URL $apiOrigin
    Set-Default BLUEPULSE_TRUST_PROXY '0'
    Set-Default BLUEPULSE_COLLECT_ENABLED '1'
    Set-Default BLUEPULSE_MODEL_CALLS_ENABLED '1'
    Set-Default BLUEPULSE_MODEL_BUDGET_MINUTE '300'
    Set-Default BLUEPULSE_MODEL_BUDGET_HOUR '6000'
    Set-Default BLUEPULSE_MODEL_BUDGET_DAY '40000'
    Set-Default BLUEPULSE_FEEDBACK_ENABLED '1'
    if ($Mode -in @('production', 'dev', 'check')) {
        Assert-PulseLaunchOriginConfiguration -SiteOrigin $env:BLUEPULSE_SITE_ORIGIN -LocalWebOrigin $webOrigin `
            -QuickTunnel $env:BLUEPULSE_QUICK_TUNNEL -ApiOrigin $env:BLUEPULSE_API_URL `
            -LocalApiOrigin $apiOrigin -TrustProxy $env:BLUEPULSE_TRUST_PROXY
    }
    # Diagnostic modes must not acquire launch locks, prepare storage, or start services.
    if ($Mode -eq 'check') {
        $workerConfig = Invoke-Backend bluepulse_backend.worker --check-config
        Write-Host "Worker configuration (syntax only; provider not probed): $workerConfig"
        exit 0
    }
    if ($Mode -in @('health', 'probe')) {
        Push-Location $backend
        try {
            if ($Mode -eq 'probe') { & $python -m bluepulse_backend.runtime_health --probe-model }
            else { & $python -m bluepulse_backend.runtime_health }
            $healthExit = $LASTEXITCODE
        } finally { Pop-Location }
        exit $healthExit
    }
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    $lock = Open-LaunchLock (Join-Path $launcherDir 'launch.lock')
    try {
        $services = @{}
        $saved = $null
        if (Test-Path -LiteralPath $stateFile) {
            $saved = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            foreach ($role in 'api', 'worker', 'web') { $services[$role] = $saved.services.$role }
        }
        if ($Mode -eq 'stop') {
            Stop-OwnedService worker 210
            Stop-OwnedService web 45
            Stop-OwnedService api 45
            Write-Host 'Pulse services stopped.'
            exit 0
        }
        if (-not (Test-Path -LiteralPath $next)) { throw 'Run pnpm install in the Pulse workspace.' }
        $node = (Get-Command node.exe).Source
        $pnpm = (Get-Command pnpm.cmd).Source
        if ($Mode -ne 'check') {
            [void](Assert-PortOwner api $apiPort)
            [void](Assert-PortOwner web $webPort)
        }
        $effective = Get-LocalCredentials -ReadOnly:($Mode -eq 'check')
        $effective.BLUEPULSE_INTERNAL_TOKEN = $env:BLUEPULSE_INTERNAL_TOKEN
        foreach ($name in $effective.Keys) {
            # Only the API needs these secrets. They do not enter the Next build or process.
            [Environment]::SetEnvironmentVariable($name, $null)
        }
        $workerConfig = Invoke-Backend bluepulse_backend.worker --check-config
        Write-Host "Worker configuration: $workerConfig"
        if ($Mode -eq 'check') { exit 0 }
        $revision = if (Test-Path -LiteralPath (Join-Path $root '.git')) {
            & git -C $root rev-parse HEAD
            if ($LASTEXITCODE -ne 0) { throw 'Unable to determine the Pulse checkout revision.' }
        }
        $settings = @($revision, $Mode, $env:BLUEPULSE_SITE_ORIGIN, $env:BLUEPULSE_QUICK_TUNNEL,
            $env:BLUEPULSE_API_URL, $env:BLUEPULSE_TRUST_PROXY, $env:BLUEPULSE_DATABASE_URL,
            $env:BLUEPULSE_FEEDBACK_ENABLED, $workerConfig, $env:BLUEPULSE_MODELS,
            $env:BLUEPULSE_MODEL_PRESETS, $effective.BLUEPULSE_INTERNAL_TOKEN)
        foreach ($name in $credentials.Keys) { $settings += $effective[$name] }
        $hash = [Security.Cryptography.SHA256]::Create()
        try {
            $signature = [Convert]::ToBase64String($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($settings | ConvertTo-Json -Compress))))
        } finally { $hash.Dispose() }
        if ($saved -and $saved.signature -ne $signature -and
            ((Get-OwnedProcess api) -or (Get-OwnedProcess worker) -or (Get-OwnedProcess web))) {
            throw 'A Pulse service is already running with different settings. Stop the current instance first.'
        }

        if ($Mode -eq 'production' -and -not (Get-OwnedProcess web)) {
            # All launch profiles in this checkout share the production build directory.
            foreach ($file in Get-ChildItem -LiteralPath $launcherDir -Directory | ForEach-Object { Join-Path $_.FullName 'services.json' }) {
                if ($file -ne $stateFile -and (Test-Path -LiteralPath $file)) {
                    $other = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
                    if (Get-RecordedProcess $other.services.web) { throw 'Stop the other Pulse Web instance in this checkout before rebuilding.' }
                }
            }
            Push-Location $root
            try {
                & $pnpm build
                if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' }
            } finally { Pop-Location }
        }
        if (-not (Get-OwnedProcess api)) {
            if (-not (Get-OwnedProcess worker) -and -not (Get-OwnedProcess web)) {
                Write-Host 'Preparing the Pulse database and source registry...'
                Invoke-Backend bluepulse_backend.cli initialize --local-live
            }
            foreach ($name in $effective.Keys) { [Environment]::SetEnvironmentVariable($name, $effective[$name]) }
            try {
                Start-ServiceProcess api $python "-m uvicorn bluepulse_backend.api:app --host 127.0.0.1 --port $apiPort" $backend
            } finally {
                foreach ($name in $effective.Keys) { [Environment]::SetEnvironmentVariable($name, $null) }
            }
        }
        [void](Wait-Http api $apiPort '/api/v1/health/ready' status 60)

        if (-not (Get-OwnedProcess worker)) { Start-ServiceProcess worker $python '-m bluepulse_backend.worker' $backend }
        Invoke-Backend bluepulse_backend.worker --wait-ready
        if (-not (Get-OwnedProcess worker)) { throw "The Pulse worker exited. See its logs in $runDir." }

        if (-not (Get-OwnedProcess web)) {
            $nextMode = if ($Mode -eq 'dev') { 'dev' } else { 'start' }
            Start-ServiceProcess web $node "`"$next`" $nextMode --hostname 127.0.0.1 --port $webPort" $root
        }
        $stats = Wait-Http web $webPort '/api/bluepulse/site/stats' sources 90
        $publicOrigin = $env:BLUEPULSE_SITE_ORIGIN.TrimEnd('/')
        $entryUrl = $publicOrigin
        if ($stats.items -gt 0) {
            $hasFeatured = $stats.selected -gt 0
            try {
                $timeline = Invoke-RestMethod -Uri "$webOrigin/api/bluepulse/site/timeline?limit=1" -TimeoutSec 5
                if ($null -ne $timeline.cards) { $hasFeatured = $timeline.cards.Count -gt 0 }
            } catch { }
            if (-not $hasFeatured) { $entryUrl = "$publicOrigin/all" }
        }
        Write-Host "Pulse public items: $($stats.items). Opening page: $entryUrl"
        Write-Host "Pulse API, Worker and Web services are ready. Public origin: $publicOrigin; local Web: $webOrigin; local API: $apiOrigin. Logs: $runDir"
        Push-Location $backend
        try {
            & $python -m bluepulse_backend.runtime_health
            if ($LASTEXITCODE -ne 0) {
                Write-Host 'Pulse services are running; content pipeline audit has degraded or unavailable checks. See above.' -ForegroundColor Yellow
            }
        } finally { Pop-Location }
        if ($env:BLUEPULSE_LAUNCH_NO_BROWSER -ne '1') { Start-Process $entryUrl }
    } finally { $lock.Dispose() }
} catch {
    Write-Host "[Pulse] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
