from unittest.mock import MagicMock, patch

from hotline_prices.config import AppConfig
from hotline_prices.notifications import send_price_alert


def test_send_price_alert_with_auth_logs_in_and_sends():
    config = AppConfig(
        smtp_host="mail.example.com",
        smtp_port=587,
        smtp_username="bot",
        smtp_password="secret",
        smtp_from="noreply@example.com",
    )
    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch(
        "hotline_prices.notifications.smtplib.SMTP", return_value=smtp_instance
    ) as smtp_cls:
        send_price_alert(
            config, "user@example.com", "Monitor", 12345, "https://hotline.ua/ua/cat/a/"
        )

    smtp_cls.assert_called_once_with("mail.example.com", 587, timeout=15)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("bot", "secret")
    smtp_instance.send_message.assert_called_once()

    msg = smtp_instance.send_message.call_args[0][0]
    assert msg["From"] == "noreply@example.com"
    assert msg["To"] == "user@example.com"
    assert "Monitor" in msg["Subject"]
    assert "12345" in msg["Subject"]
    body = msg.get_content()
    assert "Monitor" in body
    assert "12345" in body
    assert "https://hotline.ua/ua/cat/a/" in body


def test_send_price_alert_without_username_skips_login():
    config = AppConfig(smtp_username="")
    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("hotline_prices.notifications.smtplib.SMTP", return_value=smtp_instance):
        send_price_alert(
            config, "user@example.com", "Monitor", 999, "https://hotline.ua/ua/cat/a/"
        )

    smtp_instance.login.assert_not_called()
    smtp_instance.send_message.assert_called_once()
