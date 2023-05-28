from django.http.request import HttpRequest
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.http import urlencode
from django.urls import reverse


def only_if_unauthenticated_user(view_func):
    """
    Decorator to redirect back logged-in users
    """

    def wrapper_func(request: HttpRequest, *args, **kwargs):
        if request.user.is_authenticated:
            messages.warning(request, f"You're already authenticated!")
            return redirect(request.META.get("HTTP_REFERER"))
        else:
            return view_func(request, *args, **kwargs)

    return wrapper_func


def only_if_authenticated_user(view_func):
    """
    Decorator to redirect back unauthenticated users
    """

    def wrapper_func(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, f"You must be authenticated!")
            return redirect(reverse("ctfpad:user-login") + "?" + urlencode({"redirect_to": request.path}))
        else:
            return view_func(request, *args, **kwargs)

    return wrapper_func


def only_if_admin(view_func):
    """
    View decorator only for admin
    """

    def wrapper_func(request: HttpRequest, *args, **kwargs):
        group = None
        if request.user.groups.exists():
            group = request.user.groups.all()[0].name

        if group == "admin":
            return view_func(request, *args, **kwargs)

    return wrapper_func
