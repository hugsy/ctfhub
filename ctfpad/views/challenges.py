from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin

from ctfpad.forms import (
    ChallengeCreateForm,
    ChallengeUpdateForm,
    ChallengeSetFlagForm,
    ChallengeFileCreateForm,
)
from ctfpad.models import Challenge, Ctf
from ctftools.settings import HEDGEDOC_URL



class ChallengeListView(LoginRequiredMixin, ListView):
    model = Challenge
    template_name = "ctfpad/challenges/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"


class ChallengeCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Challenge
    template_name = "ctfpad/challenges/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = ChallengeCreateForm
    initial = {
        "name": "",
        "points": "",
        "description": "",
        "category": "",
        "flag": "",
        "solvers": "",
        "solved_time": "",
        "note_id": None,
        "jitsi_id": None,
    }
    success_message = "Challenge '%(name)s' successfully created"

    def get(self, request, *args, **kwargs):
        try:
            self.initial["ctf"] = Ctf.objects.get(pk=self.kwargs.get("ctf"))
        except Ctf.DoesNotExist:
            pass
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})


    def form_valid(self, form):
        if Challenge.objects.filter(name=form.instance.name, ctf=form.instance.ctf).count() > 0:
            form.errors["name"] = "ChallengeNameAlreadyExistError"
            return render(self.request, self.template_name, {'form': form})
        return super().form_valid(form)


    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.pk})


class ChallengeDetailView(LoginRequiredMixin, DetailView):
    model = Challenge
    template_name = "ctfpad/challenges/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    extra_context = {
        "flag_form": ChallengeSetFlagForm(),
        "file_upload_form": ChallengeFileCreateForm(),
        "hedgedoc_url": HEDGEDOC_URL,
    }

    # def get_context_data(self, **kwargs):
    #     ctx = super().get_context_data(**kwargs)
    #     return ctx


class ChallengeUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Challenge
    form_class = ChallengeUpdateForm
    template_name = "ctfpad/challenges/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Challenge successfully updated"

    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.pk})


class ChallengeSetFlagView(ChallengeUpdateView):
    form_class = ChallengeSetFlagForm

    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if form.instance.ctf.is_finished:
            messages.error(self.request, f"Cannot score when CTF is over")
            return redirect("ctfpad:challenges-detail", self.object.id)

        if not form.instance.flag.startswith( form.instance.ctf.flag_prefix ):
            messages.warning(self.request, f"Unexpected format for flag (missing '{form.instance.ctf.flag_prefix}')")

        return super().form_valid(form)


class ChallengeDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Challenge
    template_name = "ctfpad/challenges/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Challenge deleted successfully"

    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.object.ctf.id})
