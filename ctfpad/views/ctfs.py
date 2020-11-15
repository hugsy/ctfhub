from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render, redirect
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin

from ctfpad.forms import CreateUpdateCtfForm
from ctfpad.models import Ctf
from ctfpad.helpers import ctftime_fetch_next_ctf_data


class CtfListView(LoginRequiredMixin, ListView):
    model = Ctf
    template_name = "ctfpad/ctfs/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    paginate_by = 10
    ordering = ["id"]
    extra_context = {
        "ctftime_ctfs": ctftime_fetch_next_ctf_data(),
    }


class CtfCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Ctf
    template_name = "ctfpad/ctfs/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = CreateUpdateCtfForm
    initial = {
        "name": "",
        "url": "",
        "description": "",
        "start_date": "",
        "end_date": "",
        "flag_prefix": "",
    }
    success_message = "CTF '%(name)s' created"

    def get(self, request, *args, **kwargs):
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})


    def form_valid(self, form):
        if Ctf.objects.filter(name=form.instance.name).count() > 0:
            form.errors["name"] = "CtfAlreadyExistError"
            return render(self.request, self.template_name, {'form': form})
        return super().form_valid(form)


    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.object.pk})


class CtfDetailView(LoginRequiredMixin, DetailView):
    model = Ctf
    template_name = "ctfpad/ctfs/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"


class CtfUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Ctf
    form_class = CreateUpdateCtfForm
    template_name = "ctfpad/ctfs/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "CTF '%(name)s' updated"

    def get_success_url(self):
        return reverse("ctfpad:ctfs-detail", kwargs={'pk': self.object.pk})


class CtfDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Ctf
    success_url = reverse_lazy('ctfpad:dashboard')
    template_name = "ctfpad/ctfs/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "CTF '%(name)s' deleted"

