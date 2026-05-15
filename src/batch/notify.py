"""Email notifications for batch completion."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_SMTP_HOST = lambda: os.environ.get("TAGENT_SMTP_HOST", "")
_SMTP_PORT = lambda: int(os.environ.get("TAGENT_SMTP_PORT", "587"))
_SMTP_USER = lambda: os.environ.get("TAGENT_SMTP_USER", "")
_SMTP_PASS = lambda: os.environ.get("TAGENT_SMTP_PASS", "")
_NOTIFY_EMAILS = lambda: os.environ.get("TAGENT_NOTIFY_EMAILS", "nitesh@tagent.club,tech@tagent.club")


def send_batch_notification(
    founder_slug: str,
    total_posts: int,
    trigger: str,
    schedule_id: str | None = None,
) -> None:
    host = _SMTP_HOST()
    user = _SMTP_USER()
    password = _SMTP_PASS()
    if not host or not user or not password:
        logger.debug("[notify] SMTP not configured, skipping email notification")
        return

    recipients = [e.strip() for e in _NOTIFY_EMAILS().split(",") if e.strip()]
    if not recipients:
        return

    founder_name = founder_slug.replace("_", " ").title()
    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    trigger_label = {"scheduled": "Scheduled", "direct": "Direct run", "run-now": "Manual (Run Now)"}.get(trigger, trigger)

    subject = f"[Tagent] Batch ready — {founder_name} ({total_posts} posts)"

    html = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
  <div style="background: #0a0a0a; border-radius: 12px; padding: 24px; color: #e4e4e7;">
    <h2 style="margin: 0 0 16px; font-size: 18px; color: #fff;">Batch Ready</h2>
    <table style="width: 100%; font-size: 14px; line-height: 1.8;">
      <tr><td style="color: #888;">Founder</td><td style="color: #fff; font-weight: 600;">{founder_name}</td></tr>
      <tr><td style="color: #888;">Posts</td><td style="color: #4ade80; font-weight: 600;">{total_posts}</td></tr>
      <tr><td style="color: #888;">Trigger</td><td>{trigger_label}</td></tr>
      {"<tr><td style='color: #888;'>Schedule</td><td>" + schedule_id + "</td></tr>" if schedule_id else ""}
      <tr><td style="color: #888;">Time</td><td>{now_ist}</td></tr>
    </table>
    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid #222;">
      <a href="https://tagent.club/admin" style="color: #60a5fa; text-decoration: none; font-size: 13px;">Open Admin Dashboard &rarr;</a>
    </div>
  </div>
</div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(f"Batch ready: {founder_name} — {total_posts} posts ({trigger_label}) at {now_ist}", "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(host, _SMTP_PORT(), timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, recipients, msg.as_string())

        logger.info("[notify] Sent batch notification for %s (%d posts) to %s", founder_slug, total_posts, recipients)
    except Exception:
        logger.warning("[notify] Failed to send email notification", exc_info=True)
