import datetime

from django.contrib import auth, messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models.functions import datetime
from django.http.request import HttpRequest
from django.http.response import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    UpdateView,
    DeleteView,
    ListView,
    DetailView,
)
from django.contrib.auth.views import LoginView, LogoutView

from ctfpad.models import Challenge, ChallengeFile, Member, Team
from ctfpad.forms import CreateUserForm, UpdateMemberForm
from ctfpad.decorators import only_if_unauthenticated_user, only_if_authenticated_user


class CtfpadLogin(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = False
    redirect_field_name = "redirect_to"


@only_if_authenticated_user
def logout(request: HttpRequest) -> HttpResponse:
    """Log out from current session. CBV is not necessary for logging out.

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    auth.logout(request)
    return redirect("ctfpad:home")


class MemberCreateView(SuccessMessageMixin, CreateView):
    model = Member
    template_name = "users/register.html"
    form_class = CreateUserForm
    success_message = "Member '%(username)s' successfully created"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def form_valid(self, form):
        # validate team presence
        teams = Team.objects.all()
        if teams.count() == 0:
            return redirect("ctfpad:team-register")

        # validate api_key
        team = teams.first()
        if team.api_key != form.cleaned_data["api_key"]:
            messages.error(self.request, f"The API key for team '{team.name}' is invalid")
            return redirect("ctfpad:home")

        # validate user uniqueness
        users = User.objects.filter(username=form.cleaned_data["username"])
        if users.count() > 0:
            form.errors["name"] = "UsernameAlreadyExistError"
            messages.error(self.request, "Username already exists, try logging in instead")
            return redirect("ctfpad:home")

        # create the django user
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password1"],
            email=form.cleaned_data["email"],
        )
        user.save()

        # populate the missing required fields
        form.instance.user = user
        form.instance.team = team

        # process
        return super().form_valid(form)

    def get_success_url(self):
        if User.objects.all().count() == 1:
            return reverse("ctfpad:user-login")
        return reverse("ctfpad:dashboard")


class MemberUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    success_url = reverse_lazy('ctfpad:dashboard')
    template_name = "users/edit.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Member successfully updated"
    form_class = UpdateMemberForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.pk != request.user.id:
            raise Http404()
        return super().get(request, *args, **kwargs)


class MemberDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Member
    success_url = reverse_lazy('ctfpad:dashboard')
    template_name = "users/delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Member successfully deleted"
    # todo: also delete user


class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    template_name = "users/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    paginate_by = 10
    ordering = ["user_id"]


class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = "users/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        context = super(MemberDetailView, self).get_context_data(**kwargs)
        context.update(
            {"solved_challenges": Challenge.objects.filter(solver = self.object.id).order_by("-solved_time")}
        )
        return context