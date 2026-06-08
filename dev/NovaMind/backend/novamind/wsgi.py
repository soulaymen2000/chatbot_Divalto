"""WSGI config for novamind project."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "novamind.settings.development")
application = get_wsgi_application()
