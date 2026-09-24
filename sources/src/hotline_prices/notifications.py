"""SMTP email sending for price-target alerts."""

import logging
import smtplib
from email.message import EmailMessage

from .config import AppConfig

logger = logging.getLogger(__name__)


def send_price_alert(
    config: AppConfig, to_addr: str, title: str, price: float, url: str
) -> None:
    """Send a plain-text email notifying that a product hit its target price."""
    msg = EmailMessage()
    msg["Subject"] = f"Hotline: {title} — ціна впала до {price:.0f} ₴"
    msg["From"] = config.smtp_from
    msg["To"] = to_addr
    msg.set_content(
        f"Товар «{title}» досяг цільової ціни.\n\n"
        f"Поточна ціна: {price:.0f} ₴\n"
        f"Посилання: {url}\n"
    )

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if config.smtp_username:
            smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(msg)
