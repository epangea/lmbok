# ============================================================
# FreqLearn — utils/email.py
# Thin wrapper around the host's sendmail binary.
# No external libraries required; the droplet's MTA is already
# configured with valid DNS (SPF/DKIM/DMARC).
# ============================================================

import os
import hashlib
import subprocess
from email.message import EmailMessage
from html import escape as _esc
from typing import Optional


_SENDMAIL = "/usr/sbin/sendmail"
_FROM     = os.getenv("FREQLEARN_MAIL_FROM", "epangea.info@gmail.com")
_REPLY_TO = os.getenv("FREQLEARN_MAIL_REPLY_TO", "epangea.info@gmail.com")

# Same base URL auth.py's verification email already builds links against
# (FREQLEARN_VERIFY_URL_BASE) -- reused here so the unsubscribe link points
# at the live site without a second env var to keep in sync.
_APP_BASE_URL = os.getenv("FREQLEARN_VERIFY_URL_BASE", "https://build.onehouse.top")
# Reuses auth.py's existing JWT_SECRET rather than adding a new env var --
# this isn't a JWT, just an HMAC-style stamp, but the secret only needs to
# be "known only to the server," which JWT_SECRET already satisfies.
_UNSUB_SECRET = os.getenv("JWT_SECRET", "change-this-in-production-please")


def send_mail(
    to: str,
    subject: str,
    body: str,
    *,
    reply_to: Optional[str] = None,
    html: Optional[str] = None,
    list_unsubscribe_url: Optional[str] = None,
) -> None:
    """
    Send a plain-text (and optional HTML) email via the local MTA.
    Raises RuntimeError if sendmail is missing or returns non-zero.

    list_unsubscribe_url: pass this only for bulk/subscription mail (the
    newsletter) -- it's what unsubscribe_link() below already builds.
    Adds RFC 8058 List-Unsubscribe + List-Unsubscribe-Post headers, which
    is what lets Gmail/Yahoo/etc. show their own one-click "Unsubscribe"
    button next to the sender name instead of relying on the reader to
    find the footer link -- meaningfully better for spam/deliverability
    scoring than the footer link alone. Leave unset for transactional
    mail (verification, org match notices, admin one-off messages) --
    there's no subscription relationship there for a mail client to
    offer to cancel.
    """
    if not os.path.isfile(_SENDMAIL):
        raise RuntimeError(f"sendmail binary not found at {_SENDMAIL}")

    msg = EmailMessage()
    msg["From"]    = _FROM
    msg["To"]      = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply_to or _REPLY_TO
    if list_unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{list_unsubscribe_url}>"
        # One-Click (RFC 8058) tells the mail client it can POST the
        # unsubscribe itself with no confirmation page -- the POST route
        # in auth.py (unsubscribe_newsletter_one_click) is what answers it.
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        proc = subprocess.run(
            [_SENDMAIL, "-i", "-f", _FROM, "-t"],
            input=msg.as_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"sendmail exited {proc.returncode}: {err}")
    except FileNotFoundError:
        raise RuntimeError(f"sendmail binary not found at {_SENDMAIL}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("sendmail timed out after 30s")


# ============================================================
# Newsletter unsubscribe -- stateless token (2026-08-23)
#
# No extra DB column or lookup table for the token itself: it's a
# deterministic HMAC-style hash of (learner id, email, JWT_SECRET), so a
# click can be verified by recomputing the same hash instead of storing
# and looking one up. If a learner's email ever changes, their old
# unsubscribe links stop verifying -- acceptable, since a stale link
# from a genuinely no-longer-valid address shouldn't unsubscribe the new
# one anyway.
# ============================================================

def _unsubscribe_token(learner_id: int, email: str, kind: str = "newsletter") -> str:
    # kind differentiates which opt-out flag a link controls (2026-08-29,
    # weekly-report split) -- "newsletter" is the default and keeps the
    # exact same hash input as before the split, so every newsletter
    # unsubscribe link already sent still verifies correctly. Only a
    # non-default kind (e.g. "weekly_report") gets a distinct hash space.
    suffix = "" if kind == "newsletter" else f":{kind}"
    raw = f"{learner_id}:{email}{suffix}:{_UNSUB_SECRET}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def verify_unsubscribe_token(learner_id: int, email: str, token: str, kind: str = "newsletter") -> bool:
    return _unsubscribe_token(learner_id, email, kind) == token


def unsubscribe_link(learner_id: int, email: str, kind: str = "newsletter") -> str:
    """Full URL for an unsubscribe footer/header. Points at a public,
    no-auth GET (or, for RFC 8058 one-click, POST) endpoint in auth.py
    (see verify-email for the precedent of a public token-based mutation
    reached straight from an email link). kind="weekly_report" for the
    weekly digest, default "newsletter" for the admin newsletter --
    determines which LearnerPreferences opt-out flag the link flips."""
    token = _unsubscribe_token(learner_id, email, kind)
    kind_param = "" if kind == "newsletter" else f"&kind={kind}"
    return (
        f"{_APP_BASE_URL}/api/auth/unsubscribe"
        f"?lid={learner_id}&token={token}{kind_param}"
    )


def append_unsubscribe_footer(body: str, unsubscribe_url: str) -> str:
    """Plain-text counterpart to newsletter_html()'s footer -- send_mail()
    sends both a text body and an html alternative, and a client that
    renders text-only (or a preview pane that ignores the html part)
    would otherwise never show an unsubscribe option at all. Kept as a
    separate small function, not folded into newsletter_html(), since the
    two parts are built and passed to send_mail() independently."""
    return f"{body}\n\n---\nDon't want these emails? Unsubscribe: {unsubscribe_url}"


def newsletter_html(subject: str, body: str, unsubscribe_url: str) -> str:
    """Wrap a plain-text newsletter body (paragraphs separated by a blank
    line) in a small branded HTML template for the multipart/alternative
    `html=` part of send_mail(). Deliberately a light background with the
    platform's teal accent (#00B8A2, a slightly darker shade of the in-app
    --wave for contrast on white) rather than the dark in-app theme --
    email clients render a fixed dark background unreliably (forced light
    mode, clipped previews, etc.), so this doesn't try to reuse app.css's
    CSS variables directly."""
    paragraphs = "".join(
        '<p style="margin:0 0 16px;line-height:1.6;color:#1A2238;font-size:15px">'
        + _esc(p).replace("\n", "<br>")
        + "</p>"
        for p in body.split("\n\n")
        if p.strip()
    )
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#F4F6FB;font-family:-apple-system,'Segoe UI',Roboto,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #E4E8F2">
        <tr><td style="background:#00B8A2;padding:20px 28px">
          <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:0.3px">🌊 LMBoK</span>
          <div style="color:rgba(255,255,255,0.85);font-size:12px;margin-top:2px">Surfing the Frequencies</div>
        </td></tr>
        <tr><td style="padding:28px">
          <h1 style="margin:0 0 20px;font-size:20px;color:#0D1220">{_esc(subject)}</h1>
          {paragraphs}
        </td></tr>
        <tr><td style="padding:20px 28px;border-top:1px solid #E4E8F2">
          <div style="font-size:12px;color:#8B96B8;line-height:1.6">
            You're receiving this because you have an account on LMBoK.
            <a href="{unsubscribe_url}" style="color:#00B8A2">Unsubscribe from newsletters</a>.
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
