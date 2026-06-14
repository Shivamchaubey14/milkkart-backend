from .channels import CHANNELS
from .models import Category, Notification, NotificationPreference

# Category -> the preference field that opts a user in/out of it.
CATEGORY_PREF_FIELD = {
    Category.ORDER: "order_updates",
    Category.PROMO: "promotions",
    Category.SUBSCRIPTION: "subscription_reminders",
    Category.SYSTEM: None,  # system messages are never suppressed
}

CHANNEL_PREF_FIELD = {
    "push": "push_enabled",
    "sms": "sms_enabled",
    "email": "email_enabled",
}


def get_preference(user):
    pref, _ = NotificationPreference.objects.get_or_create(user=user)
    return pref


def notify(user, category, title, body="", data=None, channels=("push",)):
    """Record an in-app notification and fan out to external channels per the user's prefs.

    Promotions are opt-in: if disabled, nothing is recorded. Other categories are
    always recorded in-app; external channels are gated by both the category opt-in
    and the per-channel toggle. Returns the Notification, or None if suppressed.
    """
    data = data or {}
    pref = get_preference(user)
    pref_field = CATEGORY_PREF_FIELD.get(category)
    category_enabled = pref_field is None or getattr(pref, pref_field)

    if category == Category.PROMO and not category_enabled:
        return None

    notification = Notification.objects.create(
        user=user, category=category, title=title, body=body, data=data
    )

    if not category_enabled:
        return notification  # in-app only

    for channel_name in channels:
        channel_field = CHANNEL_PREF_FIELD.get(channel_name)
        if channel_field and not getattr(pref, channel_field):
            continue
        backend = CHANNELS.get(channel_name)
        if backend:
            backend.send(user, title, body, data)

    return notification
