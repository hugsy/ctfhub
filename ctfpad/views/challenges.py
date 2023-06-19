import json

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from ctfpad.decorators import only_if_authenticated_user
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView, FormView
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ctfpad.decorators import user

from ctfpad.forms import (
    ChallengeCreateForm,
    ChallengeFileCreateForm,
    ChallengeSetFlagForm,
    ChallengeUpdateForm,
    ChallengeImportForm,
)
from ctfpad.models import Challenge, Ctf, ChallengeCategory
from ctftools.settings import HEDGEDOC_URL

from ctfpad.helpers import (
    export_challenge_note,
    generate_github_page_header,
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


class ChallengeImportView(LoginRequiredMixin, FormView):
    model = Challenge
    template_name = "ctfpad/challenges/import.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = ChallengeImportForm
    success_message = "Challenges were successfully imported!"

    def get(self, request, *args, **kwargs):
        self.initial["ctf"] = self.kwargs.get("ctf")
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})

    def form_valid(self, form):
        ctf_id = self.kwargs.get("ctf")
        ctf = Ctf.objects.get(pk=ctf_id)
        data = form.cleaned_data['data']

        try:
            for challenge in data:
                category, created = ChallengeCategory.objects.get_or_create(name=challenge["category"].strip().lower())
                points = 0
                description = ""

                if form.cleaned_data['format'] == 'CTFd':
                    points = challenge.get("value")
                elif form.cleaned_data['format'] == 'rCTF':
                    points = challenge.get("points")
                    description = challenge.get("description")

                defaults = {
                    "name": challenge.get("name"),
                    "points": points,
                    "category": category,
                    "description": description,
                    "ctf": ctf,
                }

                Challenge.objects.update_or_create(
                    defaults=defaults,
                    name=challenge.get("name"),
                    ctf=ctf,
                )

            messages.success(self.request, "Import successful!")
            return super().form_valid(form)
        except Exception as e:
            messages.error(self.request, f"Error: {str(e)}")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.initial["ctf"]})


class ChallengeDetailView(LoginRequiredMixin, DetailView):
    model = Challenge
    template_name = "ctfpad/challenges/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx |= {
            "flag_form": ChallengeSetFlagForm(),
            "file_upload_form": ChallengeFileCreateForm(),
            "hedgedoc_url": HEDGEDOC_URL,
            "excalidraw_url": self.object.get_excalidraw_url(self.request.user.member),
        }
        return ctx


class ChallengeUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Challenge
    form_class = ChallengeUpdateForm
    template_name = "ctfpad/challenges/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Challenge successfully updated"

    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if "solvers" in form.cleaned_data:

            if (len(form.cleaned_data["solvers"]) > 0 and not form.cleaned_data["flag"]) or \
                    (len(form.cleaned_data["solvers"]) == 0 and form.cleaned_data["flag"]):
                messages.error(
                    self.request, "Cannot set flag without solver(s)")
                return redirect("ctfpad:challenges-detail", self.object.id)

        return super().form_valid(form)


class ChallengeSetFlagView(ChallengeUpdateView):
    form_class = ChallengeSetFlagForm
    template_name = "ctfpad/challenges/detail.html"

    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if form.instance.ctf.is_finished:
            messages.error(self.request, f"Cannot score when CTF is over")
            return redirect("ctfpad:challenges-detail", self.object.id)

        if form.instance.ctf.flag_prefix and "flag" in form.cleaned_data:
            if not form.cleaned_data["flag"].startswith(form.instance.ctf.flag_prefix):
                messages.warning(
                    self.request, f"Unexpected flag format: missing pattern '{form.instance.ctf.flag_prefix}'")

        return super().form_valid(form)


class ChallengeDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Challenge
    template_name = "ctfpad/challenges/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Challenge deleted successfully"

    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.object.ctf.id})


class ChallengeExportAsGithubPageView(LoginRequiredMixin, DetailView):
    model = Challenge
    template_name = "ctfpad/challenges/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get(self, request, *args, **kwargs):
        c = self.get_object()
        u = request.user.member
        tags = "[" + c.category.name + ","
        for t in c.tags.all():
            tags += t.name + ","
        tags += "]"
        content = generate_github_page_header(
            title=c.name, author=u.username, tags=tags)
        if c.description:
            content += f"Description:\n> {c.description}\n\n"
        content += export_challenge_note(u, c.note_id)
        response = HttpResponse(
            content, content_type="text/markdown; charset=utf-8")
        response["Content-Length"] = len(content)
        return response
