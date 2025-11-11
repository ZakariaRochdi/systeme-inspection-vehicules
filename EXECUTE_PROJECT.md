# 🚀 HOW TO RUN YOUR COMPLETE PROJECT

## Quick Overview
Your project has:
- ✅ **Frontend**: Already redesigned with French + Purple theme
- ✅ **7 Backend Services**: FastAPI microservices
- ✅ **PostgreSQL**: Already installed and running
- ✅ **Python 3.13.5**: Ready to go

---

## 🎯 FASTEST WAY TO RUN (3 Steps)

### Step 1: Create Databases (One-Time Setup)

Open PowerShell and run:

```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main"

# Option A: Run the script (will prompt for password)
powershell -ExecutionPolicy Bypass -File ".\RUN_PROJECT.ps1"
```

**OR manually create databases:**

```powershell
# Open PostgreSQL command prompt
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres

# When prompted, enter your PostgreSQL password
# Then paste these commands:

CREATE DATABASE auth_db;
CREATE DATABASE appointments_db;
CREATE DATABASE payments_db;
CREATE DATABASE inspections_db;
CREATE DATABASE logs_db;
CREATE DATABASE notifications_db;
CREATE DATABASE files_db;

# Verify databases
\l

# Exit
\q
```

### Step 2: Install Dependencies (One-Time Setup)

```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main"

# Install for all 7 services
cd backend\auth-service
pip install fastapi uvicorn sqlalchemy asyncpg pyjwt python-multipart bcrypt

cd ..\appointment-service
pip install fastapi uvicorn sqlalchemy asyncpg python-multipart reportlab

cd ..\payment-service
pip install fastapi uvicorn sqlalchemy asyncpg python-multipart

cd ..\inspection-service
pip install fastapi uvicorn sqlalchemy asyncpg python-multipart

cd ..\logging-service
pip install fastapi uvicorn sqlalchemy asyncpg python-multipart

cd ..\notification-service
pip install fastapi uvicorn sqlalchemy asyncpg python-multipart

cd ..\file-service
pip install fastapi uvicorn sqlalchemy asyncpg python-multipart aiofiles

cd ..\..
```

### Step 3: Start All Services

**Open 8 separate PowerShell windows** and run ONE command in each:

#### Window 1 - Auth Service (Port 8001)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\auth-service"
python main.py
```

#### Window 2 - Appointment Service (Port 8002)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\appointment-service"
python main.py
```

#### Window 3 - Payment Service (Port 8003)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\payment-service"
python main.py
```

#### Window 4 - Inspection Service (Port 8004)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\inspection-service"
python main.py
```

#### Window 5 - Logging Service (Port 8005)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\logging-service"
python main.py
```

#### Window 6 - Notification Service (Port 8006)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\notification-service"
python main.py
```

#### Window 7 - File Service (Port 8007)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\backend\file-service"
python main.py
```

#### Window 8 - Frontend (Port 3000)
```powershell
cd "c:\Users\DELL PC\Desktop\vehicle-inspection-system-main\frontend"
python -m http.server 3000
```

---

## 🌐 Access Your Application

After all services start (wait ~10 seconds), open your browser:

### Main Application
**http://localhost:3000**

You'll see your redesigned interface with:
- 🇫🇷 Complete French translation
- 🟣 Purple/Indigo color theme
- ✨ Modern gradient buttons
- 🎨 Enhanced shadows and rounded corners

### API Documentation (Swagger UI)
- Auth: http://localhost:8001/docs
- Appointment: http://localhost:8002/docs
- Payment: http://localhost:8003/docs
- Inspection: http://localhost:8004/docs
- Logging: http://localhost:8005/docs
- Notification: http://localhost:8006/docs
- File: http://localhost:8007/docs

---

## 🧪 Test the Application

### 1. Create an Account
1. Go to http://localhost:3000
2. Click **"Créer un Compte"**
3. Fill in:
   - Email: test@example.com
   - Password: password123
4. Check the reCAPTCHA box
5. Click **"S'Inscrire"**

### 2. Login
1. Click **"Retour à la Connexion"**
2. Enter credentials
3. Click **"Se Connecter"**

### 3. Book an Appointment
1. Navigate to **"📅 Rendez-vous"**
2. Fill vehicle details:
   - Type: Voiture
   - Registration: AB-123-CD
   - Brand: Renault
   - Model: Clio
3. Select date/time
4. Click **"Réserver le Rendez-vous"**

### 4. View Results
Navigate to **"📋 Mes Résultats"** to see inspection status

---

## 🔧 Troubleshooting

### Problem: Database connection fails
**Solution:** Create .env files in each service folder:

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_postgres_password
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

Create this file in:
- backend/auth-service/.env
- backend/appointment-service/.env
- backend/payment-service/.env
- backend/inspection-service/.env
- backend/logging-service/.env
- backend/notification-service/.env
- backend/file-service/.env

### Problem: Port already in use
**Solution:** Find and kill the process:

```powershell
# Find process using port 8001 (example)
netstat -ano | findstr :8001

