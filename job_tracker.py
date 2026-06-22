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

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import gspread
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

def get_or_create_results_folder_and_files(gc: gspread.Client, source_spreadsheet_id: str):
    """Finds or creates a 'Job listings' directory at the same level as the source sheet, then initializes target sheets."""
    your_gmail = os.environ.get("GMAIL_SENDER")
    
    # 1. Get the parent folder ID of the source file
    meta = gc.get_file_drive_metadata(source_spreadsheet_id)
    parents = meta.get("parents", [])
    parent_folder_id = parents[0] if parents else "root"

    # 2. Find or create the 'Job listings' folder
    folder_id = None
    query = f"name = 'Job listings' and mimeType = 'application/vnd.google-apps.folder' and trashed = false and '{parent_folder_id}' in parents"
    
    # Drive API direct query via gspread client
    folder_search = gc.http_client.request(
        "get", 
        f"https://www.googleapis.com/drive/v3/files?q={query}"
    ).json().get("files", [])
    
    if folder_search:
        folder_id = folder_search[0]["id"]
        log.info(f"Found existing 'Job listings' folder with ID: {folder_id}")
    else:
        # Construct directory metadata payload
        body = {
            "name": "Job listings",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id]
        }
        res = gc.http_client.request(
            "post",
            "https://www.googleapis.com/drive/v3/files",
            json=body
        ).json()
        folder_id = res.get("id")
        log.info(f"Created new 'Job listings' folder with ID: {folder_id}")
        
        # Share folder with user if ownership transfer can't be done directly on folder metadata
        if your_gmail:
            try:
                gc.share_file(folder_id, your_gmail, perm_type='user', role='writer')
            except Exception as e:
                log.warning(f"Failed to share directory with user: {e}")

    master_title = "All job listings"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_title = f"Jobs {today_str}"
    
    master_sheet = None
    daily_sheet = None
    
    # 3. Search for target tracking sheets inside the specific target folder directory location
    file_query = f"mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false and '{folder_id}' in parents"
    file_search = gc.http_client.request(
        "get",
        f"https://www.googleapis.com/drive/v3/files?q={file_query}"
    ).json().get("files", [])
    
    for f in file_search:
        if f["name"] == master_title:
            master_sheet = gc.open_by_key(f["id"])
        if f["name"] == daily_title:
            daily_sheet = gc.open_by_key(f["id"])
            
    # 4. Initialize files inside the folder if missing, transferring ownership to clear quota limits
    if not master_sheet:
        master_sheet = gc.create(master_title, folder_id=folder_id)
        if your_gmail:
            try:
                master_sheet.share(your_gmail, perm_type='user', role='owner', transfer_ownership=True)
                log.info(f"Transferred ownership of '{master_title}' to {your_gmail}")
            except Exception as e:
                log.warning(f"Could not transfer owner for master sheet: {e}. Sharing as editor instead.")
                master_sheet.share(your_gmail, perm_type='user', role='writer')
        
        ws = master_sheet.get_worksheet(0)
        ws.append_row(RESULTS_HEADERS, value_input_option="RAW")
        log.info(f"Created system wide target file inside folder: {master_title}")
        
    if not daily_sheet:
        daily_sheet = gc.create(daily_title, folder_id=folder_id)
        if your_gmail:
            try:
                daily_sheet.share(your_gmail, perm_type='user', role='owner', transfer_ownership=True)
                log.info(f"Transferred ownership of '{daily_title}' to {your_gmail}")
            except Exception as e:
                log.warning(f"Could not transfer owner for daily sheet: {e}. Sharing as editor instead.")
                daily_sheet.share(your_gmail, perm_type='user', role='writer')
                
        ws = daily_sheet.get_worksheet(0)
        ws.append_row(RESULTS_HEADERS, value_input_option="RAW")
        log.info(f"Created isolated diary record file inside folder: {daily_title}")
        
    return master_sheet.get_worksheet(0), daily_sheet.get_worksheet(0)

def already_logged_master(ws: gspread.Worksheet, job_url: str) -> bool:
    try:
        urls = ws.col_values(8) # Column H = URL
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