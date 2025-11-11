# 🐳 Docker Deployment Guide

## ✅ Complete Dockerized Vehicle Inspection System

This system is fully containerized with Docker and Docker Compose for easy deployment.

---

## 📋 **Prerequisites**

- ✅ **Docker** (version 20.10+)
- ✅ **Docker Compose** (version 2.0+)

**Install Docker:**
- Windows/Mac: https://www.docker.com/products/docker-desktop
- Linux: `curl -fsSL https://get.docker.com | sh`

---

## 🚀 **Quick Start**

### **1. Clone Repository**
```bash
git clone https://github.com/Mohamed5027/vehicle-inspection-system.git
cd vehicle-inspection-system
```

### **2. Configure Environment**
```bash
cp .env.example .env
# Edit .env file with your settings (optional, has good defaults)
```

### **3. Build and Start**
```bash
docker-compose up --build -d
```

### **4. Access Application**
- **Frontend:** http://localhost:3000
- **Auth Service:** http://localhost:8001
- **Appointment Service:** http://localhost:8002
- **Payment Service:** http://localhost:8003
- **Inspection Service:** http://localhost:8004
- **Logging Service:** http://localhost:8005
- **Notification Service:** http://localhost:8006
- **File Service:** http://localhost:8007

### **5. Stop System**
```bash
docker-compose down
```

---

## 🏗️ **System Architecture**

### **Containers:**
- `vehicle-inspection-postgres` - PostgreSQL 15 with 7 databases
- `vehicle-inspection-auth` - Authentication service
- `vehicle-inspection-appointment` - Appointment management
- `vehicle-inspection-payment` - Payment processing
- `vehicle-inspection-inspection` - Inspection results
- `vehicle-inspection-logging` - Centralized logging
- `vehicle-inspection-notification` - Notifications
- `vehicle-inspection-file` - File uploads
- `vehicle-inspection-frontend` - Nginx frontend

### **Volumes:**
- `postgres_data` - Database persistence
- `file_uploads` - Uploaded files

### **Network:**
- `inspection-network` - Internal bridge network

---

## 🔧 **Configuration**

### **Environment Variables (.env)**

```bash
# Database
DB_USER=admin
DB_PASSWORD=your_secure_password_here

# JWT
JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Services Ports (optional, defaults shown)
AUTH_SERVICE_PORT=8001
APPOINTMENT_SERVICE_PORT=8002
PAYMENT_SERVICE_PORT=8003
INSPECTION_SERVICE_PORT=8004
LOGGING_SERVICE_PORT=8005
NOTIFICATION_SERVICE_PORT=8006
FILE_SERVICE_PORT=8007
UI_SERVICE_PORT=3000

# Database Names (optional, defaults shown)
DB_NAME_AUTH=auth_db
DB_NAME_APPOINTMENTS=appointments_db
DB_NAME_PAYMENTS=payments_db
DB_NAME_INSPECTIONS=inspections_db
DB_NAME_LOGS=logs_db
DB_NAME_NOTIFICATIONS=notifications_db
DB_NAME_FILES=files_db
```

---

## 📊 **Docker Commands**

### **Start Services**
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d auth-service

# Start with logs
docker-compose up
```

### **View Logs**
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f auth-service

# Last 100 lines
docker-compose logs --tail=100
```

### **Check Status**
```bash
# List running containers
docker-compose ps

# Check health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### **Stop Services**
```bash
# Stop all
docker-compose down

# Stop and remove volumes (⚠️ deletes data!)
docker-compose down -v

# Stop specific service
docker-compose stop auth-service
```

### **Restart Services**
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart auth-service
```

### **Rebuild**
```bash
# Rebuild all services
docker-compose up --build -d

# Rebuild specific service
docker-compose up --build -d auth-service
```

### **Execute Commands in Container**
```bash
# Access bash in container
docker-compose exec auth-service /bin/sh

# Run Python command
docker-compose exec auth-service python -c "print('Hello')"

# Check database
docker-compose exec postgres psql -U admin -d auth_db -c "SELECT * FROM users;"
```

---

## 🗄️ **Database Management**

### **Access PostgreSQL**
```bash
docker-compose exec postgres psql -U admin
```

### **List Databases**
```sql
\l
```

### **Connect to Database**
```sql
\c auth_db
```

### **List Tables**
```sql
\dt
```

### **Backup Database**
```bash
docker-compose exec postgres pg_dumpall -U admin > backup.sql
```

### **Restore Database**
```bash
docker-compose exec -T postgres psql -U admin < backup.sql
```

---

## 🔍 **Troubleshooting**

### **Service Won't Start**
```bash
# Check logs
docker-compose logs service-name

# Check if port is already in use
netstat -ano | findstr :8001  # Windows
lsof -i :8001  # Linux/Mac
```

