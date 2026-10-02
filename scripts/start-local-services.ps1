# Start native local services; no Docker runtime, deployment or provider calls.
$ErrorActionPreference = "Stop"
$localRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $localRoot "data/local-service-logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$uvPath = (Get-Command uv).Source
$nodePath = (Get-Command node).Source
$services = @(
    @{ Name="api"; Port=8002; Exe=$uvPath; Args=@("run","--no-sync","uvicorn","voice_api.main:app","--host","127.0.0.1","--port","8002","--no-access-log"); Dir=$localRoot },
    @{ Name="runtime"; Port=8001; Exe=$uvPath; Args=@("run","--no-sync","uvicorn","voice_runner.main:app","--host","127.0.0.1","--port","8001","--no-access-log"); Dir=$localRoot },
    @{ Name="dashboard"; Port=5174; Exe=$nodePath; Args=@("node_modules/vite/bin/vite.js","--configLoader","runner","--host","127.0.0.1","--port","5174","--strictPort"); Dir=(Join-Path $localRoot "apps/dashboard") }
)
foreach ($service in $services) {
    $listener = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Output "$($service.Name): port $($service.Port) is already listening; left untouched"
        continue
    }
    $process = Start-Process -FilePath $service.Exe -ArgumentList $service.Args -WorkingDirectory $service.Dir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot "$($service.Name).out.log") -RedirectStandardError (Join-Path $logRoot "$($service.Name).err.log") -PassThru
    Write-Output "$($service.Name): launched locally on port $($service.Port), launcher PID $($process.Id)"
}
Write-Output "Dashboard: http://localhost:5174 ; API: http://127.0.0.1:8002 ; runtime: http://127.0.0.1:8001"
Write-Output "Startup logs: $logRoot"
