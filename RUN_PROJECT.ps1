# ============================================
# RUN PROJECT - Vehicle Inspection System
# Complete setup and launch script
# ============================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Vehicle Inspection System Setup" -ForegroundColor Cyan
Write-Host "  Centre de Controle Technique" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$baseDir = $PSScriptRoot
$psqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

# ============================================
# STEP 1: Check Prerequisites
# ============================================
Write-Host "[STEP 1/5] Checking prerequisites..." -ForegroundColor Yellow
Write-Host ""

# Check Python
$pythonVersion = python --version 2>&1
Write-Host "  Python: $pythonVersion" -ForegroundColor Green

# Check PostgreSQL
$pgService = Get-Service postgresql* -ErrorAction SilentlyContinue
if ($pgService) {
    Write-Host "  PostgreSQL: Running ($($pgService.DisplayName))" -ForegroundColor Green
} else {
    Write-Host "  PostgreSQL: NOT FOUND!" -ForegroundColor Red
    exit 1
}

Write-Host ""

# ============================================
# STEP 2: Get Database Password
# ============================================
Write-Host "[STEP 2/5] Database configuration..." -ForegroundColor Yellow
Write-Host ""

Write-Host "Enter PostgreSQL password (default: postgres): " -ForegroundColor Cyan -NoNewline
$dbPassword = Read-Host

if ([string]::IsNullOrWhiteSpace($dbPassword)) {
    $dbPassword = "postgres"
}

$env:PGPASSWORD = $dbPassword
Write-Host ""

# ============================================
# STEP 3: Create Databases
# ============================================
Write-Host "[STEP 3/5] Creating databases..." -ForegroundColor Yellow
Write-Host ""

$databases = @("auth_db", "appointments_db", "payments_db", "inspections_db", "logs_db", "notifications_db", "files_db")

foreach ($db in $databases) {
    Write-Host "  Creating $db..." -ForegroundColor Cyan -NoNewline
    
    $checkDb = & $psqlPath -U postgres -t -c "SELECT 1 FROM pg_database WHERE datname='$db'" 2>$null
    
    if ($checkDb -match "1") {
        Write-Host " [Already exists]" -ForegroundColor Yellow
    } else {
        & $psqlPath -U postgres -c "CREATE DATABASE $db" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host " Done" -ForegroundColor Green
        } else {
            Write-Host " Failed" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "  Databases ready!" -ForegroundColor Green
Write-Host ""

# ============================================
# STEP 4: Install Dependencies & Create .env
# ============================================
Write-Host "[STEP 4/5] Installing dependencies..." -ForegroundColor Yellow
Write-Host ""

$services = @("auth-service", "appointment-service", "payment-service", "inspection-service", "logging-service", "notification-service", "file-service")

$envContent = @"
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=$dbPassword
JWT_SECRET_KEY=vehicle-inspection-secret-key-2024-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
"@

$count = 1
foreach ($service in $services) {
    Write-Host "  [$count/7] $service..." -ForegroundColor Cyan
    
    $servicePath = Join-Path $baseDir "backend\$service"
    
    # Create .env file
    $envPath = Join-Path $servicePath ".env"
    $envContent | Out-File -FilePath $envPath -Encoding UTF8 -Force
    
    # Install dependencies
    $requirementsPath = Join-Path $servicePath "requirements.txt"
    if (Test-Path $requirementsPath) {
        Push-Location $servicePath
        pip install -r requirements.txt --quiet --disable-pip-version-check 2>&1 | Out-Null
        Pop-Location
    }
    
    $count++
}

Write-Host ""
Write-Host "  Dependencies installed!" -ForegroundColor Green
Write-Host ""

# ============================================
# STEP 5: Start All Services
# ============================================
Write-Host "[STEP 5/5] Starting all services..." -ForegroundColor Yellow
Write-Host ""

$serviceConfigs = @(
    @{Name="Auth Service"; Port=8001; Path="backend\auth-service"},
    @{Name="Appointment Service"; Port=8002; Path="backend\appointment-service"},
    @{Name="Payment Service"; Port=8003; Path="backend\payment-service"},
    @{Name="Inspection Service"; Port=8004; Path="backend\inspection-service"},
    @{Name="Logging Service"; Port=8005; Path="backend\logging-service"},
    @{Name="Notification Service"; Port=8006; Path="backend\notification-service"},
    @{Name="File Service"; Port=8007; Path="backend\file-service"}
)

# Start backend services
$count = 1
foreach ($svc in $serviceConfigs) {
    Write-Host "  [$count/8] Starting $($svc.Name) on port $($svc.Port)..." -ForegroundColor Cyan
    
    $svcPath = Join-Path $baseDir $svc.Path
    $title = "$($svc.Name) - Port $($svc.Port)"
    
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$svcPath'; `$host.UI.RawUI.WindowTitle='$title'; Write-Host '$title' -ForegroundColor Cyan; python main.py" -WindowStyle Normal
    
    Start-Sleep -Milliseconds 500
    $count++
}

# Start frontend
Write-Host "  [8/8] Starting Frontend on port 3000..." -ForegroundColor Cyan
$frontendPath = Join-Path $baseDir "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; `$host.UI.RawUI.WindowTitle='Frontend - Port 3000'; Write-Host 'Frontend Server - Port 3000' -ForegroundColor Magenta; python -m http.server 3000" -WindowStyle Normal

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ALL SERVICES STARTING!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Service URLs:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  FRONTEND:  http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  API Documentation:" -ForegroundColor White
Write-Host "    Auth:         http://localhost:8001/docs" -ForegroundColor Gray
Write-Host "    Appointment:  http://localhost:8002/docs" -ForegroundColor Gray
Write-Host "    Payment:      http://localhost:8003/docs" -ForegroundColor Gray
Write-Host "    Inspection:   http://localhost:8004/docs" -ForegroundColor Gray
Write-Host "    Logging:      http://localhost:8005/docs" -ForegroundColor Gray
Write-Host "    Notification: http://localhost:8006/docs" -ForegroundColor Gray
Write-Host "    File:         http://localhost:8007/docs" -ForegroundColor Gray
Write-Host ""

Write-Host "Waiting 15 seconds for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

Write-Host ""
Write-Host "Opening browser..." -ForegroundColor Cyan
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  SYSTEM STARTED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your redesigned French interface features:" -ForegroundColor Magenta
Write-Host "  - Complete French translation" -ForegroundColor White
Write-Host "  - Purple/Indigo color theme" -ForegroundColor White
Write-Host "  - Modern gradient buttons" -ForegroundColor White
Write-Host "  - Enhanced shadows and rounded corners" -ForegroundColor White
Write-Host ""
Write-Host "To stop: Close all PowerShell windows" -ForegroundColor Gray
Write-Host ""
