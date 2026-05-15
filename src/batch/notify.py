"""Email notifications for batch completion."""

from __future__ import annotations

import json
import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "notify-config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_notify_config() -> dict:
    cfg = _load_config()
    return {
        "recipients": cfg.get("recipients", os.environ.get("TAGENT_NOTIFY_EMAILS", "nitesh@tagent.club,tech@tagent.club")),
        "subject_template": cfg.get("subject_template", "[Tagent] Batch ready — {founder} ({posts} posts)"),
        "body_header": cfg.get("body_header", "Batch Ready"),
        "body_footer": cfg.get("body_footer", ""),
        "enabled": cfg.get("enabled", True),
    }


def update_notify_config(updates: dict) -> dict:
    cfg = _load_config()
    for key in ("recipients", "subject_template", "body_header", "body_footer", "enabled"):
        if key in updates:
            cfg[key] = updates[key]
    _save_config(cfg)
    return get_notify_config()


def send_batch_notification(
    founder_slug: str,
    total_posts: int,
    trigger: str,
    schedule_id: str | None = None,
) -> None:
    host = os.environ.get("TAGENT_SMTP_HOST", "")
    user = os.environ.get("TAGENT_SMTP_USER", "")
    password = os.environ.get("TAGENT_SMTP_PASS", "")
    if not host or not user or not password:
        logger.debug("[notify] SMTP not configured, skipping email notification")
        return

    cfg = get_notify_config()
    if not cfg.get("enabled", True):
        logger.debug("[notify] Notifications disabled in config")
        return

    recipients = [e.strip() for e in cfg["recipients"].split(",") if e.strip()]
    if not recipients:
        return

    founder_name = founder_slug.replace("_", " ").title()
    now_ist = datetime.now(IST)
    now_str = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    date_str = now_ist.strftime("%Y-%m-%d")
    trigger_label = {"scheduled": "Scheduled", "direct": "Direct run", "run-now": "Manual (Run Now)"}.get(trigger, trigger)

    subdomain = founder_slug.replace("_", "-")
    batch_link = f"https://tagent.club/admin/founders/{founder_slug}"
    founder_link = f"https://{subdomain}.tagent.club"

    subject = cfg.get("subject_template", "[Tagent] Batch ready — {founder} ({posts} posts)").format(
        founder=founder_name, posts=total_posts, trigger=trigger_label, date=date_str,
    )

    header = cfg.get("body_header", "Batch Ready")
    footer = cfg.get("body_footer", "")
    footer_html = f'<div style="margin-top: 12px; font-size: 12px; color: #666;">{footer}</div>' if footer else ""

    html = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
  <div style="background: #0a0a0a; border-radius: 12px; padding: 24px; color: #e4e4e7;">
    <h2 style="margin: 0 0 16px; font-size: 18px; color: #fff;">{header}</h2>
    <table style="width: 100%; font-size: 14px; line-height: 1.8;">
      <tr><td style="color: #888; padding-right: 16px;">Founder</td><td style="color: #fff; font-weight: 600;">{founder_name}</td></tr>
      <tr><td style="color: #888; padding-right: 16px;">Posts</td><td style="color: #4ade80; font-weight: 600;">{total_posts}</td></tr>
      <tr><td style="color: #888; padding-right: 16px;">Trigger</td><td>{trigger_label}</td></tr>
      {"<tr><td style='color: #888; padding-right: 16px;'>Schedule</td><td>" + schedule_id + "</td></tr>" if schedule_id else ""}
      <tr><td style="color: #888; padding-right: 16px;">Time</td><td>{now_str}</td></tr>
    </table>
    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid #222; display: flex; gap: 16px;">
      <a href="{batch_link}" style="color: #60a5fa; text-decoration: none; font-size: 13px;">View Batch &rarr;</a>
      <a href="{founder_link}" style="color: #a78bfa; text-decoration: none; font-size: 13px;">{founder_name}'s Portal &rarr;</a>
      <a href="https://tagent.club/admin" style="color: #888; text-decoration: none; font-size: 13px;">Admin</a>
    </div>
    {footer_html}
  </div>
</div>"""

    plain = f"{header}: {founder_name} — {total_posts} posts ({trigger_label}) at {now_str}\nView batch: {batch_link}"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        port = int(os.environ.get("TAGENT_SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, recipients, msg.as_string())

        logger.info("[notify] Sent batch notification for %s (%d posts) to %s", founder_slug, total_posts, recipients)
    except Exception:
        logger.warning("[notify] Failed to send email notification", exc_info=True)
