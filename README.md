# Ekho VIN Verification Scheduling Portal

Streamlit web app for scheduling VIN verification appointments across Southern California. Leads route to Quick VIN Verification (QVV) or partner verifiers based on the customer's city.

**Live App:** [schedule.vinverifications.com](https://schedule.vinverifications.com/) — self-hosted on the QAT Windows VPS since 2026-09-16 (always on, never sleeps). Alias: `schedule.quickautotags.com`.

> The old Streamlit Community Cloud URL (`qvv-scheduler.streamlit.app`) went to sleep after 12 h without visitors and showed customers a "Zzzz" page. It is retired — do not share it.

## What It Does

- **Customer Form** (root URL): Customers type their address, enter vehicle info, pick a date/time. The app geocodes the address and routes the lead to the right team by county.
- **Admin Panel** (`?page=admin`): Password-protected dashboard with lead management, dispatch map, and partner configuration.

### Lead Routing

Routing is **by county, resolved from the customer's typed address** (street, city, ZIP — all free text, no dropdown).

1. **US Census Geocoder** (free, no key) → county + coordinates
2. **OpenStreetMap Nominatim** (free) → fallback if Census has no match
3. **Built-in city table** (~450 cities/communities across the five counties) → fallback if both geocoders fail but the typed city is recognised; also supplies the finer `region` tag used by dispatch-map conflict warnings
4. Anything else → `unassigned`

| County | Territory | Routing |
|--------|-----------|---------|
| Riverside, San Bernardino, Orange | **QVV** | Zoho Desk ticket + email/SMS to QVV team → confirm via Bookings |
| Los Angeles | **Henry** | Email + SMS to partner |
| San Diego | **Joy** | Email + SMS to partner |
| Any other county (e.g. Ventura), or address not found | **unassigned** | Treated like a QVV lead but flagged **[NEEDS ROUTING]** in the ticket, email and SMS so the team hands it off manually. Never dropped. |

Each saved appointment records how it was routed in `notes` (e.g. `Routed by census → Riverside County`). The admin Leads tab can filter on `unassigned`.

> San Fernando Valley was Michael's territory until 2026-07; Henry Alvarez took it over.
> Until 2026-09-23 the form used a fixed dropdown of ~100 cities; customers outside those exact names could not book.

### Notifications

- **Customer** receives a confirmation email + SMS immediately after booking
- **QVV leads** create a Zoho Desk ticket via API (contact = the customer) + SMS to the QVV team; the lead email goes to `QVV_LEADS_EMAIL` if set, otherwise directly to Ekho
- **Partner leads** send email + SMS to the assigned partner verifier
- **Ekho** (`support@ekho.com`) is CC'd on every lead notification email (constant `EKHO_CC` in `app.py`)
- **Email From:** Quick VIN Verification (via SendGrid, `SENDGRID_FROM_EMAIL`)
- **Reply-To:** leads@quickautotags.com (TeamInbox shared inbox)
- **SMS From:** (951) 394-7012 via RingCentral
- **Phone numbers** are auto-formatted with +1 prefix on the backend

## Tech Stack

- **Streamlit** — UI framework
- **Supabase** — PostgreSQL database (free tier)
- **RingCentral** — SMS notifications
- **SendGrid** — Email notifications (HTTP API)
- **Folium** — Interactive dispatch map
- **geopy (Nominatim)** — Free address geocoding

## Setup From Scratch

### 1. Clone the repo

```bash
git clone https://github.com/meinc-projects/qvv-scheduler.git
cd qvv-scheduler
```

### 2. Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor**
3. Paste and run the entire contents of `supabase_schema.sql`
4. Copy your **Project URL** and **anon public key** from Settings → API

### 3. Set up RingCentral

1. Go to [developers.ringcentral.com](https://developers.ringcentral.com)
2. Create a new app: REST API, Server/Bot type
3. Enable **SMS** permission
4. Generate a **JWT credential** under your app's Credentials tab
5. Note your Client ID, Client Secret, JWT, and the phone number to send from

### 4. Set up SendGrid (Email Sending)

1. Create an API key at [app.sendgrid.com](https://app.sendgrid.com) → Settings → API Keys (Mail Send permission)
2. Verify the From address: either a **Single Sender** or **Domain Authentication**
   (Settings → Sender Authentication; domain auth = 3 CNAME records at your DNS host)
3. Use the key as `SENDGRID_API_KEY` and the verified address as `SENDGRID_FROM_EMAIL`

### 5. Configure Secrets

**For local development:** Create `.streamlit/secrets.toml` using `secrets.toml.template` as a guide.

```bash
mkdir -p .streamlit
cp secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your actual values
```

**For Streamlit Cloud:** Paste all key-value pairs into the Secrets section in Advanced Settings during deployment.

### Environment Variables

| Secret | Description |
|--------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/public key |
| `ADMIN_PASSWORD` | Password for the admin panel |
| `SENDGRID_API_KEY` | SendGrid API key (Mail Send permission) |
| `SENDGRID_FROM_EMAIL` | Verified From address for all outgoing email |
| `RC_CLIENT_ID` | RingCentral app Client ID |
| `RC_CLIENT_SECRET` | RingCentral app Client Secret |
| `RC_JWT` | RingCentral JWT credential |
| `RC_FROM_NUMBER` | RingCentral phone number (with +1) |
| `QVV_LEADS_EMAIL` | QVV team email for QVV-territory lead notifications (optional; if blank, lead email goes straight to Ekho) |
| `QVV_LEADS_PHONE` | QVV team phone for QVV-territory lead SMS (optional) |
| `ZOHO_CLIENT_ID` | Zoho OAuth client ID (for Desk ticket creation, optional) |
| `ZOHO_CLIENT_SECRET` | Zoho OAuth client secret |
| `ZOHO_REFRESH_TOKEN_DESK` | Zoho Desk refresh token — QVV leads create Desk tickets when set |
| `PARTNER_HENRY_EMAIL` | Henry's email for lead notifications |
| `PARTNER_HENRY_PHONE` | Henry's phone for SMS notifications |
| `PARTNER_JOY_EMAIL` | Joy's email for lead notifications |
| `PARTNER_JOY_PHONE` | Joy's phone for SMS notifications |

### 6. Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 7. Production Deployment (QAT VPS — current)

The app runs as a Windows service under NSSM and is published through the existing Cloudflare Tunnel.

| Item | Value |
|------|-------|
| Service name | `QVVScheduler` (NSSM, auto-start, restarts on crash after 5 s) |
| Command | `.venv\Scripts\python.exe -m streamlit run app.py` in `C:\AI Folder\Claude\qvv-scheduler` |
| Port | 8300 (bound to 127.0.0.1; config in `.streamlit/config.toml`) |
| Public hostnames | `schedule.vinverifications.com` (primary, customer-facing) and `schedule.quickautotags.com` (alias) → tunnel `07be7746-…` → `http://localhost:8300`. DNS: CNAME `schedule` → `07be7746-7121-44fe-86db-3d9347a72c03.cfargotunnel.com`, proxied, in each zone |
| Secrets | `.streamlit/secrets.toml` (git-ignored) |
| Logs | `logs\service_stdout.log`, `logs\service_stderr.log` (rotated at 5 MB) |

```bat
nssm status QVVScheduler
nssm restart QVVScheduler
```

After a `git pull`, restart the service to pick up code changes (file watching is disabled in production).

### 7b. Deploy to Streamlit Cloud (legacy — no longer used)

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo, select `app.py` as the main file
4. In **Advanced Settings**, paste all your secrets
5. Deploy

**URLs after deployment:**
- Customer form: `https://your-app.streamlit.app`
- Admin panel: `https://your-app.streamlit.app?page=admin`

## Architecture Notes

- **Future-proofed schema**: Fields for `confirmed_date/time`, `assigned_to`, `notes`, and `source` are in the DB but unused in V1 UI
- **Multi-source ready**: The `source` field defaults to `"ekho"` — future integrations (Zoho Forms, website intake) will use different values
- **Region tags**: Enable scheduling conflict warnings now and will power V2 auto-scheduling
- **Partner territories**: county → partner map is hardcoded (`COUNTY_TERRITORIES`); the city table is the fallback — V2 will pull both from the Supabase `partners` table
- **Geocoding**: US Census Geocoder + Nominatim, both free/keyless, 24 h cache — geocoding decides routing, and an outage degrades to the city table, never blocks a booking
- **Zoho Desk integration**: Planned — leads will also create tickets in Zoho Desk via REST API for full ticket lifecycle tracking

## Changelog

| Date | Change |
|------|--------|
| 2026-03-08 | Initial build: customer form, admin panel, Supabase, RingCentral SMS, Teams webhook |
| 2026-03-08 | Switched email from M365 SMTP to Zoho Mail SMTP (smtp.zoho.com:465 SSL) |
| 2026-03-08 | Auto-format phone numbers with +1 prefix, added Reply-To: leads@quickautotags.com |
| 2026-03-08 | SMS formatting cleanup — proper line breaks, (951) 394-7012 contact number |
| 2026-03-08 | Partner notification branding — Ekho attribution, fixed price footer |
| 2026-03-08 | UI overhaul — logo header, white background, blue CTA (#003594), date format MM-DD-YYYY |
| 2026-03-08 | Section headers styled bold blue, reduced white space between form sections |
| 2026-07-28 | Removed Teams webhook — QVV leads now email + SMS via `QVV_LEADS_EMAIL`/`QVV_LEADS_PHONE`. San Fernando Valley reassigned from Michael to Henry Alvarez (Michael no longer a partner). Ekho (support@ekho.com) CC'd on all lead emails. Redeployed at qvv-scheduler.streamlit.app |
| 2026-07-28 | Email switched from Zoho SMTP to SendGrid API — From address now configurable via `SENDGRID_FROM_EMAIL` (leads@quickautotags.com after domain auth) |
| 2026-07-28 | QVV leads now create Zoho Desk tickets directly via API (Standard dept, contact = customer) — email-to-Desk intake was getting spam-filtered. Ekho gets the lead email directly when `QVV_LEADS_EMAIL` is unset |
| 2026-09-16 | Moved off Streamlit Community Cloud (app kept sleeping) to the QAT VPS: NSSM service `QVVScheduler`, port 8300, `schedule.quickautotags.com` via Cloudflare Tunnel. Added `.streamlit/config.toml` |
| 2026-09-23 | Branded hostname `schedule.vinverifications.com` added (CNAME to the tunnel in the vinverifications.com zone) — now the primary customer URL |
| 2026-09-23 | Routing rebuilt: city dropdown replaced by free-text address/city/ZIP; county resolved via US Census Geocoder → Nominatim → 450-city table; out-of-area or unlocatable leads tagged `unassigned` and flagged [NEEDS ROUTING] to the QVV team |
