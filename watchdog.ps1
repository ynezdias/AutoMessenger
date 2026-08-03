# Ensures the worker and the local web chat are running. Launched at logon
# (Startup folder) and every 15 minutes by the AutoMessengerWatchdog task.
# Both services append to logs\ so crashes are visible after the fact.
$root = $PSScriptRoot
New-Item -ItemType Directory -Force "$root\logs" | Out-Null

$procs = Get-CimInstance Win32_Process
if (-not ($procs | Where-Object { $_.CommandLine -match "server\.main" })) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList `
        '-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',"$root\run.ps1"
}
if (-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process cmd -WindowStyle Hidden -ArgumentList `
        '/c', "cd /d `"$root`" && python -m server.webchat >> logs\webchat.log 2>&1"
}
