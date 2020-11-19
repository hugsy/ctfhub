from django.urls.base import reverse
from ctfpad.forms import CtfCreateUpdateForm
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
    Ctf, CtfStats, Team,
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
    members = Member.objects.all()
    ctfs = Ctf.objects.all().order_by("-last_modification_time")
    user = Member.objects.filter(user__username=request.user).first()
    now = datetime.datetime.now()
    current_ctfs = Ctf.objects.filter(
        end_date__isnull=False,
        start_date__lte = now,
        end_date__gt = now,
    )
    next_ctf = Ctf.objects.filter(
        end_date__isnull=False,
        start_date__gt=now,
    ).order_by("start_date").first()
    quick_add_form = CtfCreateUpdateForm()
    context = {
        "user": user,
        "members": members,
        "ctfs": ctfs,
        "current_ctfs": current_ctfs,
        "next_ctf": next_ctf,
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
    # stats
    stats = CtfStats()

    # ranking
    rank = sorted(
        Member.objects.all(),
        key=lambda x: x.total_points_scored,
        reverse=True
    )

    context = {
        "player_ctf_count": stats.players_activity(),
        "most_solved": stats.solved_categories(),
        "last_year_stats": stats.last_year_stats(),
        "ranked_members": rank,
    }
    return render(request, "ctfpad/stats/detail.html", context)
