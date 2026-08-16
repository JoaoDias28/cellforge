param(
    [string]$BundleRoot = "C:\cf27\task027-l2-bundle",
    [string]$ProjectRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "examples\pen_engraving"),
    [string]$InstallBase = "C:\cf27\install",
    [string]$Underlay = "C:\IsaacSim-ros-workspaces\jazzy_ws\install",
    [string]$PixiPrefix = "C:\IsaacSim-ros-workspaces\jazzy_ws\.pixi\envs\default",
    [string]$IsaacSimRoot = "C:\isaacsim",
    [string]$WorkingRoot = "C:\cf27\task027-runjob",
    [string]$AcceptanceScenario = "",
    [ValidateRange(0, 101)][int]$RosDomainId = 42,
    [ValidateRange(1, 600)][int]$ClientTimeoutSeconds = 240,
    [ValidateRange(60, 600)][int]$AdapterStartupTimeoutSeconds = 360,
    [string]$RmwImplementation = "rmw_fastrtps_cpp",
    [string]$DdsAddress = "127.0.0.1"
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
$rosLogRoot = Join-Path $WorkingRoot "ros-log"
$auth = Join-Path $WorkingRoot "operator-auth.json"
$stdout = Join-Path $WorkingRoot "runtime.stdout.log"
$stderr = Join-Path $WorkingRoot "runtime.stderr.log"
$kitStdout = Join-Path $WorkingRoot "isaac-adapter.stdout.log"
$kitStderr = Join-Path $WorkingRoot "isaac-adapter.stderr.log"
$clientStdout = Join-Path $WorkingRoot "acceptance-client.stdout.log"
$clientStderr = Join-Path $WorkingRoot "acceptance-client.stderr.log"
$fastDdsProfile = Join-Path $WorkingRoot "fastdds-udp-only.xml"
New-Item -ItemType Directory -Force -Path $WorkingRoot, $stateRoot, $rosLogRoot | Out-Null
$discoveryPort = 7400 + (250 * $RosDomainId) + 10
$fastDdsProfileContent = @'
<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>udp_transport</transport_id>
      <type>UDPv4</type>
      <maxInitialPeersRange>16</maxInitialPeersRange>
      <interfaceWhiteList>
        <address>__DDS_ADDRESS__</address>
      </interfaceWhiteList>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="cellforge_udp_only" is_default_profile="true">
    <rtps>
      <defaultUnicastLocatorList>
        <locator>
          <udpv4><address>__DDS_ADDRESS__</address></udpv4>
        </locator>
      </defaultUnicastLocatorList>
      <builtin>
        <metatrafficUnicastLocatorList>
          <locator>
            <udpv4><address>__DDS_ADDRESS__</address></udpv4>
          </locator>
        </metatrafficUnicastLocatorList>
        <initialPeersList>
          __CF_INITIAL_PEERS__
        </initialPeersList>
      </builtin>
      <userTransports>
        <transport_id>udp_transport</transport_id>
      </userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
