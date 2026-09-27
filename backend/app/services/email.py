"""Transactional email. SMTP to Mailpit in development (http://localhost:8025); the
production provider is not chosen yet (docs/external-services.md). Plain text only."""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class SmtpMailer:
    def _send(self, email: Email) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg.set_content(email.body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            if s.smtp_user:
                smtp.starttls()
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)

    async def send(self, email: Email) -> None:
        # A mail server that is down must not fail the request: the user can ask again.
        try:
            await asyncio.to_thread(self._send, email)
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
