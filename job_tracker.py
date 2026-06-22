"""
Job Tracker — Main Orchestrator Custom Edition
Logs outputs into external dedicated sheets inside a targeted Drive directory.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials
from scraper import scrape_jobs
from notifier import send_email_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
PRIORITY_THRESHOLD = 8          
DAYS_LOOKBACK      = 2          
GEMINI_MODEL       = "gemini-2.5-flash" 

TAB_SOURCES  = "Sources"        
RESULTS_HEADERS = ["Date Logged", "Company", "Job Title", "Location", "Date Posted", "Score", "Priority", "URL", "Summary", "Score Reasoning"]

class JobEvaluation(BaseModel):
    score: int = Field(..., description="Score from 1 to 10 evaluating fit.")
    summary: str = Field(..., description="A one-sentence description of the role.")
    score_reason: str = Field(..., description="A one-sentence reason explaining the assigned score.")

def get_sheets_client() -> gspread.Client:
    creds_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def read_sources(sheet: gspread.Spreadsheet) -> list[dict]:
    ws = sheet.worksheet(TAB_SOURCES)
    rows = ws.get_all_values()
    sources = []
    for row in rows[1:]:          
        if row and len(row) > 1 and row[1].strip():
            sources.append({
                "label": row[0].strip(),
                "url":   row[1].strip()
            })
    return sources

def create_file_with_user_quota(gc: gspread.Client, name: str, folder_id: str, your_gmail: str) -> str:
    """Create a new spreadsheet directly in the shared folder, trying multiple methods."""
    try:
        # Primary method: Use gspread's built-in create method
        spreadsheet = gc.create(name, folder_id=folder_id)
        file_id = spreadsheet.id
        log.info(f"✅ Successfully created file '{name}' with ID: {file_id}")
        
        # Try to transfer ownership to your Gmail account
        if your_gmail:
            try:
                gc.share(file_id, your_gmail, perm_type='user', role='owner', notify=False)
                log.info(f"✅ Transferred ownership to {your_gmail}")
            except Exception as te:
                log.warning(f"Ownership transfer failed (file is still usable): {te}")
        
        return file_id

    except Exception as e:
        log.error(f"Error creating file {name}: {e}")
        
        # Fallback: Use raw Drive API
        try:
            body = {
                "name": name,
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "parents": [folder_id]
            }
            res = gc.http_client.request(
                "post", "https://www.googleapis.com/drive/v3/files", json=body
            ).json()
            file_id = res.get("id")
            if file_id:
                log.info(f"✅ Successfully created via raw API: {file_id}")
                return file_id
        except Exception as e2:
            log.error(f"Raw API also failed: {e2}")
        
        raise RuntimeError(f"Failed to create file '{name}'. Error: {e}") from e

def get_or_create_results_folder_and_files(gc: gspread.Client, source_spreadsheet_id: str):
    """Improved version that creates the 'Job listings' folder and daily files."""
    your_gmail = os.environ.get("GMAIL_SENDER")
    
    # Get the parent folder of the source spreadsheet
    meta = gc.get_file_drive_metadata(source_spreadsheet_id)
    parent_folder_id = meta.get("parents", [None])[0] or "root"

    # Find or create the "Job listings" folder
    query = f"name='Job listings' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent_folder_id}' in parents"
    folder_search = gc.http_client.request(
        "get", f"https://www.googleapis.com/drive/v3/files?q={quote_plus(query)}"
    ).json().get("files", [])

    if folder_search:
        folder_id = folder_search[0]["id"]
        log.info(f"Found existing 'Job listings' folder: {folder_id}")
    else:
        folder_body = {
            "name": "Job listings", 
            "mimeType": "application/vnd.google-apps.folder", 
            "parents": [parent_folder_id]
        }
        res = gc.http_client.request("post", "https://www.googleapis.com/drive/v3/files", json=folder_body).json()
        folder_id = res.get("id")
        log.info(f"✅ Created 'Job listings' folder: {folder_id}")
        
        if your_gmail:
            try:
                gc.share_file(folder_id, your_gmail, role='writer')
            except Exception as e:
                log.warning(f"Failed to share folder: {e}")

    # Define file names
    master_title = "All job listings"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_title = f"Jobs {today_str}"

    master_sheet = None
    daily_sheet = None

    # Search for existing files in the folder
    file_query = f"mimeType='application/vnd.google-apps.spreadsheet' and trashed=false and '{folder_id}' in parents"
    files = gc.http_client.request(
        "get", f"https://www.googleapis.com/drive/v3/files?q={quote_plus(file_query)}"
    ).json().get("files", [])

    for f in files:
        if f["name"] == master_title:
            master_sheet = gc.open_by_key(f["id"])
        elif f["name"] == daily_title:
            daily_sheet = gc.open_by_key(f["id"])

    # Create Master sheet if it doesn't exist
    if not master_sheet:
        fid = create_file_with_user_quota(gc, master_title, folder_id, your_gmail)
        master_sheet = gc.open_by_key(fid)
        master_sheet.sheet1.append_row(RESULTS_HEADERS, value_input_option="RAW")
        log.info(f"✅ Created Master sheet: {master_title}")

    # Create Daily sheet if it doesn't exist
    if not daily_sheet:
        fid = create_file_with_user_quota(gc, daily_title, folder_id, your_gmail)
        daily_sheet = gc.open_by_key(fid)
        daily_sheet.sheet1.append_row(RESULTS_HEADERS, value_input_option="RAW")
        log.info(f"✅ Created new Daily sheet: {daily_title}")

    return master_sheet.sheet1, daily_sheet.sheet1

def already_logged_master(ws: gspread.Worksheet, job_url: str) -> bool:
    try:
        urls = ws.col_values(8) 
        return job_url in urls
    except:
        return False

def append_to_worksheets(worksheets: list, jobs: list[dict]):
    if not jobs: return
    jobs_sorted = sorted(jobs, key=lambda j: (-j.get("score", 0), j.get("date_posted", "")))
    rows = []
    for j in jobs_sorted:
        rows.append([
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            j.get("company", ""), j.get("title", ""), j.get("location", ""), j.get("date_posted", ""),
            j.get("score", ""), "🔴 HIGH" if j.get("score", 0) >= PRIORITY_THRESHOLD else "—",
            j.get("url", ""), j.get("summary", ""), j.get("score_reason", "")
        ])
    for ws in worksheets:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        log.info(f"Appended records to worksheet: {ws.title}")

def score_job_with_gemini(client: genai.Client, job: dict, user_profile: str) -> dict:
    prompt = f"""You are a career advisor helping a job seeker evaluate roles.
