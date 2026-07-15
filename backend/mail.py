# ============================================================
# FreqLearn — utils/email.py
# Thin wrapper around the host's sendmail binary.
# No external libraries required; the droplet's MTA is already
# configured with valid DNS (SPF/DKIM/DMARC).
# ============================================================

import os
import subprocess
from email.message import EmailMessage
from typing import Optional


_SENDMAIL = "/usr/sbin/sendmail"
_FROM     = os.getenv("FREQLEARN_MAIL_FROM", "epangea.info@gmail.com")
_REPLY_TO = os.getenv("FREQLEARN_MAIL_REPLY_TO", "epangea.info@gmail.com")


def send_mail(
    to: str,
    subject: str,
    body: str,
    *,
    reply_to: Optional[str] = None,
    html: Optional[str] = None,
) -> None:
    """
    Send a plain-text (and optional HTML) email via the local MTA.
    Raises RuntimeError if sendmail is missing or returns non-zero.
    """
    if not os.path.isfile(_SENDMAIL):
        raise RuntimeError(f"sendmail binary not found at {_SENDMAIL}")

    msg = EmailMessage()
    msg["From"]    = _FROM
    msg["To"]      = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply_to or _REPLY_TO
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
