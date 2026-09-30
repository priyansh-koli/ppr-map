"""Transactional email. SMTP to Mailpit in development (http://localhost:8025); the
production provider is not chosen yet (docs/external-services.md). Plain text only."""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    body: str
    headers: tuple[tuple[str, str], ...] = ()


class Mailer(Protocol):
    async def send(self, email: Email) -> None:
        """Send, logging a failure: for mail the user can ask for again."""

    async def deliver(self, email: Email) -> None:
        """Send, raising on failure: for callers that record the outcome (alerts)."""


class SmtpMailer:
    def _send(self, email: Email) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = email.to
        msg["Subject"] = email.subject
        for name, value in email.headers:
            msg[name] = value
        msg.set_content(email.body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            if s.smtp_user:
                smtp.starttls()
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)

    async def deliver(self, email: Email) -> None:
        await asyncio.to_thread(self._send, email)

    async def send(self, email: Email) -> None:
        # A mail server that is down must not fail the request: the user can ask again.
        try:
            await self.deliver(email)
        except (OSError, smtplib.SMTPException):
            log.exception("could not send %r to %s", email.subject, email.to)


def get_mailer() -> Mailer:
    return SmtpMailer()


def link(path: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}{path}"


def verify_email(to: str, name: str, token: str) -> Email:
    return Email(
        to,
        "Confirm your email for PPR Map",
        f"Hello {name},\n\nConfirm your email address by opening this link:\n\n"
        f"{link('/verify-email?token=' + token)}\n\n"
        "The link works for 24 hours. If you did not create an account, ignore this email.\n",
    )


def already_registered(to: str) -> Email:
    return Email(
        to,
        "You already have a PPR Map account",
        "Someone, probably you, tried to create a PPR Map account with this email address, "
        "but one already exists.\n\n"
        f"Sign in: {link('/login')}\nForgot your password? {link('/forgot-password')}\n\n"
        "If this was not you, you can ignore this email.\n",
    )


def account_closed(to: str, purge_on: date) -> Email:
    return Email(
        to,
        "Your PPR Map account is closed",
        "Someone, probably you, tried to create a PPR Map account with this email address. "
        "The account that used it was closed, and it is deleted for good on "
        f"{purge_on.day} {purge_on:%B %Y}. You can register with this address again after that.\n\n"
        "If this was not you, you can ignore this email.\n",
    )


def reset_password(to: str, name: str, token: str) -> Email:
    return Email(
        to,
        "Reset your PPR Map password",
        f"Hello {name},\n\nChoose a new password here:\n\n"
        f"{link('/reset-password?token=' + token)}\n\n"
        "The link works for 1 hour and only once. If you did not ask for this, ignore this "
        "email: your password has not changed.\n",
    )


def password_changed(to: str, name: str) -> Email:
    return Email(
        to,
        "Your PPR Map password was changed",
        f"Hello {name},\n\nThe password for your PPR Map account was just changed, and you "
        "were signed out everywhere else.\n\nIf this was not you, reset it now: "
        f"{link('/forgot-password')}\n",
    )


def unsubscribe_link(token: str) -> str:
    return link("/alerts/unsubscribe?token=" + token)


def search_alert(
    to: str,
    name: str,
    search_name: str,
    total: int,
    sales: list[tuple[str, str, str, str]],
    search_path: str,
    unsubscribe_token: str,
) -> Email:
    """New sales on the register that match a saved search. `sales` are (address, price,
    date, property path), newest first; `total` may be larger than the list."""
    lines = [f"- {a}\n  {p}, sold {d}\n  {link(path)}" for a, p, d, path in sales]
    more = total - len(sales)
    unsubscribe = unsubscribe_link(unsubscribe_token)
    body = (
        f"Hello {name},\n\n"
        f"The Property Price Register has {total} new "
        f"{'sale' if total == 1 else 'sales'} matching your saved search "
        f'"{search_name}":\n\n'
        + "\n\n".join(lines)
        + "\n\n"
        + (f"...and {more} more. " if more > 0 else "")
        + f"See them all: {link(search_path)}\n\n"
        "Sales are filed with the register weeks after they close, so some may be months "
        "old. The latest two months of the register are provisional.\n\n"
        f"Change or stop this alert: {link('/account/saved-searches')}\n"
        f"Stop this alert in one click: {unsubscribe}\n"
    )
    return Email(
        to,
        f"{total} new {'sale' if total == 1 else 'sales'}: {search_name}",
        body,
        headers=(("List-Unsubscribe", f"<{unsubscribe}>"),),
    )


REQUEST_KIND = {
    "suppress_display": "stop showing an address",
    "correct_location": "correct a location",
    "correct_details": "correct a detail",
}


def report_received(to: str, reference: str, kind: str, address: str) -> Email:
    return Email(
        to,
        f"We received your request ({reference})",
        f"Thank you. We received your request to {REQUEST_KIND.get(kind, kind)}:\n\n"
        f"  {address}\n\nIts reference is {reference}. We review requests by hand and will "
        "email you when it is decided. You do not need to do anything else.\n\n"
        "The sale itself stays on the Property Services Regulatory Authority's register, "
        "which we cannot change: www.propertypriceregister.ie\n",
    )


def report_decided(to: str, reference: str, approved: bool, note: str | None) -> Email:
    outcome = "approved" if approved else "not approved"
    return Email(
        to,
        f"Your request {reference} was {outcome}",
        f"Your request {reference} was {outcome}."
        + (f"\n\nOur note: {note}" if note else "")
        + "\n\nIf you have a question about it, reply to this email.\n",
    )
