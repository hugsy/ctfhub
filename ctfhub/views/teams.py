from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, UpdateView

from ctfhub.forms import TeamCreateUpdateForm
from ctfhub.mixins import RequireSuperPowersMixin
from ctfhub.models import Team

MESSAGE_SUCCESS_TEAM_CREATED: str = "Team successfully created"
MESSAGE_ERROR_MULTIPLE_TEAM_CREATE: str = "Only one team can be created"


class TeamCreateView(SuccessMessageMixin, CreateView):
    model = Team
    template_name = "team/create.html"
    form_class = TeamCreateUpdateForm
    success_url = reverse_lazy("ctfhub:dashboard")
    success_message = MESSAGE_SUCCESS_TEAM_CREATED

    def dispatch(self, request, *args, **kwargs):
        if Team.objects.all().count():
            messages.error(self.request, MESSAGE_ERROR_MULTIPLE_TEAM_CREATE)
            return redirect("ctfhub:home")
        if request.method and request.method.lower() in self.http_method_names:
            handler = getattr(
                self, request.method.lower(), self.http_method_not_allowed
            )
        else:
            handler = self.http_method_not_allowed
        return handler(request, *args, **kwargs)

    def get_success_message(self, cleaned_data):
        msg = f"Team '{self.object.name}' successfully created!"
        msg += f"Use the API key '{self.object.api_key}' to register new members."
        return msg


class TeamUpdateView(
    LoginRequiredMixin, RequireSuperPowersMixin, SuccessMessageMixin, UpdateView
):
    model = Team
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "team/edit.html"
    login_url = reverse_lazy("ctfhub:user-login")
    form_class = TeamCreateUpdateForm
    redirect_field_name = "redirect_to"
    success_message = "Team successfully edited"


class TeamDeleteView(
    LoginRequiredMixin, RequireSuperPowersMixin, SuccessMessageMixin, DeleteView
):
    model = Team
    success_url = reverse_lazy("ctfhub:team-register")
    template_name = "team/confirm_delete.html"
    login_url = reverse_lazy("ctfhub:user-login")
    redirect_field_name = "redirect_to"
    success_message = "Team successfully deleted"
