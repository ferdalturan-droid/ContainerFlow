"""ContainerFlow – Resend-backed transactional email service.

Sends two kinds of mails:
- Invitation (new account → user picks own password via /set-password?token=…)
- Password reset (user clicks Glemt adgangskode → token mail → /reset-password)

Resend's free/sandbox plan only lets you mail the verified account-owner address
until you verify a custom domain. The `EMAIL_OVERRIDE` env var lets us redirect
ALL outbound mail to a single inbox during testing while still showing the
original recipient in the body. Empty/unset = no override (production).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
SENDER_NAME = os.environ.get("SENDER_NAME", "ContainerFlow").strip()
EMAIL_OVERRIDE = os.environ.get("EMAIL_OVERRIDE", "").strip()
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")

# Resend SDK is a thin wrapper around a module-level api_key
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def _from_header() -> str:
    if SENDER_NAME:
        return f"{SENDER_NAME} <{SENDER_EMAIL}>"
    return SENDER_EMAIL


async def _send(to_email: str, subject: str, html: str, *, original_to: Optional[str] = None) -> dict:
    """Send via Resend in a thread (SDK is sync). Returns Resend response dict.

    If RESEND_API_KEY is empty we just log the mail body (so the user can copy
    the link from backend logs during local testing).
    """
    actual_to = EMAIL_OVERRIDE or to_email
    if EMAIL_OVERRIDE and EMAIL_OVERRIDE != to_email:
        # Make the override visible so the developer always knows who the mail
        # was *supposed* to go to.
        banner = (
            f'<div style="background:#fef3c7;border:1px solid #f59e0b;padding:10px 14px;'
            f'margin:0 0 16px;border-radius:8px;font-family:sans-serif;color:#92400e;font-size:13px;">'
            f'<strong>EMAIL_OVERRIDE aktiv</strong> – '
            f'denne mail var oprindeligt adresseret til <code>{to_email}</code>.</div>'
        )
        html = banner + html

    if not RESEND_API_KEY:
        logger.warning(
            "[EMAIL FALLBACK – no RESEND_API_KEY] would-have-sent to=%s subject=%s body=%s",
            actual_to, subject, html[:500],
        )
        return {"id": "mocked-no-api-key", "to": actual_to, "delivered": False}

    params = {
        "from": _from_header(),
        "to": [actual_to],
        "subject": subject,
        "html": html,
    }
    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Email sent via Resend: id=%s to=%s", resp.get("id"), actual_to)
        return resp
    except Exception as e:  # noqa: BLE001 – we want broad logging here
        logger.exception("Resend send failed (to=%s subject=%s): %s", actual_to, subject, e)
        # We do NOT raise — caller decides via response dict
        return {"id": None, "to": actual_to, "delivered": False, "error": str(e)}


# ---------- public API ----------

def _action_button(href: str, label: str) -> str:
    return (
        f'<a href="{href}" '
        f'style="display:inline-block;background:#10b981;color:#fff;padding:12px 28px;'
        f'border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">'
        f'{label}</a>'
    )


def _branded_shell(*, headline: str, body_html: str) -> str:
    """Minimal inline-styled HTML shell – emails MUST use inline CSS."""
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:28px 0;">
  <tr>
    <td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;overflow:hidden;">
        <tr>
          <td style="background:#0F172A;color:#ffffff;padding:18px 24px;">
            <div style="font-size:18px;font-weight:800;letter-spacing:.5px;">ContainerFlow</div>
            <div style="font-size:11px;color:#34d399;text-transform:uppercase;letter-spacing:1.5px;margin-top:2px;">Logistik & Genbrug</div>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 24px 12px;">
            <h1 style="margin:0 0 14px;font-size:22px;font-weight:800;">{headline}</h1>
            {body_html}
          </td>
        </tr>
        <tr>
          <td style="padding:18px 24px 28px;color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;">
            Denne mail blev sendt automatisk fra ContainerFlow. Hvis du ikke forventede den, kan du roligt ignorere den.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
""".strip()


async def send_invitation_email(
    *,
    to_email: str,
    name: str,
    token: str,
    company_name: str,
    role: str,
    company_type: str = "customer",  # "customer" | "logistics"
    ttl_hours: int = 72,
) -> dict:
    link = f"{APP_PUBLIC_URL}/set-password?token={token}"
    role_intro = {
        "logistics_admin": "logistik-administrator",
        "customer_admin": "kunde-administrator",
        "location_admin": "lokations-administrator",
        "order": "medarbejder",
        "driver": "chauffør",
        "super_admin": "system-ejer",
    }.get(role, "bruger")

    if company_type == "logistics":
        ctx_line = (
            f"Du er blevet inviteret som {role_intro} hos <strong>{company_name}</strong> – "
            f"logistik-partner i ContainerFlow-platformen."
        )
    else:
        ctx_line = (
            f"Du er blevet inviteret som {role_intro} hos <strong>{company_name}</strong> i ContainerFlow."
        )

    body = f"""
      <p style="font-size:15px;line-height:1.5;margin:0 0 12px;">Hej {name or 'der'},</p>
      <p style="font-size:15px;line-height:1.55;margin:0 0 20px;">
        {ctx_line} Klik på knappen herunder for at vælge din adgangskode og komme i gang.
      </p>
      <p style="margin:0 0 24px;">{_action_button(link, 'Sæt din adgangskode')}</p>
      <p style="font-size:13px;color:#475569;line-height:1.55;margin:0 0 8px;">
        Linket er gyldigt i <strong>{ttl_hours} timer</strong> og kan kun bruges én gang.
        Hvis linket er udløbet, kan din administrator gensende invitationen.
      </p>
      <p style="font-size:12px;color:#94a3b8;margin:18px 0 0;word-break:break-all;">
        Virker knappen ikke? Kopier dette link ind i din browser:<br>
        <a href="{link}" style="color:#10b981;">{link}</a>
      </p>
    """
    html = _branded_shell(headline="Velkommen til ContainerFlow", body_html=body)
    return await _send(to_email, f"Du er inviteret til ContainerFlow ({company_name})", html, original_to=to_email)