### **Database Connection Issues**
```bash
# Check postgres is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres pg_isready -U admin

# Check database exists
docker-compose exec postgres psql -U admin -l
```

### **Reset Everything**
```bash
# Stop and remove everything
docker-compose down -v

# Remove all images
docker-compose down --rmi all

# Start fresh
docker-compose up --build -d
```

### **Permission Issues**
```bash
# Fix volume permissions (Linux)
sudo chown -R $USER:$USER postgres_data file_uploads
```

---

## 📈 **Monitoring**

### **Resource Usage**
```bash
# Check CPU/Memory
docker stats

# Specific container
docker stats vehicle-inspection-auth
```

### **Health Checks**
```bash
# Check all health statuses
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### **Disk Usage**
```bash
# Docker system info
docker system df

# Clean up unused data
docker system prune -a
```

---

## 🔒 **Security Best Practices**

1. ✅ **Change default passwords** in `.env`
2. ✅ **Use strong JWT secret** (min 32 characters)
3. ✅ **Don't commit `.env`** file to git
4. ✅ **Use Docker secrets** for production
5. ✅ **Regular backups** of volumes
6. ✅ **Update images** regularly

---

## 🚀 **Production Deployment**

### **1. Use Docker Secrets**
```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
```

### **2. Add Reverse Proxy (nginx)**
```nginx
upstream backend {
    server localhost:8001;
    server localhost:8002;
    # ... other services
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://backend;
    }
}
```

### **3. Enable SSL/TLS**
```bash
# Using Let's Encrypt
docker run -it --rm -p 443:443 -p 80:80 \
  -v "/etc/letsencrypt:/etc/letsencrypt" \
  certbot/certbot certonly
```

### **4. Set Resource Limits**
```yaml
services:
  auth-service:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          memory: 256M
```

---

## 📦 **Image Sizes**

Estimated sizes:
- PostgreSQL: ~80MB
- Python services (each): ~150MB
- Nginx frontend: ~25MB
- **Total:** ~1.1GB

---

## 🧪 **Testing**

### **Test All Services**
```bash
# Check health endpoints
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
curl http://localhost:8006/health
curl http://localhost:8007/health
```

### **Test Frontend**
```bash
curl http://localhost:3000
```

### **Test Database**
```bash
docker-compose exec postgres psql -U admin -c "SELECT version();"
```

---

## 📝 **Development Workflow**

### **Hot Reload (Development)**
Mount source code as volumes:
```yaml
volumes:
  - ./backend/auth-service:/app
```

### **Run Tests**
```bash
docker-compose exec auth-service pytest
```

### **Install New Dependencies**
```bash
# Update requirements.txt, then rebuild
docker-compose up --build -d auth-service
```

---

## 🎯 **Default Credentials**

### **Admin Account**
- Email: `admin@test.com`
- Password: `Test1234`

### **Test Customer**
- Email: `customer@test.com`
- Password: `Test1234`

### **Test Technician**
- Email: `tech@test.com`
- Password: `Test1234`

---

## 📊 **Performance Tuning**

### **PostgreSQL**
Edit `docker-compose.yml`:
```yaml
POSTGRES_INITDB_ARGS: "-c shared_buffers=512MB -c max_connections=300"
```

### **Service Replicas** (Docker Swarm)
```yaml
deploy:
  replicas: 3
  update_config:
    parallelism: 1
    delay: 10s
```

---

## ✅ **Verification Checklist**

After deployment:
- [ ] All 9 containers running
- [ ] All health checks passing
- [ ] Frontend accessible
- [ ] Can login successfully
- [ ] Can create appointment
- [ ] Can make payment
- [ ] Can submit inspection
- [ ] Notifications working
- [ ] File upload working
- [ ] Database persisting data

---

## 🐛 **Common Issues**

### **Port Already in Use**
Change port in `.env`:
```bash
AUTH_SERVICE_PORT=9001
```

### **Out of Memory**
Increase Docker memory:
- Docker Desktop → Settings → Resources → Memory → 4GB+

### **Slow Build**
Use BuildKit:
```bash
DOCKER_BUILDKIT=1 docker-compose build
```

### **Network Issues**
Recreate network:
```bash
docker network rm inspection-network
docker-compose up -d
```

---

## 📚 **Additional Resources**

- Docker Docs: https://docs.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- FastAPI: https://fastapi.tiangolo.com/
- PostgreSQL: https://www.postgresql.org/docs/

---

## 🎉 **Success!**

Your Vehicle Inspection System is now running in Docker!

**Access it:** http://localhost:3000

**Happy inspecting!** 🚗✅
