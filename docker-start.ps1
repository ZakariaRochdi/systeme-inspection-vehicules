# Vehicle Inspection System - Docker Quick Start

Write-Host "Vehicle Inspection System - Docker Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Create .env if not exists
if (!(Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    "DB_USER=postgres`nDB_PASSWORD=azerty5027`nJWT_SECRET_KEY=your-secret-key-change-in-prod" | Out-File .env -Encoding ASCII
    Write-Host "OK: .env created" -ForegroundColor Green
}

Write-Host "`nBuilding Docker images..." -ForegroundColor Yellow
docker compose build

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Build complete" -ForegroundColor Green
    Write-Host "`nStarting services..." -ForegroundColor Yellow
    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: Services started!" -ForegroundColor Green
        Write-Host "`nContainer Status:" -ForegroundColor Cyan
        docker compose ps
        Write-Host "`nAccess:" -ForegroundColor Cyan
        Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
        Write-Host "`nCommands:" -ForegroundColor Yellow
        Write-Host "  View logs: docker compose logs -f"
        Write-Host "  Stop: docker compose down"
    }
}
