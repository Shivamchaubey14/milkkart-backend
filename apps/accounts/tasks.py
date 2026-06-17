import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@shared_task
def send_otp_sms(phone, code):
    """Send OTP via SMS. Currently logs to console; plug in SMS provider (Twilio/MSG91) here."""
    logger.info("[SMS] OTP %s sent to %s", code, phone)
    return {"phone": phone, "status": "sent"}


@shared_task
def send_otp_email(email, code):
    """Email the OTP using a branded HTML template (falls back to plain text)."""
    if not email:
        logger.warning("[EMAIL] No recipient for OTP %s — skipping email", code)
        return {"email": None, "status": "skipped"}

    context = {"code": code, "expiry_minutes": settings.OTP_EXPIRY_MINUTES}
    html_body = render_to_string("accounts/otp_email.html", context)
    text_body = (
        f"Your MilkKart verification code is {code}.\n"
        f"It expires in {settings.OTP_EXPIRY_MINUTES} minutes. Do not share it with anyone.\n\n"
        "If you didn't request this code, you can safely ignore this email."
    )

    message = EmailMultiAlternatives(
        subject=f"{code} is your MilkKart verification code",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)

    logger.info("[EMAIL] OTP %s sent to %s", code, email)
    return {"email": email, "status": "sent"}
