"""Email adapter (T11). Resend when configured; dev-log otherwise.

The invite flow never blocks on email delivery — failures are logged and the
candidacy stays valid (the link is retrievable from the dashboard)."""

import logging

import httpx

from app.config import get_settings

log = logging.getLogger("notify")


def send_email(to: str, subject: str, html: str) -> bool:
    settings = get_settings()
    if not settings.resend_api_key:
        log.info("[dev email] to=%s subject=%r (RESEND_API_KEY unset — not sent)", to, subject)
        return False
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("email send failed to %s: %s", to, exc)
        return False


def invite_email_html(candidate_name: str, org_name: str, link: str) -> str:
    return f"""
    <div style="font-family:system-ui;max-width:560px;margin:auto">
      <h2>You're invited to interview with {org_name}</h2>
      <p>Hi {candidate_name},</p>
      <p>{org_name} has invited you to an AI-conducted interview. You'll pick a
      time that works for you, review exactly what is recorded and analyzed,
      and give your consent before anything starts.</p>
      <p><a href="{link}" style="background:#2f6fed;color:#fff;padding:10px 22px;
      border-radius:8px;text-decoration:none">Schedule your interview</a></p>
      <p style="color:#667">This link is personal to you and expires per the
      security policy shown on the scheduling page.</p>
    </div>
    """
