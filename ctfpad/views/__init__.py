from ctfpad.forms import CreateUpdateCtfForm
from ctfpad.decorators import only_if_authenticated_user
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

import datetime

from . import (
    users,
    teams,
    ctfs,
    challenges,
    categories,
    files,
)

from ..models import (
    Ctf, Team,
    Member,
)


def index(request: HttpRequest) -> HttpResponse:
    """
    Redirects to the dashboard
    """
    teams = Team.objects.all()
    if teams.count() == 0:
        return redirect("ctfpad:team-register")

    if Member.objects.all().count() == 0:
        return redirect("ctfpad:users-register")

    return redirect("ctfpad:dashboard")


@only_if_authenticated_user
def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view: contains basic summary of all the info in the ctfpad

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    members = Member.objects.all().order_by("-last_logged_in")
    ctfs = Ctf.objects.all().order_by("-last_modification_time")
    user = Member.objects.filter(user__username=request.user).first()
    now = datetime.datetime.now()
    current_ctfs = Ctf.objects.filter(
        end_date__isnull=False,
        start_date__lte = now,
        end_date__gt = now,
    )
    quick_add_form = CreateUpdateCtfForm()
    context = {
        "user": user,
        "members": members,
        "ctfs": ctfs,
        "current_ctfs": current_ctfs,
        "quick_add_form": quick_add_form,
    }
    return render(request, "ctfpad/dashboard/dashboard.html", context)


@only_if_authenticated_user
def generate_stats(request: HttpRequest) -> HttpResponse:
    """Generate some statistics of the CTFPad

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    # todo
    plot1 = [0, 1, 2, 3, 5]

    # todo
    rank = Member.objects.all()

    context = {
        "plot1": plot1,
        "plot2": plot1,
        "plot3": plot1,
        "ranked_members": rank,
    }
    return render(request, "ctfpad/stats/detail.html", context)
