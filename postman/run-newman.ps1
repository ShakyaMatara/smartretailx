# Run the SmartRetailX API test collection with Newman.
#
# Prerequisites (one-time):
#   npm install -g newman newman-reporter-htmlextra
#
# Usage:  .\postman\run-newman.ps1

$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path "postman\results" | Out-Null

# Arguments are built as an array and splatted. PowerShell passes each
# element as a discrete argument, which avoids the comma-separated
# reporter list reaching Newman as a single quoted string.
$newmanArgs = @(
    "run"
    "postman/SmartRetailX.postman_collection.json"
    "-e"
    "postman/SmartRetailX.postman_environment.json"
    "--reporters"
    "cli,json,htmlextra"
    "--reporter-json-export"
    "postman/results/newman-report.json"
    "--reporter-htmlextra-export"
    "postman/results/newman-report.html"
    "--reporter-htmlextra-title"
    "SmartRetailX API Test Report"
)

newman @newmanArgs
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "All assertions passed." -ForegroundColor Green
} else {
    Write-Host "Some assertions failed - see the summary above." -ForegroundColor Yellow
}
Write-Host "HTML report: postman\results\newman-report.html" -ForegroundColor Cyan
