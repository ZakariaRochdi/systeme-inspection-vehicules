-- Setup script for new databases

-- Create notifications database
CREATE DATABASE notifications_db;

-- Create files database
CREATE DATABASE files_db;

-- Verify databases
SELECT datname FROM pg_database WHERE datname IN ('notifications_db', 'files_db');

SELECT 'New databases created successfully!' as status;