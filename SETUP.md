# Job Application Tracker - Setup Guide

A powerful Streamlit web app for tracking job applications with Google Sheets integration, role-based access control, and interactive analytics.

## 🚀 Quick Start

### 1. Clone and Install Dependencies

```bash
git clone <your-repo>
cd job-application-tracker
pip install -r requirements.txt
```

### 2. Set Up Google Sheets

#### Step A: Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: **Job Application Tracker**
3. Enable these APIs:
   - Google Sheets API
   - Google Drive API

#### Step B: Create a Service Account
1. In Google Cloud Console, go to **Service Accounts**
2. Click **Create Service Account**
3. Fill in the details:
   - Service account name: `job-tracker-app`
   - Click through and finish
4. Click the service account → **Keys tab**
5. **Create new key** → Choose **JSON**
6. A JSON file will download automatically - **keep it safe!**

#### Step C: Create Google Sheet
1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new spreadsheet titled "Job Applications"
3. Set up headers in Row 1:
```
No | Applied Date | Company Name | Job Title | Status | Company Address | Job Description | Job Location | Job ID | Salary Range | Recruiter Info | Notes | Coordinates
```

#### Step D: Share with Service Account
1. Open the JSON file you downloaded in Step B
2. Find the `client_email` field (looks like: `job-tracker-app@xxx.iam.gserviceaccount.com`)
3. In your Google Sheet, click **Share** button
4. Paste the service account email
5. Give it **Editor** access
6. Copy the **Share URL** of the spreadsheet (you'll need it for secrets.toml)

### 3. Configure Streamlit Secrets

Create a file `.streamlit/secrets.toml` in your project root:

```toml
# Google Sheets Configuration
sheet_url = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit#gid=0"

# Admin email (gets full editing access)
admin_email = "your.email@example.com"

# Trusted viewers (family members - read-only access)
# Use a list of emails
trusted_viewers = ["spouse@example.com", "brother@example.com"]

# Google Cloud Service Account (paste entire JSON)
[gcp_service_account]
type = "service_account"
project_id = "your-project-id-123"
private_key_id = "key-id-here"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "job-tracker-app@xxx.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/..."
```

**To extract the JSON content:**
1. Open the JSON key file downloaded from Google Cloud
2. Copy the entire content
3. In `secrets.toml`, replace `[gcp_service_account]` and paste the JSON structure
4. Convert the `private_key` field to have proper escape characters (usually done automatically)

### 4. Run the App

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

---

## 🔐 Authentication System (3 Tiers)

### Tier 1: Admin (You)
- **Login with**: Your email address (from `admin_email` in secrets.toml)
- **Access**: View all real data
- **Features**:
  - See actual company names and job titles
  - View all analytics and detailed data
  - Full data export capabilities
  - Access all sensitive information

**Admin Status Badge** 👑 (red)

### Tier 2: Trusted Viewers (Family)
- **Login with**: Emails listed in `trusted_viewers` in secrets.toml
- **Access**: View only (read-only)
- **Features**:
  - See actual company names and job titles
  - View all analytics and filtered data
  - Cannot modify or update anything
  - Cannot access admin-only features

**Viewer Status Badge** 👁️ (teal)

### Tier 3: Public (Recruiters/Others)
- **Access**: No login required
- **View**: Masked/dummy data only
  - Company names replaced with generic labels (e.g., "Top Fintech Company")
  - Job titles replaced with confidential titles
  - Addresses marked as "Confidential Location"
  - Other sensitive info hidden
  - Salary Range and Notes columns hidden entirely
- **Cannot**: Edit, export, or access any real data

**Public Status Badge** 🌐 (gray)

## 🔒 Data Security Implementation

**Source-Level Redaction**: All sensitive data is masked at the data pipeline level before being passed to any UI components. This ensures:
- The DataTable and Map components consume the same redacted data object
- Public viewers never have access to real company information in the DOM or state
- Sensitive columns (Salary Range, Notes) are removed entirely for public users
- Consistent data masking across all UI elements

## 🗺️ Geospatial Features

### Interactive Map with Distance Calculator
- Display company locations on an interactive Folium map
- Color-coded pins by application status
- **New**: Enter a postal code to calculate distance to each job location
- Distance displayed in popup when clicking a map pin
- Location statistics showing:
  - Number of jobs without location data
  - Number of jobs with valid coordinates on map

### How to Use the Distance Calculator
1. Locate the "Enter Postal Code" input above the map
2. Type your postal code (e.g., "94102" or "SW1A0AA")
3. The app geocodes your postal code and calculates distance to each job
4. Click any map pin to see the calculated distance
5. Distances are calculated as straight-line (haversine) distance in kilometers

---

## 🎨 UI/UX Improvements

### Horizontal Navigation Bar
- **Replaced**: Sidebar-based login with responsive horizontal top navigation
- **Login integration**: Email sign-in form in the top navigation (no sidebar cluttering)
- **User role badge**: Displays current role (Admin/Viewer/Public) aligned to the far right
- **Logout button**: Quick logout with icon button next to role badge
- **Responsive**: Adapts to desktop and mobile screens

### Section Headers & Layout
- **Application Details**: Single unified header for table + map section
- **Removed**: Redundant sub-headers and instructional clutter
- **Privacy Notice**: Moved above the table for public users with clear sign-in instructions

### Metrics Display
- **Responsive layout**: Desktop shows 4 metrics in one line (Applied — Rejected — Interviews — Offers)
- **Dynamic calculation**: "Applied" count is calculated by filtering rows where Status = "Applied"
- **Font sizing**: Metric labels are proportional to values (50%+ of number size) for better readability
- **Removed**: Redundant "Total Applied" and "Waiting" metrics

### Table Improvements
- **Removed**: "No." column for cleaner display
- **1-based indexing**: Row numbers start at 1 instead of 0 for user-friendly navigation
- **Column visibility**: Salary Range and Notes columns automatically hidden for public users
- **Optimized height**: Scroll-friendly display supports 500+ rows without performance issues
- **Privacy disclaimer**: Displayed above table for public users with sign-in call-to-action

### Map Enhancements
- **Location Statistics Header**: Shows "[X] jobs without locations" and "[Y] job locations in map"
- **Distance Calculator**: Postal code input with real-time geocoding via Nominatim
- **Interactive tooltips**: Map popups display calculated distances on click
- **Postal code support**: Works with formats like US zip codes (94102), UK postcodes (SW1A0AA), etc.

---

## 📊 Google Sheets Column Guide

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| **No** | Number | Optional | Row identifier |
| **Applied Date** | Date | Optional | When you applied (YYYY-MM-DD) |
| **Company Name** | Text | ✅ Required | Official company name |
| **Job Title** | Text | ✅ Required | Job position title |
| **Status** | Dropdown | ✅ Required | Applied / Rejected / Interviews / Offers |
| **Company Address** | Text | Optional | Full address (for map) |
| **Job Description** | Text | Optional | Job details |
| **Job Location** | Text | Optional | Remote / Hybrid / Onsite |
| **Job ID** | Text | Optional | Internal job ID |
| **Salary Range** | Text | Optional | e.g., "$100K - $150K" (hidden for public users) |
| **Recruiter Info** | Text | Optional | Recruiter name/email |
| **Notes** | Text | Optional | Personal notes (hidden for public users) |
| **Coordinates** | Text | Optional | "Latitude,Longitude" (e.g., "40.7128,-74.0060") |

### Getting Coordinates
To populate the **Coordinates** column for map display:
1. Search the company address on Google Maps
2. Right-click on the location
3. Copy the coordinates (latitude, longitude)
4. Paste in the format: `40.7128,-74.0060`

---

## ✨ App Features

### 📋 Application Management
- Display up to 500+ applications smoothly with st.dataframe()
- Search by company name
- Filter by job title
- Filter by status (Applied, Rejected, Interviews, Offers)
- Filter by job location (Remote, Hybrid, Onsite)
- 1-based row indexing for intuitive navigation
- Responsive layout: Side-by-side on desktop, stacked on mobile

### 🗺️ Interactive Map
- Displays company locations as color-coded markers
- Color-coded by status:
  - 🔵 Blue = Applied
  - 🔴 Red = Rejected
  - 🟠 Orange = Interviews
  - 🟢 Green = Offers
- **Distance Calculator**: Enter postal code to see distances to each job location
- Location statistics: Shows count of jobs with/without coordinates
- Click markers for company details
- Auto-centered on all locations

### 📈 Analytics Dashboard
- **Bar Chart**: Job location distribution (Remote/Hybrid/Onsite)
- **Line Chart**: Applications over time
- **Pie Chart**: Status distribution
- All charts update based on filtered data

### 💾 Data Export
- Download filtered data as CSV
- Filename includes current date
- One click from sidebar
- Public users cannot export data

### 📱 Responsive Design
- Optimized for desktop and mobile
- Horizontal top navigation (no sidebar clutter)
- Two-column layout on wide screens
- Single column on mobile (natural stacking)
- Clean, minimal UI with Streamlit defaults

---

## 🔑 Environment Variables

If deploying to Streamlit Cloud, add to **Settings → Secrets**:

```toml
sheet_url = "https://docs.google.com/spreadsheets/d/..."
admin_email = "your.email@example.com"
trusted_viewers = ["spouse@example.com", "brother@example.com"]

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
auth_uri = "..."
token_uri = "..."
auth_provider_x509_cert_url = "..."
client_x509_cert_url = "..."
```

---

## 🚀 Deployment to Streamlit Cloud

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Initial commit: Job Application Tracker"
git push origin main
```

### Step 2: Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **Deploy an app**
3. Select your repository
4. Enter repo details:
   - **Repository**: `ThucDao/job-application-tracker`
   - **Branch**: `main`
   - **Main file path**: `app.py`
5. Click **Deploy**

### Step 3: Add Secrets
1. In Streamlit Cloud dashboard, go to your app
2. Click **...** → **Edit secrets**
3. Paste your `.streamlit/secrets.toml` content
4. Save

Your app is now live! 🎉

---

## 🐛 Troubleshooting

### Error: "Missing SHEET_URL in secrets.toml"
- Ensure `.streamlit/secrets.toml` exists
- Verify `sheet_url` is correctly formatted
- Copy the full "Share URL" from your Google Sheet

### Error: "Failed to connect to Google Sheets"
- Confirm service account email is shared on the Google Sheet
- Check JSON key is valid and pasted correctly
- Ensure Google Sheets API is enabled in Google Cloud

### Map not showing
- Make sure rows have coordinates in "Latitude,Longitude" format
- Check coordinates are valid (latitude -90 to 90, longitude -180 to 180)
- Example: `40.7128,-74.0060`

### Status update not working
- Verify you're logged in as Admin
- Check that "Status" column exists in Google Sheet
- Ensure the new status matches a valid option

### Public user sees real data
- This shouldn't happen. Verify `st.session_state.user_tier == "public"` triggers masking
- Check that you haven't logged in with an admin/viewer email while testing

---

## 📝 Example Data

Here's a sample row to get started:

| No | Applied Date | Company Name | Job Title | Status | Company Address | Job Description | Job Location | Job ID | Salary Range | Recruiter Info | Notes | Coordinates |
|----|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-01-15 | Google | Senior Software Engineer | Interviews | 1600 Amphitheatre Pkwy, Mountain View, CA | Building scalable systems | Remote | G12345 | $180K - $220K | Sarah Chen | Great culture, fast process | 37.4224,-122.0842 |
| 2 | 2026-01-18 | Microsoft | Cloud Architect | Applied | One Microsoft Way, Redmond, WA | Cloud infrastructure design | Hybrid | MS67890 | $160K - $200K | John Smith | Follow up next week | 47.6739,-122.1305 |

---

## 📚 Tech Stack

- **Frontend**: Streamlit (Python web framework)
- **Database**: Google Sheets (via gspread API)
- **Authentication**: Email-based (simple, no OAuth)
- **Maps**: Folium + Streamlit-Folium with distance calculation
- **Charts**: Plotly Express
- **Geocoding**: Nominatim (OpenStreetMap) for postal code geocoding
- **Spreadsheet API**: gspread with Google OAuth2

---

## 💡 Tips & Best Practices

1. **Distance Calculator**: Postal codes are geocoded in real-time; be patient on first lookup
2. **Regular Backups**: Google Sheets auto-saves, but download CSVs regularly
3. **Date Format**: Use YYYY-MM-DD for consistent date parsing
4. **Coordinates**: Get them from Google Maps (right-click → copy coordinates)
5. **Status Names**: Keep them exactly as: "Applied", "Rejected", "Interviews", "Offers"
6. **Performance**: App caches data for 5 minutes; refresh manually if needed
7. **Mobile**: Two-column layout naturally stacks on mobile
8. **Data Privacy**: All sensitive data is masked at the source level for security

---

## 🆘 Support

If you encounter issues:
1. Check `.streamlit/secrets.toml` is in the right location
2. Verify Google Cloud credentials are valid
3. Clear browser cache and restart Streamlit app
4. Check Streamlit logs: `streamlit run app.py --logger.level=debug`

---

## 📄 License

This project is open source. Feel free to modify and share!

---

**Happy job hunting! 🎯**
