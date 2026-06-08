"""Development settings — DEBUG on, verbose logging."""
from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all hosts in dev
ALLOWED_HOSTS = ["*"]

# Simpler password validation in dev
AUTH_PASSWORD_VALIDATORS = []

# CORS — allow both Vite default port (5173) and custom port (3000)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Show SQL queries in console (uncomment if needed)
# LOGGING['loggers']['django.db.backends'] = {
#     'handlers': ['console'],
#     'level': 'DEBUG',
# }
