# 📋 Job Application Tracker

A powerful Streamlit web app for tracking job applications with **Google Sheets integration**, **role-based access control**, **geospatial features**, and **interactive analytics**.

## ✨ Features

### 🔐 3-Tier Authentication System
- **Admin (You)**: Full access - see real company names and job titles; view all data
- **Trusted Viewers (Family)**: Read-only access; see real data but cannot modify
- **Public (Recruiters)**: No login; see masked/dummy data for privacy protection

### 🔒 Data Security & Masking
- **Source-level redaction**: Sensitive data is masked at the data pipeline level before reaching any UI components
- **Column visibility control**: Salary Range and Notes columns are hidden from public users
- Company names masked as "Top Fintech Company", "Leading Tech Corp", etc.
- Job titles masked as "Confidential Senior Role", "Strategic Position", etc.
- Addresses masked as "Confidential Location"
- Both DataTable and Map consume the same redacted data for consistency

### 📊 Dashboard & Analytics
- Summary metrics: Applied, Rejected, Interviews, Offers
- Responsive metric display: 1-line on desktop, 2-lines on mobile
- Interactive charts: Location distribution, applications over time, status breakdown
- Real-time data sync with Google Sheets

### 🗺️ Interactive Map with Geospatial Features
- Company locations displayed on Folium map
- Color-coded markers by application status (Blue/Red/Orange/Green)
- Click markers for company details
- Auto-centered on all locations
- **Distance Calculator**: Enter postal code to calculate road distance to each job
- Location Statistics: Shows count of jobs with/without coordinates

### 📋 Application Management
- Responsive horizontal navigation bar with login
- Search by company name or job title
- Filter by status and job location
- Support for 500+ applications (optimized with st.dataframe)
- 1-based table indexing for better readability
- Export filtered data to CSV with one click
- Privacy disclaimer for public users

### 📱 Responsive Design
- Two-column layout on desktop (table + map)
- Mobile-friendly stacking
- Horizontal top navigation (no sidebar clutter)
- Clean, minimal UI using Streamlit defaults

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Google Sheets & Service Account
Follow the detailed setup guide in [SETUP.md](SETUP.md)

### 3. Configure Secrets
Create `.streamlit/secrets.toml` with your Google Sheets URL and service account credentials (see [example.secrets.toml](example.secrets.toml))

### 4. Run the App
```bash
streamlit run app.py
```

Visit `http://localhost:8501` in your browser.

## 📚 Documentation

- **[SETUP.md](SETUP.md)** - Complete setup guide with Google Sheets integration
- **[example.secrets.toml](example.secrets.toml)** - Example secrets configuration

## 🛠️ Tech Stack

- **Frontend**: Streamlit
- **Database**: Google Sheets (via gspread)
- **Maps**: Folium + Streamlit-Folium
- **Charts**: Plotly Express
- **Authentication**: Email-based (simple, no OAuth)

## 📖 Google Sheets Columns

| Column | Type | Required |
|--------|------|----------|
| No | Number | Optional |
| Applied Date | Date | Optional |
| Company Name | Text | ✅ |
| Job Title | Text | ✅ |
| Status | Dropdown | ✅ |
| Company Address | Text | Optional |
| Job Description | Text | Optional |
| Job Location | Text | Optional |
| Job ID | Text | Optional |
| Salary Range | Text | Optional |
| Recruiter Info | Text | Optional |
| Notes | Text | Optional |
| Coordinates | Text | Optional |

## 🔑 Environment Variables

Create `.streamlit/secrets.toml`:
```toml
sheet_url = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
admin_email = "your.email@gmail.com"
trusted_viewers = ["spouse@gmail.com", "brother@gmail.com"]

[gcp_service_account]
# Paste your Google Cloud service account JSON here
type = "service_account"
project_id = "..."
...
```

## 🚀 Deployment

Deploy to Streamlit Cloud:
1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Select your repository and deploy
4. Add secrets in Streamlit Cloud dashboard

See [SETUP.md](SETUP.md) for detailed deployment instructions.

## 💡 Usage Tips

1. **Get Coordinates**: Right-click location on Google Maps → copy lat/lng coordinates
2. **Date Format**: Use YYYY-MM-DD for consistent parsing
3. **Status Values**: Use exactly "Applied", "Rejected", "Interviews", or "Offers"
4. **Admin Updates**: Only admins can change application status; changes sync instantly
5. **Data Privacy**: Public users see masked data; real data is secure

## 🆘 Troubleshooting

See [SETUP.md](SETUP.md) for troubleshooting guide.

---

**Happy job hunting! 🎯**