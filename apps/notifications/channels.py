"""Outbound notification channels.

These are mock implementations that log — swap PushChannel for FCM,
SMSChannel for MSG91/Twilio and EmailChannel for SES in production. Each
exposes the same ``send`` interface so the dispatcher is backend-agnostic.
"""

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

# Expo's push service — accepts a batch of messages addressed to ExponentPushTokens.
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class BaseChannel:
    name = "base"

    def send(self, user, title, body, data):
        raise NotImplementedError


class PushChannel(BaseChannel):
    """Sends a real push via Expo's push service so the device shows a banner,
    plays a sound (ring) and vibrates. Device tokens are registered by the app
    via POST /notifications/devices/. Non-Expo tokens are ignored."""

    name = "push"

    def send(self, user, title, body, data):
        tokens = list(user.device_tokens.filter(is_active=True).values_list("token", flat=True))
        expo_tokens = [t for t in tokens if t.startswith(("ExponentPushToken", "ExpoPushToken"))]
        if not expo_tokens:
            logger.info("[PUSH] no Expo device tokens for %s", user.phone)
            return False

        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": data or {},
                "sound": "default",       # plays the notification sound (ring)
                "priority": "high",       # wake the device / deliver promptly
                "channelId": "default",   # Android channel carrying sound + vibration
            }
            for token in expo_tokens
        ]

        try:
            req = urllib.request.Request(
                EXPO_PUSH_URL,
                data=json.dumps(messages).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            logger.info("[PUSH] sent to %d device(s) for %s — %s", len(expo_tokens), user.phone, title)
            return True
        except Exception:
            logger.exception("[PUSH] Expo push failed for %s", user.phone)
            return False


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
