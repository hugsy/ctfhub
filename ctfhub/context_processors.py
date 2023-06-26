import django.http
from django.conf import settings


def add_debug_context(request: django.http.HttpRequest) -> dict:
    return {
        "DEBUG": settings.DEBUG,
        "VERSION": settings.VERSION,
    }
