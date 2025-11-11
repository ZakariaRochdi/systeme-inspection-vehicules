-- Create notifications database
CREATE DATABASE notifications_db;

-- Connect to it
\c notifications_db;

-- The table will be created automatically by SQLAlchemy
-- But we can verify the connection works
SELECT 'Notifications database ready!' as status;