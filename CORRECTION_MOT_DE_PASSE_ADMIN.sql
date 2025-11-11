\connect auth_db;

-- Update admin password to Test1234 (with correct hash)
UPDATE accounts 
SET password_hash = '$2b$12$ZgyVlYwrUwINKt/2ROWsl.W8wnA1rhPPZwIBfFEUTPsKEwVVJXq22',
    updated_at = NOW()
WHERE email = 'admin@test.com';

SELECT 'Admin password updated successfully!' as status;
SELECT email, role, is_verified FROM accounts WHERE email = 'admin@test.com';
