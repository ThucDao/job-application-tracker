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

# ============================================================================
# PAGE CONFIG & STYLING
# ============================================================================
st.set_page_config(
    page_title="Job Application Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better UI
st.markdown("""
    <style>
    .metric-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #f0f2f6;
    }
    .admin-badge {
        background-color: #ff6b6b;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
        font-size: 12px;
    }
    .viewer-badge {
        background-color: #4ecdc4;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
        font-size: 12px;
    }
    .public-badge {
        background-color: #95a5a6;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
        font-size: 12px;
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

# Role configuration
ADMIN_EMAIL = st.secrets.get("admin_email", "admin@example.com")
TRUSTED_VIEWERS = st.secrets.get("trusted_viewers", [])
# Ensure TRUSTED_VIEWERS is a list
if isinstance(TRUSTED_VIEWERS, str):
    TRUSTED_VIEWERS = [TRUSTED_VIEWERS]

def authenticate_user():
    """Simple email-based authentication"""
    with st.sidebar.form("login_form"):
        st.markdown("### 🔐 Authentication")
        email = st.text_input("Enter your email:", key="login_email")
        submit = st.form_submit_button("Login")
        
        if submit and email:
            if email == ADMIN_EMAIL:
                st.session_state.user_tier = "admin"
                st.session_state.user_email = email
                st.session_state.authenticated = True
                st.success("✅ Logged in as Admin")
                st.rerun()
            elif email in TRUSTED_VIEWERS:
                st.session_state.user_tier = "trusted_viewer"
                st.session_state.user_email = email
                st.session_state.authenticated = True
                st.success("✅ Logged in as Trusted Viewer")
                st.rerun()
            else:
                st.error("❌ Email not recognized. Access as Public User.")

def logout():
    """Logout function"""
    st.session_state.user_tier = None
    st.session_state.user_email = None
    st.session_state.authenticated = False
    st.rerun()

# Check if user is not authenticated, default to public tier
if not st.session_state.authenticated:
    authenticate_user()
    st.session_state.user_tier = "public"
else:
    if st.sidebar.button("🚪 Logout"):
        logout()

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

def update_status_in_sheets(sheet_url, row_num, new_status):
    """Update application status in Google Sheets (Admin only)"""
    try:
        if st.session_state.user_tier != "admin":
            st.error("❌ Only admins can update statuses.")
            return False
        
        gc = get_gsheet_connection()
        if gc is None:
            return False
        
        sh = gc.open_by_url(sheet_url)
        worksheet = sh.sheet1
        
        # Find the Status column index
        headers = worksheet.row_values(1)
        status_col = headers.index("Status") + 1
        
        # Update the specific cell (row_num + 1 because rows are 1-indexed in Sheets)
        worksheet.update_cell(row_num + 1, status_col, new_status)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error updating status: {e}")
        return False

# ============================================================================
# DATA MASKING FOR PUBLIC USERS
# ============================================================================

def mask_data_for_public(df):
    """Replace sensitive data for public viewers"""
    df_masked = df.copy()
    
    # Mapping for realistic dummy values
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
    
    return df_masked

# ============================================================================
# FILTERING & SEARCH
# ============================================================================

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

# ============================================================================
# EXPORT FUNCTION
# ============================================================================

def export_to_csv(df):
    """Export dataframe to CSV"""
    csv = df.to_csv(index=False)
    return csv

# ============================================================================
# MAP GENERATION
# ============================================================================

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

def generate_map(df):
    """Generate Folium map with company locations"""
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
            popup_text = f"""
            <b>{row.get('Company Name', 'N/A')}</b><br>
            {row.get('Job Title', 'N/A')}<br>
            Status: {row.get('Status', 'N/A')}<br>
            Location: {row.get('Job Location', 'N/A')}
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
    """Calculate summary metrics"""
    if len(df) == 0:
        return {"total": 0, "waiting": 0, "rejected": 0, "interviews": 0, "offers": 0}
    
    return {
        "total": len(df),
        "waiting": len(df[df["Status"] == "Applied"]),
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
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("📋 Job Application Tracker")
    with col2:
        if st.session_state.authenticated:
            if st.session_state.user_tier == "admin":
                st.markdown('<span class="admin-badge">👑 ADMIN</span>', 
                           unsafe_allow_html=True)
            else:
                st.markdown('<span class="viewer-badge">👁️ VIEWER</span>', 
                           unsafe_allow_html=True)
        else:
            st.markdown('<span class="public-badge">🌐 PUBLIC</span>', 
                       unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Search & Filter")
    
    # Get sheet URL from secrets
    SHEET_URL = st.secrets.get("sheet_url")
    if not SHEET_URL:
        st.error("❌ Missing SHEET_URL in secrets.toml")
        return
    
    # Load data
    df = load_data_from_sheets(SHEET_URL)
    
    if len(df) == 0:
        st.warning("⚠️ No data found in Google Sheet.")
        return
    
    # Show login info
    st.sidebar.markdown("---")
    if st.session_state.authenticated:
        st.sidebar.success(f"✅ Logged in as:\n{st.session_state.user_email}\n"
                          f"Tier: {st.session_state.user_tier.upper()}")
    else:
        st.sidebar.info("🌐 Viewing as Public User\n(Data is masked for privacy)")
    
    # Apply data masking for public users
    if st.session_state.user_tier == "public":
        df_display = mask_data_for_public(df)
    else:
        df_display = df.copy()
    
    # Filters in sidebar
    search_company = st.sidebar.text_input("🏢 Search Company:", "")
    search_title = st.sidebar.text_input("💼 Search Job Title:", "")
    filter_status = st.sidebar.selectbox(
        "📊 Filter by Status:",
        ["All", "Applied", "Rejected", "Interviews", "Offers"]
    )
    filter_location = st.sidebar.selectbox(
        "📍 Filter by Location:",
        ["All", "Remote", "Hybrid", "Onsite"]
    )
    
    # Apply filters
    df_filtered = apply_filters(df_display, search_company, search_title, 
                               filter_status, filter_location)
    
    # Export button
    st.sidebar.markdown("---")
    csv_data = export_to_csv(df_filtered)
    st.sidebar.download_button(
        label="📥 Export to CSV",
        data=csv_data,
        file_name=f"job_applications_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
    
    # Summary Metrics
    st.markdown("### 📊 Summary Metrics")
    metrics = get_summary_metrics(df_filtered)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📨 Total Applied", metrics["total"])
    with col2:
        st.metric("⏳ Waiting", metrics["waiting"])
    with col3:
        st.metric("📞 Interviews", metrics["interviews"])
    with col4:
        st.metric("🎉 Offers", metrics["offers"])
    with col5:
        st.metric("❌ Rejected", metrics["rejected"])
    
    st.markdown("---")
    
    # Main content - Two columns layout
    st.markdown("### 📋 Applications & 🗺️ Map")
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        st.markdown("#### Applications Table")
        
        # Display table with editing capability for admin
        if st.session_state.user_tier == "admin":
            st.info("💡 **Tip**: Click the checkbox to select rows and update status below.")
            
            # Create a display-only version first
            display_cols = ["No", "Applied Date", "Company Name", "Job Title", 
                          "Status", "Job Location", "Salary Range", "Notes"]
            display_cols = [col for col in display_cols if col in df_filtered.columns]
            st.dataframe(df_filtered[display_cols], use_container_width=True)
            
            # Admin update section
            st.markdown("#### ✏️ Update Status (Admin Only)")
            
            if len(df_filtered) > 0:
                row_num = st.selectbox(
                    "Select application to update:",
                    range(len(df_filtered)),
                    format_func=lambda i: f"{df_filtered.iloc[i]['Company Name']} - "
                                         f"{df_filtered.iloc[i]['Job Title']}"
                )
                
                current_status = df_filtered.iloc[row_num]["Status"]
                new_status = st.selectbox(
                    "New Status:",
                    ["Applied", "Rejected", "Interviews", "Offers"],
                    index=["Applied", "Rejected", "Interviews", "Offers"].index(current_status)
                    if current_status in ["Applied", "Rejected", "Interviews", "Offers"] else 0
                )
                
                if st.button("🔄 Update Status", type="primary"):
                    # Get actual row number in original dataframe
                    actual_row = df[
                        (df["Company Name"] == df_filtered.iloc[row_num]["Company Name"]) &
                        (df["Job Title"] == df_filtered.iloc[row_num]["Job Title"])
                    ].index[0]
                    
                    if update_status_in_sheets(SHEET_URL, actual_row, new_status):
                        st.success(f"✅ Status updated to '{new_status}'!")
                        st.rerun()
        else:
            # Read-only view for non-admin users
            display_cols = ["No", "Applied Date", "Company Name", "Job Title", 
                          "Status", "Job Location", "Salary Range", "Notes"]
            display_cols = [col for col in display_cols if col in df_filtered.columns]
            st.dataframe(df_filtered[display_cols], use_container_width=True, height=500)
            
            if st.session_state.user_tier == "public":
                st.caption("ℹ️ Company names and job titles are masked for privacy.")
    
    with col2:
        st.markdown("#### 📍 Application Locations Map")
        
        # Generate map based on actual data (not masked)
        map_obj = generate_map(df)
        if map_obj:
            st_folium(map_obj, width=450, height=500)
        else:
            st.info("📍 Add coordinates (Latitude,Longitude) to locations to see the map.")
    
    # Analytics section
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