# Kill the process (replace PID)
taskkill /PID <process_id> /F
```

### Problem: Module not found
**Solution:** Install missing package:

```powershell
pip install <package_name>
```

### Problem: PostgreSQL not running
**Solution:** Start the service:

```powershell
Start-Service postgresql-x64-18
```

---

## 🛑 Stop All Services

Simply close all 8 PowerShell windows.

Or kill all Python processes:
```powershell
Get-Process python | Stop-Process -Force
```

---

## 📊 System Architecture

```
┌─────────────────────────────────────────┐
│    Frontend (Port 3000)                 │
│    French + Purple Theme                │
└─────────────────────────────────────────┘
                  │
    ┌─────────────┴─────────────┐
    │                           │
┌───▼────┐  ┌────────┐  ┌──────▼───┐
│ Auth   │  │ Appt   │  │ Payment  │
│ :8001  │  │ :8002  │  │ :8003    │
└────────┘  └────────┘  └──────────┘
    │           │            │
┌───▼────┐  ┌──▼─────┐  ┌──▼──────┐
│Inspect │  │ Logging│  │ Notify  │
│ :8004  │  │ :8005  │  │ :8006   │
└────────┘  └────────┘  └─────────┘
                │
           ┌────▼────┐
           │  File   │
           │  :8007  │
           └─────────┘
                │
    ┌───────────┴───────────┐
    │   PostgreSQL (7 DBs)  │
    │   - auth_db           │
    │   - appointments_db   │
    │   - payments_db       │
    │   - inspections_db    │
    │   - logs_db           │
    │   - notifications_db  │
    │   - files_db          │
    └───────────────────────┘
```

---

## ✅ Success Checklist

- [ ] PostgreSQL service running
- [ ] 7 databases created
- [ ] Python dependencies installed
- [ ] .env files configured
- [ ] 7 backend services running (8001-8007)
- [ ] Frontend running (3000)
- [ ] Can access http://localhost:3000
- [ ] Can create account and login
- [ ] All features working

---

## 🎨 Your Redesigned Features

### Color Changes
- **Old**: Teal (#1abc9c, #16a085)
- **New**: Purple/Indigo (#6366F1, #8B5CF6, #764ba2)

### Language
- **Old**: English
- **New**: Complete French translation

### Design
- Modern gradient buttons
- Enhanced shadows (0 8px 30px)
- Rounded corners (20px cards, 12px inputs)
- Hover animations
- Better typography (Inter font)

---

## 📞 Quick Commands Reference

```powershell
# Check if services are running
netstat -ano | findstr "8001 8002 8003 8004 8005 8006 8007 3000"

# Check PostgreSQL
Get-Service postgresql*

# View Python processes
Get-Process python

# Kill all Python processes
Get-Process python | Stop-Process -Force

# Test a service
curl http://localhost:8001/docs
```

---

**🎉 Enjoy your redesigned Vehicle Inspection System!**
