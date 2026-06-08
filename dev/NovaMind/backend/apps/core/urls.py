"""URL patterns for the core app."""
from django.urls import path
from .views import HealthCheckView, ConfigView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("config", ConfigView.as_view(), name="config"),
]
