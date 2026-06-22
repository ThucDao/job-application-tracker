"""
Unified scraper — detects the job board type from the URL and
dispatches to the right strategy. Returns a normalised list of job dicts.
"""

import re
import time
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlencode, urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}
TIMEOUT = 20

def is_recent(date_str: str, days: int) -> bool:
    if not date_str:
        return True   
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except ValueError:
        pass
    lower = date_str.lower()
    if any(x in lower for x in ["just now", "today", "hour", "minute", "second"]):
        return True
    m = re.search(r"(\d+)\s+day", lower)
    if m:
        return int(m.group(1)) <= days
    return True   

def normalize_date(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    now = datetime.now(timezone.utc)
    lower = raw.lower()
    if any(x in lower for x in ["just now", "today", "less than"]):
        return now.strftime("%Y-%m-%d")
    if "hour" in lower or "minute" in lower or "second" in lower:
        return now.strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s+day", lower)
    if m:
        return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    return raw

def fetch(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp

def detect_board(url: str) -> str:
    host = urlparse(url).hostname or ""
    if "linkedin.com" in host: return "linkedin"
    if "indeed.com" in host: return "indeed"
    if "jobbank.gc.ca" in host or "job-bank" in host: return "jobbank"
    return "generic"

def scrape_linkedin(url: str, days: int) -> list[dict]:
    jobs = []
    if "f_TPR" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "f_TPR=r172800"
    try:
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.base-card, li.jobs-search-results__list-item, .job-search-card")
        for card in cards:
            title_el    = card.select_one("h3.base-search-card__title, .job-search-card__title, h3")
            company_el  = card.select_one("h4.base-search-card__subtitle, .job-search-card__company-name, h4")
            location_el = card.select_one(".job-search-card__location, .base-search-card__metadata")
            date_el     = card.select_one("time")
            link_el     = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
            date_raw  = date_el.get("datetime", "") if date_el else ""
            date_norm = normalize_date(date_raw)
            if not is_recent(date_norm, days): continue
            job_url = link_el["href"].split("?")[0] if link_el else url
            jobs.append({
                "title":       title_el.get_text(strip=True) if title_el else "",
                "company":     company_el.get_text(strip=True) if company_el else "",
                "location":    location_el.get_text(strip=True) if location_el else "",
                "date_posted": date_norm,
                "url":         job_url,
                "description": "",
            })
    except Exception as e: log.error(f"LinkedIn error: {e}")
    return jobs

def scrape_indeed(url: str, days: int) -> list[dict]:
    jobs = []
    if "fromage" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "fromage=2"
    try:
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.job_seen_beacon, .jobsearch-SerpJobCard, [data-jk]")
        for card in cards:
            title_el    = card.select_one("h2.jobTitle span[title], h2.jobTitle")
            company_el  = card.select_one("[data-testid='company-name'], .companyName")
            location_el = card.select_one("[data-testid='text-location'], .companyLocation")
            date_el     = card.select_one("[data-testid='myJobsStateDate'], .date")
            link_el     = card.select_one("h2.jobTitle a, a[id^='job_']")
            date_raw  = date_el.get_text(strip=True) if date_el else ""
            date_norm = normalize_date(date_raw)
            if not is_recent(date_norm, days): continue
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"): href = "https://ca.indeed.com" + href
            jobs.append({
                "title":       title_el.get_text(strip=True) if title_el else "",
                "company":     company_el.get_text(strip=True) if company_el else "",
                "location":    location_el.get_text(strip=True) if location_el else "",
                "date_posted": date_norm,
                "url":         href,
                "description": "",
            })
    except Exception as e: log.error(f"Indeed error: {e}")
    return jobs

def scrape_jobbank(url: str, days: int) -> list[dict]:
    jobs = []
    try:
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article.resultJobItem")
        for art in articles:
            title_el    = art.select_one("span.noctitle, h3.title")
            company_el  = art.select_one("li.business span")
            location_el = art.select_one("li.location span")
            date_el     = art.select_one("li.date span")
            link_el     = art.select_one("a[href]")
            date_raw  = date_el.get_text(strip=True) if date_el else ""
            date_norm = normalize_date(date_raw)
            if not is_recent(date_norm, days): continue
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"): href = "https://www.jobbank.gc.ca" + href
            jobs.append({
                "title":       title_el.get_text(strip=True) if title_el else "",
                "company":     company_el.get_text(strip=True) if company_el else "",
                "location":    location_el.get_text(strip=True) if location_el else "",
                "date_posted": date_norm,
                "url":         href,
                "description": "",
            })
    except Exception as e: log.error(f"JobBank error: {e}")
    return jobs

def scrape_generic(url: str, days: int) -> list[dict]:
    jobs = []
    try:
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        selectors = [
            "li[class*='job']", "div[class*='job-card']", "div[class*='job_card']",
            "article[class*='job']", "div[class*='posting']", "tr[class*='job']",
        ]
        cards = []
        for sel in selectors:
            found = soup.select(sel)
            if found:
                cards = found
                break
        if not cards:
            all_links = soup.find_all("a", href=True)
            for a in all_links:
                href = a["href"]
                text = a.get_text(strip=True)
                if any(kw in href.lower() for kw in ["job", "career", "position", "opening"]) and len(text) > 5:
                    full_url = href if href.startswith("http") else urljoin(url, href)
                    jobs.append({
                        "title":       text,
                        "company":     urlparse(url).hostname or "",
                        "location":    "",
                        "date_posted": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "url":         full_url,
                        "description": "",
                    })
            return jobs
        for card in cards:
            title_el    = card.find(["h1","h2","h3","h4"], string=True)
            link_el     = card.find("a", href=True)
            date_el     = card.find("time") or card.find(class_=re.compile(r"date|posted|time", re.I))
            date_raw  = (date_el.get("datetime") or date_el.get_text(strip=True)) if date_el else ""
            date_norm = normalize_date(date_raw)
            if date_raw and not is_recent(date_norm, days): continue
            href = link_el["href"] if link_el else url
            if href and not href.startswith("http"): href = urljoin(url, href)
            jobs.append({
                "title":       title_el.get_text(strip=True) if title_el else card.get_text(" ", strip=True)[:80],
                "company":     urlparse(url).hostname or "",
                "location":    "",
                "date_posted": date_norm or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "url":         href,
                "description": card.get_text(" ", strip=True)[:1000],
            })
    except Exception as e: log.error(f"Generic error: {e}")
    return jobs

def enrich_description(job: dict) -> dict:
    if job.get("description") or not job.get("url"): return job
    try:
        resp = fetch(job["url"])
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style"]): tag.decompose()
        body = soup.find("main") or soup.find("article") or soup.body
        if body: job["description"] = body.get_text(" ", strip=True)[:3000]
    except: pass
    return job

def scrape_jobs(url: str, days_lookback: int = 2) -> list[dict]:
    board = detect_board(url)
    dispatch = {
        "linkedin": scrape_linkedin, 
        "indeed": scrape_indeed,
        "jobbank": scrape_jobbank
    }
    jobs = dispatch.get(board, scrape_generic)(url, days_lookback)
    return [enrich_description(j) for j in jobs]
