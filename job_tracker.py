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

def get_job_listings_file(gc: gspread.Client, source_spreadsheet_id: str):
    """Open the existing master sheet named 'All job listings'.

    This searches for a folder named 'Job listings' inside the same parent
    folder as the source spreadsheet (the folder that contains the Sources sheet).
    """
    log.info(f"Source spreadsheet ID: {source_spreadsheet_id}")

    # Get the first parent folder of source spreadsheet (same folder as Sources sheet)
    meta = gc.get_file_drive_metadata(source_spreadsheet_id)
    parent = meta.get("parents", [None])[0] or "root"
    log.info(f"Source spreadsheet parent folder ID: {parent}")

    # Search for "Job listings" folder inside that parent folder only
    folder_query = f"name='Job listings' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent}' in parents"
    log.info(f"Searching for 'Job listings' in parent {parent}")
    fs = gc.http_client.request(
        "get", f"https://www.googleapis.com/drive/v3/files?q={quote_plus(folder_query)}"
    ).json().get("files", [])
    log.info(f"Folder search returned {len(fs)} results for parent {parent}")

    if not fs:
        raise RuntimeError(f"Folder 'Job listings' not found in the same folder as the source spreadsheet (parent {parent}). Please create it there.")

    folder_id = fs[0]["id"]
    log.info(f"Found 'Job listings' folder with ID: {folder_id}")

    # Search for "All job listings" spreadsheet in the Job listings folder
    sheet_query = f"name='All job listings' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false and '{folder_id}' in parents"
    log.info(f"Searching for 'All job listings' spreadsheet in folder {folder_id}")
    sheet_search = gc.http_client.request(
        "get", f"https://www.googleapis.com/drive/v3/files?q={quote_plus(sheet_query)}"
    ).json().get("files", [])

    log.info(f"Spreadsheet search returned {len(sheet_search)} results in folder {folder_id}")
    if not sheet_search:
        raise RuntimeError(f"Spreadsheet 'All job listings' not found in the 'Job listings' folder {folder_id}. Please verify it exists in that folder.")

    file_id = sheet_search[0]["id"]
    log.info(f"Found 'All job listings' spreadsheet with ID: {file_id}")
    master_sheet = gc.open_by_key(file_id)
    return master_sheet.sheet1

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
    # Log actual opened sheet id to avoid using a malformed env var
    opened_id = getattr(source_sheet, 'id', None)
    log.info(f"Opened source spreadsheet id: {opened_id}")
    sources = read_sources(source_sheet)

    # Pass the opened spreadsheet id (may be different from env value)
    master_ws = get_job_listings_file(gc, opened_id)
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
        append_to_worksheets([master_ws], all_new_jobs)
        
    priority_jobs = [j for j in all_new_jobs if j.get("score", 0) >= PRIORITY_THRESHOLD]
    if priority_jobs: 
        log.info(f"Sending email digest for {len(priority_jobs)} items...")
        send_email_digest(priority_jobs)
    else:
        log.info("No high priority matches detected today.")

if __name__ == "__main__":
    main()
