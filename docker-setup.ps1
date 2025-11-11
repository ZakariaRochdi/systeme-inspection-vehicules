# Docker Setup Script for Vehicle Inspection System

Write-Host "Vehicle Inspection System - Docker Setup" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Create .env file if it doesn't exist
if (!(Test-Path ".env")) {
    Write-Host "Creating .env file with defaults..." -ForegroundColor Yellow
    @"
# Database Configuration
DB_USER=postgres
DB_PASSWORD=azerty5027

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Service Ports
AUTH_SERVICE_PORT=8001
APPOINTMENT_SERVICE_PORT=8002
PAYMENT_SERVICE_PORT=8003
INSPECTION_SERVICE_PORT=8004
LOGGING_SERVICE_PORT=8005
NOTIFICATION_SERVICE_PORT=8006
FILE_SERVICE_PORT=8007
UI_SERVICE_PORT=3000

# Database Names
DB_NAME_AUTH=auth_db
DB_NAME_APPOINTMENTS=appointments_db
DB_NAME_PAYMENTS=payments_db
DB_NAME_INSPECTIONS=inspections_db
DB_NAME_LOGS=logs_db
DB_NAME_NOTIFICATIONS=notifications_db
DB_NAME_FILES=files_db

# Frontend URL
FRONTEND_URL=http://localhost:3000
"@ | Out-File -FilePath ".env" -Encoding UTF8
    Write-Host "✅ .env file created!" -ForegroundColor Green
} else {
    Write-Host "✅ .env file already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "🚀 Building Docker images..." -ForegroundColor Yellow
docker compose build

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Build successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🚀 Starting services..." -ForegroundColor Yellow
    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Services started successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "📊 Container Status:" -ForegroundColor Cyan
        docker compose ps
        Write-Host ""
        Write-Host "🌐 Access your application:" -ForegroundColor Cyan
        Write-Host "   Frontend:     http://localhost:3000" -ForegroundColor White
        Write-Host "   Auth API:     http://localhost:8001" -ForegroundColor White
        Write-Host "   Appointment:  http://localhost:8002" -ForegroundColor White
        Write-Host "   Payment:      http://localhost:8003" -ForegroundColor White
        Write-Host "   Inspection:   http://localhost:8004" -ForegroundColor White
        Write-Host "   Logging:      http://localhost:8005" -ForegroundColor White
        Write-Host "   Notification: http://localhost:8006" -ForegroundColor White
        Write-Host "   File Service: http://localhost:8007" -ForegroundColor White
        Write-Host ""
        Write-Host "📝 View logs: docker compose logs -f" -ForegroundColor Yellow
        Write-Host "🛑 Stop system: docker compose down" -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "❌ Failed to start services" -ForegroundColor Red
        Write-Host "Check logs: docker compose logs" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "❌ Build failed" -ForegroundColor Red
    Write-Host "Check the error messages above" -ForegroundColor Yellow
}
