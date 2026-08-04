# Ensures Ollama, the worker, and the local web chat are running. Launched at
# logon (Startup folder) and every 15 minutes by the AutoMessengerWatchdog task.
# Both services append to logs\ so crashes are visible after the fact.
$root = $PSScriptRoot
New-Item -ItemType Directory -Force "$root\logs" | Out-Null

# Probe the Ollama API, not the process: a hung Ollama keeps a live process
# with a dead API (bit us on 8/3, two hours of silence) and must be restarted.
$apiOk = $false
try {
    $null = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5
    $apiOk = $true
} catch {}
if (-not $apiOk) {
    Add-Content "$root\logs\worker.log" "=== watchdog: ollama api dead, restarting it $(Get-Date) ===" -Encoding utf8
    Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Start-Process -FilePath "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
}

$procs = Get-CimInstance Win32_Process
if (-not ($procs | Where-Object { $_.CommandLine -match "server\.main" })) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList `
        '-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',"$root\run.ps1"
}
if (-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process cmd -WindowStyle Hidden -ArgumentList `
        '/c', "cd /d `"$root`" && python -m server.webchat >> logs\webchat.log 2>&1"
}
