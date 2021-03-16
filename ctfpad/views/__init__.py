from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls.base import reverse, reverse_lazy
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
    tags,
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
    user = request.user
    member = user.member
    if member.is_guest:
        members = Member.objects.filter( selected_ctf = member.selected_ctf )
    else:
        members = Member.objects.all()
    latest_ctfs = member.ctfs.order_by("-start_date")
    now = datetime.datetime.now()
    nb_ctf_played = member.ctfs.count()
    current_ctfs = member.public_ctfs.filter(
        end_date__isnull=False,
        start_date__lte = now,
        end_date__gt = now,
    )
    next_ctf = member.public_ctfs.filter(
        end_date__isnull=False,
        start_date__gt=now,
    ).order_by("start_date").first()
    context = {
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
    stats = CtfStats()

    context = {
        "team": Team.objects.first(),
        "player_ctf_count": stats.players_activity(),
        "most_solved": stats.solved_categories(),
        "last_year_stats": stats.last_year_stats(),
        "ranked_members": stats.get_ranking(),
        "ranked_history": stats.get_ranking_history()
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


@only_if_authenticated_user
def toggle_dark_mode(request: HttpRequest) -> HttpResponse:
    """Toggle dark mode cookie for user

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    val = request.POST.get("darkModeCookie")
    redirect_to = request.META.get("HTTP_REFERER") or reverse("ctfpad:dashboard")
    res = redirect(redirect_to)
    if val:
        res.set_cookie('theme', 'dark')
    else:
        res.set_cookie('theme', 'light')
    return res

