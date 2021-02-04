from ctfpad.mixins import MembersOnlyMixin
from ctfpad.decorators import only_if_authenticated_user
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q

from ctftools.settings import (
    HEDGEDOC_URL,
)

from ctfpad.forms import (
    CategoryCreateForm,
    CtfCreateUpdateForm, TagCreateForm,
)
from ctfpad.models import Ctf
from ctfpad.helpers import (
    ctftime_ctfs,
    ctftime_get_ctf_info,
    ctftime_parse_date
)


class CtfListView(LoginRequiredMixin, MembersOnlyMixin, ListView):
    model = Ctf
    template_name = "ctfpad/ctfs/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    paginate_by = 25
    ordering = ["-id"]
    extra_context = {
        "ctftime_ctfs": ctftime_ctfs(running=True, future=True),
    }

    def get_queryset(self):
        qs = super(CtfListView, self).get_queryset()
        return qs.filter( Q(visibility = "public" ) | Q(created_by = self.request.user.member ) )


class CtfCreateView(LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, CreateView):
    model = Ctf
    template_name = "ctfpad/ctfs/create.html"
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
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})


    def form_valid(self, form):
        if Ctf.objects.filter(name=form.instance.name, visibility="public").count() > 0:
            form.errors["name"] = "CtfAlreadyExistError"
            return render(self.request, self.template_name, {'form': form})

        if form.instance.ctftime_id:
            ctf = ctftime_get_ctf_info( form.instance.ctftime_id )
            form.instance.ctftime_id = ctf["id"]
            form.instance.name = ctf["title"]
            form.instance.url = ctf["url"]
            form.instance.description = ctf["description"]
            form.instance.start_date = ctftime_parse_date(ctf["start"])
            form.instance.end_date = ctftime_parse_date(ctf["finish"])

        form.instance.created_by = self.request.user.member
        return super().form_valid(form)


    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.object.pk})


class CtfImportView(CtfCreateView):
    def get(self, request, *args, **kwargs):
        initial = self.initial
        initial["name"] = request.GET.get("name") or ""

        try:
            initial["ctftime_id"] = int(request.GET.get("ctftime_id"))
        except ValueError:
            pass

        if initial["ctftime_id"]:
            ctf = ctftime_get_ctf_info(initial["ctftime_id"])
            initial["ctftime_id"] = ctf["id"]
            initial["name"] = ctf["title"]
            initial["url"] = ctf["url"]
            initial["description"] = ctf["description"]
            initial["start_date"] = ctftime_parse_date(ctf["start"])
            initial["end_date"] = ctftime_parse_date(ctf["finish"])
            initial["weight"] = ctf["weight"] or 1.0

        form = self.form_class(initial=initial)
        return render(request, self.template_name, {'form': form})


class CtfDetailView(LoginRequiredMixin, DetailView):
    model = Ctf
    template_name = "ctfpad/ctfs/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    extra_context = {
        "add_category_form": CategoryCreateForm(),
        "add_tag_form": TagCreateForm(),
        "hedgedoc_url": HEDGEDOC_URL,
    }


class CtfUpdateView(LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, UpdateView):
    model = Ctf
    form_class = CtfCreateUpdateForm
    template_name = "ctfpad/ctfs/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "CTF '%(name)s' updated"

    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if "visibility" in form.changed_data and self.request.user.member != form.instance.created_by:
            messages.error(self.request, f"Visibility can only by updated by {form.instance.created_by}")
            return render(self.request, self.template_name, {'form': form})
        return super().form_valid(form)


class CtfDeleteView(LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, DeleteView):
    model = Ctf
    success_url = reverse_lazy('ctfpad:dashboard')
    template_name = "ctfpad/ctfs/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "CTF deleted"


class CtfExportNotesView(LoginRequiredMixin, DetailView):
    model = Ctf
    template_name = "ctfpad/ctfs/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get(self, request, *args, **kwargs):
        self.ctf = self.get_object()
        response = HttpResponse(content_type="application/zip")
        zip_filename = self.ctf.export_notes_as_zipstream(response, request.user.member)
        response["Content-Disposition"] = f"attachment; filename={zip_filename}"
        return response
