from django.urls import path

from . import views

urlpatterns = [
    path("", views.SubscriptionListCreateView.as_view(), name="subscription-list"),
    path("summary/", views.summary, name="subscription-summary"),
    path("<int:pk>/", views.SubscriptionDetailView.as_view(), name="subscription-detail"),
    path("<int:pk>/pause/", views.pause, name="subscription-pause"),
    path("<int:pk>/resume/", views.resume, name="subscription-resume"),
    path("<int:pk>/skip/", views.skip, name="subscription-skip"),
    path("<int:pk>/quantity/", views.set_quantity, name="subscription-quantity"),
    path("<int:pk>/vacation/", views.vacation, name="subscription-vacation"),
    path(
        "<int:pk>/vacation/<int:vacation_id>/",
        views.VacationDeleteView.as_view(),
        name="subscription-vacation-delete",
    ),
    path("<int:pk>/calendar/", views.calendar, name="subscription-calendar"),
]
