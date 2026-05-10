import re
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import requests

# ============================================================================
# PAGE CONFIG & STYLING
# ============================================================================
SHEET_URL = st.secrets.get("sheet_url")

st.set_page_config(
    page_title="Job Application Tracker",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS to hide the 'Fork' button and GitHub icon
hide_fork_style = """
    <style>
    #MainMenu {visibility: hidden;} /* Hides the top-right hamburger menu */
    .stAppDeployButton {display:none;} /* Hides the 'Deploy/Fork' button area */
    header {visibility: hidden;} /* Hides the entire top header bar */
    </style>
"""
st.markdown(hide_fork_style, unsafe_allow_html=True)

# Custom CSS for better UI with horizontal nav
st.markdown("""
    <style>
    .top-navbar {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 15px 20px;
        background-color: #ffffff;
        border-bottom: 2px solid #e0e4e8;
        margin-bottom: 20px;
        border-radius: 5px;
    }
    .title-section {
        font-size: 30px;
        font-weight: 800;
        text-align: center;
        width: 100%;
        color: #111111;
        text-transform: uppercase;
    }
    @media(min-width: 769px) {
        .title-section {
            font-size: 60px;
        }
    }
    .nav-link-button {
        display: inline-block;
        text-decoration: none;
        text-align: center;
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid #7f8c8d;
        background-color: #ffffff;
        color: #2c3e50;
        font-weight: 600;
        width: 100%;
        max-width: 160px;
    }
    .stButton button {
        min-width: 0 !important;
        max-width: 160px !important;
        width: 100% !important;
    }
    .metric-card {
        text-align: center;
        padding: 18px 16px;
        border-radius: 10px;
        background-color: rgba(255,255,255,0.92);
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .metric-number {
        font-size: 2.8rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    .metric-label {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        margin-top: 5px;
    }
    .metrics-row {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 15px;
        margin-bottom: 20px;
    }
    .location-stats {
        background-color: #ffffff;
        color: #111111;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: 500;
        border: 1px solid #d1d5db;
    }
    .privacy-notice {
        background-color: #fff3cd;
        border: 1px solid #ffc107;
        padding: 12px;
        border-radius: 5px;
        margin-bottom: 15px;
        color: #333;
    }
    @media(max-width: 768px) {
        .metrics-row {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    """, unsafe_allow_html=True)

# ============================================================================
# AUTHENTICATION & SESSION STATE
# ============================================================================

# Initialize session state
if "user_tier" not in st.session_state:
    st.session_state.user_tier = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "postal_code" not in st.session_state:
    st.session_state.postal_code = ""
if "postal_code_coords" not in st.session_state:
    st.session_state.postal_code_coords = None
if "distances" not in st.session_state:
    st.session_state.distances = {}
if "active_nav" not in st.session_state:
    st.session_state.active_nav = None
if "search_company" not in st.session_state:
    st.session_state.search_company = ""
if "search_title" not in st.session_state:
    st.session_state.search_title = ""
if "filter_status" not in st.session_state:
    st.session_state.filter_status = "All"
if "filter_location" not in st.session_state:
    st.session_state.filter_location = "All"
if "selected_row_no" not in st.session_state:
    st.session_state.selected_row_no = 1

# Role configuration
ADMIN_EMAILS = st.secrets.get("admin_emails", [])
if isinstance(ADMIN_EMAILS, str):
    ADMIN_EMAILS = [ADMIN_EMAILS]
if not ADMIN_EMAILS and st.secrets.get("admin_email"):
    ADMIN_EMAILS = [st.secrets.get("admin_email")]

TRUSTED_VIEWERS = st.secrets.get("trusted_viewers", [])
if isinstance(TRUSTED_VIEWERS, str):
    TRUSTED_VIEWERS = [TRUSTED_VIEWERS]

USER_PASSWORDS = st.secrets.get("user_passwords", {})

def authenticate_user(email, password):
    """Authenticate user by email and password."""
    if not email or not password:
        return False

    if USER_PASSWORDS and email in USER_PASSWORDS:
        expected_password = USER_PASSWORDS[email]
        if password != expected_password:
            return False
    else:
        return False

    if email in ADMIN_EMAILS:
        st.session_state.user_tier = "admin"
    elif email in TRUSTED_VIEWERS:
        st.session_state.user_tier = "trusted_viewer"
    else:
        st.session_state.user_tier = "public"

    st.session_state.user_email = email
    st.session_state.authenticated = True
    return True


def logout():
    """Logout function"""
    st.session_state.user_tier = None
    st.session_state.user_email = None
    st.session_state.authenticated = False
    st.session_state.active_nav = None
    st.session_state.search_company = ""
    st.session_state.search_title = ""
    st.session_state.filter_status = "All"
    st.session_state.filter_location = "All"
    st.session_state.selected_row_no = 1
    st.session_state.postal_code = ""
    st.session_state.postal_code_coords = None
    st.rerun()

# TOP NAVIGATION BAR
st.markdown(
    '<div class="top-navbar"><div class="title-section">JOB APPLICATION TRACKER</div></div>',
    unsafe_allow_html=True
)

nav_columns = st.columns([1, 1, 1, 1, 1] if st.session_state.user_tier == "admin" else [1, 1, 1, 1])
with nav_columns[0]:
    if not st.session_state.authenticated:
        if st.button("Log in", key="nav_login"):
            st.session_state.active_nav = "login"
    else:
        user_label = "Admin" if st.session_state.user_tier == "admin" else "Viewer"
        st.markdown(f"**Logged in as {user_label}**")
with nav_columns[1]:
    if st.button("Search", key="nav_search"):
        st.session_state.active_nav = "search"
with nav_columns[2]:
    if st.button("Filter", key="nav_filter"):
        st.session_state.active_nav = "filter"
with nav_columns[3]:
    if st.button("Export", key="nav_export"):
        st.session_state.active_nav = "export"
if st.session_state.user_tier == "admin":
    with nav_columns[4]:
        if SHEET_URL:
            st.markdown(
                f'<a class="nav-link-button" href="{SHEET_URL}" target="_blank">Import</a>',
                unsafe_allow_html=True
            )

if st.session_state.authenticated:
    logout_col1, logout_col2 = st.columns([9, 1])
    with logout_col2:
        if st.button("Logout", key="nav_logout"):
            logout()

if st.session_state.active_nav == "login":
    with st.form("login_form"):
        email = st.text_input("Email address:", key="login_email", placeholder="your.email@example.com")
        password = st.text_input("Password:", key="login_password", type="password")
        submit_login = st.form_submit_button("Log in")
        if submit_login:
            if authenticate_user(email, password):
                st.success("Logged in successfully.")
                st.session_state.active_nav = None
                st.experimental_rerun()
            else:
                st.error("Invalid email or password. Please try again.")

elif st.session_state.active_nav == "search":
    st.text_input("Search by company:", key="search_company", placeholder="Company name")
    st.text_input("Search by job title:", key="search_title", placeholder="Job title")

elif st.session_state.active_nav == "filter":
    st.selectbox(
        "Filter by status:",
        ["All", "Applied", "Rejected", "Interviews", "Offers"],
        key="filter_status"
    )
    st.selectbox(
        "Filter by location:",
        ["All", "Remote", "Hybrid", "Onsite"],
        key="filter_location"
    )

elif st.session_state.active_nav == "export":
    st.info("Export to CSV is available below once data has loaded.")

st.markdown("---")

# Set public tier as default if not authenticated
if not st.session_state.authenticated:
    st.session_state.user_tier = "public"

# ============================================================================
# GOOGLE SHEETS CONNECTION
# ============================================================================

@st.cache_resource
def get_gsheet_connection():
    """Initialize Google Sheets connection"""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                   "https://www.googleapis.com/auth/drive"]
        )
        gc = gspread.authorize(credentials)
        return gc
    except Exception as e:
        st.error(f"❌ Failed to connect to Google Sheets: {e}")
        return None

