from rest_framework.throttling import AnonRateThrottle


class OTPRateThrottle(AnonRateThrottle):
    scope = "otp"
