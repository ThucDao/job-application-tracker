"""
Email notifier — sends a nicely-formatted HTML digest of high-priority jobs.
Uses Gmail SMTP with an App Password (no OAuth needed).
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def build_html(jobs: list[dict]) -> str:
    date_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y")

    rows = ""
    for j in jobs:
        score = j.get("score", 0)
        color = "#1a7f37" if score >= 9 else "#0969da"
        rows += f"""
        <tr>
          <td style="padding:16px;border-bottom:1px solid #e8e8e8;">
            <div style="font-size:17px;font-weight:600;margin-bottom:4px;">
              <a href="{j.get('url','')}" style="color:#0969da;text-decoration:none;">
                {j.get('title','(No title)')}
              </a>
            </div>
            <div style="color:#57606a;font-size:13px;margin-bottom:8px;">
              🏢 {j.get('company','?')} &nbsp;·&nbsp;
              📍 {j.get('location','?')} &nbsp;·&nbsp;
              📅 Posted: {j.get('date_posted','?')}
            </div>
            <div style="margin-bottom:6px;font-size:14px;color:#24292f;">
              {j.get('summary','')}
            </div>
            <div style="font-size:13px;color:#57606a;">
              <span style="background:{color};color:#fff;
                           padding:2px 8px;border-radius:12px;font-weight:600;">
                ★ {score}/10
              </span>
              &nbsp; {j.get('score_reason','')}
            </div>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f6f8fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8fa;padding:32px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
             style="background:#fff;border:1px solid #d0d7de;border-radius:12px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:#0969da;padding:24px 32px;">
            <div style="color:#fff;font-size:22px;font-weight:700;">🎯 Top Job Matches Today</div>
            <div style="color:#cae8ff;font-size:13px;margin-top:4px;">{date_str}</div>
          </td>
        </tr>

        <!-- Summary bar -->
        <tr>
          <td style="background:#ddf4ff;padding:12px 32px;
                     color:#0969da;font-size:14px;font-weight:600;
                     border-bottom:1px solid #d0d7de;">
            {len(jobs)} high-priority role{"s" if len(jobs)!=1 else ""} scored 8+ out of 10 today
          </td>
        </tr>

        <!-- Job rows -->
        <table width="100%" cellpadding="0" cellspacing="0">
          {rows}
        </table>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px;background:#f6f8fa;
                     color:#57606a;font-size:12px;
                     border-top:1px solid #d0d7de;">
            Scored by Gemini · All results logged in your Google Sheet ·
            <a href="https://github.com" style="color:#0969da;">View workflow</a>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email_digest(jobs: list[dict]) -> None:
    sender    = os.environ["GMAIL_SENDER"]       
    password  = os.environ["GMAIL_APP_PASSWORD"]  
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 {len(jobs)} Top Job Match{'es' if len(jobs)!=1 else ''} — {datetime.now(timezone.utc).strftime('%b %d')}"
    msg["From"]    = sender
    msg["To"]      = recipient

    # Plain text fallback
    plain = f"Top Job Matches — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
    for j in jobs:
        plain += (
            f"[{j.get('score',0)}/10] {j.get('title','')} @ {j.get('company','')}\n"
            f"  {j.get('location','')} · Posted {j.get('date_posted','')}\n"
            f"  {j.get('url','')}\n"
            f"  {j.get('summary','')}\n\n"
        )

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(build_html(jobs), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())
        log.info(f"Email sent to {recipient}")
    except Exception as e:
        log.error(f"Email failed: {e}")
        raise