@st.cache_data(ttl=300)
def load_data_from_sheets(sheet_url):
    """Load data from Google Sheets"""
    try:
        gc = get_gsheet_connection()
        if gc is None:
            return pd.DataFrame()
        
        sh = gc.open_by_url(sheet_url)
        worksheet = sh.sheet1
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Ensure critical columns exist
        required_cols = ["No", "Applied Date", "Company Name", "Job Title", 
                        "Status", "Job Location", "Coordinates"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""
        
        return df
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        return pd.DataFrame()

# ============================================================================
# DATA MASKING FOR PUBLIC USERS
# ============================================================================

def mask_sensitive_columns(df, tier):
    """
    Apply source-level masking based on user tier.
    Returns a masked dataframe that will be used for ALL UI components.
    """
    df_masked = df.copy()
    
    if tier == "public":
        # For public users, mask sensitive columns in the source data
        company_dummies = [
            "Top Fintech Company", "Leading Tech Corp", "Global Solutions Inc",
            "Innovation Hub Ltd", "Future Systems Co", "Digital Ventures LLC",
            "Enterprise Solutions", "NextGen Technologies", "Cloud Platform Inc",
            "AI Innovation Lab"
        ]
        
        job_title_dummies = [
            "Confidential Senior Role", "Strategic Position", "Key Technical Role",
            "Core Engineering Role", "Leadership Opportunity", "Specialist Position",
            "Advanced Technical Role", "Strategic Developer Position"
        ]
        
        if len(df_masked) > 0:
            # Mask Company Name
            if "Company Name" in df_masked.columns:
                for i in range(len(df_masked)):
                    df_masked.at[i, "Company Name"] = company_dummies[i % len(company_dummies)]
            
            # Mask Job Title
            if "Job Title" in df_masked.columns:
                for i in range(len(df_masked)):
                    df_masked.at[i, "Job Title"] = job_title_dummies[i % len(job_title_dummies)]
            
            # Mask Company Address
            if "Company Address" in df_masked.columns:
                df_masked["Company Address"] = "Confidential Location"
            
            # Mask Recruiter Info
            if "Recruiter Info" in df_masked.columns:
                df_masked["Recruiter Info"] = "[Hidden]"
            
            # Hide sensitive columns entirely for public tier
            cols_to_drop = []
            if "Salary Range" in df_masked.columns:
                cols_to_drop.append("Salary Range")
            if "Notes" in df_masked.columns:
                cols_to_drop.append("Notes")
            
            if cols_to_drop:
                df_masked = df_masked.drop(columns=cols_to_drop, errors='ignore')
    
    return df_masked


def get_edmonton_region(address):
    """Returns the region name by examining the company address."""
    if not address:
        return "Unknown"

    addr_clean = address.lower()

    if any(k in addr_clean for k in ["remote", "work from home", "wfh"]):
        return "Remote"

    if "st. albert" in addr_clean or re.search(r't8[nat]', addr_clean):
        return "St. Albert"
    if "sherwood park" in addr_clean or re.search(r't8[abgh]', addr_clean):
        return "Sherwood Park"
    if "leduc" in addr_clean or "nisku" in addr_clean or re.search(r't9e', addr_clean):
        return "Leduc"

    if re.search(r't5j|t5k|t5h', addr_clean):
        return "Downtown"
    if re.search(r't5p|t5s|t5t|t5m', addr_clean):
        return "West"
    if re.search(r't5v|t5x|t6v', addr_clean):
        return "Northwest"
    if re.search(r't5y|t5z|t5w', addr_clean):
        return "Northeast"
    if re.search(r't6b|t6c|t6e|t6k|t6l|t6p|t6t', addr_clean):
        return "Southeast"
    if re.search(r't6h|t6j|t6m|t6r|t6w|t6g', addr_clean):
        return "South"

    if "downtown" in addr_clean:
        return "Downtown"
    if "industrial" in addr_clean:
        return "Northwest"

    return "Edmonton (General)"


def calculate_distance_to_postal_code(lat, lon, postal_code):
    """
    Calculate distance from given coordinates to postal code using OSRM.
    Returns distance in kilometers.
    """
    try:
        # OSRM Open Source Routing Machine
        url = f"http://router.project-osrm.org/route/v1/driving/{lon},{lat};{postal_code}"
        # Note: This would need geocoding first. For demo, return None.
        # In production, you'd geocode the postal code to lat/lon first.
        return None
    except:
        return None

def geocode_postal_code(postal_code):
    """
    Geocode a postal code using Nominatim and return (latitude, longitude).
    """
    try:
        query = postal_code.strip()
        if not query:
            return None

        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "countrycodes": "ca",
            "limit": 1
        }
        headers = {"User-Agent": "JobTrackerApp"}
        response = requests.get(url, params=params, headers=headers, timeout=7)

        if response.status_code == 200:
            results = response.json()
            if results:
                result = results[0]
                return (float(result.get("lat")), float(result.get("lon")))
    except:
        pass
    return None


