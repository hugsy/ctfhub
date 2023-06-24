from django.views.generic import UpdateView, DeleteView, CreateView
from django.contrib import messages
from ctfpad.models import Team
from ctfpad.forms import TeamCreateUpdateForm
from django.shortcuts import redirect
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin

from ctfpad.mixins import RequireSuperPowersMixin


class TeamCreateView(SuccessMessageMixin, CreateView):
    model = Team
    template_name = "team/create.html"
    form_class = TeamCreateUpdateForm
    success_url = reverse_lazy("ctfpad:dashboard")
    success_message = "Team successfully created"

    def dispatch(self, request, *args, **kwargs):
        if Team.objects.all().count():
            messages.error(self.request, "Only one team can be created")
            return redirect("ctfpad:home")
        if request.method.lower() in self.http_method_names:
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
    success_url = reverse_lazy("ctfpad:dashboard")
    template_name = "team/edit.html"
    login_url = "/users/login/"
    form_class = TeamCreateUpdateForm
    redirect_field_name = "redirect_to"
    success_message = "Team successfully edited"


class TeamDeleteView(
    LoginRequiredMixin, RequireSuperPowersMixin, SuccessMessageMixin, DeleteView
):
    model = Team
    success_url = reverse_lazy("ctfpad:team-register")
    template_name = "team/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Team successfully deleted"
