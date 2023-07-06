import requests
from ctfhub import helpers
from ctfhub.forms import CategoryCreateForm, CtfCreateUpdateForm, TagCreateForm
from ctfhub.mixins import MembersOnlyMixin
from ctfhub.models import Ctf, Member, Team
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http.response import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)


class CtfListView(LoginRequiredMixin, MembersOnlyMixin, ListView):
    model = Ctf
    template_name = "ctfhub/ctfs/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    paginate_by = 25
    ordering = ["-id"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctfs = helpers.CtfTime.ctfs(running=True, future=True)
        except RuntimeError:
            ctfs = []
            messages.warning(self.request, "CTFTime GET request failed")
        ctx |= {"ctftime_ctfs": ctfs}
        return ctx

    def get_queryset(self):
        qs = super(CtfListView, self).get_queryset()
        return qs.filter(
            Q(visibility=Ctf.VisibilityType.PUBLIC) | Q(created_by=self.member)
        ).order_by("-start_date")


class CtfCreateView(
    LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, CreateView
):
    model = Ctf
    template_name = "ctfhub/ctfs/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = CtfCreateUpdateForm
    initial = {
        "name": "",
        "url": "",
        "description": "",
        "start_date": "",
        "end_date": "",
        "flag_prefix": "",
        "team_login": "",
        "team_password": "",
        "jitsi_id": "",
        "weight": "1",
    }
    success_message = "CTF '%(name)s' created"

    def get(self, request, *args, **kwargs):
        assert self.form_class
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {"form": form})

    def form_valid(self, form: CtfCreateUpdateForm) -> HttpResponse:
        if Ctf.objects.filter(name=form.instance.name, visibility="public").count() > 0:
            form.errors["name"] = "CtfAlreadyExistError"
            return render(self.request, self.template_name, {"form": form})

        if form.instance.ctftime_id:
            try:
                ctf = helpers.CtfTime.fetch_ctf_info(form.instance.ctftime_id)
                form.instance.ctftime_id = ctf["id"]
                form.instance.name = ctf["title"]
                form.instance.url = ctf["url"]
                form.instance.description = ctf["description"]
                form.instance.start_date = helpers.CtfTime.parse_date(ctf["start"])
                form.instance.end_date = helpers.CtfTime.parse_date(ctf["finish"])
            except (RuntimeError, requests.exceptions.ReadTimeout) as e:
                messages.warning(self.request, f"CTFTime GET request failed: {str(e)}")

        member = Member.objects.get(user=self.request.user)
        form.instance.created_by = member
        return super().form_valid(form)

    def get_success_url(self):
        obj: Ctf = self.object  # type: ignore
        return reverse("ctfhub:ctfs-detail", kwargs={"pk": obj.pk})


class CtfImportView(CtfCreateView):
    def get(self, request, *args, **kwargs):
        initial = self.initial
        initial["name"] = request.GET.get("name") or ""

        try:
            initial["ctftime_id"] = int(request.GET.get("ctftime_id"))
        except ValueError:
            pass

        if initial["ctftime_id"]:
            try:
                ctf = helpers.CtfTime.fetch_ctf_info(initial["ctftime_id"])
                initial["ctftime_id"] = ctf["id"]
                initial["name"] = ctf["title"]
                initial["url"] = ctf["url"]
                initial["description"] = ctf["description"]
                initial["start_date"] = helpers.CtfTime.parse_date(ctf["start"])
                initial["end_date"] = helpers.CtfTime.parse_date(ctf["finish"])
                initial["weight"] = ctf["weight"]
            except (RuntimeError, requests.exceptions.ReadTimeout) as e:
                messages.warning(self.request, f"CTFTime GET request failed: {str(e)}")

        assert self.form_class
        form = self.form_class(initial=initial)
        return render(request, self.template_name, {"form": form})


class CtfDetailView(LoginRequiredMixin, DetailView):
    model = Ctf
    template_name = "ctfhub/ctfs/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    extra_context = {
        "add_category_form": CategoryCreateForm(),
        "add_tag_form": TagCreateForm(),
        "hedgedoc_url": helpers.HedgeDoc(("anonymous", "")).public_url,
    }

    def get_context_data(self, **kwargs):
        obj = self.get_object()
        assert isinstance(obj, Ctf)
        ctx = super().get_context_data(**kwargs)
        ctx |= {
            "team_timeline": obj.team_timeline(),
        }
        return ctx


class CtfUpdateView(
    LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, UpdateView
):
    model = Ctf
    form_class = CtfCreateUpdateForm
    template_name = "ctfhub/ctfs/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "CTF '%(name)s' updated"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx |= {"team": Team.objects.first()}
        return ctx

    def get_success_url(self):
        obj = self.get_object()
        assert isinstance(obj, Ctf)
        return reverse("ctfhub:ctfs-detail", kwargs={"pk": obj.pk})

    def form_valid(self, form: CtfCreateUpdateForm):
        if (
            "visibility" in form.changed_data
            and self.member != form.instance.created_by
        ):
            messages.error(
                self.request,
                f"Visibility can only by updated by {form.instance.created_by}",
            )
            return super().form_invalid(form)
        return super().form_valid(form)


class CtfDeleteView(
    LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, DeleteView
):
    model = Ctf
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "ctfhub/ctfs/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "CTF deleted"


class CtfExportNotesView(LoginRequiredMixin, DetailView):
    model = Ctf
    template_name = "ctfhub/ctfs/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        ctf = self.get_object()
        assert isinstance(ctf, Ctf)
        response = HttpResponse(content_type="application/zip")
        member = Member.objects.get(user=self.request.user)
        zip_filename = ctf.export_notes_as_zipstream(response, member)  # type: ignore HttpResponse is compatible with IO[bytes]
        response["Content-Disposition"] = f"attachment; filename={zip_filename}"
        return response
