from rest_framework.permissions import BasePermission

from .models import DeliveryPartner


class IsRider(BasePermission):
    message = "Rider access required."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        try:
            partner = user.delivery_partner
        except DeliveryPartner.DoesNotExist:
            return False
        return partner.is_active
