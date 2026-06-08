"""
Core views: health check and front-end config endpoint.
"""
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class HealthCheckView(APIView):
    """GET /api/health/ — Simple liveness check."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "NovaMind API"})


class ConfigView(APIView):
    """
    GET /api/config — Returns runtime configuration for the front-end.
    config.ts in the React app fetches this on startup.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "API_BASE_URL": request.build_absolute_uri("/").rstrip("/"),
        })