## Candidate Profile
{user_profile}
## Job Listing
Company: {job.get('company', 'Unknown')} | Title: {job.get('title', '')} | Location: {job.get('location', '')}
Description: {job.get('description', '')}
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JobEvaluation,
                temperature=0.2
            ),
        )
        parsed = json.loads(response.text.strip())
        job["score"]        = int(parsed.get("score", 0))
        job["summary"]      = parsed.get("summary", "")
        job["score_reason"] = parsed.get("score_reason", "")
    except Exception as e:
        log.warning(f"Gemini evaluation failed for {job.get('title')}: {e}")
        job["score"], job["summary"], job["score_reason"] = 0, "", f"Scoring error: {e}"
    return job

def main():
    log.info("━━━ Starting Gemini Job Tracker (Root Deployment) ━━━")
    user_profile = os.environ.get("USER_PROFILE", "").strip()
    source_id = os.environ["GOOGLE_SPREADSHEET_ID"]
    
    gc = get_sheets_client()
    source_sheet = gc.open_by_key(source_id)
    sources = read_sources(source_sheet)
    
    master_ws, daily_ws = get_or_create_results_folder_and_files(gc, source_id)
    gemini_client = genai.Client()

    all_new_jobs = []
    for source in sources:
        log.info(f"Scraping: {source['url']}")
        try:
            jobs = scrape_jobs(source["url"], days_lookback=DAYS_LOOKBACK)
            log.info(f"  → Found {len(jobs)} recent listings")
        except Exception as e:
            log.error(f"  → Scrape failed: {e}")
            continue

        for job in jobs:
            if already_logged_master(master_ws, job.get("url", "")):
                log.info(f"  ↷ Already exists in master: {job.get('title')}")
                continue

            job = score_job_with_gemini(gemini_client, job, user_profile)
            log.info(f"  ✓ {job['title']} @ {job.get('company','?')} — Score: {job['score']}")
            all_new_jobs.append(job)
            time.sleep(0.5)

    if all_new_jobs:
        append_to_worksheets([master_ws, daily_ws], all_new_jobs)
        
    priority_jobs = [j for j in all_new_jobs if j.get("score", 0) >= PRIORITY_THRESHOLD]
    if priority_jobs: 
        log.info(f"Sending email digest for {len(priority_jobs)} items...")
        send_email_digest(priority_jobs)
    else:
        log.info("No high priority matches detected today.")

if __name__ == "__main__":
    main()