# Runs the AutoMessenger worker unattended: starts Ollama if needed and
# restarts the worker automatically if it ever exits. Logs to logs\worker.log.
$root = $PSScriptRoot
$ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
Set-Location $root

while ($true) {
    # Probe the API, not the process: a hung Ollama keeps a live process
    # with a dead API and must be killed and restarted.
    $apiOk = $false
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5
        $apiOk = $true
    } catch {}
    if (-not $apiOk) {
        Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 2
        Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
    Add-Content "$root\logs\worker.log" "=== worker starting $(Get-Date) ===" -Encoding utf8
    cmd /c "python -m server.main >> ""$root\logs\worker.log"" 2>&1"
    Add-Content "$root\logs\worker.log" "=== worker exited $(Get-Date), restarting in 10s ===" -Encoding utf8
    Start-Sleep -Seconds 10
}
