"""Email tool — STUB.

v2 will wire up Gmail (or SMTP) for trade-summary emails.
"""
from __future__ import annotations


def send_email(to: str, subject: str, body: str) -> None:
    """Send an email. Not implemented in v1.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.

    Raises:
        NotImplementedError: Always, until v2.
    """
    raise NotImplementedError("Wire up Gmail/Calendar API in v2")
