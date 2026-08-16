param(
    [string]$BundleRoot = "C:\cf27\task027-l2-bundle",
    [string]$ProjectRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "examples\pen_engraving"),
    [string]$InstallBase = "C:\cf27\install",
    [string]$Underlay = "C:\IsaacSim-ros-workspaces\jazzy_ws\install",
    [string]$PixiPrefix = "C:\IsaacSim-ros-workspaces\jazzy_ws\.pixi\envs\default",
    [string]$IsaacSimRoot = "C:\isaacsim",
    [string]$WorkingRoot = "C:\cf27\task027-runjob-matrix",
    [ValidateRange(0, 101)][int]$RosDomainId = 42,
    [string]$RmwImplementation = "rmw_fastrtps_cpp",
    [string]$DdsAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$scenarios = @(
    "pen-nominal",
    "pen-physical-dropped",
    "pen-physical-failed-seating",
    "pen-physical-collision"
)
$reports = @()
foreach ($scenario in $scenarios) {
    $runRoot = Join-Path $WorkingRoot $scenario
    & (Join-Path $PSScriptRoot "run_isaac_l2_runjob.ps1") `
        -BundleRoot $BundleRoot `
        -ProjectRoot $ProjectRoot `
        -InstallBase $InstallBase `
        -Underlay $Underlay `
        -PixiPrefix $PixiPrefix `
        -IsaacSimRoot $IsaacSimRoot `
        -WorkingRoot $runRoot `
        -AcceptanceScenario $scenario `
        -RosDomainId $RosDomainId `
        -RmwImplementation $RmwImplementation `
        -DdsAddress $DdsAddress
    $reportPath = Join-Path $runRoot "isaac-l2-runjob-report.json"
    if (-not (Test-Path -LiteralPath $reportPath)) {
        throw "Task 027 scenario '$scenario' did not produce an acceptance report."
    }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($report.scenario_count -ne 1 -or $report.results.Count -ne 1) {
        throw "Task 027 scenario '$scenario' report is incomplete."
    }
    $reports += $report.results[0]
}
$output = Join-Path $WorkingRoot "isaac-l2-runjob-matrix-report.json"
@{
    schema_version = "0.1.0"
    kind = "cellforge.isaac_l2_runjob_acceptance_matrix"
    submitted_action = "/cell/run_job"
    event_origin = "runtime/adapters"
    scenario_count = $reports.Count
    results = $reports
    isolation = "Each scenario uses a fresh real Isaac Sim/ROS runtime because declared fault scenarios correctly end in RECOVERABLE_FAULT."
    laser_qualification_excluded = @("beam/material interaction", "mark quality", "text fidelity")
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $output -Encoding utf8
Write-Output "Task 027 Isaac L2 RunJob matrix passed $($reports.Count)/$($scenarios.Count) isolated scenarios. Report: $output"
