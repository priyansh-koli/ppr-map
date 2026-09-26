-- Runs once, when the database volume is first created. Migrations also create these
-- (IF NOT EXISTS), so this only saves a superuser step in local development.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

-- Disposable database for backend tests that need PostGIS (TEST_DATABASE_URL).
CREATE DATABASE pprmap_test;
\connect pprmap_test
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
