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
st.set_page_config(
    page_title="Job Application Tracker",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS for better UI with horizontal nav
st.markdown("""
    <style>
    .top-navbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 15px 20px;
        background-color: #f0f2f6;
        border-bottom: 2px solid #e0e4e8;
        margin-bottom: 20px;
        border-radius: 5px;
    }
    .title-section {
        display: flex;
        align-items: center;
        gap: 15px;
    }
    .admin-badge {
        background-color: #ff6b6b;
        color: white;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
    }
    .viewer-badge {
        background-color: #4ecdc4;
        color: white;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
    }
    .public-badge {
        background-color: #95a5a6;
        color: white;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
    }
    .metric-label {
        font-size: 14px !important;
        font-weight: 600;
    }
    .privacy-notice {
        background-color: #fff3cd;
        border: 1px solid #ffc107;
        padding: 12px;
        border-radius: 5px;
        margin-bottom: 15px;
        color: #333;
    }
    .location-stats {
        background-color: #e8f4f8;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: 500;
    }
    </style>
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
if "distances" not in st.session_state:
    st.session_state.distances = {}

# Role configuration
ADMIN_EMAIL = st.secrets.get("admin_email", "admin@example.com")
TRUSTED_VIEWERS = st.secrets.get("trusted_viewers", [])
if isinstance(TRUSTED_VIEWERS, str):
    TRUSTED_VIEWERS = [TRUSTED_VIEWERS]

def authenticate_user(email):
    """Authenticate user by email"""
    if email == ADMIN_EMAIL:
        st.session_state.user_tier = "admin"
        st.session_state.user_email = email
        st.session_state.authenticated = True
        return True
    elif email in TRUSTED_VIEWERS:
        st.session_state.user_tier = "trusted_viewer"
        st.session_state.user_email = email
        st.session_state.authenticated = True
        return True
    return False

def logout():
    """Logout function"""
    st.session_state.user_tier = None
    st.session_state.user_email = None
    st.session_state.authenticated = False
    st.rerun()

# TOP NAVIGATION BAR
col_nav1, col_nav2, col_nav3 = st.columns([2, 3, 1])

with col_nav1:
    st.markdown("### 📋 Job Application Tracker")

with col_nav2:
    if not st.session_state.authenticated:
        with st.form("login_form_inline"):
            email = st.text_input("Sign in with email:", key="login_email", placeholder="your.email@gmail.com")
            submit_col = st.columns([1, 4])
            with submit_col[0]:
                submit = st.form_submit_button("Sign In", use_container_width=True)
            
            if submit and email:
                if authenticate_user(email):
                    st.success(f"✅ Logged in!")
                    st.rerun()
                else:
                    st.error("❌ Email not recognized. Viewing as Public User.")

with col_nav3:
    if st.session_state.authenticated:
        badge_col, logout_col = st.columns([2, 1])
        with badge_col:
            if st.session_state.user_tier == "admin":
                st.markdown('<span class="admin-badge">👑 ADMIN</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="viewer-badge">👁️ VIEWER</span>', unsafe_allow_html=True)
        with logout_col:
            if st.button("🚪", help="Logout"):
                logout()
    else:
        st.markdown('<span class="public-badge">🌐 PUBLIC</span>', unsafe_allow_html=True)

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
    Geocode postal code to latitude and longitude using Nominatim API.
    Returns (latitude, longitude) or None.
    """
    try:
        url = f"https://nominatim.openstreetmap.org/search?postalcode={postal_code}&format=json"
        headers = {"User-Agent": "JobTrackerApp"}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200 and len(response.json()) > 0:
            result = response.json()[0]
            return (float(result.get("lat")), float(result.get("lon")))
    except:
        pass
    return None

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

def generate_map(df, postal_code_coords=None):
    """Generate Folium map with company locations and optional distance display"""
    # Filter out rows without coordinates
    df_with_coords = df[df["Coordinates"].notna() & (df["Coordinates"] != "")]
    
    if len(df_with_coords) == 0:
        st.info("📍 No location data available for map.")
        return None
    
    # Calculate center (average of all coordinates)
    coords_list = [parse_coordinates(c) for c in df_with_coords["Coordinates"]]
    coords_list = [c for c in coords_list if c is not None]
    
    if not coords_list:
        st.info("📍 No valid coordinates found.")
        return None
    
    center_lat = sum([c[0] for c in coords_list]) / len(coords_list)
    center_lng = sum([c[1] for c in coords_list]) / len(coords_list)
    
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=12,
        tiles="OpenStreetMap"
    )
    
    # Add markers
    for idx, row in df_with_coords.iterrows():
        coords = parse_coordinates(row["Coordinates"])
        if coords:
            # Calculate distance if postal code provided
            distance_text = ""
            if postal_code_coords:
                distance_km = calculate_haversine_distance(
                    coords[0], coords[1],
                    postal_code_coords[0], postal_code_coords[1]
                )
                distance_text = f"<br>Distance: {distance_km:.1f} km"
            
            popup_text = f"""
            <b>{row.get('Company Name', 'N/A')}</b><br>
            {row.get('Job Title', 'N/A')}<br>
            Status: {row.get('Status', 'N/A')}<br>
            Location: {row.get('Job Location', 'N/A')}{distance_text}
            """
            
            # Color code by status
            status_colors = {
                "Applied": "blue",
                "Rejected": "red",
                "Interviews": "orange",
                "Offers": "green"
            }
            color = status_colors.get(row.get("Status", "Applied"), "gray")
            
            folium.Marker(
                location=coords,
                popup=folium.Popup(popup_text, max_width=250),
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
    """Plot job location distribution"""
    if len(df) == 0 or "Job Location" not in df.columns:
        return None
    
    location_counts = df["Job Location"].value_counts()
    fig = px.bar(
        x=location_counts.index,
        y=location_counts.values,
        labels={"x": "Job Location", "y": "Count"},
        title="Job Applications by Location Type",
        color=location_counts.values,
        color_continuous_scale="Viridis"
    )
    return fig

def plot_applications_per_day(df):
    """Plot applications over time"""
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
        return fig
    except:
        return None

def plot_status_distribution(df):
    """Plot status distribution"""
    if len(df) == 0 or "Status" not in df.columns:
        return None
    
    status_counts = df["Status"].value_counts()
    fig = px.pie(
        values=status_counts.values,
        names=status_counts.index,
        title="Application Status Distribution"
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
    
    # SIDEBAR FILTERS (collapsible)
    with st.sidebar:
        st.markdown("### 🔍 Search & Filter")
        search_company = st.text_input("🏢 Search Company:", "")
        search_title = st.text_input("💼 Search Job Title:", "")
        filter_status = st.selectbox(
            "📊 Filter by Status:",
            ["All", "Applied", "Rejected", "Interviews", "Offers"]
        )
        filter_location = st.selectbox(
            "📍 Filter by Location:",
            ["All", "Remote", "Hybrid", "Onsite"]
        )
        
        st.markdown("---")
        
        # Export button
        csv_data = export_to_csv(df_to_use)
        st.download_button(
            label="📥 Export to CSV",
            data=csv_data,
            file_name=f"job_applications_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    # Apply filters
    df_filtered = apply_filters(df_to_use, search_company, search_title, 
                               filter_status, filter_location)
    
    # SUMMARY METRICS - Responsive layout
    st.markdown("### 📊 Summary Metrics")
    metrics = get_summary_metrics(df_filtered)
    
    # Check screen size and adjust layout
    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("Applied", metrics["applied"])
    with metric_cols[1]:
        st.metric("Rejected", metrics["rejected"])
    with metric_cols[2]:
        st.metric("Interviews", metrics["interviews"])
    with metric_cols[3]:
        st.metric("Offers", metrics["offers"])
    
    st.markdown("---")
    
    # APPLICATION DETAILS SECTION
    st.markdown("### 📋 Application Details")
    
    # Two-column layout for table and map
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        # Privacy notice for non-admin users
        if st.session_state.user_tier == "public":
            st.markdown(
                '<div class="privacy-notice">ℹ️ <strong>Privacy Notice:</strong> '
                'Company names and job titles are masked for privacy.<br>'
                'To access real data, please sign in as an admin or trusted viewer.</div>',
                unsafe_allow_html=True
            )
        
        # Display table with 1-based indexing (remove "No." column if it exists)
        display_cols = ["Applied Date", "Company Name", "Job Title", 
                      "Status", "Job Location"]
        
        # Add optional columns only if present
        optional_cols = ["Salary Range", "Notes", "Job Description", "Recruiter Info"]
        for col in optional_cols:
            if col in df_filtered.columns:
                # Only show Salary Range and Notes for non-public users
                if st.session_state.user_tier != "public":
                    display_cols.append(col)
        
        # Filter to available columns
        display_cols = [col for col in display_cols if col in df_filtered.columns]
        
        # Create 1-based index
        df_display = df_filtered[display_cols].reset_index(drop=True)
        df_display.index = df_display.index + 1
        df_display.index.name = "Index"
        
        st.dataframe(df_display, use_container_width=True, height=500)
    
    with col2:
        # Location stats header
        total_with_coords = len(df_filtered[df_filtered["Coordinates"].notna() & 
                                            (df_filtered["Coordinates"] != "")])
        total_without_coords = len(df_filtered) - total_with_coords
        
        st.markdown(
            f'<div class="location-stats">'
            f'📍 {total_without_coords} jobs without locations<br>'
            f'📍 {total_with_coords} job locations in map'
            f'</div>',
            unsafe_allow_html=True
        )
        
        # Postal code distance calculator
        postal_code_input = st.text_input(
            "Enter Postal Code:",
            value=st.session_state.postal_code,
            placeholder="e.g., 94102 or SW1A0AA",
            key="postal_input"
        )
        
        postal_code_coords = None
        if postal_code_input and postal_code_input != st.session_state.postal_code:
            st.session_state.postal_code = postal_code_input
            with st.spinner("🔍 Geocoding postal code..."):
                postal_code_coords = geocode_postal_code(postal_code_input)
                if postal_code_coords:
                    st.success(f"✅ Found: {postal_code_coords[0]:.4f}, {postal_code_coords[1]:.4f}")
                else:
                    st.warning("⚠️ Postal code not found")
        elif st.session_state.postal_code:
            postal_code_coords = geocode_postal_code(st.session_state.postal_code)
        
        # Generate and display map
        map_obj = generate_map(df_filtered, postal_code_coords)
        if map_obj:
            st_folium(map_obj, width=450, height=500)
        else:
            st.info("📍 Add coordinates (Latitude,Longitude) to locations to see the map.")
    
    # ANALYTICS SECTION
    st.markdown("---")
    st.markdown("### 📈 Analytics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        fig = plot_location_distribution(df_filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = plot_applications_per_day(df_filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    
    with col3:
        fig = plot_status_distribution(df_filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
