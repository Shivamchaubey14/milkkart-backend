from rest_framework import serializers

from .models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    is_eligible = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    potential_discount = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "code",
            "description",
            "discount_type",
            "value",
            "min_order_value",
            "max_discount",
            "valid_until",
            "is_eligible",
            "reason",
            "potential_discount",
        ]

    def _eligibility(self, obj):
        if not hasattr(obj, "_elig"):
            user = self.context["request"].user
            obj._elig = obj.check_eligibility(user, self.context["subtotal"])
        return obj._elig

    def get_is_eligible(self, obj):
        return self._eligibility(obj)[0]

    def get_reason(self, obj):
        return self._eligibility(obj)[1]

    def get_potential_discount(self, obj):
        if self._eligibility(obj)[0]:
            return obj.calculate_discount(self.context["subtotal"])
        return None
