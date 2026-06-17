from django.urls import path

from . import import_views

urlpatterns = [
    path("", import_views.imports, name="bulk-imports"),
    path("template/<str:kind>/", import_views.import_template, name="bulk-import-template"),
    path("<int:import_id>/", import_views.import_detail, name="bulk-import-detail"),
]
