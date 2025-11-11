# Complete Vehicle Inspection System Startup Script
# Starts all backend services and frontend in separate windows

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Vehicle Inspection System" -ForegroundColor Cyan
Write-Host "Complete System Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Starting all services in separate windows..." -ForegroundColor Yellow
Write-Host ""

# Start Auth Service (Port 8001)
Write-Host "[1/6] Starting Auth Service (Port 8001)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\auth-service'; Write-Host 'Auth Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Appointment Service (Port 8002)
Write-Host "[2/6] Starting Appointment Service (Port 8002)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\appointment-service'; Write-Host 'Appointment Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Payment Service (Port 8003)
Write-Host "[3/6] Starting Payment Service (Port 8003)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\payment-service'; Write-Host 'Payment Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Inspection Service (Port 8004)
Write-Host "[4/6] Starting Inspection Service (Port 8004)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\inspection-service'; Write-Host 'Inspection Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Logging Service (Port 8005)
Write-Host "[5/8] Starting Logging Service (Port 8005)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\logging-service'; Write-Host 'Logging Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Notification Service (Port 8006)
Write-Host "[6/8] Starting Notification Service (Port 8006)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\notification-service'; Write-Host 'Notification Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start File Service (Port 8007)
Write-Host "[7/8] Starting File Service (Port 8007)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\backend\file-service'; Write-Host 'File Service Starting...' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Frontend (Port 3000)
Write-Host "[8/8] Starting Frontend (Port 3000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$baseDir\frontend'; Write-Host 'Frontend Starting...' -ForegroundColor Cyan; python -m http.server 3000" -WindowStyle Normal

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "All services are starting!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Please wait ~10 seconds for all services to initialize..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Service URLs:" -ForegroundColor Cyan
Write-Host "  - Auth Service:         http://localhost:8001" -ForegroundColor White
Write-Host "  - Appointment Service:  http://localhost:8002" -ForegroundColor White
Write-Host "  - Payment Service:      http://localhost:8003" -ForegroundColor White
Write-Host "  - Inspection Service:   http://localhost:8004" -ForegroundColor White
Write-Host "  - Logging Service:      http://localhost:8005" -ForegroundColor White
Write-Host "  - Notification Service: http://localhost:8006" -ForegroundColor White
Write-Host "  - File Service:         http://localhost:8007" -ForegroundColor White
Write-Host "  - Frontend:             http://localhost:3000" -ForegroundColor White
Write-Host ""
Write-Host "Opening browser in 5 seconds..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Open browser
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "System started successfully!" -ForegroundColor Green
Write-Host "Check the separate terminal windows for service logs." -ForegroundColor Gray
Write-Host ""