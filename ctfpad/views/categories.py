from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages

from ctfpad.models import ChallengeCategory

def create(request: HttpRequest) -> HttpResponse:
    """Create a new category

    Args:
        request (HttpRequest): controlled by django

    Returns:
        HttpResponse: controlled by django
    """
    if request.method == "POST":
        category = ChallengeCategory(name=request.POST.get("category_name"))
        category.save()
        messages.success(request, f"Category '{category.name}' successfully was created!")
        return redirect( request.META.get("HTTP_REFERER") )

