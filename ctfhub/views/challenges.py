from typing import Any
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpRequest, HttpResponseNotFound
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)
from ctfhub import helpers

from ctfhub.forms import (
    ChallengeCreateForm,
    ChallengeFileCreateForm,
    ChallengeImportForm,
    ChallengeSetFlagForm,
    ChallengeUpdateForm,
)
from ctfhub.helpers import generate_github_page_header
from ctfhub.models import Challenge, ChallengeCategory, Ctf, Member


class ChallengeListView(LoginRequiredMixin, ListView):
    model = Challenge
    template_name = "ctfhub/challenges/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"


class ChallengeCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Challenge
    template_name = "ctfhub/challenges/create.html"
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
        if self.form_class:
            form = self.form_class(initial=self.initial)
        else:
            form = {}
        return render(request, self.template_name, {"form": form})

    def form_valid(self, form: ChallengeCreateForm):
        if (
            Challenge.objects.filter(
                name=form.instance.name, ctf=form.instance.ctf
            ).count()
            > 0
        ):
            form.errors["name"] = "ChallengeNameAlreadyExistError"
            return render(self.request, self.template_name, {"form": form})
        return super().form_valid(form)

    def get_success_url(self):
        obj: Challenge = self.object  # type: ignore
        return reverse("ctfhub:challenges-detail", kwargs={"pk": obj.pk})


class ChallengeImportView(LoginRequiredMixin, FormView):
    model = Challenge
    template_name = "ctfhub/challenges/import.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = ChallengeImportForm
    success_message = "Challenges were successfully imported!"

    def get(self, request, *args, **kwargs):
        self.initial["ctf"] = get_object_or_404(Ctf, pk=self.kwargs.get("ctf"))
        assert self.form_class
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {"form": form})

    def form_valid(self, form):
        ctf_id = self.kwargs.get("ctf")
        ctf = Ctf.objects.get(pk=ctf_id)
        data = form.cleaned_data["data"]

        try:
            for challenge in data:
                category, _ = ChallengeCategory.objects.get_or_create(
                    name=challenge["category"].strip().lower()
                )
                points = 0
                description = ""

                if form.cleaned_data["format"] == "CTFd":
                    points = challenge.get("value")
                elif form.cleaned_data["format"] == "rCTF":
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
        return reverse("ctfhub:ctfs-detail", kwargs={"pk": self.initial["ctf"].id})


class ChallengeDetailView(LoginRequiredMixin, DetailView):
    model = Challenge
    template_name = "ctfhub/challenges/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        obj = self.get_object()
        assert isinstance(obj, Challenge)
        member = Member.objects.get(user=self.request.user)
        cli = helpers.HedgeDoc(member)
        ctx = super().get_context_data(**kwargs)
        ctx |= {
            "flag_form": ChallengeSetFlagForm(),
            "file_upload_form": ChallengeFileCreateForm(),
            "hedgedoc_url": cli.public_url,
            "excalidraw_url": obj.get_excalidraw_url(member),
        }
        return ctx


class ChallengeUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Challenge
    form_class = ChallengeUpdateForm
    template_name = "ctfhub/challenges/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Challenge successfully updated"

    def get_success_url(self):
        return reverse("ctfhub:challenges-detail", kwargs={"pk": self.get_object().pk})

    def form_valid(self, form: ChallengeUpdateForm):
        if "solvers" in form.cleaned_data:
            if (
                len(form.cleaned_data["solvers"]) > 0 and not form.cleaned_data["flag"]
            ) or (len(form.cleaned_data["solvers"]) == 0 and form.cleaned_data["flag"]):
                messages.error(self.request, "Cannot set flag without solver(s)")
                return super().form_invalid(form)

        return super().form_valid(form)


class ChallengeSetFlagView(ChallengeUpdateView):
    form_class = ChallengeSetFlagForm
    template_name = "ctfhub/challenges/detail.html"

    def get_success_url(self):
        return reverse("ctfhub:challenges-detail", kwargs={"pk": self.get_object().pk})

    def form_valid(self, form):
        if form.instance.ctf.is_finished:
            messages.error(self.request, "Cannot score when CTF is over")
            return redirect("ctfhub:challenges-detail", self.get_object().pk)

        if form.instance.ctf.flag_prefix and "flag" in form.cleaned_data:
            if not form.cleaned_data["flag"].startswith(form.instance.ctf.flag_prefix):
                messages.warning(
                    self.request,
                    f"Unexpected flag format: missing pattern '{form.instance.ctf.flag_prefix}'",
                )

        return super().form_valid(form)


class ChallengeDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Challenge
    template_name = "ctfhub/challenges/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Challenge deleted successfully"

    def get_success_url(self):
        obj = self.get_object()
        assert isinstance(obj, Challenge)
        return reverse("ctfhub:ctfs-detail", kwargs={"pk": obj.ctf.pk})


class ChallengeExportAsGithubPageView(LoginRequiredMixin, DetailView):
    model = Challenge
    template_name = "ctfhub/challenges/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        assert isinstance(obj, Challenge)
        member = Member.objects.get(user=self.request.user)
        assert obj.category, "Challenge must always have category"
        tags = f"[{obj.category.name}, {','.join([t.name for t in obj.tags.all()])} ]"
        content = generate_github_page_header(
            title=obj.name, author=member.username, tags=tags
        )
        if obj.description:
            content += f"Description:\n> {obj.description}\n\n"
        content += member.export_note(obj.note_id)
        response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
        response["Content-Length"] = len(content)
        return response


@login_required
def assign_to_current_member(request: HttpRequest, pk: str) -> HttpResponse:
    """Assign the current member to the challenge

    Args:
        request (HttpRequest): _description_
        pk (str): _description_

    Returns:
        HttpResponse: _description_
    """
    if not request.method == "POST":
        return HttpResponseNotFound()

    challenge = get_object_or_404(Challenge, pk=pk)
    member = Member.objects.get(user=request.user)

    #
    # Toggle the current user's assignment to the challenge
    #
    if member in challenge.assigned_members.all():
        challenge.assigned_members.remove(member)
        messages.info(
            request,
            f"{member.username} removed from assigned players of {challenge.ctf.name}/{challenge.name}",
        )

    else:
        challenge.assigned_members.add(member)
        messages.info(
            request,
            f"{member.username} added to assigned players of {challenge.ctf.name}/{challenge.name}",
        )

    #
    # Update last modification date
    #
    member.save()

    return redirect(reverse("ctfhub:ctfs-detail", kwargs={"pk": challenge.ctf.id}))
