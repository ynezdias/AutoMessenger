# Starts the AutoMessenger local agent worker (leave this window open).
$ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}
Set-Location $PSScriptRoot
python -m server.main