def get_postal_code_coordinates(postal_code):
    postal_code = (postal_code or "").strip()
    if not postal_code:
        return None

    if st.session_state.postal_code == postal_code and st.session_state.postal_code_coords is not None:
        return st.session_state.postal_code_coords

    coords = geocode_postal_code(postal_code)
    st.session_state.postal_code = postal_code
    st.session_state.postal_code_coords = coords
    return coords


def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate great-circle distance between two points on earth (in km).
    Note: This is straight-line distance, not road distance.
    """
    from math import radians, cos, sin, asin, sqrt
    
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

def apply_filters(df, search_company, search_title, filter_status, filter_location):
    """Apply search and filter options to dataframe"""
    df_filtered = df.copy()
    
    if search_company:
        df_filtered = df_filtered[
            df_filtered["Company Name"].str.contains(search_company, case=False, na=False)
        ]
    
    if search_title:
        df_filtered = df_filtered[
            df_filtered["Job Title"].str.contains(search_title, case=False, na=False)
        ]
    
    if filter_status and filter_status != "All":
        df_filtered = df_filtered[df_filtered["Status"] == filter_status]
    
    if filter_location and filter_location != "All":
        df_filtered = df_filtered[df_filtered["Job Location"] == filter_location]
    
    return df_filtered

def export_to_csv(df):
    """Export dataframe to CSV"""
    csv = df.to_csv(index=False)
    return csv


def parse_coordinates(coord_str):
    """Parse 'lat,lng' string to tuple"""
    try:
        if isinstance(coord_str, str) and coord_str.strip():
            parts = coord_str.split(",")
            if len(parts) == 2:
                return (float(parts[0].strip()), float(parts[1].strip()))
    except:
        pass
    return None

def generate_map(df, postal_code_coords=None, center_coords=None):
    """Generate Folium map with company locations and optional distance display."""
    # Filter out rows without coordinates
    df_with_coords = df[df["Coordinates"].notna() & (df["Coordinates"] != "")]
    
    if len(df_with_coords) == 0:
        st.info("📍 No location data available for map.")
        return None
    
    coords_list = [parse_coordinates(c) for c in df_with_coords["Coordinates"]]
    coords_list = [c for c in coords_list if c is not None]
    
    if not coords_list:
        st.info("📍 No valid coordinates found.")
        return None
    
    if center_coords:
        center_lat, center_lng = center_coords
        zoom_start = 13
    else:
        center_lat = sum([c[0] for c in coords_list]) / len(coords_list)
        center_lng = sum([c[1] for c in coords_list]) / len(coords_list)
        zoom_start = 12
    
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=zoom_start,
        tiles="OpenStreetMap"
    )
    
    if center_coords:
        folium.CircleMarker(
            location=center_coords,
            radius=10,
            color="black",
            fill=True,
            fill_color="yellow",
            fill_opacity=0.8,
            popup="Selected company"
        ).add_to(m)
    
    for idx, row in df_with_coords.iterrows():
        coords = parse_coordinates(row["Coordinates"])
        if coords:
            distance_text = ""
            if postal_code_coords:
                distance_km = calculate_haversine_distance(
                    coords[0], coords[1],
                    postal_code_coords[0], postal_code_coords[1]
                )
                distance_text = f"<br>Distance: {distance_km:.1f} km"
            
            popup_text = f"""
            <b>{row.get('Company Name', 'N/A')}</b><br>
            <i>{row.get('Job Title', 'N/A')}</i><br>
            Status: {row.get('Status', 'N/A')}<br>
            Location: {row.get('Job Location', 'N/A')}<br>
            Address: {row.get('Company Address', 'N/A')}{distance_text}
            """
            
            status_colors = {
                "Applied": "blue",
                "Rejected": "red",
                "Interviews": "orange",
                "Offers": "green"
            }
            color = status_colors.get(row.get("Status", "Applied"), "gray")
            
            folium.Marker(
                location=coords,
                popup=folium.Popup(popup_text, max_width=280),
                icon=folium.Icon(color=color, icon="briefcase")
            ).add_to(m)
    
    return m

# ============================================================================
# ANALYTICS
# ============================================================================

def get_summary_metrics(df):
    """Calculate summary metrics - dynamically count 'Applied' status"""
    if len(df) == 0:
        return {"applied": 0, "rejected": 0, "interviews": 0, "offers": 0}
    
    return {
        "applied": len(df[df["Status"] == "Applied"]),
        "rejected": len(df[df["Status"] == "Rejected"]),
        "interviews": len(df[df["Status"] == "Interviews"]),
        "offers": len(df[df["Status"] == "Offers"])
    }

def plot_location_distribution(df):
    """Plot the job location distribution as a pie chart."""
    if len(df) == 0 or "Job Location" not in df.columns:
        return None
    
    location_counts = df["Job Location"].value_counts()
    fig = px.pie(
        values=location_counts.values,
        names=location_counts.index,
        title="Applications by Job Location",
        color_discrete_sequence=px.colors.qualitative.Plotly
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation='h',
            y=-0.15,
            x=0.5,
            xanchor='center',
            yanchor='top',
            title_text=''   
        ),
        margin=dict(t=40, b=80)
    )
    return fig

def plot_applications_per_day(df):
    """Plot applications over time."""
    if len(df) == 0 or "Applied Date" not in df.columns:
        return None
    
    try:
        df_temp = df.copy()
        df_temp["Applied Date"] = pd.to_datetime(df_temp["Applied Date"], errors='coerce')
        df_temp = df_temp[df_temp["Applied Date"].notna()]
        
        if len(df_temp) == 0:
            return None
        
        daily_counts = df_temp.groupby(df_temp["Applied Date"].dt.date).size()
        fig = px.line(
            x=daily_counts.index,
            y=daily_counts.values,
            labels={"x": "Date", "y": "Applications"},
            title="Applications Over Time",
            markers=True
        )
        fig.update_yaxes(range=[0, max(0, daily_counts.max() + 1)])
        fig.update_layout(hovermode='closest')
        return fig
    except:
        return None

def plot_region_distribution(df):
    """Plot applications by Edmonton region."""
    if len(df) == 0 or "Company Address" not in df.columns:
        return None
    
    region_series = df["Company Address"].fillna("").apply(get_edmonton_region)
    region_counts = region_series.value_counts()
    fig = px.bar(
        x=region_counts.values,
        y=region_counts.index,
        labels={"x": "Applications", "y": "Region"},
        title="Applications by Regions",
        color=region_counts.index,
        color_discrete_sequence=px.colors.qualitative.Safe,
        orientation='h'
    )
    fig.update_layout(
        showlegend=False,
        xaxis_title="Applications",
        yaxis_title="Region",
        bargap=0.15,
        bargroupgap=0.1
    )
    return fig

# ============================================================================
# MAIN APP
# ============================================================================

def main():
    # Get sheet URL from secrets
    SHEET_URL = st.secrets.get("sheet_url")
    if not SHEET_URL:
        st.error("❌ Missing SHEET_URL in secrets.toml")
        return
    
    # Load data from Google Sheets
    df = load_data_from_sheets(SHEET_URL)
    
    if len(df) == 0:
        st.warning("⚠️ No data found in Google Sheet.")
        return
    
    # APPLY SOURCE-LEVEL MASKING BASED ON USER TIER
    df_to_use = mask_sensitive_columns(df, st.session_state.user_tier)

    # Apply filters and search values from the top menu
    search_company = st.session_state.search_company
    search_title = st.session_state.search_title
    filter_status = st.session_state.filter_status
    filter_location = st.session_state.filter_location

    if st.session_state.active_nav == "export":
        csv_data = export_to_csv(df_to_use)
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"job_applications_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    # Apply filters
    df_filtered = apply_filters(df_to_use, search_company, search_title,
                               filter_status, filter_location)

    # SUMMARY METRICS - Responsive layout
    st.markdown("<h3 style='text-align:center'>Summary Metrics</h3>", unsafe_allow_html=True)
    metrics = get_summary_metrics(df_filtered)
    
    st.markdown(
        f"""
        <div class="metrics-row">
            <div class="metric-card"><div class="metric-number">{metrics['applied']}</div><div class="metric-label">Applied</div></div>
            <div class="metric-card"><div class="metric-number">{metrics['rejected']}</div><div class="metric-label">Rejected</div></div>
            <div class="metric-card"><div class="metric-number">{metrics['interviews']}</div><div class="metric-label">Interviews</div></div>
            <div class="metric-card"><div class="metric-number">{metrics['offers']}</div><div class="metric-label">Offers</div></div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("---")
    
    # APPLICATION DETAILS SECTION
    st.markdown("### 📋 Application Details")
    
    # Two-column layout for table and map
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        # Privacy notice for public users
        if st.session_state.user_tier == "public":
            st.markdown(
                '<div class="privacy-notice"><strong>For public viewers:</strong> '
                'Company names and job titles are masked for privacy.<br>'
                'To access real data, please sign in as an admin or trusted viewer.</div>',
                unsafe_allow_html=True
            )
        
        # Display table with 1-based indexing and a dedicated "No." index label
        display_cols = ["Applied Date", "Company Name", "Job Title", "Status", "Company Address", "Job Location"]
        
        # Add optional columns only if present and allowed
        optional_cols = ["Salary Range", "Job Description"]
        for col in optional_cols:
            if col in df_filtered.columns and st.session_state.user_tier != "public":
                display_cols.append(col)

        display_cols = [col for col in display_cols if col in df_filtered.columns]

        df_filtered_reset = df_filtered.reset_index(drop=True)
        df_display = df_filtered_reset[display_cols].copy()
        df_display.index = df_display.index + 1
        df_display.index.name = "No."

        st.dataframe(df_display, use_container_width=True, height=420)

        selected_center_coords = None
        if len(df_display) > 0:
            selected_row_no = st.selectbox(
                "Center map on application row:",
                df_display.index,
                key="selected_row_no",
                format_func=lambda x: f"{x}: {df_display.loc[x, 'Company Name']}"
            )
            if selected_row_no and selected_row_no <= len(df_filtered_reset):
                selected_row = df_filtered_reset.iloc[selected_row_no - 1]
                selected_center_coords = parse_coordinates(selected_row.get("Coordinates", ""))
    
    with col2:
        # Location stats header and postal code input share a row
        stats_col, postal_col = st.columns([1, 1])
        total_with_coords = len(df_filtered[df_filtered["Coordinates"].notna() & 
                                            (df_filtered["Coordinates"] != "")])
        total_without_coords = len(df_filtered) - total_with_coords

        with stats_col:
            st.markdown(
                f'<div class="location-stats">'
                f'📍 {total_without_coords} jobs without locations<br>'
                f'📍 {total_with_coords} job locations in map'
                f'</div>',
                unsafe_allow_html=True
            )

        with postal_col:
            postal_code_input = st.text_input(
                "Enter Postal Code:",
                value=st.session_state.postal_code,
                placeholder="e.g., A1B 2C3",
                key="postal_input"
            )

        postal_code_coords = None
        if postal_code_input:
            with st.spinner("🔍 Geocoding postal code..."):
                postal_code_coords = get_postal_code_coordinates(postal_code_input)
                if postal_code_coords:
                    st.success(f"✅ Found: {postal_code_coords[0]:.4f}, {postal_code_coords[1]:.4f}")
                else:
                    st.warning("⚠️ Postal code not found")

        map_obj = generate_map(df_filtered, postal_code_coords, center_coords=selected_center_coords)
        if map_obj:
            st_folium(map_obj, width=420, height=420)
        else:
            st.info("📍 Add coordinates (Latitude,Longitude) to locations to see the map.")
    
    # ANALYTICS SECTION
    st.markdown("---")
    st.markdown("### 📈 Analytics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        fig = plot_location_distribution(df_filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True})
    
    with col2:
        fig = plot_applications_per_day(df_filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True})
    
    with col3:
        fig = plot_region_distribution(df_filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True})

if __name__ == "__main__":
    main()
