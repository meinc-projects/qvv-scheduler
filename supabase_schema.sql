-- =============================================================
-- Ekho VIN Verification Scheduling Portal — Supabase Schema
-- Run this entire file in the Supabase SQL Editor
-- =============================================================

-- -----------------------------------------------
-- Table: appointments
-- Stores all VIN verification appointment requests
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT now(),

    -- Customer info
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT NOT NULL,

    -- Location
    address         TEXT NOT NULL,
    city            TEXT NOT NULL,
    county          TEXT,
    region          TEXT,

    -- Vehicle
    vehicle_year    TEXT NOT NULL,
    vehicle_make    TEXT NOT NULL,
    vehicle_model   TEXT NOT NULL,

    -- Scheduling
    preferred_date  TEXT NOT NULL,              -- YYYY-MM-DD
    preferred_time  TEXT NOT NULL,              -- time slot label
    confirmed_date  TEXT,                       -- V2: after team confirms
    confirmed_time  TEXT,                       -- V2: after team confirms

    -- Routing
    territory_key   TEXT NOT NULL,              -- qvv, henry, michael, joy
    territory_label TEXT NOT NULL,              -- human-readable territory name
    route_method    TEXT NOT NULL,              -- "bookings" or "notify"
    status          TEXT DEFAULT 'pending',     -- pending/confirmed/completed/cancelled

    -- Geocoding
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,

    -- Multi-source tracking
    source          TEXT DEFAULT 'ekho',        -- ekho, website, zoho_form, etc.

    -- V2 fields (present but unused in V1)
    assigned_to     TEXT,                       -- team member assignment
    notes           TEXT,                       -- internal notes

    -- Notification tracking
    customer_notified BOOLEAN DEFAULT false,
    partner_notified  BOOLEAN DEFAULT false,
    teams_notified    BOOLEAN DEFAULT false
);

-- -----------------------------------------------
-- Table: partners
-- Stores partner verifier contact info
-- -----------------------------------------------
CREATE TABLE IF NOT EXISTS partners (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT now(),
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT NOT NULL,
    territory_key   TEXT UNIQUE NOT NULL,
    territory_label TEXT NOT NULL,
    cities_csv      TEXT NOT NULL,              -- comma-separated city list
    active          BOOLEAN DEFAULT true
);

-- -----------------------------------------------
-- Indexes for performance
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_appointments_created_at ON appointments (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments (status);
CREATE INDEX IF NOT EXISTS idx_appointments_territory ON appointments (territory_key);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments (preferred_date);
CREATE INDEX IF NOT EXISTS idx_appointments_city ON appointments (city);
CREATE INDEX IF NOT EXISTS idx_partners_territory ON partners (territory_key);

-- -----------------------------------------------
-- Row Level Security
-- Enable RLS and allow anon key full access (V1)
-- -----------------------------------------------
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE partners ENABLE ROW LEVEL SECURITY;

-- Appointments: anon can do everything
CREATE POLICY "anon_select_appointments" ON appointments FOR SELECT TO anon USING (true);
CREATE POLICY "anon_insert_appointments" ON appointments FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon_update_appointments" ON appointments FOR UPDATE TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_delete_appointments" ON appointments FOR DELETE TO anon USING (true);

-- Partners: anon can do everything
CREATE POLICY "anon_select_partners" ON partners FOR SELECT TO anon USING (true);
CREATE POLICY "anon_insert_partners" ON partners FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon_update_partners" ON partners FOR UPDATE TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_delete_partners" ON partners FOR DELETE TO anon USING (true);

-- -----------------------------------------------
-- Seed default partners
-- -----------------------------------------------
INSERT INTO partners (name, email, phone, territory_key, territory_label, cities_csv) VALUES
    ('Henry', '', '', 'henry', 'Los Angeles / South LA', 'Los Angeles,Long Beach,Inglewood,Compton,Torrance,Carson,Hawthorne,Downey,Norwalk,Whittier,South Gate,Lynwood,Paramount,Bellflower,Lakewood'),
    ('Michael', '', '', 'michael', 'San Fernando Valley', 'North Hollywood,Van Nuys,Burbank,Glendale,Pasadena,Sherman Oaks,Encino,Woodland Hills,Canoga Park,Reseda,Northridge,Panorama City,Sun Valley,Sylmar,Tarzana'),
    ('Joy', '', '', 'joy', 'San Diego County', 'San Diego,Chula Vista,Oceanside,Escondido,Carlsbad,El Cajon,Vista,San Marcos,Encinitas,National City,La Mesa,Santee,Poway,Imperial Beach,Coronado')
ON CONFLICT (territory_key) DO NOTHING;

-- -----------------------------------------------
-- V2 TABLES (commented out — uncomment when ready)
-- -----------------------------------------------

/*
-- Normalized city-to-territory mapping with day restrictions
CREATE TABLE IF NOT EXISTS territories (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    city            TEXT NOT NULL,
    county          TEXT,
    region          TEXT,
    territory_key   TEXT NOT NULL,
    territory_label TEXT NOT NULL,
    day_restrictions JSONB,  -- e.g. {"preferred_days": ["wednesday"], "avoid_days": ["friday"]}
    UNIQUE(city, territory_key)
);

-- Audit trail for all notifications sent
CREATE TABLE IF NOT EXISTS notification_log (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT now(),
    appointment_id  UUID REFERENCES appointments(id),
    channel         TEXT NOT NULL,      -- email, sms, teams
    recipient       TEXT NOT NULL,      -- email address or phone number
    recipient_type  TEXT NOT NULL,      -- customer, partner, team
    status          TEXT NOT NULL,      -- sent, failed
    error_message   TEXT,
    payload_summary TEXT
);
*/
