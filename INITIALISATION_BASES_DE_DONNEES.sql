CREATE DATABASE auth_db;
CREATE DATABASE appointments_db;
CREATE DATABASE payments_db;
CREATE DATABASE inspections_db;
CREATE DATABASE logs_db;
CREATE DATABASE notifications_db;
CREATE DATABASE files_db;

\connect auth_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect appointments_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect payments_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect inspections_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect logs_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect notifications_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect files_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";