async def send_missing_clock_reminder_email(
    *,
    to_email: str,
    name: str,
    entries: list,
    days_back: int = 7,
) -> dict:
    """Send the weekly Sunday-evening reminder to a single driver that lists
    every "missing clock" entry (open IND with no UD) from the last `days_back`
    days. `entries` is a list of dicts with keys: date (YYYY-MM-DD), start_time
    (HH:MM), slice_type (work|pause).

    The mail intentionally keeps the formatting compact — drivers read these
    on their phone right after a long shift.
    """
    if not entries:
        # Should never be called with empty list, but guard anyway.
        return {"id": None, "to": to_email, "delivered": False, "skipped": "no_entries"}

    # Sort newest → oldest so most recent forgetfuls show first.
    rows = sorted(entries, key=lambda e: (e.get("date") or "", e.get("start_time") or ""), reverse=True)
    row_html = "".join([
        f"<tr>"
        f"<td style='padding:8px 10px;border-bottom:1px solid #e2e8f0;font-size:14px;color:#0f172a;'>"
        f"{e.get('date') or '—'}"
        f"</td>"
        f"<td style='padding:8px 10px;border-bottom:1px solid #e2e8f0;font-size:14px;color:#0f172a;font-variant-numeric:tabular-nums;'>"
        f"{e.get('start_time') or '—'}"
        f"</td>"
        f"<td style='padding:8px 10px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;'>"
        f"{'Pause' if (e.get('slice_type') == 'pause') else 'Arbejde'}"
        f"</td>"
        f"</tr>"
        for e in rows
    ])

    link = f"{APP_PUBLIC_URL}/" if APP_PUBLIC_URL else "#"
    body = f"""
      <p style="font-size:15px;line-height:1.55;margin:0 0 12px;">Hej {name or 'der'},</p>
      <p style="font-size:15px;line-height:1.55;margin:0 0 18px;">
        Vi har bemærket at du har <strong>{len(rows)}</strong> uafsluttet
        {'stempling' if len(rows) == 1 else 'stemplinger'} fra de seneste {days_back} dage —
        altså IND uden tilhørende UD. Lønberegningen kan ikke afsluttes før de er rettet.
      </p>
      <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin:0 0 22px;">
        <thead>
          <tr style="background:#f8fafc;">
            <th style="padding:10px;text-align:left;font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.5px;">Dato</th>
            <th style="padding:10px;text-align:left;font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.5px;">IND kl.</th>
            <th style="padding:10px;text-align:left;font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.5px;">Type</th>
          </tr>
        </thead>
        <tbody>{row_html}</tbody>
      </table>
      <p style="margin:0 0 22px;">{_action_button(link, 'Åbn ContainerFlow og ret nu')}</p>
      <p style="font-size:13px;color:#475569;line-height:1.55;margin:0 0 8px;">
        Log ind, gå til <strong>Min tidsregistrering</strong> og brug
        <em>"Manuel stempel"</em> for at tilføje det manglende UD-tidspunkt.
      </p>
      <p style="font-size:12px;color:#94a3b8;margin:18px 0 0;">
        Du modtager denne mail automatisk hver søndag aften kl. 18:00 sålænge du har
        uafsluttede stemplinger. Når alle stempler er rettet, holder påmindelserne op.
      </p>
    """
    subject = f"Manglende stempel — {len(rows)} {'registrering' if len(rows) == 1 else 'registreringer'} mangler at blive lukket"
    html = _branded_shell(headline="Manglende stempling i denne uge", body_html=body)
    return await _send(to_email, subject, html, original_to=to_email)


async def send_password_reset_email(
    *, to_email: str, name: str, token: str, ttl_hours: int = 72,
) -> dict:
    link = f"{APP_PUBLIC_URL}/reset-password?token={token}"
    body = f"""
      <p style="font-size:15px;line-height:1.5;margin:0 0 12px;">Hej {name or 'der'},</p>
      <p style="font-size:15px;line-height:1.55;margin:0 0 20px;">
        Vi har modtaget en forespørgsel om at nulstille din adgangskode på ContainerFlow.
        Klik på knappen herunder for at vælge en ny adgangskode.
      </p>
      <p style="margin:0 0 24px;">{_action_button(link, 'Vælg ny adgangskode')}</p>
      <p style="font-size:13px;color:#475569;line-height:1.55;margin:0 0 8px;">
        Linket er gyldigt i <strong>{ttl_hours} timer</strong> og kan kun bruges én gang.
      </p>
      <p style="font-size:13px;color:#475569;line-height:1.55;margin:0 0 12px;">
        Har du <strong>ikke</strong> selv anmodet om nulstilling, kan du roligt ignorere denne mail – din nuværende kode er stadig gyldig.
      </p>
      <p style="font-size:12px;color:#94a3b8;margin:18px 0 0;word-break:break-all;">
        Virker knappen ikke? Kopier dette link ind i din browser:<br>
        <a href="{link}" style="color:#10b981;">{link}</a>
      </p>
    """
    html = _branded_shell(headline="Nulstil din adgangskode", body_html=body)
    return await _send(to_email, "Nulstil din adgangskode – ContainerFlow", html, original_to=to_email)
