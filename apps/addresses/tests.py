import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.addresses.models import Address

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def address(user):
    return Address.objects.create(
        user=user,
        label="home",
        address_line="42 Dairy Lane",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        is_default=True,
    )


@pytest.mark.django_db
class TestAddressModel:
    def test_str(self, address):
        assert "42 Dairy Lane" in str(address)
        assert "Mumbai" in str(address)

    def test_default_unset_on_new_default(self, user, address):
        addr2 = Address.objects.create(
            user=user,
            label="work",
            address_line="99 Office Park",
            city="Mumbai",
            state="Maharashtra",
            pincode="400002",
            is_default=True,
        )
        address.refresh_from_db()
        assert not address.is_default
        assert addr2.is_default


@pytest.mark.django_db
class TestAddressListCreateAPI:
    def test_list_empty(self, auth_client):
        response = auth_client.get(reverse("address-list-create"))
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_create_address(self, auth_client):
        data = {
            "label": "home",
            "address_line": "42 Dairy Lane",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
        }
        response = auth_client.post(reverse("address-list-create"), data)
        assert response.status_code == 201
        assert response.data["address_line"] == "42 Dairy Lane"

    def test_list_with_address(self, auth_client, address):
        response = auth_client.get(reverse("address-list-create"))
        assert len(response.data) == 1

    def test_unauthenticated(self):
        client = APIClient()
        response = client.get(reverse("address-list-create"))
        assert response.status_code == 401

    def test_user_isolation(self, auth_client, address):
        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse("address-list-create"))
        assert len(response.data) == 0


@pytest.mark.django_db
class TestAddressDetailAPI:
    def test_get_address(self, auth_client, address):
        response = auth_client.get(reverse("address-detail", kwargs={"address_id": address.id}))
        assert response.status_code == 200
        assert response.data["city"] == "Mumbai"

    def test_update_address(self, auth_client, address):
        response = auth_client.patch(
            reverse("address-detail", kwargs={"address_id": address.id}),
            {"city": "Delhi"},
        )
        assert response.status_code == 200
        assert response.data["city"] == "Delhi"

    def test_delete_address(self, auth_client, address):
        response = auth_client.delete(reverse("address-detail", kwargs={"address_id": address.id}))
        assert response.status_code == 204
        assert Address.objects.count() == 0

    def test_not_found(self, auth_client):
        response = auth_client.get(reverse("address-detail", kwargs={"address_id": 99999}))
        assert response.status_code == 404

    def test_other_user_cannot_access(self, address):
        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse("address-detail", kwargs={"address_id": address.id}))
        assert response.status_code == 404
