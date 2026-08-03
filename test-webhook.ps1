# Sends a test merchant text to the AutoMessenger inbound webhook.
# Usage:  .\test-webhook.ps1
#         .\test-webhook.ps1 -Phone "+15550009999" -Message "tell me more"
# Reads the webhook secret from aws\deploy-params.txt (never prints it).
param(
    [string]$Phone = "+15550002222",
    [string]$Message = "Hi, I got your text about business funding. Tell me more",
    [string]$Name = "Sam"
)
$ErrorActionPreference = "Stop"

$paramsFile = Join-Path $PSScriptRoot "aws\deploy-params.txt"
$secret = (Get-Content $paramsFile | Select-Object -First 1) -replace '^WEBHOOK_SECRET\s*[=:]\s*', ''

$body = @{ phone = $Phone; message = $Message; merchantFirst = $Name } | ConvertTo-Json

Write-Host "POSTing as $Phone : `"$Message`"" -ForegroundColor Cyan
$resp = Invoke-RestMethod -Method Post `
    -Uri "https://01o1xporok.execute-api.us-east-2.amazonaws.com/inbound" `
    -Headers @{ "X-Auth-Token" = $secret } `
    -ContentType "application/json" `
    -Body $body
$resp
Write-Host "Now watch the agent pick it up:  Get-Content logs\worker.log -Tail 5 -Wait" -ForegroundColor Cyan
