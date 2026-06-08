"""NovaMind URL Configuration — Root router."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # Authentication endpoints → /api/auth/register/, /api/auth/login/, etc.
    path("api/auth/", include("apps.accounts.urls")),

    # Chat / RAG endpoints → /api/conversations/, etc.
    path("api/", include("apps.chat.urls")),

    # Feedback endpoints
    path("api/", include("apps.feedback.urls")),

    # Core / health-check
    path("api/", include("apps.core.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin site customization
admin.site.site_header = "NovaMind Admin"
admin.site.site_title = "NovaMind Admin Portal"
admin.site.index_title = "Welcome to NovaMind Administration"
