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
import requests
from datetime import datetime, timedelta, date
from functools import lru_cache

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit command
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Quick VIN Verification — Scheduling",
    page_icon="🚗",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Hide Streamlit default header, footer, and hamburger menu
# Apply QVV green branding (#1a5632)
# ---------------------------------------------------------------------------
LOGO_URL = "https://www.vinverifications.com/wp-content/uploads/2021/08/quick-vin-verification-logo.png"

st.markdown(f"""
<style>
    /* Hide default Streamlit chrome */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    /* Clean white background everywhere */
    .stApp, .main, section[data-testid="stSidebar"],
    .block-container, [data-testid="stForm"] {{
        background-color: #ffffff !important;
    }}

    /* Kill Streamlit's massive default top padding */
    .block-container {{
        padding-top: 1rem !important;
    }}

    /* Force all form inputs to white background with dark text */
    input, select, textarea,
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div,
    .stSelectbox [data-baseweb="select"],
    .stSelectbox [data-baseweb="select"] > div,
    .stDateInput > div > div > input,
    [data-baseweb="input"] > div,
    [data-baseweb="base-input"],
    [data-baseweb="select"] > div {{
        background-color: #ffffff !important;
        color: #333 !important;
        border-radius: 8px !important;
    }}

    /* Input borders */
    .stTextInput > div > div > input,
    .stDateInput > div > div > input {{
        border: 1px solid #ccc !important;
    }}
    .stTextInput > div > div > input:focus,
    .stDateInput > div > div > input:focus {{
        border-color: #003594 !important;
        box-shadow: 0 0 0 1px #003594 !important;
    }}

    /* Dropdown menus white background */
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    ul[role="listbox"],
    ul[role="listbox"] li {{
        background-color: #ffffff !important;
        color: #333 !important;
    }}
    ul[role="listbox"] li:hover {{
        background-color: #f0f4ff !important;
    }}

    /* Blue CTA button */
    .stButton > button,
    .stFormSubmitButton > button {{
        background-color: #003594 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.75rem 2rem !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        letter-spacing: 0.3px;
        transition: background-color 0.2s ease;
    }}
    .stButton > button:hover,
    .stFormSubmitButton > button:hover {{
        background-color: #002570 !important;
        color: white !important;
    }}

    /* Metric card styling */
    div[data-testid="metric-container"] {{
        background: #f8f9fa;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 16px;
    }}

    /* Logo header */
    .logo-header {{
        text-align: center;
        padding: 0.5rem 0 0.5rem 0;
    }}
    .logo-header img {{
        max-width: 280px;
        margin-bottom: 0.5rem;
    }}
    .logo-header p {{
        color: #666;
        font-size: 17px;
        margin-top: 0.25rem;
    }}

    /* Success banner */
    .success-banner {{
        background: #f0f4ff;
        border: 2px solid #003594;
        border-radius: 12px;
        padding: 2.5rem;
        text-align: center;
        margin: 2rem 0;
    }}
    .success-banner h2 {{
        color: #003594;
        margin-bottom: 0.5rem;
    }}

    /* Info notice */
    .info-notice {{
        background: #f0f4ff;
        border-left: 4px solid #003594;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 1.5rem;
        font-size: 14px;
        color: #555;
    }}

    /* Footer */
    .qvv-footer {{
        text-align: center;
        padding: 2rem 0 1rem 0;
        margin-top: 2rem;
        border-top: 1px solid #eee;
        color: #999;
        font-size: 13px;
    }}
    .qvv-footer a {{
        color: #003594;
        text-decoration: none;
    }}

    /* Label styling */
    .stTextInput label, .stSelectbox label, .stDateInput label {{
        color: #333 !important;
        font-weight: 500 !important;
    }}

    /* Reduce white space between form sections */
    [data-testid="stForm"] hr {{
        margin-top: 0.4rem !important;
        margin-bottom: 0.4rem !important;
    }}
    [data-testid="stForm"] [data-testid="stVerticalBlock"] > div {{
        gap: 0rem !important;
    }}
    [data-testid="stForm"] .stMarkdown p {{
        margin-bottom: 0.2rem !important;
    }}

    /* Tighten overall block gap inside form */
    [data-testid="stForm"] [data-testid="stVerticalBlockBorderWrapper"] {{
        padding: 1rem !important;
    }}
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# TERRITORY CONFIGURATION
# Coverage is by COUNTY. Every incorporated city in the five service counties
# is listed, plus the unincorporated communities and LA / San Diego
# neighborhoods that customers commonly type as their "city".
#
#   Riverside / San Bernardino / Orange County  -> QVV (in-house, confirm via Bookings)
#   Los Angeles County                          -> Henry (partner)
#   San Diego County                            -> Joy (partner)
#
# PRIMARY routing is by ADDRESS: the customer types street / city / ZIP as free
# text and resolve_territory() geocodes it (US Census Geocoder, then Nominatim)
# to get the COUNTY, which decides the partner. This city table is the fallback
# when geocoding fails, and it supplies the finer `region` tag used by the
# dispatch-map conflict warnings. Anything unresolvable is tagged `unassigned`
# and sent to the QVV team for manual routing, so no lead is ever lost.
# V2 will pull this from the Supabase partners table cities_csv field.
# ===========================================================================

CITY_TERRITORIES = {}


def _add(cities, territory_key, territory_label, route_method, county, region):
    """Register a group of cities under one territory/county/region."""
    for city in cities:
        CITY_TERRITORIES[city] = {
            "territory_key": territory_key,
            "territory_label": territory_label,
            "route_method": route_method,
            "county": county,
            "region": region,
        }


def _qvv(cities, county, region):
    _add(cities, "qvv", "Quick VIN Verification", "bookings", county, region)


def _henry(cities, label, region):
    _add(cities, "henry", label, "notify", "Los Angeles County", region)


def _joy(cities, region):
    _add(cities, "joy", "Joy — San Diego County", "notify", "San Diego County", region)


# --- QVV: San Bernardino County -------------------------------------------
_qvv([
    "San Bernardino", "Ontario", "Rancho Cucamonga", "Fontana", "Redlands", "Upland",
    "Rialto", "Yucaipa", "Highland", "Chino", "Chino Hills", "Colton", "Grand Terrace",
    "Loma Linda", "Montclair", "Bloomington", "Muscoy", "Mentone", "Lytle Creek",
    "Devore", "Mt. Baldy", "San Antonio Heights",
], "San Bernardino County", "inland")
_qvv([
    "Victorville", "Hesperia", "Apple Valley", "Adelanto", "Barstow", "Phelan",
    "Pinon Hills", "Oak Hills", "Wrightwood", "Lucerne Valley", "Helendale",
    "Silver Lakes", "Oro Grande", "Spring Valley Lake", "Newberry Springs", "Yermo",
    "Daggett", "Hinkley", "Fort Irwin", "Baker", "Ludlow", "Trona", "Needles", "Big River",
], "San Bernardino County", "high_desert")
_qvv([
    "Big Bear Lake", "Big Bear", "Big Bear City", "Sugarloaf", "Fawnskin", "Lake Arrowhead",
    "Crestline", "Running Springs", "Blue Jay", "Twin Peaks", "Cedar Glen",
    "Green Valley Lake", "Forest Falls", "Angelus Oaks",
], "San Bernardino County", "mountain")
_qvv([
    "Twentynine Palms", "Joshua Tree", "Yucca Valley", "Landers", "Morongo Valley",
    "Pioneertown", "Wonder Valley",
], "San Bernardino County", "desert")

# --- QVV: Riverside County ------------------------------------------------
_qvv([
    "Riverside", "Corona", "Moreno Valley", "Hemet", "Perris", "Jurupa Valley", "Eastvale",
    "Norco", "San Jacinto", "Mira Loma", "Rubidoux", "Pedley", "Glen Avon", "Sunnyslope",
    "Woodcrest", "Mead Valley", "Good Hope", "Highgrove", "March Air Reserve Base",
    "Nuevo", "Romoland", "Homeland", "Winchester", "East Hemet", "Valle Vista",
    "Home Gardens", "El Cerrito", "Coronita", "Temescal Valley", "Lake Mathews",
    "Green Acres",
], "Riverside County", "inland")
_qvv([
    "Temecula", "Murrieta", "Menifee", "Lake Elsinore", "Wildomar", "Canyon Lake",
    "Sun City", "Quail Valley", "Lakeland Village", "French Valley",
    "Murrieta Hot Springs", "Anza", "Aguanga", "Sage",
], "Riverside County", "southwest")
_qvv([
    "Beaumont", "Banning", "Calimesa", "Cherry Valley", "Cabazon", "Idyllwild",
    "Pine Cove", "Mountain Center",
], "Riverside County", "pass")
_qvv([
    "Palm Springs", "Palm Desert", "Indio", "Cathedral City", "La Quinta",
    "Desert Hot Springs", "Coachella", "Rancho Mirage", "Indian Wells", "Thousand Palms",
    "Bermuda Dunes", "Thermal", "Mecca", "Oasis", "North Shore", "Whitewater",
    "Sky Valley", "Blythe", "Ripley", "Desert Center",
], "Riverside County", "desert")

# --- QVV: Orange County ----------------------------------------------------
_qvv([
    "Aliso Viejo", "Anaheim", "Anaheim Hills", "Brea", "Buena Park", "Capistrano Beach",
    "Corona del Mar", "Costa Mesa", "Coto de Caza", "Cypress", "Dana Point",
    "Foothill Ranch", "Fountain Valley", "Fullerton", "Garden Grove", "Huntington Beach",
    "Irvine", "La Habra", "La Palma", "Ladera Ranch", "Laguna Beach", "Laguna Hills",
    "Laguna Niguel", "Laguna Woods", "Lake Forest", "Las Flores", "Los Alamitos",
    "Midway City", "Mission Viejo", "Newport Beach", "Newport Coast", "North Tustin",
    "Orange", "Placentia", "Rancho Mission Viejo", "Rancho Santa Margarita", "Rossmoor",
    "San Clemente", "San Juan Capistrano", "Santa Ana", "Seal Beach", "Silverado",
    "Stanton", "Sunset Beach", "Trabuco Canyon", "Tustin", "Villa Park", "Westminster",
    "Yorba Linda",
], "Orange County", "orange_county")

# --- Partner: Henry — Los Angeles County ------------------------------------
_henry([
    # City of LA (central / Westside / Harbor) + South Bay + Gateway cities
    "Los Angeles", "Downtown Los Angeles", "Hollywood", "West Hollywood", "Koreatown",
    "Silver Lake", "Echo Park", "Los Feliz", "Eagle Rock", "Highland Park",
    "Boyle Heights", "East Los Angeles", "Watts", "Willowbrook", "Florence-Graham",
    "Walnut Park", "West Los Angeles", "Century City", "Brentwood", "Pacific Palisades",
    "Venice", "Mar Vista", "Playa del Rey", "Playa Vista", "Westchester", "Marina del Rey",
    "Culver City", "Santa Monica", "Beverly Hills", "Ladera Heights", "View Park",
    "Malibu", "Topanga",
    "San Pedro", "Wilmington", "Harbor City", "Long Beach", "Signal Hill",
    "Inglewood", "Lennox", "Del Aire", "Hawthorne", "Gardena", "Lawndale",
    "Alondra Park", "El Segundo", "Manhattan Beach", "Hermosa Beach", "Redondo Beach",
    "Torrance", "West Carson", "Lomita", "Carson", "Rancho Dominguez",
    "East Rancho Dominguez", "Palos Verdes Estates", "Rancho Palos Verdes",
    "Rolling Hills", "Rolling Hills Estates", "Compton", "Athens", "Lynwood",
    "South Gate", "Huntington Park", "Bell", "Bell Gardens", "Cudahy", "Maywood",
    "Vernon", "Commerce", "Downey", "Norwalk", "Paramount", "Bellflower", "Lakewood",
    "Cerritos", "Artesia", "Hawaiian Gardens", "La Mirada", "Santa Fe Springs",
    "Pico Rivera", "Montebello", "Whittier", "South Whittier", "West Whittier",
    "La Habra Heights", "Avalon",
], "Henry — LA / South Bay / Westside", "la_south")
_henry([
    "North Hollywood", "Van Nuys", "Burbank", "Glendale", "Sherman Oaks", "Encino",
    "Woodland Hills", "Canoga Park", "Reseda", "Northridge", "Panorama City",
    "Sun Valley", "Sylmar", "Tarzana", "Studio City", "Valley Village", "Toluca Lake",
    "Universal City", "Chatsworth", "Granada Hills", "Porter Ranch", "Winnetka",
    "West Hills", "Mission Hills", "Pacoima", "Arleta", "Lake Balboa", "Sunland",
    "Tujunga", "San Fernando", "La Crescenta", "Montrose", "La Cañada Flintridge",
    "Calabasas", "Hidden Hills", "Agoura Hills", "Westlake Village",
], "Henry — San Fernando Valley", "sfv")
_henry([
    "Pasadena", "South Pasadena", "Altadena", "East Pasadena", "San Marino", "Alhambra",
    "Arcadia", "Monrovia", "Bradbury", "Duarte", "Sierra Madre", "Temple City",
    "San Gabriel", "South San Gabriel", "Rosemead", "Monterey Park", "El Monte",
    "South El Monte", "North El Monte", "Baldwin Park", "Irwindale", "Azusa", "Citrus",
    "Glendora", "Charter Oak", "Covina", "West Covina", "San Dimas", "La Verne",
    "Claremont", "Pomona", "Diamond Bar", "Walnut", "City of Industry",
    "La Puente", "West Puente Valley", "Valinda", "Avocado Heights", "Hacienda Heights",
    "Rowland Heights", "Mayflower Village",
], "Henry — San Gabriel Valley", "la_sgv")
_henry([
    "Santa Clarita", "Valencia", "Newhall", "Saugus", "Canyon Country", "Stevenson Ranch",
    "Castaic", "Acton", "Agua Dulce", "Palmdale", "Lancaster", "Quartz Hill",
    "Lake Los Angeles", "Littlerock", "Sun Village",
], "Henry — Santa Clarita / Antelope Valley", "la_north")

# --- Partner: Joy — San Diego County ----------------------------------------
_joy([
    "San Diego", "Downtown San Diego", "La Jolla", "Pacific Beach", "Ocean Beach",
    "Point Loma", "Mission Valley", "Hillcrest", "North Park", "Clairemont",
    "Kearny Mesa", "Linda Vista", "Serra Mesa", "Tierrasanta", "University City",
    "Sorrento Valley", "Torrey Pines", "Carmel Valley", "Del Mar Heights", "Mira Mesa",
    "Scripps Ranch", "Rancho Penasquitos", "Rancho Bernardo", "Carmel Mountain Ranch",
    "Sabre Springs", "Black Mountain Ranch", "4S Ranch", "Del Cerro", "College Area",
    "Logan Heights", "Barrio Logan", "Encanto", "Paradise Hills", "Otay Mesa",
    "San Ysidro", "Chula Vista", "National City", "Bonita", "Lincoln Acres",
    "Imperial Beach", "Coronado", "Lemon Grove", "Spring Valley", "La Mesa",
    "Casa de Oro", "Mount Helix", "Rancho San Diego",
], "san_diego")
_joy([
    "Oceanside", "Camp Pendleton", "Carlsbad", "Encinitas", "Cardiff", "Solana Beach",
    "Del Mar", "Rancho Santa Fe", "Escondido", "Hidden Meadows", "San Marcos", "Vista",
    "Bonsall", "Fallbrook", "Rainbow", "Valley Center", "Pauma Valley", "Poway",
    "Ramona", "Palomar Mountain", "Warner Springs",
], "sd_north")
_joy([
    "El Cajon", "Santee", "Lakeside", "Winter Gardens", "Eucalyptus Hills", "Alpine",
    "Crest", "Harbison Canyon", "Jamul", "Dulzura", "Descanso", "Pine Valley", "Julian",
    "Campo", "Potrero", "Boulevard", "Jacumba", "Borrego Springs",
], "sd_east")

# County -> territory. The partner is decided by county; `region` here is the
# default when the city is not in CITY_TERRITORIES.
COUNTY_TERRITORIES = {
    "Riverside County":       {"territory_key": "qvv",   "territory_label": "Quick VIN Verification",       "route_method": "bookings", "region": "inland"},
    "San Bernardino County":  {"territory_key": "qvv",   "territory_label": "Quick VIN Verification",       "route_method": "bookings", "region": "inland"},
    "Orange County":          {"territory_key": "qvv",   "territory_label": "Quick VIN Verification",       "route_method": "bookings", "region": "orange_county"},
    "Los Angeles County":     {"territory_key": "henry", "territory_label": "Henry — Los Angeles County",   "route_method": "notify",   "region": "la_south"},
    "San Diego County":       {"territory_key": "joy",   "territory_label": "Joy — San Diego County",       "route_method": "notify",   "region": "san_diego"},
}


def _unassigned(county=None):
    """Territory record for a lead nobody is mapped to — goes to QVV for manual routing."""
    if county:
        label = f"Unassigned — {county} is outside the service area (route manually)"
    else:
        label = "Unassigned — address could not be located (route manually)"
    return {
        "territory_key": "unassigned",
        "territory_label": label,
        "route_method": "bookings",   # handled by notify_qvv_team like a QVV lead
        "county": county or "Unknown",
        "region": "unknown",
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


def format_phone_e164(phone_str):
    """
    Clean a phone number and add +1 prefix for US numbers.
    Customers just type 10 digits like 9515551234 or (951) 555-1234.
    Returns formatted number like +19515551234.
    """
    # Strip everything except digits
    digits = "".join(c for c in phone_str if c.isdigit())
    # If they typed 11 digits starting with 1, already has country code
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    # Standard 10-digit US number — add +1
    if len(digits) == 10:
        return f"+1{digits}"
    # Fallback: return whatever we got with +1
    return f"+1{digits}"


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
# GEOCODING + TERRITORY RESOLUTION
# Free, keyless services: US Census Geocoder (authoritative county for any US
# street address) with OpenStreetMap Nominatim as the fallback. Results are
# cached 24 h. Everything here is best-effort: a geocoder outage never blocks a
# booking — the lead simply falls back to the city table or to `unassigned`.
# ===========================================================================
def _geocode_census(full_address):
    """US Census Geocoder -> (county, city, lat, lon) or None."""
    try:
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
            params={
                "address": full_address,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
            timeout=8,
        ).json()
        matches = r.get("result", {}).get("addressMatches") or []
        if not matches:
            return None
        m = matches[0]
        counties = m.get("geographies", {}).get("Counties") or []
        county = counties[0].get("NAME") if counties else None
        city = (m.get("addressComponents") or {}).get("city") or ""
        coords = m.get("coordinates") or {}
        return county, city.title(), coords.get("y"), coords.get("x")
    except Exception:
        return None


def _geocode_nominatim(full_address):
    """OpenStreetMap Nominatim -> (county, city, lat, lon) or None."""
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="qvv-scheduler-app")
        loc = geolocator.geocode(full_address, addressdetails=True, timeout=8)
        if not loc:
            return None
        ad = loc.raw.get("address") or {}
        county = ad.get("county")
        city = ad.get("city") or ad.get("town") or ad.get("village") or ad.get("hamlet") or ""
        return county, city, loc.latitude, loc.longitude
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def resolve_territory(address, city, zip_code):
    """
    Turn a free-text address into a routing decision.
    Returns a dict: territory_key, territory_label, route_method, county, region,
    latitude, longitude, matched_city, resolved_by.
      resolved_by = "census" | "nominatim" | "city_table" | "none"
    """
    parts = [address.strip(), city.strip(), "CA"]
    if zip_code and zip_code.strip():
        parts.append(zip_code.strip())
    full_address = ", ".join(p for p in parts if p)

    county = matched_city = None
    lat = lon = None
    resolved_by = "none"
    for name, fn in (("census", _geocode_census), ("nominatim", _geocode_nominatim)):
        hit = fn(full_address)
        if hit and hit[0]:
            county, matched_city, lat, lon = hit
            resolved_by = name
            break
        if hit and lat is None:
            # No county but we did get coordinates — keep them for the map
            _, _, lat, lon = hit

    # Region (and a finer label) from the city table when the city is known
    city_hit = CITY_TERRITORIES.get(matched_city) or CITY_TERRITORIES.get(city.strip().title())

    if county in COUNTY_TERRITORIES:
        base = dict(COUNTY_TERRITORIES[county])
        base["county"] = county
        if city_hit and city_hit["county"] == county:
            base["region"] = city_hit["region"]
            base["territory_label"] = city_hit["territory_label"]
        territory = base
    elif county:
        territory = _unassigned(county)             # e.g. Ventura County — out of area
    elif city_hit:
        territory = dict(city_hit)                  # geocoders failed; trust the typed city
        resolved_by = "city_table"
    else:
        territory = _unassigned()

    territory.update({
        "latitude": lat,
        "longitude": lon,
        "matched_city": matched_city or city.strip().title(),
        "resolved_by": resolved_by,
    })
    return territory


# ===========================================================================
# NOTIFICATION FUNCTIONS
# ===========================================================================

# Ekho (the lead source) is CC'd on every lead notification email
EKHO_CC = "support@ekho.com"


def send_email(to_address, subject, html_body, cc=None):
    """
    Send an HTML email via the SendGrid API. Optionally CC an address.
    From address comes from SENDGRID_FROM_EMAIL (must be a verified sender
    or on an authenticated domain in SendGrid); replies go to the leads inbox.
    Returns True on success, False on failure (logs error to st.error).
    """
    if not require_secrets("SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL"):
        return False
    try:
        personalization = {"to": [{"email": to_address}]}
        if cc:
            personalization["cc"] = [{"email": cc}]
        payload = {
            "personalizations": [personalization],
            "from": {
                "email": st.secrets["SENDGRID_FROM_EMAIL"],
                "name": "Quick VIN Verification",
            },
            "reply_to": {"email": "leads@quickautotags.com"},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
        }
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {st.secrets['SENDGRID_API_KEY']}"},
            timeout=15,
        )
        if resp.status_code == 202:
            return True
        st.error(f"Email send failed: {resp.status_code} {resp.text[:300]}")
        return False
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

        # Format phone numbers with +1 prefix automatically
        formatted_to = format_phone_e164(to_number)
        formatted_from = format_phone_e164(st.secrets["RC_FROM_NUMBER"])

        # Send SMS via RingCentral API
        platform.post(
            "/restapi/v1.0/account/~/extension/~/sms",
            {
                "from": {"phoneNumber": formatted_from},
                "to": [{"phoneNumber": formatted_to}],
                "text": message_text,
            },
        )
        return True
    except Exception as e:
        st.error(f"SMS send failed: {e}")
        return False


def create_desk_ticket(appt):
    """
    Create a Zoho Desk ticket for a QVV-territory lead via the Desk REST API.
    The ticket contact is the customer, so the team can reply directly.
    Needs ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET / ZOHO_REFRESH_TOKEN_DESK secrets.
    Returns True on success.
    """
    if not require_secrets("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN_DESK"):
        return False
    try:
        tok = requests.post(
            "https://accounts.zoho.com/oauth/v2/token",
            data={
                "refresh_token": st.secrets["ZOHO_REFRESH_TOKEN_DESK"],
                "client_id": st.secrets["ZOHO_CLIENT_ID"],
                "client_secret": st.secrets["ZOHO_CLIENT_SECRET"],
                "grant_type": "refresh_token",
            },
            timeout=15,
        ).json()
        access = tok.get("access_token")
        if not access:
            st.error(f"Desk auth failed: {tok.get('error', 'no access token')}")
            return False

        display_date = format_date_display(appt.get("preferred_date", ""))
        routing_note = (
            "<b style='color:#c0392b'>NEEDS ROUTING: this city is not in the service list. "
            "Confirm coverage and hand off to the right verifier.</b><br><br>"
            if appt.get("territory_key") == "unassigned" else ""
        )
        description = (
            f"<b>New VIN Verification Lead (Ekho)</b><br><br>"
            f"{routing_note}"
            f"<b>Customer:</b> {appt['full_name']}<br>"
            f"<b>Phone:</b> {appt['phone']}<br>"
            f"<b>Email:</b> {appt['email']}<br>"
            f"<b>Address:</b> {appt['address']}, {appt['city']}, CA<br>"
            f"<b>County:</b> {appt.get('county', '')}<br>"
            f"<b>Region:</b> {appt.get('region', '')}<br>"
            f"<b>Vehicle:</b> {appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}<br>"
            f"<b>Preferred Date:</b> {display_date}<br>"
            f"<b>Preferred Time:</b> {appt['preferred_time']}<br><br>"
            f"<b>Please confirm this appointment via Microsoft Bookings.</b>"
        )
        prefix = "[NEEDS ROUTING] " if appt.get("territory_key") == "unassigned" else ""
        payload = {
            "subject": f"{prefix}New VIN Verification Lead — {appt['full_name']} in {appt['city']}",
            "departmentId": "561223000000006907",  # Standard department
            "channel": "Web",
            "contact": {
                "lastName": appt["full_name"],
                "email": appt["email"],
                "phone": appt["phone"],
            },
            "description": description,
        }
        resp = requests.post(
            "https://desk.zoho.com/api/v1/tickets",
            json=payload,
            headers={"Authorization": f"Zoho-oauthtoken {access}", "orgId": "732767718"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True
        st.error(f"Desk ticket failed: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        st.error(f"Desk ticket failed: {e}")
        return False


def notify_qvv_team(appt):
    """
    Notify the QVV team of a new lead in their territory:
    1. Zoho Desk ticket via API (if Zoho secrets configured) — primary intake
    2. Lead email — to QVV_LEADS_EMAIL if set (CC Ekho), else straight to Ekho
       so Ekho always gets a copy
    3. SMS to QVV_LEADS_PHONE if set
    Each channel is independent; the lead is always saved to the admin panel.
    Returns True if at least one notification went out.
    """
    display_date = format_date_display(appt.get("preferred_date", ""))
    notified = False
    unassigned = appt.get("territory_key") == "unassigned"
    subject_prefix = "[NEEDS ROUTING] " if unassigned else ""
    routing_html = (
        '<p style="font-weight: bold; color: #c0392b;">NEEDS ROUTING: this city is not in the '
        'service list. Confirm coverage and hand off to the right verifier.</p>'
        if unassigned else ""
    )
    routing_sms = "NEEDS ROUTING - city not in service list.\n\n" if unassigned else ""

    if get_secret("ZOHO_REFRESH_TOKEN_DESK"):
        if create_desk_ticket(appt):
            notified = True

    qvv_email = get_secret("QVV_LEADS_EMAIL")
    if qvv_email or EKHO_CC:
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a5632; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">New VIN Verification Lead (Ekho)</h1>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                {routing_html}
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr><td style="padding: 8px; font-weight: bold;">Customer:</td><td style="padding: 8px;">{appt['full_name']}</td></tr>
                    <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Phone:</td><td style="padding: 8px;">{appt['phone']}</td></tr>
                    <tr><td style="padding: 8px; font-weight: bold;">Email:</td><td style="padding: 8px;">{appt['email']}</td></tr>
                    <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Address:</td><td style="padding: 8px;">{appt['address']}, {appt['city']}, CA</td></tr>
                    <tr><td style="padding: 8px; font-weight: bold;">County:</td><td style="padding: 8px;">{appt.get('county', '')}</td></tr>
                    <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Region:</td><td style="padding: 8px;">{appt.get('region', '')}</td></tr>
                    <tr><td style="padding: 8px; font-weight: bold;">Vehicle:</td><td style="padding: 8px;">{appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}</td></tr>
                    <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Preferred Date:</td><td style="padding: 8px;">{display_date}</td></tr>
                    <tr><td style="padding: 8px; font-weight: bold;">Preferred Time:</td><td style="padding: 8px;">{appt['preferred_time']}</td></tr>
                </table>
                <p style="font-weight: bold; color: #c0392b;">Please confirm this appointment via Microsoft Bookings.</p>
            </div>
        </div>
        """
        subject = f"{subject_prefix}New VIN Verification Lead — {appt['full_name']} in {appt['city']}"
        if qvv_email:
            sent = send_email(qvv_email, subject, html, cc=EKHO_CC)
        else:
            # No QVV inbox configured — Ekho still gets its copy directly
            sent = send_email(EKHO_CC, subject, html)
        if sent:
            notified = True

    qvv_phone = get_secret("QVV_LEADS_PHONE")
    if qvv_phone:
        msg = (
            f"New VIN Verification Lead (Ekho)\n\n"
            f"{routing_sms}"
            f"Customer: {appt['full_name']}\n"
            f"Phone: {appt['phone']}\n"
            f"Email: {appt['email']}\n"
            f"Address: {appt['address']}, {appt['city']}, CA\n"
            f"Vehicle: {appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}\n"
            f"Date: {display_date}\n"
            f"Time: {appt['preferred_time']}\n\n"
            f"Please confirm via Microsoft Bookings."
        )
        if send_sms(qvv_phone, msg):
            notified = True

    return notified


def send_customer_confirmation_email(appt):
    """Send the customer a confirmation email with their appointment summary."""
    display_date = format_date_display(appt['preferred_date'])
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
                <tr><td style="padding: 8px; font-weight: bold;">Preferred Date:</td><td style="padding: 8px;">{display_date}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Preferred Time:</td><td style="padding: 8px;">{appt['preferred_time']}</td></tr>
            </table>
            <p><em>Your preferred date and time are not confirmed until a team member contacts you.</em></p>
            <hr style="border: 1px solid #ddd;">
            <p style="font-size: 14px; color: #666;">
                Quick VIN Verification<br>
                Phone: (951) 394-7012<br>
                Website: <a href="https://www.vinverifications.com">vinverifications.com</a>
            </p>
        </div>
    </div>
    """
    return send_email(appt["email"], "Your VIN Verification Appointment Request — Quick VIN Verification", html)


def send_customer_confirmation_sms(appt):
    """Send the customer a short SMS confirming we received their request."""
    display_date = format_date_display(appt['preferred_date'])
    msg = (
        f"Hi {appt['full_name']}! We received your VIN verification request "
        f"for a {appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']} "
        f"on {display_date} ({appt['preferred_time']}).\n\n"
        f"A team member will contact you to confirm your appointment.\n\n"
        f"Questions? Call (951) 394-7012\n\n"
        f"Thank you,\n"
        f"Quick VIN Verification Team"
    )
    return send_sms(appt["phone"], msg)


def send_partner_notification_email(appt, partner_email):
    """Send partner verifier an email with all lead details."""
    display_date = format_date_display(appt['preferred_date'])
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1a5632; padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">New Lead — Quick VIN Verification</h1>
        </div>
        <div style="padding: 20px; background: #f9f9f9;">
            <p style="font-size: 16px; font-weight: bold; color: #1a5632;">This is a lead from Quick VIN Verification — Ekho</p>
            <p>Please contact the customer below to confirm their VIN verification appointment:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr><td style="padding: 8px; font-weight: bold;">Customer:</td><td style="padding: 8px;">{appt['full_name']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Phone:</td><td style="padding: 8px;">{appt['phone']}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Email:</td><td style="padding: 8px;">{appt['email']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Address:</td><td style="padding: 8px;">{appt['address']}, {appt['city']}, CA</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Vehicle:</td><td style="padding: 8px;">{appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}</td></tr>
                <tr style="background: #eee;"><td style="padding: 8px; font-weight: bold;">Preferred Date:</td><td style="padding: 8px;">{display_date}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Preferred Time:</td><td style="padding: 8px;">{appt['preferred_time']}</td></tr>
            </table>
            <hr style="border: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 13px; color: #666;">
                The payment will be sent to you by your partner Quick VIN Verification — the price for this VIN verification is fixed. Any questions, please contact your partner.
            </p>
        </div>
    </div>
    """
    return send_email(partner_email, f"New VIN Verification Lead — {appt['full_name']} in {appt['city']}", html, cc=EKHO_CC)


def send_partner_notification_sms(appt, partner_phone):
    """Send partner verifier a compact SMS with lead details."""
    display_date = format_date_display(appt['preferred_date'])
    msg = (
        f"This is a lead from Quick VIN Verification — Ekho\n\n"
        f"Customer: {appt['full_name']}\n"
        f"Phone: {appt['phone']}\n"
        f"Email: {appt['email']}\n"
        f"Address: {appt['address']}, {appt['city']}, CA\n"
        f"Vehicle: {appt['vehicle_year']} {appt['vehicle_make']} {appt['vehicle_model']}\n"
        f"Date: {display_date}\n"
        f"Time: {appt['preferred_time']}\n\n"
        f"Please contact the customer to confirm.\n\n"
        f"The payment will be sent to you by your partner Quick VIN Verification — "
        f"the price for this VV is fixed. Any questions, please contact your partner."
    )
    return send_sms(partner_phone, msg)


# ===========================================================================
# PAGE: Customer Scheduling Form
# ===========================================================================
def format_date_display(d):
    """Format a date as MM-DD-YYYY for display."""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return d
    return d.strftime("%m-%d-%Y")


def page_customer_form():
    """Render the customer-facing VIN verification scheduling form."""

    # --- Logo header ---
    st.markdown(
        f"""
        <div class="logo-header">
            <img src="{LOGO_URL}" alt="Quick VIN Verification">
            <p>Schedule Your Mobile VIN Verification Appointment</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Info notice ---
    st.markdown(
        '<div class="info-notice">'
        'Your preferred date and time are <strong>not confirmed</strong> until a team member contacts you.'
        '</div>',
        unsafe_allow_html=True,
    )

    # If we just submitted successfully, show the success screen
    if st.session_state.get("form_submitted"):
        st.markdown(
            """
            <div class="success-banner">
                <div style="font-size: 48px; margin-bottom: 0.5rem;">&#10003;</div>
                <h2>Appointment Request Submitted!</h2>
                <p style="font-size: 17px; color: #555; margin-top: 0.5rem;">
                    Someone from our team will contact you shortly to confirm your appointment.
                </p>
                <div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #e0e0e0;">
                    <p style="margin: 0; color: #666;">
                        <strong>Phone:</strong> (951) 394-7012<br>
                        <strong>Website:</strong> <a href="https://www.vinverifications.com" style="color: #1a5632;">vinverifications.com</a>
                    </p>
                </div>
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

        # Section 1: Contact Info
        st.markdown('<p style="font-size: 18px; font-weight: 700; color: #003594; margin: 0.1rem 0 0.25rem 0;">Contact Information</p>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *")
            email = st.text_input("Email Address *")
        with col2:
            phone = st.text_input("Phone Number *", placeholder="(951) 555-1234")

        st.divider()

        # Section 2: Location
        st.markdown('<p style="font-size: 18px; font-weight: 700; color: #003594; margin: 0.1rem 0 0.25rem 0;">Appointment Location</p>', unsafe_allow_html=True)
        address = st.text_input("Street Address *", placeholder="e.g. 3900 Main St")
        colc, colz = st.columns([2, 1])
        with colc:
            city = st.text_input("City *", placeholder="e.g. Riverside")
        with colz:
            zip_code = st.text_input("ZIP Code", placeholder="92501")

        st.divider()

        # Section 3: Vehicle
        st.markdown('<p style="font-size: 18px; font-weight: 700; color: #003594; margin: 0.1rem 0 0.25rem 0;">Vehicle Information</p>', unsafe_allow_html=True)
        col3, col4, col5 = st.columns(3)
        current_year = datetime.now().year
        with col3:
            vehicle_year = st.selectbox(
                "Vehicle Year *",
                options=["— Year —"] + [str(y) for y in range(current_year + 1, 1979, -1)],
                index=0,
            )
        with col4:
            vehicle_make = st.text_input("Vehicle Make *", placeholder="e.g. Toyota")
        with col5:
            vehicle_model = st.text_input("Vehicle Model *", placeholder="e.g. Corolla")

        st.divider()

        # Section 4: Schedule
        st.markdown('<p style="font-size: 18px; font-weight: 700; color: #003594; margin: 0.1rem 0 0.25rem 0;">Preferred Schedule</p>', unsafe_allow_html=True)
        col6, col7 = st.columns(2)
        with col6:
            tomorrow = date.today() + timedelta(days=1)
            max_date = date.today() + timedelta(days=30)
            preferred_date = st.date_input(
                "Preferred Date *",
                value=tomorrow,
                min_value=tomorrow,
                max_value=max_date,
                format="MM/DD/YYYY",
            )
        with col7:
            preferred_time = st.selectbox(
                "Preferred Time *",
                options=["— Select a time —"] + TIME_SLOTS,
                index=0,
            )

        st.markdown("")  # Small spacer before button
        submitted = st.form_submit_button("Submit Appointment Request", use_container_width=True)

    # --- Footer ---
    st.markdown(
        f'<div class="qvv-footer">'
        f'<img src="{LOGO_URL}" alt="QVV" style="max-width: 120px; opacity: 0.5; margin-bottom: 0.5rem;"><br>'
        f'(951) 394-7012 &nbsp;|&nbsp; <a href="https://www.vinverifications.com">vinverifications.com</a>'
        f'</div>',
        unsafe_allow_html=True,
    )

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
        if not city.strip():
            errors.append("City is required.")
        zip_digits = "".join(c for c in zip_code if c.isdigit())
        if zip_code.strip() and len(zip_digits) != 5:
            errors.append("ZIP Code must be 5 digits (or leave it blank).")
        if not vehicle_year or vehicle_year == "— Year —":
            errors.append("Vehicle Year is required.")
        if not vehicle_make.strip():
            errors.append("Vehicle Make is required.")
        if not vehicle_model.strip():
            errors.append("Vehicle Model is required.")
        if not preferred_time or preferred_time == "— Select a time —":
            errors.append("Preferred Time is required.")

        if errors:
            for err in errors:
                st.error(err)
            return

        # --- Geocode the address and pick the territory by county ---
        with st.spinner("Processing your request..."):
            territory = resolve_territory(address, city, zip_digits)
            lat, lon = territory["latitude"], territory["longitude"]
            city = territory["matched_city"] or city.strip().title()

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
                "notes": f"Routed by {territory['resolved_by']} → {territory['county']}",
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
                # QVV territory — email + SMS to the QVV team
                # (teams_notified is the legacy column name; tracks QVV notification)
                if notify_qvv_team(appt):
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
        territory_filter = st.selectbox("Territory", ["All", "qvv", "henry", "joy", "unassigned"])
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
        np_tkey = st.text_input("Territory Key (e.g., henry, joy)")
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
