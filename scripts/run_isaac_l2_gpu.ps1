param(
    [string]$IsaacSimRoot = "C:\isaacsim",
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
$versionPath = Join-Path $IsaacSimRoot "VERSION"
$kitPath = Join-Path $IsaacSimRoot "kit\kit.exe"
$appPath = Join-Path $IsaacSimRoot "apps\isaacsim.exp.base.python.kit"
$probePath = Join-Path $RepositoryRoot "scripts\verify_kit_l2_runtime.py"
if (-not (Test-Path -LiteralPath $versionPath) -or -not (Test-Path -LiteralPath $kitPath)) {
    throw "Task 027 requires a complete Isaac Sim 6 installation at '$IsaacSimRoot'."
}
$version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
if (-not $version.StartsWith("6.")) {
    throw "Task 027 requires Isaac Sim 6; found '$version'."
}
$gpuOutput = & nvidia-smi --query-gpu=name --format=csv,noheader
$gpuExitCode = $LASTEXITCODE
$gpuName = ($gpuOutput | Select-Object -First 1).Trim()
if ($gpuExitCode -ne 0 -or -not $gpuName) {
    throw "Task 027 requires an available NVIDIA GPU; CPU fallback is forbidden."
}
if (-not $ReportPath) {
    $ReportPath = Join-Path $RepositoryRoot ".artifacts\task027\isaac-l2-seed-report.json"
}
$env:ISAAC_SIM_ROOT = $IsaacSimRoot
$env:CELLFORGE_L2_REPORT = $ReportPath
& $kitPath $appPath --no-window --exec $probePath
if ($LASTEXITCODE -ne 0) {
    throw "Isaac Sim L2 GPU probe failed with exit code $LASTEXITCODE."
}
$report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
if (-not $report.actual_physx_executed -or $report.summary.passed -ne 100 -or $report.summary.failed -ne 0) {
    throw "Isaac L2 report does not prove 100 successful actual-PhysX runs."
}
Write-Output "Isaac Sim $version L2 GPU acceptance passed on $gpuName. Report: $ReportPath"
