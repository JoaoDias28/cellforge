param(
    [string]$BuildBase = "C:\cf27\build",
    [string]$InstallBase = "C:\cf27\install",
    [string]$Underlay = "C:\IsaacSim-ros-workspaces\jazzy_ws\install",
    [string]$PixiPrefix = "C:\IsaacSim-ros-workspaces\jazzy_ws\.pixi\envs\default",
    [string]$LlvmBin = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\x64\bin"
)

$ErrorActionPreference = "Stop"
$toolPath = @(
    (Join-Path $Underlay "Scripts")
    $PixiPrefix
    (Join-Path $PixiPrefix "Library\bin")
    (Join-Path $PixiPrefix "Scripts")
    $LlvmBin
    "C:\Windows\System32"
    "C:\Windows"
    "C:\Program Files\Git\cmd"
    "C:\Program Files\CMake\bin"
) -join ";"
$rosLogDirectory = Join-Path $BuildBase "ros-log"
New-Item -ItemType Directory -Force -Path $rosLogDirectory | Out-Null

function Invoke-RosCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = "C:\Windows\System32\cmd.exe"
    $start.Arguments = "/d /c $Command"
    $start.UseShellExecute = $false
    $preserved = @{
        "APPDATA" = $env:APPDATA
        "LOCALAPPDATA" = $env:LOCALAPPDATA
        "PATHEXT" = $env:PATHEXT
        "PROGRAMDATA" = $env:PROGRAMDATA
        "SYSTEMDRIVE" = $env:SYSTEMDRIVE
        "SYSTEMROOT" = $env:SYSTEMROOT
        "TEMP" = $env:TEMP
        "TMP" = $env:TMP
        "USERPROFILE" = $env:USERPROFILE
        "ROS_LOG_DIR" = $rosLogDirectory
    }
    $null = $start.Environment
    $childProcessEnvironment = $start.EnvironmentVariables
    $childProcessEnvironment.Clear()
    foreach ($entry in $preserved.GetEnumerator()) {
        if ($entry.Value) {
            $childProcessEnvironment.Add($entry.Key, $entry.Value)
        }
    }
    $childProcessEnvironment.Add("Path", $toolPath)
    $process = [System.Diagnostics.Process]::Start($start)
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "ROS command failed with exit code $($process.ExitCode): $Command"
    }
}

$setup = "call $(Join-Path $InstallBase 'setup.bat') && set `"RMW_IMPLEMENTATION=rmw_fastrtps_cpp`""
$skip = "cellforge_bringup cellforge_device_sdk cellforge_hardware_adapters cellforge_job_gateway cellforge_mock_adapters cellforge_operator_api cellforge_simulation cellforge_state_trace"
$pythonTests = "ros_ws/src/cellforge_hardware_adapters/test ros_ws/src/cellforge_job_gateway/test ros_ws/src/cellforge_mock_adapters/test ros_ws/src/cellforge_operator_api/test ros_ws/src/cellforge_simulation/test ros_ws/src/cellforge_state_trace/test"

Invoke-RosCommand "$setup && colcon test --build-base $BuildBase --install-base $InstallBase --merge-install --packages-skip $skip --return-code-on-test-failure --event-handlers console_direct+"
Invoke-RosCommand "$setup && python -m pytest -q --basetemp $BuildBase/ros-python-pytest -o cache_dir=$BuildBase/ros-python-pytest-cache $pythonTests"
Invoke-RosCommand "colcon test-result --test-result-base $BuildBase --verbose"
