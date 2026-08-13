param(
    [string]$BundleRoot = "C:\cf27\task027-l2-bundle",
    [string]$ProjectRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "examples\pen_engraving"),
    [string]$InstallBase = "C:\cf27\install",
    [string]$Underlay = "C:\IsaacSim-ros-workspaces\jazzy_ws\install",
    [string]$PixiPrefix = "C:\IsaacSim-ros-workspaces\jazzy_ws\.pixi\envs\default",
    [string]$IsaacSimRoot = "C:\isaacsim",
    [string]$WorkingRoot = "C:\cf27\task027-runjob",
    [string]$AcceptanceScenario = ""
)

$ErrorActionPreference = "Stop"
if (-not $AcceptanceScenario) {
    throw "Task 027 RunJob acceptance requires one explicit scenario per isolated runtime. Use scripts/run_isaac_l2_runjob_matrix.ps1 for the complete matrix."
}
$repository = Split-Path -Parent $PSScriptRoot
$scenario = Join-Path $ProjectRoot "scenarios\nominal.yaml"
$report = Join-Path $WorkingRoot "isaac-l2-runjob-report.json"
$adapterReport = Join-Path $WorkingRoot "isaac-l2-adapter-events.json"
$stateRoot = Join-Path $WorkingRoot "state"
$auth = Join-Path $WorkingRoot "operator-auth.json"
$stdout = Join-Path $WorkingRoot "runtime.stdout.log"
$stderr = Join-Path $WorkingRoot "runtime.stderr.log"
$kitStdout = Join-Path $WorkingRoot "isaac-adapter.stdout.log"
$kitStderr = Join-Path $WorkingRoot "isaac-adapter.stderr.log"
New-Item -ItemType Directory -Force -Path $WorkingRoot, $stateRoot | Out-Null

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$hash = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("task-027-local-acceptance"))
$sha256.Dispose()
$tokenHash = ([System.BitConverter]::ToString($hash) -replace "-", "").ToLowerInvariant()
$authDocument = @{
    schema_version = "0.1.0"
    tokens = @(
        @{
            token_sha256 = $tokenHash
            principal_id = "task-027-acceptance"
            display_name = "Task 027 Acceptance"
            role = "maintainer"
        }
    )
} | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($auth, $authDocument, [System.Text.UTF8Encoding]::new($false))

$toolPath = @(
    $PixiPrefix
    (Join-Path $InstallBase "bin")
    (Join-Path $Underlay "bin")
    (Join-Path $PixiPrefix "Library\bin")
    (Join-Path $PixiPrefix "Scripts")
    "C:\Windows\System32"
    "C:\Windows"
) -join ";"

function New-CleanProcessStart {
    param([Parameter(Mandatory = $true)][string]$Command)

    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = "C:\Windows\System32\cmd.exe"
    $start.Arguments = "/d /c $Command"
    $start.UseShellExecute = $false
    foreach ($name in @("APPDATA", "LOCALAPPDATA", "PATHEXT", "PROGRAMDATA", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")) {
        $value = [System.Environment]::GetEnvironmentVariable($name)
        if ($value) {
            $start.Environment[$name] = $value
        }
    }
    $start.Environment["Path"] = $toolPath
    return $start
}

function Stop-ProcessTree {
    param([int]$RootId)

    $descendants = @()
    $frontier = @($RootId)
    while ($frontier.Count -gt 0) {
        $parent = $frontier[0]
        $frontier = @($frontier | Select-Object -Skip 1)
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$parent" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            $descendants += [int]$child.ProcessId
            $frontier += [int]$child.ProcessId
        }
    }
    foreach ($processId in @($descendants | Select-Object -Last $descendants.Count) + $RootId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

$setup = "call $(Join-Path $InstallBase 'setup.bat') && set `"RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`" && set `"ROS_DOMAIN_ID=42`""
$pythonPath = "$InstallBase\Lib\site-packages;$Underlay\Lib\site-packages;$PixiPrefix\Lib\site-packages;$PixiPrefix\Library\lib\site-packages;$(Join-Path $IsaacSimRoot 'site')"
$isaac = "set `"OMNI_KIT_ACCEPT_EULA=YES`" && set `"PYTHONPATH=$pythonPath`" && set `"CELLFORGE_PYTHONPATH=$pythonPath`""
$adapter = "$setup && $isaac && set `"CELLFORGE_L2_SCENE=$BundleRoot\assets\scene.usda`" && set `"CELLFORGE_L2_SCENARIO=$scenario`" && set `"CELLFORGE_L2_SCENARIO_ROOT=$ProjectRoot`" && set `"CELLFORGE_L2_REPORT=$adapterReport`" && $IsaacSimRoot\kit\kit.exe $IsaacSimRoot\apps\isaacsim.exp.base.python.kit --no-window --exec $(Join-Path $repository 'scripts\start_isaac_l2_ros_adapter.py')"
$kitStart = New-CleanProcessStart $adapter
$kitStart.CreateNoWindow = $true
$kitStart.RedirectStandardOutput = $true
$kitStart.RedirectStandardError = $true
$kit = [System.Diagnostics.Process]::Start($kitStart)
$kitOutTask = $kit.StandardOutput.ReadToEndAsync()
$kitErrTask = $kit.StandardError.ReadToEndAsync()

$launch = "$setup && $isaac && ros2 launch cellforge_bringup integrated_runtime.launch.py bundle_root:=$BundleRoot fidelity:=L2 local_state_root:=$stateRoot operator_auth:=$auth operator_port:=19080 l2_scenario:=$scenario l2_scenario_root:=$ProjectRoot l2_report:=$adapterReport l2_launch_adapter:=false"
$launchStart = New-CleanProcessStart $launch
$launchStart.CreateNoWindow = $true
$launchStart.RedirectStandardOutput = $true
$launchStart.RedirectStandardError = $true
$runtime = [System.Diagnostics.Process]::Start($launchStart)
$outTask = $runtime.StandardOutput.ReadToEndAsync()
$errTask = $runtime.StandardError.ReadToEndAsync()
try {
    Start-Sleep -Seconds 70
    if ($runtime.HasExited -or $kit.HasExited) {
        throw "L2 runtime or Kit-hosted adapter exited before the acceptance client started."
    }
    $scenarioArgument = if ($AcceptanceScenario) { " --scenario $AcceptanceScenario" } else { "" }
    $client = "$setup && python $(Join-Path $repository 'scripts\run_isaac_l2_runjob_acceptance.py') --project $ProjectRoot --report $report$scenarioArgument"
    $clientStart = New-CleanProcessStart $client
    $client = [System.Diagnostics.Process]::Start($clientStart)
    $client.WaitForExit()
    if ($client.ExitCode -ne 0) {
        throw "RunJob acceptance client failed with exit code $($client.ExitCode)."
    }
} finally {
    Stop-ProcessTree $runtime.Id
    Stop-ProcessTree $kit.Id
    $runtime.WaitForExit(10000) | Out-Null
    $kit.WaitForExit(10000) | Out-Null
    $outTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $stdout -Encoding utf8
    $errTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $stderr -Encoding utf8
    $kitOutTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $kitStdout -Encoding utf8
    $kitErrTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $kitStderr -Encoding utf8
}

if (-not (Test-Path -LiteralPath $report)) {
    throw "RunJob acceptance did not produce '$report'."
}
$document = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($document.scenario_count -lt 1 -or $document.submitted_action -ne "/cell/run_job") {
    throw "RunJob acceptance report is incomplete."
}
Write-Output "Task 027 Isaac L2 RunJob acceptance passed $($document.scenario_count) scenarios. Report: $report"
