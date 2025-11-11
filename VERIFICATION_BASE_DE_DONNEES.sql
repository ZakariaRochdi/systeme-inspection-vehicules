-- ================================================
-- DATABASE VERIFICATION SCRIPT
-- Check what data actually exists
-- ================================================

-- 1. Check Accounts
\c auth_db;

SELECT 
    '========== ACCOUNTS ==========' as info;

SELECT 
    email,
    role,
    created_at
FROM accounts
ORDER BY role, created_at DESC;

SELECT 
    role,
    COUNT(*) as count
FROM accounts
GROUP BY role;

-- 2. Check Appointments
\c appointments_db;

SELECT 
    '========== APPOINTMENTS ==========' as info;

SELECT 
    id::text as appointment_id,
    vehicle_info->>'registration' as registration,
    vehicle_info->>'brand' as brand,
    vehicle_info->>'model' as model,
    status,
    appointment_date,
    created_at
FROM appointments
ORDER BY created_at DESC
LIMIT 20;

SELECT 
    status,
    COUNT(*) as count
FROM appointments
GROUP BY status;

-- 3. Check Inspections
\c inspections_db;

SELECT 
    '========== INSPECTIONS ==========' as info;

SELECT 
    id::text as inspection_id,
    appointment_id::text,
    final_status,
    created_at
FROM inspections
ORDER BY created_at DESC
LIMIT 20;

SELECT 
    final_status,
    COUNT(*) as count
FROM inspections
GROUP BY final_status;

-- 4. Summary
SELECT 
    '========== SUMMARY ==========' as info;

\c appointments_db;
SELECT 'Total Appointments: ' || COUNT(*)::text as summary FROM appointments;
SELECT 'Pending Appointments: ' || COUNT(*)::text as summary FROM appointments WHERE status = 'pending';
SELECT 'Confirmed Appointments: ' || COUNT(*)::text as summary FROM appointments WHERE status = 'confirmed';

\c inspections_db;
SELECT 'Total Inspections: ' || COUNT(*)::text as summary FROM inspections;
SELECT 'Not Checked: ' || COUNT(*)::text as summary FROM inspections WHERE final_status = 'not_checked';

-- 5. Check if appointments have vehicle_info properly formatted
\c appointments_db;
SELECT 
    '========== VEHICLE INFO CHECK ==========' as info;

SELECT 
    id::text,
    vehicle_info,
    vehicle_info ? 'registration' as has_registration,
    vehicle_info ? 'brand' as has_brand,
    vehicle_info ? 'model' as has_model,
    vehicle_info ? 'type' as has_type
FROM appointments
LIMIT 5;
