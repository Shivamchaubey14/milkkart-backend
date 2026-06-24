from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from apps.delivery.models import DeliveryAssignment, DeliveryPartner
from apps.delivery.services import NoRiderAvailable, assign_order
from apps.orders.models import Order

User = get_user_model()


@pytest.fixture
def customer(db):
    return User.objects.create_user(phone="+919876500000", name="Customer")


@pytest.fixture
def order(customer):
    return Order.objects.create(
        user=customer,
        total=Decimal("100.00"),
        address_snapshot="42 Dairy Lane",
        status=Order.Status.CONFIRMED,
    )


@pytest.fixture
def rider(db):
    user = User.objects.create_user(phone="+918888888888", name="Rider")
    return DeliveryPartner.objects.create(user=user, vehicle_number="UP78AB1234", is_on_duty=True)


@pytest.fixture
def rider_client(rider):
    client = APIClient()
    client.force_authenticate(user=rider.user)
    return client


def _order_for(user):
    return Order.objects.create(user=user, total=Decimal("50.00"), address_snapshot="x", status=Order.Status.CONFIRMED)


@pytest.mark.django_db
class TestAssignmentService:
    def test_manual_assign(self, order, rider):
        assignment = assign_order(order, rider)
        assert assignment.status == DeliveryAssignment.Status.ASSIGNED
        assert assignment.rider == rider
        assert len(assignment.delivery_otp) == 6

    def test_idempotent_when_active(self, order, rider):
        first = assign_order(order, rider)
        second = assign_order(order, rider)
        assert first.pk == second.pk

    def test_auto_assign_picks_least_loaded(self, customer, rider):
        rider2 = DeliveryPartner.objects.create(
            user=User.objects.create_user(phone="+917777777777", name="Rider2"), is_on_duty=True
        )
        # Give `rider` an active assignment so rider2 is less loaded.
        assign_order(_order_for(customer), rider)
        assignment = assign_order(_order_for(customer))
        assert assignment.rider == rider2

    def test_no_rider_available(self, order, rider):
        rider.is_on_duty = False
        rider.save()
        with pytest.raises(NoRiderAvailable):
            assign_order(order)


@pytest.mark.django_db
class TestRiderPermission:
    def test_non_rider_forbidden(self, customer):
        client = APIClient()
        client.force_authenticate(user=customer)
        response = client.get(reverse("rider-assignments"))
        assert response.status_code == 403

    def test_unauthenticated(self):
        response = APIClient().get(reverse("rider-assignments"))
        assert response.status_code == 401


@pytest.mark.django_db
class TestRiderDuty:
    def test_toggle_off(self, rider_client, rider):
        response = rider_client.post(reverse("rider-duty"), {"on_duty": False})
        assert response.status_code == 200
        assert response.data["is_on_duty"] is False

    def test_set_location_with_duty(self, rider_client, rider):
        response = rider_client.post(
            reverse("rider-duty"), {"on_duty": True, "lat": "26.449923", "lng": "80.331871"}
        )
        assert response.status_code == 200
        rider.refresh_from_db()
        assert rider.current_lat == Decimal("26.449923")

    def test_location_update(self, rider_client, rider):
        response = rider_client.post(reverse("rider-location"), {"lat": "26.5", "lng": "80.3"})
        assert response.status_code == 200
        rider.refresh_from_db()
        assert rider.current_lat == Decimal("26.500000")
        assert rider.last_location_at is not None


