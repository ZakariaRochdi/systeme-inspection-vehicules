-- ================================================
-- CREATE TEST DATA FOR TECHNICIAN TESTING
-- ================================================
-- This script creates a complete test scenario:
-- 1. Customer account
-- 2. Technician account
-- 3. Confirmed appointment
-- ================================================

-- Connect to auth_db first
\c auth_db;

-- 1. Create test customer (if not exists)
INSERT INTO accounts (
    id, email, password_hash, role, is_verified,
    first_name, last_name, birthdate, country, session_timeout_minutes
) VALUES (
    '11111111-1111-1111-1111-111111111111'::uuid,
    'customer@test.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIl.YNlvuW', -- Password: Test1234
    'customer',
    true,
    'Test',
    'Customer',
    '1990-01-01',
    'France',
    '15'
) ON CONFLICT (email) DO NOTHING;

-- 2. Create test technician (if not exists)
INSERT INTO accounts (
    id, email, password_hash, role, is_verified,
    first_name, last_name, birthdate, country, session_timeout_minutes
) VALUES (
    '22222222-2222-2222-2222-222222222222'::uuid,
    'tech@test.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIl.YNlvuW', -- Password: Test1234
    'technician',
    true,
    'Test',
    'Technician',
    '1985-01-01',
    'France',
    '15'
) ON CONFLICT (email) DO NOTHING;

SELECT 'Test accounts created!' as status;
SELECT email, role FROM accounts WHERE email IN ('customer@test.com', 'tech@test.com');

-- Connect to appointments_db
\c appointments_db;

-- 3. Create test appointment (CONFIRMED status)
INSERT INTO appointments (
    id, user_id, vehicle_info, status,
    appointment_date, created_at
) VALUES (
    '33333333-3333-3333-3333-333333333333'::uuid,
    '11111111-1111-1111-1111-111111111111'::uuid, -- customer ID
    '{
        "type": "Car",
        "registration": "TEST-123-XY",
        "brand": "Toyota",
        "model": "Corolla"
    }'::jsonb,
    'confirmed', -- IMPORTANT: Must be confirmed
    NOW() + INTERVAL '1 day', -- Tomorrow
    NOW()
) ON CONFLICT (id) DO UPDATE SET status = 'confirmed';

SELECT 'Test appointment created!' as status;
SELECT id, vehicle_info->>'registration' as registration, status, appointment_date 
FROM appointments 
WHERE id = '33333333-3333-3333-3333-333333333333'::uuid;

-- 4. Verify the appointment is queryable
SELECT 
    '✓ Confirmed appointments count' as check_name,
    COUNT(*) as count
FROM appointments 
WHERE status = 'confirmed';

-- ================================================
-- VERIFICATION QUERIES
-- ================================================

-- Connect back to auth_db for summary
\c auth_db;

SELECT '========== TEST DATA SUMMARY ==========' as info;

SELECT 'Accounts Created:' as info;
SELECT email, role FROM accounts WHERE email LIKE '%test.com' ORDER BY role;

\c appointments_db;

SELECT 'Appointments Created:' as info;
SELECT 
    id::text as appointment_id,
    vehicle_info->>'registration' as registration,
    vehicle_info->>'brand' as brand,
    status,
    appointment_date
FROM appointments 
WHERE vehicle_info->>'registration' = 'TEST-123-XY';

SELECT '========================================' as info;
SELECT 'Test data created successfully!' as status;
SELECT 'Login credentials:' as info;
SELECT '  Customer: customer@test.com / Test1234' as credentials;
SELECT '  Technician: tech@test.com / Test1234' as credentials;
SELECT '' as blank;
SELECT 'The confirmed appointment should now be visible to the technician!' as note;
