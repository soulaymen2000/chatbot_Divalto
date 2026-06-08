"""
Authentication views for NovaMind.
Handles: register, login, logout, token refresh, profile, password change.
All sensitive endpoints are protected with rate limiting.
"""
import logging
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    ProfileUpdateSerializer,
    ChangePasswordSerializer,
)

logger = logging.getLogger("apps.accounts")


def get_tokens_for_user(user):
    """Generate JWT access + refresh token pair for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@method_decorator(
    ratelimit(key="ip", rate=settings.RATE_LIMIT_SIGNUP, method="POST", block=True),
    name="post",
)
class RegisterView(APIView):
    """
    POST /api/auth/register/
    Create a new user account. Rate limited: 2/min per IP.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user, context={"request": request}).data
            logger.info("New user registered: %s", user.email)
            return Response(
                {
                    "message": "Account created successfully.",
                    "user": user_data,
                    "tokens": tokens,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(
    ratelimit(key="ip", rate=settings.RATE_LIMIT_LOGIN, method="POST", block=True),
    name="post",
)
class LoginView(APIView):
    """
    POST /api/auth/login/
    Authenticate and return JWT tokens. Rate limited: 5/min per IP.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user, context={"request": request}).data
            logger.info("User logged in: %s", user.email)
            return Response(
                {
                    "user": user_data,
                    "tokens": {
                        "access": tokens["access"],
                        "refresh": tokens["refresh"],
                    },
                },
                status=status.HTTP_200_OK,
            )
        logger.warning("Failed login attempt for: %s", request.data.get("email", "unknown"))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    POST /api/users/logout/
    Blacklist the refresh token to invalidate the session.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("User logged out: %s", request.user.email)
            return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/users/profile/ — View and update user profile."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ProfileUpdateSerializer
        return UserSerializer

    def get_object(self):
        return self.request.user

    def get_serializer_context(self):
        return {"request": self.request}

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """POST /api/users/password/change/ — Change password."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            request.user.set_password(serializer.validated_data["new_password"])
            request.user.save()
            logger.info("Password changed for user: %s", request.user.email)
            return Response({"message": "Password changed successfully."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