@pytest.mark.django_db
class TestRiderFlow:
    def test_full_flow(self, rider_client, order, rider):
        assignment = assign_order(order, rider)

        # appears in the rider's assignment list
        listing = rider_client.get(reverse("rider-assignments"))
        assert len(listing.data) == 1

        accept = rider_client.post(reverse("rider-accept", kwargs={"order_number": order.order_number}))
        assert accept.status_code == 200
        assert accept.data["status"] == "accepted"

        pickup = rider_client.post(reverse("rider-pickup", kwargs={"order_number": order.order_number}))
        assert pickup.status_code == 200
        assert pickup.data["status"] == "picked_up"
        order.refresh_from_db()
        assert order.status == Order.Status.OUT_FOR_DELIVERY

        assignment.refresh_from_db()
        wrong_otp = "999999" if assignment.delivery_otp != "999999" else "111111"
        bad = rider_client.post(
            reverse("rider-deliver", kwargs={"order_number": order.order_number}), {"otp": wrong_otp}
        )
        assert bad.status_code == 400

        deliver = rider_client.post(
            reverse("rider-deliver", kwargs={"order_number": order.order_number}),
            {"otp": assignment.delivery_otp, "proof_photo": "proof.jpg"},
        )
        assert deliver.status_code == 200
        assert deliver.data["status"] == "delivered"
        order.refresh_from_db()
        assert order.status == Order.Status.DELIVERED

    def test_deliver_before_pickup(self, rider_client, order, rider):
        assignment = assign_order(order, rider)
        response = rider_client.post(
            reverse("rider-deliver", kwargs={"order_number": order.order_number}),
            {"otp": assignment.delivery_otp},
        )
        assert response.status_code == 400

    def test_pickup_unassigned_order(self, rider_client, customer):
        other = _order_for(customer)
        response = rider_client.post(reverse("rider-pickup", kwargs={"order_number": other.order_number}))
        assert response.status_code == 404

    def test_accept_twice_rejected(self, rider_client, order, rider):
        assign_order(order, rider)
        rider_client.post(reverse("rider-accept", kwargs={"order_number": order.order_number}))
        again = rider_client.post(reverse("rider-accept", kwargs={"order_number": order.order_number}))
        assert again.status_code == 400


@pytest.mark.django_db
class TestOrderDetailAssignment:
    def test_customer_sees_assignment(self, customer, order, rider):
        assign_order(order, rider)
        client = APIClient()
        client.force_authenticate(user=customer)
        response = client.get(reverse("order-detail", kwargs={"order_number": order.order_number}))
        assert response.status_code == 200
        assignment = response.data["assignment"]
        assert assignment["rider_phone"] == rider.user.phone
        assert len(assignment["delivery_otp"]) == 6

    def test_no_assignment_is_null(self, customer, order):
        client = APIClient()
        client.force_authenticate(user=customer)
        response = client.get(reverse("order-detail", kwargs={"order_number": order.order_number}))
        assert response.data["assignment"] is None


@pytest.mark.django_db
class TestRiderReturn:
    def _picked_up(self, order, rider, rider_client):
        from apps.orders.models import OrderItem

        OrderItem.objects.create(order=order, product_name="Milk", product_price=Decimal("40"), quantity=1)
        OrderItem.objects.create(order=order, product_name="Bread", product_price=Decimal("30"), quantity=2)
        assign_order(order, rider)
        rider_client.post(reverse("rider-pickup", kwargs={"order_number": order.order_number}))

    def test_partial_return_trims_bill(self, rider_client, order, rider):
        self._picked_up(order, rider, rider_client)
        milk = order.items.get(product_name="Milk")
        r = rider_client.post(
            reverse("rider-return", kwargs={"order_number": order.order_number}),
            {"item_ids": [milk.id], "reason": "refused"},
            format="json",
        )
        assert r.status_code == 200, r.data
        assert r.data["status"] == "delivered"
        order.refresh_from_db()
        milk.refresh_from_db()
        assert milk.is_returned is True
        assert order.status == "delivered"
        assert order.total == Decimal("60.00")  # 100 − 40 refused

    def test_full_return_marks_returned(self, rider_client, order, rider):
        self._picked_up(order, rider, rider_client)
        ids = list(order.items.values_list("id", flat=True))
        r = rider_client.post(
            reverse("rider-return", kwargs={"order_number": order.order_number}),
            {"item_ids": ids},
            format="json",
        )
        assert r.status_code == 200, r.data
        assert r.data["status"] == "returned"
        order.refresh_from_db()
        assert order.status == "returned"

    def test_return_before_pickup_rejected(self, rider_client, order, rider):
        from apps.orders.models import OrderItem

        item = OrderItem.objects.create(order=order, product_name="Milk", product_price=Decimal("40"), quantity=1)
        assign_order(order, rider)
        r = rider_client.post(
            reverse("rider-return", kwargs={"order_number": order.order_number}),
            {"item_ids": [item.id]},
            format="json",
        )
        assert r.status_code == 400


@pytest.mark.django_db
class TestCreateRiderCommand:
    def test_create_rider(self):
        call_command("create_rider", "--phone=+919000000001")
        user = User.objects.get(phone="+919000000001")
        assert user.delivery_partner.is_on_duty is True
