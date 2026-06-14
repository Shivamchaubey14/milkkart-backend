from django.urls import path

from . import views

urlpatterns = [
    path("check/", views.check, name="serviceability-check"),
    path("areas/", views.ServiceableAreaListCreateView.as_view(), name="serviceable-area-list"),
    path("areas/<int:pk>/", views.ServiceableAreaDetailView.as_view(), name="serviceable-area-detail"),
]
