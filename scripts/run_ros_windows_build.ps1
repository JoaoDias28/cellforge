param(
    [string]$SourceBase = "ros_ws\src",
    [string]$BuildBase = "C:\cf27\build",
    [string]$InstallBase = "C:\cf27\install",
    [string]$Underlay = "C:\IsaacSim-ros-workspaces\jazzy_ws\install",
    [string]$PixiPrefix = "C:\IsaacSim-ros-workspaces\jazzy_ws\.pixi\envs\default",
    [string]$VsDevCmd = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
)

$ErrorActionPreference = "Stop"
$toolPath = @(
    $PixiPrefix
    (Join-Path $PixiPrefix "Library\bin")
    (Join-Path $PixiPrefix "Scripts")
    "C:\Windows\System32"
    "C:\Windows"
    "C:\Program Files\Git\cmd"
    "C:\Program Files\CMake\bin"
) -join ";"
$start = [System.Diagnostics.ProcessStartInfo]::new()
$start.FileName = "C:\Windows\System32\cmd.exe"
$pythonExecutable = (Join-Path $PixiPrefix "python.exe").Replace('\', '/')
$pythonRoot = $PixiPrefix.Replace('\', '/')
$numpyInclude = (Join-Path $PixiPrefix "Lib\site-packages\numpy\_core\include").Replace('\', '/')
$command = "call `"$VsDevCmd`" -arch=x64 && call $(Join-Path $Underlay 'setup.bat') && set `"RMW_IMPLEMENTATION=rmw_fastrtps_cpp`" && colcon build --base-paths $SourceBase --build-base $BuildBase --install-base $InstallBase --merge-install --cmake-args -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_OBJECT_PATH_MAX=200 -DPython3_EXECUTABLE=$pythonExecutable -DPython3_ROOT_DIR=$pythonRoot -DPython3_NumPy_INCLUDE_DIR=$numpyInclude --event-handlers console_direct+"
$start.Arguments = "/d /c $command"
$start.UseShellExecute = $false
$null = $start.Environment
$childProcessEnvironment = $start.EnvironmentVariables
$childProcessEnvironment.Clear()
foreach ($name in @("APPDATA", "LOCALAPPDATA", "PATHEXT", "PROGRAMDATA", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")) {
    $value = [System.Environment]::GetEnvironmentVariable($name)
    if ($value) {
        $childProcessEnvironment.Add($name, $value)
    }
}
$childProcessEnvironment.Add("Path", $toolPath)
$process = [System.Diagnostics.Process]::Start($start)
$process.WaitForExit()
if ($process.ExitCode -ne 0) {
    throw "ROS build failed with exit code $($process.ExitCode)."
}
