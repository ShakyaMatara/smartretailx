# Scalability comparison: identical load against 1 instance vs 3 instances
# of the order service. This IS the scalability analysis for Task 6.
#
# Uses the ScalingUser profile, which shares one pre-issued token so that
# Argon2id password hashing in the User Service does not dominate the
# measurement and relocate the bottleneck away from the component under test.
#
# Usage:  .\perf\run-scaling.ps1

$ErrorActionPreference = "Stop"
$results = "perf\results"
New-Item -ItemType Directory -Force -Path $results | Out-Null

function Wait-Healthy {
    param([int]$Seconds = 90)
    Write-Host "Waiting for all containers to report healthy..." -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $status = docker compose ps --format "{{.Service}} {{.Status}}"
        if (($status -match "starting").Count -eq 0 -and ($status -match "unhealthy").Count -eq 0) {
            Write-Host "All healthy." -ForegroundColor DarkGray
            Start-Sleep -Seconds 5
            return
        }
        Start-Sleep -Seconds 5
    }
    Write-Host "Timed out waiting for healthy containers - check 'docker compose ps'" -ForegroundColor Yellow
}

Write-Host "`n--- Resetting stack to a clean state ---" -ForegroundColor Cyan
docker compose down | Out-Null
docker compose up -d | Out-Null
Wait-Healthy

Write-Host "`n=== Run A: order-service x1, 100 users, 4 min ===" -ForegroundColor Cyan
docker compose ps order-service
locust -f perf/locustfile.py --headless `
  --users 100 --spawn-rate 10 --run-time 4m `
  ScalingUser `
  --csv "$results/05-scale-1x" --html "$results/05-scale-1x.html"

Write-Host "`n--- Scaling order-service to 3 instances ---" -ForegroundColor Cyan
docker compose up -d --scale order-service=3 order-service
Wait-Healthy
docker compose ps order-service

Write-Host "`n=== Run B: order-service x3, 100 users, 4 min ===" -ForegroundColor Cyan
locust -f perf/locustfile.py --headless `
  --users 100 --spawn-rate 10 --run-time 4m `
  ScalingUser `
  --csv "$results/06-scale-3x" --html "$results/06-scale-3x.html"

Write-Host "`n--- Returning to 1 instance ---" -ForegroundColor Cyan
docker compose up -d --scale order-service=1 order-service

Write-Host "`nComplete. Now run:  python perf\compare.py" -ForegroundColor Green