'@
$peerLocators = (0..40 | Where-Object { $_ % 2 -eq 0 } | ForEach-Object {
    $port = $discoveryPort + $_
    "          <locator><udpv4><address>__DDS_ADDRESS__</address><port>$port</port></udpv4></locator>"
}) -join "`n"
$fastDdsProfileContent = $fastDdsProfileContent.Replace("          __CF_INITIAL_PEERS__", $peerLocators)
$fastDdsProfileContent = $fastDdsProfileContent.Replace("__DDS_ADDRESS__", $DdsAddress)
[System.IO.File]::WriteAllText($fastDdsProfile, $fastDdsProfileContent, [System.Text.UTF8Encoding]::new($false))

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
    $null = $start.Environment
    $childProcessEnvironment = $start.EnvironmentVariables
    $childProcessEnvironment.Clear()
    foreach ($name in @("APPDATA", "LOCALAPPDATA", "PATHEXT", "PROGRAMDATA", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")) {
        $value = [System.Environment]::GetEnvironmentVariable($name)
        if ($value) {
            $childProcessEnvironment.Add($name, $value)
        }
    }
    $childProcessEnvironment.Add("ROS_LOG_DIR", $rosLogRoot)
    $childProcessEnvironment.Add("Path", $toolPath)
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
    foreach ($processId in @($descendants + $RootId)) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

$fastDdsEnvironment = if ($RmwImplementation -eq "rmw_fastrtps_cpp") {
    " && set `"FASTDDS_DEFAULT_PROFILES_FILE=$fastDdsProfile`" && set `"FASTRTPS_DEFAULT_PROFILES_FILE=$fastDdsProfile`""
} else {
    ""
}
$cycloneDdsEnvironment = if ($RmwImplementation -eq "rmw_cyclonedds_cpp") {
    " && set `"CYCLONEDDS_URI=<CycloneDDS><Domain><General><Interfaces><NetworkInterface address='127.0.0.1' multicast='true'/></Interfaces><AllowMulticast>true</AllowMulticast></General><Tracing><Verbosity>config</Verbosity></Tracing></Domain></CycloneDDS>`""
} else {
    ""
}
$setup = "call $(Join-Path $InstallBase 'setup.bat') && set `"RMW_IMPLEMENTATION=$RmwImplementation`" && set `"ROS_DOMAIN_ID=$RosDomainId`"$fastDdsEnvironment$cycloneDdsEnvironment"
$pythonPath = "$InstallBase\Lib\site-packages;$Underlay\Lib\site-packages;$PixiPrefix\Lib\site-packages;$PixiPrefix\Library\lib\site-packages;$(Join-Path $IsaacSimRoot 'site')"
$isaac = "set `"OMNI_KIT_ACCEPT_EULA=YES`" && set `"PYTHONPATH=$pythonPath`" && set `"CELLFORGE_PYTHONPATH=$pythonPath`""
$adapter = "$setup && $isaac && set `"CELLFORGE_L2_SCENE=$BundleRoot\assets\scene.usda`" && set `"CELLFORGE_L2_SCENARIO=$scenario`" && set `"CELLFORGE_L2_SCENARIO_ROOT=$ProjectRoot`" && set `"CELLFORGE_L2_REPORT=$adapterReport`" && $IsaacSimRoot\kit\kit.exe $IsaacSimRoot\apps\isaacsim.exp.base.python.kit --no-window --exec $(Join-Path $repository 'scripts\start_isaac_l2_ros_adapter.py')"
$kitStart = New-CleanProcessStart "$adapter 1>>`"$kitStdout`" 2>>`"$kitStderr`""
$kitStart.CreateNoWindow = $true
$kit = [System.Diagnostics.Process]::Start($kitStart)

$launch = "$setup && $isaac && ros2 launch cellforge_bringup integrated_runtime.launch.py bundle_root:=$BundleRoot fidelity:=L2 local_state_root:=$stateRoot operator_auth:=$auth operator_port:=19080 l2_scenario:=$scenario l2_scenario_root:=$ProjectRoot l2_report:=$adapterReport l2_launch_adapter:=false"
$launchStart = New-CleanProcessStart "$launch 1>>`"$stdout`" 2>>`"$stderr`""
$launchStart.CreateNoWindow = $true
$runtime = [System.Diagnostics.Process]::Start($launchStart)
$clientProcess = $null
$clientOutTask = $null
$clientErrTask = $null
try {
    $adapterReadyDeadline = [DateTime]::UtcNow.AddSeconds($AdapterStartupTimeoutSeconds)
    $adapterReady = $false
    while ([DateTime]::UtcNow -lt $adapterReadyDeadline) {
        if ($runtime.HasExited -or $kit.HasExited) {
            throw "L2 runtime or Kit-hosted adapter exited before the adapter became ready."
        }
        if (Test-Path -LiteralPath $kitStdout) {
            $kitOutput = Get-Content -LiteralPath $kitStdout -Raw -ErrorAction SilentlyContinue
            if ($kitOutput -match "Isaac Sim L2 adapters are READY for scenario") {
                $adapterReady = $true
                break
            }
        }
        if (Test-Path -LiteralPath $rosLogRoot) {
            $adapterLog = Get-ChildItem -LiteralPath $rosLogRoot -File -ErrorAction SilentlyContinue |
                Select-String -Pattern "Isaac Sim L2 adapters are READY for scenario" -SimpleMatch -List |
                Select-Object -First 1
            if ($adapterLog) {
                $adapterReady = $true
                break
            }
        }
        Start-Sleep -Seconds 1
    }
    if (-not $adapterReady) {
        throw "Isaac Sim L2 adapter did not become ready within $AdapterStartupTimeoutSeconds seconds."
    }
    $scenarioArgument = if ($AcceptanceScenario) { " --scenario $AcceptanceScenario" } else { "" }
    $client = "$setup && python $(Join-Path $repository 'scripts\run_isaac_l2_runjob_acceptance.py') --project $ProjectRoot --report $report$scenarioArgument"
    $clientStart = New-CleanProcessStart "$client 1>>`"$clientStdout`" 2>>`"$clientStderr`""
    $clientProcess = [System.Diagnostics.Process]::Start($clientStart)
    $clientDeadline = [DateTime]::UtcNow.AddSeconds($ClientTimeoutSeconds)
    while (-not $clientProcess.HasExited -and [DateTime]::UtcNow -lt $clientDeadline) {
        Start-Sleep -Milliseconds 250
    }
    if (-not $clientProcess.HasExited) {
        Stop-ProcessTree $clientProcess.Id
        throw "RunJob acceptance client timed out after $ClientTimeoutSeconds seconds."
    }
    if ($clientProcess.ExitCode -ne 0) {
        throw "RunJob acceptance client failed with exit code $($clientProcess.ExitCode)."
    }
} finally {
    Stop-ProcessTree $runtime.Id
    Stop-ProcessTree $kit.Id
    $runtime.WaitForExit(10000) | Out-Null
    $kit.WaitForExit(10000) | Out-Null
}

if (-not (Test-Path -LiteralPath $report)) {
    throw "RunJob acceptance did not produce '$report'."
}
$document = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($document.scenario_count -lt 1 -or $document.submitted_action -ne "/cell/run_job") {
    throw "RunJob acceptance report is incomplete."
}
Write-Output "Task 027 Isaac L2 RunJob acceptance passed $($document.scenario_count) scenarios. Report: $report"
