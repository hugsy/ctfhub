from django.views.generic import UpdateView, DeleteView, CreateView
from django.contrib import messages
from ctfpad.models import Team
from ctfpad.forms import TeamCreateUpdateForm
from django.shortcuts import redirect
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin


class TeamCreateView(SuccessMessageMixin, CreateView):
    model = Team
    template_name = "team/create.html"
    form_class = TeamCreateUpdateForm
    success_url = reverse_lazy("ctfpad:users-register")
    success_message = "FOO"

    def form_valid(self, form):
        if Team.objects.count() == 1:
            form.errors["name"] = "TeamAlreadyExistError"
            messages.error(self.request, "Only one team can be created")
            return redirect("ctfpad:home")
        return super().form_valid(form)

    def get_success_message(self, cleaned_data):
        msg = f"Team '{self.object.name}' successfully created!<br>"
        msg+= f"Use the API key <b>'{self.object.api_key}</b> to register new members."
        return msg


class TeamUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Team
    success_url = reverse_lazy('ctfpad:dashboard')
    template_name = "team/update.html"
    login_url = "/users/login/"
    form_class = TeamCreateUpdateForm
    redirect_field_name = "redirect_to"
    success_message = "Team successfully edited"


class TeamDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Team
    success_url = reverse_lazy('ctfpad:team-register')
    template_name = "team/delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Team successfully deleted"