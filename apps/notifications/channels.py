"""Outbound notification channels.

These are mock implementations that log — swap PushChannel for FCM,
SMSChannel for MSG91/Twilio and EmailChannel for SES in production. Each
exposes the same ``send`` interface so the dispatcher is backend-agnostic.
"""

import logging

logger = logging.getLogger(__name__)


class BaseChannel:
    name = "base"

    def send(self, user, title, body, data):
        raise NotImplementedError


class PushChannel(BaseChannel):
    name = "push"

    def send(self, user, title, body, data):
        tokens = list(user.device_tokens.filter(is_active=True).values_list("token", flat=True))
        if not tokens:
            return False
        logger.info("[PUSH] %d device(s) for %s — %s", len(tokens), user.phone, title)
        return True


class SMSChannel(BaseChannel):
    name = "sms"

    def send(self, user, title, body, data):
        logger.info("[SMS] %s — %s", user.phone, body or title)
        return True


class EmailChannel(BaseChannel):
    name = "email"

    def send(self, user, title, body, data):
        email = getattr(user, "email", "")
        if not email:
            return False
        logger.info("[EMAIL] %s — %s", email, title)
        return True


CHANNELS = {
    "push": PushChannel(),
    "sms": SMSChannel(),
    "email": EmailChannel(),
}
