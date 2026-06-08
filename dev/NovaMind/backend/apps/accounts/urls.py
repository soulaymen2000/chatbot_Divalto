"""URL patterns for the accounts / authentication app."""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, LogoutView, ProfileView, ChangePasswordView

urlpatterns = [
    # Registration — POST /api/auth/register/
    path("register/", RegisterView.as_view(), name="auth-register"),

    # Login — POST /api/auth/login/
    path("login/", LoginView.as_view(), name="auth-login"),

    # Logout — POST /api/auth/logout/
    path("logout/", LogoutView.as_view(), name="auth-logout"),

    # Token refresh — POST /api/auth/token/refresh/
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),

    # User profile — GET/PATCH /api/auth/profile/
    path("profile/", ProfileView.as_view(), name="auth-profile"),

    # Password change — POST /api/auth/password/change/
    path("password/change/", ChangePasswordView.as_view(), name="auth-password-change"),
]
