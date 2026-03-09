"""
Ekho VIN Verification Scheduling Portal
========================================
Streamlit app for scheduling VIN verification appointments across Southern California.
Leads route to Quick VIN Verification (QVV) or partner verifiers based on customer city.

Pages:
  - Root URL: Customer scheduling form
  - ?page=admin: Admin panel (leads, dispatch map, partner management)
"""

import streamlit as st
import smtplib
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, date
from functools import lru_cache

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit command
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Quick VIN Verification — Scheduling",
    page_icon="🚗",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Hide Streamlit default header, footer, and hamburger menu
# Apply QVV green branding (#1a5632)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Hide default Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* QVV brand green for primary elements */
    .stButton > button {
        background-color: #1a5632;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #134025;
        color: white;
    }

    /* Metric card styling */
    div[data-testid="metric-container"] {
        background: #f0f7f3;
        border: 1px solid #1a5632;
        border-radius: 8px;
        padding: 12px;
    }

    /* Success banner */
    .success-banner {
        background: #f0f7f3;
        border: 2px solid #1a5632;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        margin: 2rem 0;
    }
    .success-banner h2 { color: #1a5632; }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# TERRITORY CONFIGURATION
# Each city maps to a territory with county, region, and routing info.
# V2 will pull this from the Supabase partners table cities_csv field.
# ===========================================================================

# Helper to build city entries quickly
def _qvv(city, county, region):
    """Create a QVV territory entry (routes to Microsoft Bookings via Teams)."""
    return {
        "territory_key": "qvv",
        "territory_label": "Quick VIN Verification",
        "route_method": "bookings",
        "county": county,
        "region": region,
    }

def _partner(city, key, label, county, region):
    """Create a partner territory entry (routes via email + SMS to partner)."""
    return {
        "territory_key": key,
        "territory_label": label,
        "route_method": "notify",
        "county": county,
        "region": region,
    }

# Master city-to-territory mapping — sorted alphabetically in the dropdown
CITY_TERRITORIES = {
    # --- QVV: San Bernardino County (inland) ---
    "San Bernardino":     _qvv("San Bernardino", "San Bernardino County", "inland"),
    "Ontario":            _qvv("Ontario", "San Bernardino County", "inland"),
    "Rancho Cucamonga":   _qvv("Rancho Cucamonga", "San Bernardino County", "inland"),
    "Fontana":            _qvv("Fontana", "San Bernardino County", "inland"),
    "Redlands":           _qvv("Redlands", "San Bernardino County", "inland"),
    "Upland":             _qvv("Upland", "San Bernardino County", "inland"),
    "Rialto":             _qvv("Rialto", "San Bernardino County", "inland"),
    "Yucaipa":            _qvv("Yucaipa", "San Bernardino County", "inland"),
    "Highland":           _qvv("Highland", "San Bernardino County", "inland"),
    # --- QVV: San Bernardino County (high desert) ---
    "Victorville":        _qvv("Victorville", "San Bernardino County", "high_desert"),
    "Hesperia":           _qvv("Hesperia", "San Bernardino County", "high_desert"),
    "Apple Valley":       _qvv("Apple Valley", "San Bernardino County", "high_desert"),
    "Barstow":            _qvv("Barstow", "San Bernardino County", "high_desert"),
    # --- QVV: San Bernardino County (mountain) ---
    "Big Bear":           _qvv("Big Bear", "San Bernardino County", "mountain"),
    # --- QVV: San Bernardino County (desert) ---
    "Twentynine Palms":   _qvv("Twentynine Palms", "San Bernardino County", "desert"),
    "Joshua Tree":        _qvv("Joshua Tree", "San Bernardino County", "desert"),
    # --- QVV: Riverside County (inland) ---
    "Riverside":          _qvv("Riverside", "Riverside County", "inland"),
    "Corona":             _qvv("Corona", "Riverside County", "inland"),
    "Moreno Valley":      _qvv("Moreno Valley", "Riverside County", "inland"),
    "Hemet":              _qvv("Hemet", "Riverside County", "inland"),
    "Perris":             _qvv("Perris", "Riverside County", "inland"),
    # --- QVV: Riverside County (southwest) ---
    "Temecula":           _qvv("Temecula", "Riverside County", "southwest"),
    "Murrieta":           _qvv("Murrieta", "Riverside County", "southwest"),
    "Menifee":            _qvv("Menifee", "Riverside County", "southwest"),
    "Lake Elsinore":      _qvv("Lake Elsinore", "Riverside County", "southwest"),
    # --- QVV: Riverside County (pass) ---
    "Beaumont":           _qvv("Beaumont", "Riverside County", "pass"),
    "Banning":            _qvv("Banning", "Riverside County", "pass"),
    # --- QVV: Riverside County (desert) ---
    "Palm Springs":       _qvv("Palm Springs", "Riverside County", "desert"),
    "Palm Desert":        _qvv("Palm Desert", "Riverside County", "desert"),
    "Indio":              _qvv("Indio", "Riverside County", "desert"),
    "Cathedral City":     _qvv("Cathedral City", "Riverside County", "desert"),
    "La Quinta":          _qvv("La Quinta", "Riverside County", "desert"),
    "Desert Hot Springs": _qvv("Desert Hot Springs", "Riverside County", "desert"),
    "Coachella":          _qvv("Coachella", "Riverside County", "desert"),
    # --- QVV: Orange County ---
    "Anaheim":            _qvv("Anaheim", "Orange County", "orange_county"),
    "Santa Ana":          _qvv("Santa Ana", "Orange County", "orange_county"),
    "Irvine":             _qvv("Irvine", "Orange County", "orange_county"),
    "Huntington Beach":   _qvv("Huntington Beach", "Orange County", "orange_county"),
    "Garden Grove":       _qvv("Garden Grove", "Orange County", "orange_county"),
    "Orange":             _qvv("Orange", "Orange County", "orange_county"),
    "Fullerton":          _qvv("Fullerton", "Orange County", "orange_county"),
    "Costa Mesa":         _qvv("Costa Mesa", "Orange County", "orange_county"),
    "Mission Viejo":      _qvv("Mission Viejo", "Orange County", "orange_county"),
    "Lake Forest":        _qvv("Lake Forest", "Orange County", "orange_county"),
    "Buena Park":         _qvv("Buena Park", "Orange County", "orange_county"),
    "Yorba Linda":        _qvv("Yorba Linda", "Orange County", "orange_county"),
    "San Clemente":       _qvv("San Clemente", "Orange County", "orange_county"),
    "Laguna Niguel":      _qvv("Laguna Niguel", "Orange County", "orange_county"),
    # --- Partner: Henry (LA / South LA) ---
    "Los Angeles":        _partner("Los Angeles", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Long Beach":         _partner("Long Beach", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Inglewood":          _partner("Inglewood", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Compton":            _partner("Compton", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Torrance":           _partner("Torrance", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Carson":             _partner("Carson", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Hawthorne":          _partner("Hawthorne", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Downey":             _partner("Downey", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Norwalk":            _partner("Norwalk", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Whittier":           _partner("Whittier", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "South Gate":         _partner("South Gate", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Lynwood":            _partner("Lynwood", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Paramount":          _partner("Paramount", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Bellflower":         _partner("Bellflower", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    "Lakewood":           _partner("Lakewood", "henry", "Henry — LA / South LA", "Los Angeles County", "la_south"),
    # --- Partner: Michael (San Fernando Valley) ---
    "North Hollywood":    _partner("North Hollywood", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Van Nuys":           _partner("Van Nuys", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Burbank":            _partner("Burbank", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Glendale":           _partner("Glendale", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Pasadena":           _partner("Pasadena", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Sherman Oaks":       _partner("Sherman Oaks", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Encino":             _partner("Encino", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Woodland Hills":     _partner("Woodland Hills", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Canoga Park":        _partner("Canoga Park", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Reseda":             _partner("Reseda", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Northridge":         _partner("Northridge", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Panorama City":      _partner("Panorama City", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Sun Valley":         _partner("Sun Valley", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Sylmar":             _partner("Sylmar", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    "Tarzana":            _partner("Tarzana", "michael", "Michael — San Fernando Valley", "Los Angeles County", "sfv"),
    # --- Partner: Joy (San Diego County) ---
    "San Diego":          _partner("San Diego", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Chula Vista":        _partner("Chula Vista", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Oceanside":          _partner("Oceanside", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Escondido":          _partner("Escondido", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Carlsbad":           _partner("Carlsbad", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "El Cajon":           _partner("El Cajon", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Vista":              _partner("Vista", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "San Marcos":         _partner("San Marcos", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Encinitas":          _partner("Encinitas", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "National City":      _partner("National City", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "La Mesa":            _partner("La Mesa", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Santee":             _partner("Santee", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Poway":              _partner("Poway", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Imperial Beach":     _partner("Imperial Beach", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
    "Coronado":           _partner("Coronado", "joy", "Joy — San Diego County", "San Diego County", "san_diego"),
}

# Sorted city list for the dropdown
ALL_CITIES = sorted(CITY_TERRITORIES.keys())

# Time slot options for the scheduling form
TIME_SLOTS = [
    "Morning (8 AM – 10 AM)",
    "Mid-Morning (10 AM – 12 PM)",
    "Afternoon (12 PM – 2 PM)",
    "Mid-Afternoon (2 PM – 4 PM)",
    "Late Afternoon (4 PM – 5 PM)",
]


# ===========================================================================
# HELPER: Check a secret exists, show friendly error if missing
# ===========================================================================
def get_secret(key):
    """Retrieve a secret from st.secrets. Returns None and shows error if missing."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return None


def require_secrets(*keys):
    """Check that all listed secrets exist. Returns True if all present, else shows errors."""
    missing = [k for k in keys if get_secret(k) is None]
    if missing:
        st.error(
            f"Missing secrets: {', '.join(missing)}. "
            "Add them to .streamlit/secrets.toml (local) or Streamlit Cloud secrets."
        )
        return False
    return True


# ===========================================================================
# SUPABASE CLIENT (cached so we only create one per session)
# ===========================================================================
@st.cache_resource
def get_supabase():
    """Initialize and return the Supabase client."""
    from supabase import create_client
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


# ===========================================================================
# GEOCODING — free Nominatim via geopy, with simple caching
# ===========================================================================
@st.cache_data(ttl=86400)  # Cache geocoding results for 24 hours
def geocode_address(address, city):
    """
    Convert an address + city to lat/lon using OpenStreetMap Nominatim.
    Returns (latitude, longitude) or (None, None) on failure.
    """
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="qvv-scheduler-app")
        full_address = f"{address}, {city}, CA"
        location = geolocator.geocode(full_address, timeout=10)
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass  # Geocoding is best-effort; don't block the submission
    return None, None


# ===========================================================================
# NOTIFICATION FUNCTIONS
# ===========================================================================

def send_email(to_address, subject, html_body):
    """
    Send an HTML email via Microsoft 365 SMTP.
    Returns True on success, False on failure (logs error to st.error).
    """
    if not require_secrets("M365_EMAIL", "M365_APP_PASSWORD"):
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = st.secrets["M365_EMAIL"]
        msg["To"] = to_address
        msg.attach(MIMEText(html_body, "html"))

        # Connect to M365 SMTP with STARTTLS
        with smtplib.SMTP("smtp.office365.com", 587) as server:
            server.starttls()
            server.login(st.secrets["M365_EMAIL"], st.secrets["M365_APP_PASSWORD"])
            server.sendmail(st.secrets["M365_EMAIL"], to_address, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Email send failed: {e}")
        return False


def send_sms(to_number, message_text):
    """
    Send an SMS via RingCentral REST API.
    Returns True on success, False on failure.
    """
    if not require_secrets("RC_CLIENT_ID", "RC_CLIENT_SECRET", "RC_JWT", "RC_FROM_NUMBER"):
        return False
    try:
        from ringcentral import SDK
        sdk = SDK(
            st.secrets["RC_CLIENT_ID"],
            st.secrets["RC_CLIENT_SECRET"],
            "https://platform.ringcentral.com",
        )
        platform = sdk.platform()
        platform.login(jwt=st.secrets["RC_JWT"])

        # Send SMS via RingCentral API
        platform.post(
            "/restapi/v1.0/account/~/extension/~/sms",
            {
                "from": {"phoneNumber": st.secrets["RC_FROM_NUMBER"]},
                "to": [{"phoneNumber": to_number}],
                "text": message_text,
            },
        )
        return True
    except Exception as e:
        st.error(f"SMS send failed: {e}")
        return False


def send_teams_webhook(appointment_data):
    """
    Send an Adaptive Card to Microsoft Teams via Incoming Webhook.
    Contains all lead details so the team can confirm via Bookings.
    Returns True on success, False on failure.
    """
    if not require_secrets("TEAMS_WEBHOOK_URL"):
        return False
    try:
        # Build the Adaptive Card payload
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "text": "New VIN Verification Lead (Ekho)",
                                "color": "Good",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Customer", "value": appointment_data["full_name"]},
                                    {"title": "Phone", "value": appointment_data["phone"]},
                                    {"title": "Email", "value": appointment_data["email"]},
                                    {"title": "Address", "value": f"{appointment_data['address']}, {appointment_data['city']}"},
                                    {"title": "County", "value": appointment_data.get("county", "")},
                                    {"title": "Region", "value": appointment_data.get("region", "")},
                                    {"title": "Vehicle", "value": f"{appointment_data['vehicle_year']} {appointment_data['vehicle_make']} {appointment_data['vehicle_model']}"},
                                    {"title": "Preferred Date", "value": appointment_data["preferred_date"]},
                                    {"title": "Preferred Time", "value": appointment_data["preferred_time"]},
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": "Please confirm this appointment via Microsoft Bookings.",
                                "wrap": True,
                                "weight": "Bolder",
                                "color": "Attention",
                            },
                        ],
                    },
                }
            ],
        }
        resp = requests.post(
            st.secrets["TEAMS_WEBHOOK_URL"],
            json=card,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        return resp.status_code in (200, 202)
    except Exception as e:
        st.error(f"Teams webhook failed: {e}")
        return False


def send_customer_confirmation_email(appt):
    """Send the customer a confirmation email with their appointment summary."""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1a5632; padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">Quick VIN Verification</h1>
        </div>
        <div style="padding: 20px; background: #f9f9f9;">
            <h2>Appointment Request Received!</h2>
            <p>Hi {appt['full_name']},</p>
            <p>We've received your VIN verification appointment request. A team member will contact you shortly to confirm your appointment.</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr><td style="padding: 8px; font-weight: bold;">Address:</td><td style="padding: 8px;">{appt['address']}, {appt['city']}, CA</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Vehicle:</td><td style="padding: 8px;">{appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Preferred Date:</td><td style="padding: 8px;">{appt['preferred_date']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Preferred Time:</td><td style="padding: 8px;">{appt['preferred_time']}</td></tr>
            </table>
            <p><em>Your preferred date and time are not confirmed until a team member contacts you.</em></p>
            <hr style="border: 1px solid #ddd;">
            <p style="font-size: 14px; color: #666;">
                Quick VIN Verification<br>
                Phone: (951) 339-2029<br>
                Website: <a href="https://www.vinverifications.com">vinverifications.com</a>
            </p>
        </div>
    </div>
    """
    return send_email(appt["email"], "Your VIN Verification Appointment Request — Quick VIN Verification", html)


def send_customer_confirmation_sms(appt):
    """Send the customer a short SMS confirming we received their request."""
    msg = (
        f"Hi {appt['full_name']}! We received your VIN verification request for "
        f"{appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']} "
        f"on {appt['preferred_date']} ({appt['preferred_time']}). "
        f"A team member will contact you to confirm. "
        f"Questions? Call (951) 339-2029 — Quick VIN Verification"
    )
    return send_sms(appt["phone"], msg)


def send_partner_notification_email(appt, partner_email):
    """Send partner verifier an email with all lead details."""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1a5632; padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">New Lead — Ekho Scheduling Portal</h1>
        </div>
        <div style="padding: 20px; background: #f9f9f9;">
            <p>You have a new VIN verification lead from the Ekho scheduling portal:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr><td style="padding: 8px; font-weight: bold;">Customer:</td><td style="padding: 8px;">{appt['full_name']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Phone:</td><td style="padding: 8px;">{appt['phone']}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Email:</td><td style="padding: 8px;">{appt['email']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Address:</td><td style="padding: 8px;">{appt['address']}, {appt['city']}, CA</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Vehicle:</td><td style="padding: 8px;">{appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Preferred Date:</td><td style="padding: 8px;">{appt['preferred_date']}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Preferred Time:</td><td style="padding: 8px;">{appt['preferred_time']}</td></tr>
            </table>
            <p>Please contact the customer to confirm the appointment.</p>
        </div>
    </div>
    """
    return send_email(partner_email, f"New VIN Verification Lead — {appt['full_name']} in {appt['city']}", html)


def send_partner_notification_sms(appt, partner_phone):
    """Send partner verifier a compact SMS with lead details."""
    msg = (
        f"New VIN lead from Ekho: {appt['full_name']}, "
        f"Ph: {appt['phone']}, {appt['city']}, "
        f"{appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}, "
        f"Date: {appt['preferred_date']} {appt['preferred_time']}"
    )
    return send_sms(partner_phone, msg)


# ===========================================================================
# PAGE: Customer Scheduling Form
# ===========================================================================
def page_customer_form():
    """Render the customer-facing VIN verification scheduling form."""

    st.markdown(
        "<h1 style='color: #1a5632; text-align: center;'>"
        "Quick VIN Verification</h1>"
        "<h3 style='text-align: center; color: #444;'>"
        "Schedule Your Mobile VIN Verification Appointment</h3>",
        unsafe_allow_html=True,
    )

    st.info(
        "Your preferred date and time are not confirmed until a team member contacts you."
    )

    # If we just submitted successfully, show the success screen
    if st.session_state.get("form_submitted"):
        st.markdown(
            """
            <div class="success-banner">
                <h2>Appointment Request Submitted!</h2>
                <p style="font-size: 18px;">Someone from our team will contact you shortly to confirm your appointment.</p>
                <p style="margin-top: 1rem;">
                    <strong>Phone:</strong> (951) 339-2029<br>
                    <strong>Website:</strong> <a href="https://www.vinverifications.com">vinverifications.com</a>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Schedule Another Appointment"):
            st.session_state["form_submitted"] = False
            st.rerun()
        return  # Don't show the form while success screen is visible

    # --- The scheduling form ---
    with st.form("appointment_form"):
        st.subheader("Your Information")
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *")
            email = st.text_input("Email Address *")
        with col2:
            phone = st.text_input("Phone Number *")

        st.subheader("Appointment Location")
        address = st.text_input("Street Address *")
        city = st.selectbox("City *", options=[""] + ALL_CITIES, index=0)

        st.subheader("Vehicle Information")
        col3, col4, col5 = st.columns(3)
        current_year = datetime.now().year
        with col3:
            vehicle_year = st.selectbox(
                "Vehicle Year *",
                options=[""] + [str(y) for y in range(current_year + 1, 1979, -1)],
                index=0,
            )
        with col4:
            vehicle_make = st.text_input("Vehicle Make *")
        with col5:
            vehicle_model = st.text_input("Vehicle Model *")

        st.subheader("Preferred Schedule")
        col6, col7 = st.columns(2)
        with col6:
            tomorrow = date.today() + timedelta(days=1)
            max_date = date.today() + timedelta(days=30)
            preferred_date = st.date_input(
                "Preferred Date *",
                value=tomorrow,
                min_value=tomorrow,
                max_value=max_date,
            )
        with col7:
            preferred_time = st.selectbox("Preferred Time *", options=[""] + TIME_SLOTS, index=0)

        submitted = st.form_submit_button("Submit Appointment Request", use_container_width=True)

    if submitted:
        # --- Validation ---
        errors = []
        if not full_name.strip():
            errors.append("Full Name is required.")
        if not email.strip() or "@" not in email:
            errors.append("A valid Email Address is required.")
        if not phone.strip():
            errors.append("Phone Number is required.")
        if not address.strip():
            errors.append("Street Address is required.")
        if not city:
            errors.append("City is required.")
        if not vehicle_year:
            errors.append("Vehicle Year is required.")
        if not vehicle_make.strip():
            errors.append("Vehicle Make is required.")
        if not vehicle_model.strip():
            errors.append("Vehicle Model is required.")
        if not preferred_time:
            errors.append("Preferred Time is required.")

        if errors:
            for err in errors:
                st.error(err)
            return

        # --- Determine territory from city ---
        territory = CITY_TERRITORIES[city]

        # --- Geocode the address ---
        with st.spinner("Processing your request..."):
            lat, lon = geocode_address(address, city)

            # --- Build the appointment record ---
            appt = {
                "full_name": full_name.strip(),
                "email": email.strip(),
                "phone": phone.strip(),
                "address": address.strip(),
                "city": city,
                "county": territory["county"],
                "region": territory["region"],
                "vehicle_year": vehicle_year,
                "vehicle_make": vehicle_make.strip(),
                "vehicle_model": vehicle_model.strip(),
                "preferred_date": preferred_date.isoformat(),
                "preferred_time": preferred_time,
                "territory_key": territory["territory_key"],
                "territory_label": territory["territory_label"],
                "route_method": territory["route_method"],
                "status": "pending",
                "latitude": lat,
                "longitude": lon,
                "source": "ekho",
            }

            # --- Save to Supabase ---
            db = get_supabase()
            if not db:
                st.error("Database not configured. Check SUPABASE_URL and SUPABASE_KEY in secrets.")
                return
            try:
                db.table("appointments").insert(appt).execute()
            except Exception as e:
                st.error(f"Failed to save appointment: {e}")
                return

            # --- Route notifications ---
            notification_updates = {}

            if territory["route_method"] == "bookings":
                # QVV territory — notify team via Teams webhook
                if send_teams_webhook(appt):
                    notification_updates["teams_notified"] = True
            else:
                # Partner territory — send email + SMS to partner
                partner_key = territory["territory_key"].upper()
                partner_email = get_secret(f"PARTNER_{partner_key}_EMAIL")
                partner_phone = get_secret(f"PARTNER_{partner_key}_PHONE")
                notified = False
                if partner_email:
                    if send_partner_notification_email(appt, partner_email):
                        notified = True
                if partner_phone:
                    if send_partner_notification_sms(appt, partner_phone):
                        notified = True
                if notified:
                    notification_updates["partner_notified"] = True

            # --- Send confirmation to customer (email + SMS) ---
            if send_customer_confirmation_email(appt):
                notification_updates["customer_notified"] = True
            send_customer_confirmation_sms(appt)  # SMS is best-effort

            # --- Update notification flags in database ---
            if notification_updates:
                try:
                    db.table("appointments").update(notification_updates).eq(
                        "email", appt["email"]
                    ).eq("preferred_date", appt["preferred_date"]).execute()
                except Exception:
                    pass  # Non-critical; flags are just for tracking

            # --- Show success ---
            st.session_state["form_submitted"] = True
            st.rerun()


# ===========================================================================
# PAGE: Admin Panel
# ===========================================================================
def page_admin():
    """Render the admin panel with leads management, dispatch map, and partners."""

    # --- Password gate ---
    if not st.session_state.get("admin_authenticated"):
        st.markdown(
            "<h2 style='text-align: center; color: #1a5632;'>Admin Panel</h2>",
            unsafe_allow_html=True,
        )
        pwd = st.text_input("Enter admin password:", type="password")
        if st.button("Login"):
            admin_pwd = get_secret("ADMIN_PASSWORD")
            if not admin_pwd:
                st.error("ADMIN_PASSWORD not set in secrets.")
            elif pwd == admin_pwd:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        return

    # --- Authenticated: show admin tabs ---
    st.markdown(
        "<h2 style='color: #1a5632;'>QVV Admin Panel</h2>",
        unsafe_allow_html=True,
    )

    # Horizontal tab selector
    tab = st.radio(
        "Navigate",
        ["Leads", "Dispatch Map", "Partners"],
        horizontal=True,
        label_visibility="collapsed",
    )

    db = get_supabase()
    if not db:
        st.error("Database not configured. Check SUPABASE_URL and SUPABASE_KEY.")
        return

    if tab == "Leads":
        admin_tab_leads(db)
    elif tab == "Dispatch Map":
        admin_tab_map(db)
    elif tab == "Partners":
        admin_tab_partners(db)


# ---------------------------------------------------------------------------
# Admin Tab: Leads
# ---------------------------------------------------------------------------
def admin_tab_leads(db):
    """Display filterable leads list with status management."""

    # --- Filters ---
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", ["All", "pending", "confirmed", "completed", "cancelled"])
    with col2:
        territory_filter = st.selectbox("Territory", ["All", "qvv", "henry", "michael", "joy"])
    with col3:
        date_col1, date_col2 = st.columns(2)
        with date_col1:
            date_from = st.date_input("From", value=date.today() - timedelta(days=30))
        with date_col2:
            date_to = st.date_input("To", value=date.today() + timedelta(days=30))

    # --- Query appointments ---
    try:
        query = db.table("appointments").select("*").order("created_at", desc=True)
        if status_filter != "All":
            query = query.eq("status", status_filter)
        if territory_filter != "All":
            query = query.eq("territory_key", territory_filter)
        query = query.gte("preferred_date", date_from.isoformat())
        query = query.lte("preferred_date", date_to.isoformat())
        result = query.execute()
        leads = result.data if result.data else []
    except Exception as e:
        st.error(f"Failed to load leads: {e}")
        return

    # --- Metric cards ---
    total = len(leads)
    pending = sum(1 for l in leads if l.get("status") == "pending")
    confirmed = sum(1 for l in leads if l.get("status") == "confirmed")
    completed = sum(1 for l in leads if l.get("status") == "completed")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Leads", total)
    m2.metric("Pending", pending)
    m3.metric("Confirmed", confirmed)
    m4.metric("Completed", completed)

    st.divider()

    # --- Lead cards ---
    if not leads:
        st.info("No leads match the current filters.")
        return

    for lead in leads:
        # Build a readable label for the expander
        status_emoji = {"pending": "🟠", "confirmed": "🟢", "completed": "🔵", "cancelled": "🔴"}.get(
            lead.get("status", ""), "⚪"
        )
        label = (
            f"{status_emoji} {lead.get('full_name', 'Unknown')} — "
            f"{lead.get('city', '')} — {lead.get('preferred_date', '')} "
            f"{lead.get('preferred_time', '')}"
        )
        with st.expander(label):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Name:** {lead.get('full_name', '')}")
                st.write(f"**Phone:** {lead.get('phone', '')}")
                st.write(f"**Email:** {lead.get('email', '')}")
                st.write(f"**Address:** {lead.get('address', '')}, {lead.get('city', '')}")
            with c2:
                st.write(f"**Vehicle:** {lead.get('vehicle_year', '')} {lead.get('vehicle_make', '')} {lead.get('vehicle_model', '')}")
                st.write(f"**Date/Time:** {lead.get('preferred_date', '')} — {lead.get('preferred_time', '')}")
                st.write(f"**Region:** {lead.get('region', '')} ({lead.get('county', '')})")
                st.write(f"**Territory:** {lead.get('territory_label', '')} ({lead.get('territory_key', '')})")

            # Status update controls
            statuses = ["pending", "confirmed", "completed", "cancelled"]
            current_idx = statuses.index(lead.get("status", "pending")) if lead.get("status") in statuses else 0
            new_status = st.selectbox(
                "Update status",
                statuses,
                index=current_idx,
                key=f"status_{lead['id']}",
            )
            if st.button("Save Status", key=f"save_{lead['id']}"):
                try:
                    db.table("appointments").update({"status": new_status}).eq("id", lead["id"]).execute()
                    st.success(f"Status updated to {new_status}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")


# ---------------------------------------------------------------------------
# Admin Tab: Dispatch Map
# ---------------------------------------------------------------------------
def admin_tab_map(db):
    """Show a Folium map of geocoded appointments with scheduling conflict warnings."""
    import folium
    from streamlit_folium import st_folium

    # --- Date range filter ---
    col1, col2 = st.columns(2)
    with col1:
        map_from = st.date_input("From date", value=date.today(), key="map_from")
    with col2:
        map_to = st.date_input("To date", value=date.today() + timedelta(days=7), key="map_to")

    # --- Query appointments in range ---
    try:
        result = (
            db.table("appointments")
            .select("*")
            .gte("preferred_date", map_from.isoformat())
            .lte("preferred_date", map_to.isoformat())
            .order("preferred_date")
            .execute()
        )
        appointments = result.data if result.data else []
    except Exception as e:
        st.error(f"Failed to load appointments: {e}")
        return

    # --- Build map ---
    # Center on geocoded appointments if available, otherwise default SoCal center
    geocoded = [a for a in appointments if a.get("latitude") and a.get("longitude")]
    if geocoded:
        avg_lat = sum(a["latitude"] for a in geocoded) / len(geocoded)
        avg_lon = sum(a["longitude"] for a in geocoded) / len(geocoded)
        center = [avg_lat, avg_lon]
        zoom = 9
    else:
        center = [33.95, -117.40]  # Southern California default
        zoom = 8

    m = folium.Map(location=center, zoom_start=zoom)

    # Color and icon mapping
    status_colors = {
        "pending": "orange",
        "confirmed": "green",
        "completed": "blue",
        "cancelled": "red",
    }

    for appt in geocoded:
        color = status_colors.get(appt.get("status", ""), "gray")
        # QVV territory = star icon, partner territory = info-sign icon
        icon_type = "star" if appt.get("territory_key") == "qvv" else "info-sign"

        popup_html = (
            f"<b>{appt.get('full_name', '')}</b><br>"
            f"{appt.get('city', '')}<br>"
            f"{appt.get('vehicle_year', '')} {appt.get('vehicle_make', '')} {appt.get('vehicle_model', '')}<br>"
            f"Date: {appt.get('preferred_date', '')} {appt.get('preferred_time', '')}<br>"
            f"Status: {appt.get('status', '')}<br>"
            f"Territory: {appt.get('territory_label', '')}"
        )

        folium.Marker(
            location=[appt["latitude"], appt["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=color, icon=icon_type),
        ).add_to(m)

    st_folium(m, width=None, height=500)

    # --- Legend ---
    st.markdown(
        """
        **Map Legend:**
        🟠 Pending &nbsp; 🟢 Confirmed &nbsp; 🔵 Completed &nbsp; 🔴 Cancelled
        &nbsp; | &nbsp; ⭐ QVV Territory &nbsp; ℹ️ Partner Territory
        """
    )

    st.divider()

    # --- Daily breakdown with scheduling conflict warnings ---
    st.subheader("Daily Breakdown")

    # Group by preferred_date
    by_date = {}
    for appt in appointments:
        d = appt.get("preferred_date", "Unknown")
        by_date.setdefault(d, []).append(appt)

    for day_str in sorted(by_date.keys()):
        day_appts = by_date[day_str]

        # Parse the day of week for conflict detection
        try:
            day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
            day_name = day_date.strftime("%A")
        except ValueError:
            day_name = ""

        # Collect regions present on this day
        day_regions = {a.get("region", "") for a in day_appts}

        # Detect scheduling conflicts
        warnings = []
        if day_name == "Friday" and "orange_county" in day_regions:
            warnings.append("Friday + OC appointment — Fridays are desert days")
        if day_name == "Wednesday" and "desert" in day_regions:
            warnings.append("Wednesday + Desert appointment — Wednesdays are OC days")
        if "desert" in day_regions and "orange_county" in day_regions:
            warnings.append("Desert + OC on same day — long drive conflict")

        # Build expander label
        label = f"{day_str} ({day_name}) — {len(day_appts)} appointment(s)"
        with st.expander(label):
            for w in warnings:
                st.warning(f"⚠️ {w}")
            for appt in day_appts:
                emoji = {"pending": "🟠", "confirmed": "🟢", "completed": "🔵", "cancelled": "🔴"}.get(
                    appt.get("status", ""), "⚪"
                )
                st.write(
                    f"{emoji} **{appt.get('full_name', '')}** — "
                    f"{appt.get('city', '')} — {appt.get('preferred_time', '')} — "
                    f"{appt.get('vehicle_year', '')} {appt.get('vehicle_make', '')} {appt.get('vehicle_model', '')}"
                )


# ---------------------------------------------------------------------------
# Admin Tab: Partners
# ---------------------------------------------------------------------------
def admin_tab_partners(db):
    """Manage partner verifiers — view, edit, add, delete."""

    # --- Load existing partners ---
    try:
        result = db.table("partners").select("*").order("created_at").execute()
        partners = result.data if result.data else []
    except Exception as e:
        st.error(f"Failed to load partners: {e}")
        return

    st.subheader("Existing Partners")

    if not partners:
        st.info("No partners configured yet. Add one below.")
    else:
        for partner in partners:
            active_label = "Active" if partner.get("active") else "Inactive"
            with st.expander(f"{partner.get('name', '')} — {partner.get('territory_label', '')} ({active_label})"):
                # Editable fields
                new_name = st.text_input("Name", value=partner.get("name", ""), key=f"pn_{partner['id']}")
                new_email = st.text_input("Email", value=partner.get("email", ""), key=f"pe_{partner['id']}")
                new_phone = st.text_input("Phone", value=partner.get("phone", ""), key=f"pp_{partner['id']}")
                new_tkey = st.text_input("Territory Key", value=partner.get("territory_key", ""), key=f"ptk_{partner['id']}")
                new_tlabel = st.text_input("Territory Label", value=partner.get("territory_label", ""), key=f"ptl_{partner['id']}")
                new_cities = st.text_area("Cities (comma-separated)", value=partner.get("cities_csv", ""), key=f"pc_{partner['id']}")
                new_active = st.checkbox("Active", value=partner.get("active", True), key=f"pa_{partner['id']}")

                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    if st.button("Save Changes", key=f"psave_{partner['id']}"):
                        try:
                            db.table("partners").update({
                                "name": new_name,
                                "email": new_email,
                                "phone": new_phone,
                                "territory_key": new_tkey,
                                "territory_label": new_tlabel,
                                "cities_csv": new_cities,
                                "active": new_active,
                            }).eq("id", partner["id"]).execute()
                            st.success("Partner updated.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")
                with bcol2:
                    if st.button("Delete Partner", key=f"pdel_{partner['id']}", type="secondary"):
                        try:
                            db.table("partners").delete().eq("id", partner["id"]).execute()
                            st.success("Partner deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")

    st.divider()

    # --- Add new partner ---
    st.subheader("Add New Partner")
    with st.form("add_partner_form"):
        np_name = st.text_input("Name")
        np_email = st.text_input("Email")
        np_phone = st.text_input("Phone")
        np_tkey = st.text_input("Territory Key (e.g., henry, michael, joy)")
        np_tlabel = st.text_input("Territory Label (e.g., Henry — LA / South LA)")
        np_cities = st.text_area("Cities (comma-separated)")
        add_submitted = st.form_submit_button("Add Partner")

    if add_submitted:
        if not all([np_name, np_email, np_phone, np_tkey, np_tlabel, np_cities]):
            st.error("All fields are required to add a partner.")
        else:
            try:
                db.table("partners").insert({
                    "name": np_name,
                    "email": np_email,
                    "phone": np_phone,
                    "territory_key": np_tkey,
                    "territory_label": np_tlabel,
                    "cities_csv": np_cities,
                }).execute()
                st.success(f"Partner '{np_name}' added!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add partner: {e}")


# ===========================================================================
# ROUTING — pick the right page based on query params
# ===========================================================================
def main():
    """Main entry point — routes to customer form or admin panel based on query params."""
    params = st.query_params
    page = params.get("page", "")

    if page == "admin":
        page_admin()
    else:
        page_customer_form()


if __name__ == "__main__":
    main()
