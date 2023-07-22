import datetime
from typing import Optional

from django.contrib import messages
from django.core.paginator import Paginator
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from django.contrib.auth.decorators import login_required

from ..models import CtfStats, Member, SearchEngine, Team

from . import (
    categories,
    challenges,
    ctfs,
    files,
    tags,
    teams,
    users,
)

__all__ = [
    "categories",
    "challenges",
    "ctfs",
    "files",
    "tags",
    "teams",
    "users",
]


DEFAULT_LATEST_CTF_NUMBER = 25
DEFAULT_SEARCH_RESULT_PER_PAGE = 25


def index(request: HttpRequest) -> HttpResponse:
    """
    Redirects to the dashboard
    """
    if Team.objects.count() == 0:
        return redirect("ctfhub:team-register")

    if Member.objects.all().count() == 0:
        return redirect("ctfhub:users-register")

    return redirect("ctfhub:dashboard")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view: contains basic summary of all the info in the ctfhub

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """

    member = Member.objects.get(user=request.user)
    if member.is_guest:
        members = Member.objects.filter(selected_ctf=member.selected_ctf)
    else:
        members = Member.objects.all()
    latest_ctfs = member.ctfs.order_by("-start_date")[:DEFAULT_LATEST_CTF_NUMBER]
    now = datetime.datetime.now()
    nb_ctf_played = member.ctfs.count()

    # `current_ctfs` holds all the ctfs currently running, including permanent (always running)
    current_ctfs = (ctf for ctf in member.public_ctfs.all() if ctf.is_running)
    next_ctf = (
        member.public_ctfs.filter(
            start_date__gt=now,
        )
        .order_by("start_date")
        .first()
    )

    context = {
        "members": members,
        "latest_ctfs": latest_ctfs,
        "current_ctfs": current_ctfs,
        "temporary_running_ctfs": [ctf for ctf in current_ctfs if not ctf.is_running],
        "next_ctf": next_ctf,
        "nb_ctf_played": nb_ctf_played,
    }
    return render(request, "ctfhub/dashboard/dashboard.html", context)


@login_required
def generate_stats(request: HttpRequest, year: Optional[int] = None) -> HttpResponse:
    """Generate some statistics of the CTFHub

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    if not year:
        return redirect("ctfhub:stats-detail", year=datetime.datetime.now().year)

    stats = CtfStats(year)
    context = {
        "team": Team.objects.first(),
        "members": stats.members(),
        "player_activity": stats.player_activity(),
        "category_stats": stats.category_stats(),
        "ctf_stats": stats.ctf_stats(),
        "ranking_stats": stats.ranking_stats(),
        "year_stats": stats.year_stats(),
        "year_pick": year,
    }
    return render(request, "ctfhub/stats/detail.html", context)


@login_required
def search(request: HttpRequest) -> HttpResponse:
    """Search pattern(s) in database

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    query = request.GET.get("q")
    if not query:
        messages.warning(request, "No search pattern given")
        return redirect("ctfhub:dashboard")

    engine = SearchEngine(query)
    paginator = Paginator(engine.results, DEFAULT_SEARCH_RESULT_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "q": query,
        "selected_category": engine.selected_category or "All",
        "total_result": len(engine.results),
        "page_obj": page_obj,
        "paginator": paginator,
    }
    return render(request, "search/list.html", context)
