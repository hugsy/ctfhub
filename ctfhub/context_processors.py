import django.http
from django.conf import settings

from ctfhub.models import Member


def add_debug_context(request: django.http.HttpRequest) -> dict[str, dict[str, str]]:
    """Adds some CTFHub environment information to every context

    Args:
        request (django.http.HttpRequest): _description_

    Returns:
        dict[str, str]: _description_
    """
    return {
        "CTFHub": {
            "DEBUG": settings.DEBUG,
            "VERSION": settings.PROJECT_VERSION,
            "URL": settings.PROJECT_URL,
        }
    }


def add_timezone_context(request: django.http.HttpRequest) -> dict[str, str]:
    """Add the client timezone information to the HTTP context

    Args:
        request (django.http.HttpRequest): _description_

    Returns:
        dict: _description_
    """
    try:
        member = Member.objects.get(user=request.user)
        return {"TZ": member.timezone}
    except Exception:
        return {"TZ": "UTC"}
