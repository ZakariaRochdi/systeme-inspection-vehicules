# 🔐 Docker Admin Account Setup

## ✅ Default Admin Credentials

After running the system with Docker, a default admin account is automatically created:

```
Email:    admin@test.com
Password: Test1234
Role:     Administrator
```

---

## 🚀 Quick Start

### 1. Start Docker Containers
```powershell
docker compose up -d
```

### 2. Wait for Services to Start (30-60 seconds)
```powershell
docker compose ps
```

All containers should show `(healthy)` status.

### 3. Create Admin Account
```powershell
Get-Content create-admin.sql | docker compose exec -T postgres psql -U postgres
```

You should see:
```
INSERT 0 1
Admin account created successfully!
admin@test.com | admin | System | Administrator
```

### 4. Access the Application
Open: **http://localhost:3000**

Login with:
- **Email:** `admin@test.com`
- **Password:** `Test1234`

---

## 📝 Important Notes

### **Why Can't Users Choose Their Role?**
For security reasons, the registration form only allows users to register as **"customer"** by default. The role selector is hidden in the UI.

Only administrators can:
- Change user roles (customer ↔ technician)
- Access the admin panel
- Manage all users, appointments, and inspections

### **Creating Additional Test Accounts**

You can register new accounts through the UI:
1. Go to http://localhost:3000
2. Click "Create Account"
3. Fill in the form (role will be "customer" by default)
4. Login as admin
5. Go to Admin Panel → Users
6. Click "Change Role" to promote users to technician

---

## 🔧 Manual Admin Creation (Alternative Method)

If you need to manually create an admin account:

```powershell
# Connect to database
docker compose exec postgres psql -U postgres -d auth_db

# Run this SQL
INSERT INTO accounts (
    id, email, password_hash, role, is_verified,
    first_name, last_name, birthdate, country, 
    session_timeout_minutes, created_at, updated_at
) VALUES (
    gen_random_uuid(),
    'youremail@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIl.YNlvuW',
    'admin',
    true,
    'Your',
    'Name',
    '1990-01-01',
    'Country',
    '60',
    NOW(),
    NOW()
);
```

**Note:** The password hash above is for `Test1234`

---

## 🔍 Verify Admin Account

```powershell
docker compose exec postgres psql -U postgres -d auth_db -c "SELECT email, role, first_name, last_name FROM accounts WHERE role='admin';"
```

---

## 🛠️ Troubleshooting

### **Admin account not working?**
1. Check if account exists:
   ```powershell
   docker compose exec postgres psql -U postgres -d auth_db -c "SELECT * FROM accounts WHERE email='admin@test.com';"
   ```

2. If not found, run the creation script again:
   ```powershell
   Get-Content create-admin.sql | docker compose exec -T postgres psql -U postgres
   ```

### **Can't login?**
- Make sure all containers are healthy: `docker compose ps`
- Check auth service logs: `docker compose logs auth-service`
- Verify database connection: `docker compose logs postgres`

### **Reset everything:**
```powershell
docker compose down -v
docker compose up -d
# Wait 60 seconds
Get-Content create-admin.sql | docker compose exec -T postgres psql -U postgres
```

---

## 📊 User Roles Explained

| Role | Permissions |
|------|-------------|
| **Customer** | Book appointments, view own inspections, make payments |
| **Technician** | View confirmed appointments, submit inspection results, upload photos |
| **Administrator** | Full access: manage users, view all data, change roles, system oversight |

---

## 🎯 Complete Workflow

1. **Admin** logs in → manages system
2. **Customer** registers → books appointment → pays
3. **Admin** confirms appointment
4. **Technician** sees confirmed appointment → performs inspection → submits results
5. **Customer** views inspection results → downloads PDF certificate

---

## ✅ Success Checklist

- [ ] Docker containers all healthy
- [ ] Admin account created (admin@test.com)
- [ ] Can login to http://localhost:3000
- [ ] Admin panel accessible
- [ ] Can create new customer accounts
- [ ] Can change user roles

---

## 📚 Related Files

- `create-admin.sql` - Admin creation script
- `init-databases.sql` - Database initialization
- `docker-compose.yml` - Docker configuration
- `CREATE_TEST_DATA.sql` - Create test customer & technician accounts

---

**Your admin account is ready to use!** 🎉

Login at: **http://localhost:3000**
