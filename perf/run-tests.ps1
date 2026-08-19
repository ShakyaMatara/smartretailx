# SmartRetailX performance test runner
# Usage:  .\perf\run-tests.ps1
#
# Runs the four scenarios the assignment requires and writes CSV plus
# HTML reports into perf\results\.

$ErrorActionPreference = "Stop"
$results = "perf\results"
New-Item -ItemType Directory -Force -Path $results | Out-Null

Write-Host "`n=== 1/4  Baseline (health endpoint, 10 users) ===" -ForegroundColor Cyan
locust -f perf/locustfile.py --headless `
  --users 10 --spawn-rate 5 --run-time 1m `
  HealthUser `
  --csv "$results/01-baseline" --html "$results/01-baseline.html"

Write-Host "`n=== 2/4  Load test (mixed traffic, 100 users, 5 min) ===" -ForegroundColor Cyan
locust -f perf/locustfile.py --headless `
  --users 100 --spawn-rate 10 --run-time 5m `
  MixedUser `
  --csv "$results/02-load" --html "$results/02-load.html"

Write-Host "`n=== 3/4  API response test (browsing only, 50 users) ===" -ForegroundColor Cyan
locust -f perf/locustfile.py --headless `
  --users 50 --spawn-rate 10 --run-time 3m `
  BrowsingUser `
  --csv "$results/03-api" --html "$results/03-api.html"

Write-Host "`n=== 4/4  Stress test (ramp to 500 users) ===" -ForegroundColor Cyan
locust -f perf/locustfile.py --headless `
  --users 500 --spawn-rate 10 --run-time 6m `
  MixedUser `
  --csv "$results/04-stress" --html "$results/04-stress.html"

Write-Host "`nAll scenarios complete. Reports in $results" -ForegroundColor Green
