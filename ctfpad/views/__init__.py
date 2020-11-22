from django.contrib import messages
from django.urls.base import reverse
from ctfpad.decorators import only_if_authenticated_user
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from django.core.paginator import Paginator


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
    Ctf, CtfStats, SearchEngine, Team,
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
    latest_ctfs = Ctf.objects.all().order_by("-last_modification_time")
    user = Member.objects.filter(user__username=request.user).first()
    now = datetime.datetime.now()
    nb_ctf_played = Ctf.objects.all().count()
    current_ctfs = Ctf.objects.filter(
        end_date__isnull=False,
        start_date__lte = now,
        end_date__gt = now,
    )
    next_ctf = Ctf.objects.filter(
        end_date__isnull=False,
        start_date__gt=now,
    ).order_by("start_date").first()
    context = {
        "user": user,
        "members": members,
        "latest_ctfs": latest_ctfs[:10],
        "current_ctfs": current_ctfs,
        "next_ctf": next_ctf,
        "nb_ctf_played": nb_ctf_played,
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
    # team info
    team = Team.objects.first()

    # stats
    stats = CtfStats()

    # ranking
    rank = sorted(
        Member.objects.all(),
        key=lambda x: x.total_points_scored,
        reverse=True
    )

    context = {
        "team": team,
        "player_ctf_count": stats.players_activity(),
        "most_solved": stats.solved_categories(),
        "last_year_stats": stats.last_year_stats(),
        "ranked_members": rank,
    }
    return render(request, "ctfpad/stats/detail.html", context)




@only_if_authenticated_user
def search(request: HttpRequest) -> HttpResponse:
    """Search pattern(s) in database

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    q = request.GET.get("q")
    if not q:
        messages.warning(request, f"No search pattern given")
        return redirect("ctfpad:dashboard")

    search = SearchEngine(q)
    paginator = Paginator(search.results, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        "q": q,
        "selected_category": search.selected_category or "All",
        "total_result": len(search.results),
        "page_obj": page_obj,
        "paginator": paginator,
    }
    return render(request, "search/list.html", context)