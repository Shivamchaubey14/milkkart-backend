import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_otp_sms(phone, code):
    """Send OTP via SMS. Currently logs to console; plug in SMS provider (Twilio/MSG91) here."""
    logger.info("[SMS] OTP %s sent to %s", code, phone)
    return {"phone": phone, "status": "sent"}
