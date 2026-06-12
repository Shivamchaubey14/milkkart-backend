from django.test import RequestFactory

from apps.core.views import health_check


class TestHealthCheck:
    def test_health_check_returns_ok(self):
        factory = RequestFactory()
        request = factory.get("/api/v1/health/")
        response = health_check(request)
        assert response.status_code == 200
        assert response.data == {"status": "ok"}
