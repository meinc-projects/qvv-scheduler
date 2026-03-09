# Ekho VIN Verification Scheduling Portal

Streamlit web app for scheduling VIN verification appointments across Southern California. Leads route to Quick VIN Verification (QVV) or partner verifiers based on the customer's city.

**Live App:** [qvv-scheduler-2oddtjvyxumtrxf5qdsipv.streamlit.app](https://qvv-scheduler-2oddtjvyxumtrxf5qdsipv.streamlit.app/)

## What It Does

- **Customer Form** (root URL): Customers select their city, enter vehicle info, pick a date/time. The app routes the lead to the right team automatically.
- **Admin Panel** (`?page=admin`): Password-protected dashboard with lead management, dispatch map, and partner configuration.

### Lead Routing

| Territory | Cities | Routing |
|-----------|--------|---------|
| **QVV** | Riverside, San Bernardino, Orange County | Teams webhook → confirm via Bookings |
| **Henry** | LA / South LA (Los Angeles, Long Beach, etc.) | Email + SMS to partner |
| **Michael** | San Fernando Valley (Burbank, Glendale, etc.) | Email + SMS to partner |
| **Joy** | San Diego County (San Diego, Chula Vista, etc.) | Email + SMS to partner |

### Notifications

- **Customer** receives a confirmation email + SMS immediately after booking
- **QVV leads** post to Microsoft Teams channel via Adaptive Card webhook
- **Partner leads** send email + SMS to the assigned partner verifier
- **Email From:** Quick VIN Verification (via Zoho Mail SMTP)
- **Reply-To:** leads@quickautotags.com (TeamInbox shared inbox)
- **SMS From:** (951) 394-7012 via RingCentral
- **Phone numbers** are auto-formatted with +1 prefix on the backend

## Tech Stack

- **Streamlit** — UI framework
- **Supabase** — PostgreSQL database (free tier)
- **RingCentral** — SMS notifications
- **Zoho Mail SMTP** — Email notifications (smtp.zoho.com:465 SSL)
- **Microsoft Teams Webhook** — Team lead notifications (Adaptive Cards)
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

### 4. Set up Zoho Mail (Email Sending)

1. Log in to [mail.zoho.com](https://mail.zoho.com)
2. Go to **Settings → Security → App Passwords**
3. Generate an **App Password** for the Streamlit app
4. Use your Zoho email address and the app password

### 5. Set up Teams Webhook

1. In Microsoft Teams, go to the channel for lead notifications
2. Click the `...` menu → **Connectors** (or **Workflows** for newer Teams)
3. Add **Incoming Webhook**, give it a name, copy the URL

### 6. Configure Secrets

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
| `ZOHO_EMAIL` | Zoho Mail email address (sender) |
| `ZOHO_APP_PASSWORD` | Zoho Mail app password |
| `RC_CLIENT_ID` | RingCentral app Client ID |
| `RC_CLIENT_SECRET` | RingCentral app Client Secret |
| `RC_JWT` | RingCentral JWT credential |
| `RC_FROM_NUMBER` | RingCentral phone number (with +1) |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams incoming webhook URL |
| `PARTNER_HENRY_EMAIL` | Henry's email for lead notifications |
| `PARTNER_HENRY_PHONE` | Henry's phone for SMS notifications |
| `PARTNER_MICHAEL_EMAIL` | Michael's email for lead notifications |
| `PARTNER_MICHAEL_PHONE` | Michael's phone for SMS notifications |
| `PARTNER_JOY_EMAIL` | Joy's email for lead notifications |
| `PARTNER_JOY_PHONE` | Joy's phone for SMS notifications |

### 7. Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 8. Deploy to Streamlit Cloud

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
- **Partner cities**: Hardcoded in V1 — V2 will pull from the Supabase `partners.cities_csv` field
- **Geocoding**: Free Nominatim with 24hr cache — no API key needed
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
