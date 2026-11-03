param([switch]$Start)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.TetheringWiFiBand,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
function Wait-WinRtOperation($Operation, [Type]$ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(30000)) { throw 'Windows hotspot operation timed out' }
    return $task.Result
}
function Wait-WinRtAction($Action) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.FullName -eq 'Windows.Foundation.IAsyncAction'
    } | Select-Object -First 1
    if ($null -eq $method) { throw 'WinRT IAsyncAction adapter is unavailable' }
    $task = $method.Invoke($null, @($Action))
    if (-not $task.Wait(30000)) { throw 'Windows hotspot configuration timed out' }
    $task.GetAwaiter().GetResult()
}
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $profile) { throw 'No Internet connection profile available for mobile hotspot' }
$capability = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::GetTetheringCapabilityFromConnectionProfile($profile)
$manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$config = $manager.GetCurrentAccessPointConfiguration()
$report = [ordered]@{ capability = "$capability"; before_state = "$($manager.TetheringOperationalState)"; clients = $manager.ClientCount; band = "$($config.Band)"; started = $false }
if ($Start) {
    if ("$capability" -ne 'Enabled') { throw "Mobile hotspot unavailable: $capability" }
    if ("$($manager.TetheringOperationalState)" -eq 'Off') {
        $config.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz
        Wait-WinRtAction ($manager.ConfigureAccessPointAsync($config))
        $result = Wait-WinRtOperation ($manager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        $report.operation_status = "$($result.Status)"
        if ("$($result.Status)" -ne 'Success') { throw "Mobile hotspot could not start: $($result.Status)" }
        $report.started = $true
    } elseif ("$($manager.TetheringOperationalState)" -ne 'On') {
        throw 'Mobile hotspot is transitioning; try after it settles'
    }
}
$report.state = "$($manager.TetheringOperationalState)"
$report.band = "$($manager.GetCurrentAccessPointConfiguration().Band)"
$report | ConvertTo-Json -Compress
