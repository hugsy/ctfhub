from pathlib import Path
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import DeleteView, CreateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin

from ctfpad.forms import ChallengeFileCreateForm
from ctfpad.models import ChallengeFile


class ChallengeFileCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = ChallengeFile
    template_name = "ctfpad/challenges/files/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = ChallengeFileCreateForm
    success_message = "File added!"

    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.challenge.id})


class ChallengeFileDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ChallengeFile
    template_name = "ctfpad/challenges/files/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "File deleted!"

    def get_success_url(self):
        return reverse("ctfpad:challenges-detail", kwargs={'pk': self.object.challenge.id})

    def post(self, request, *args, **kwargs):
        fpath = Path(self.get_object().file.path)
        res = self.delete(request, *args, **kwargs)
        # delete the file on-disk: https://docs.djangoproject.com/en/3.1/releases/1.3/#deleting-a-model-doesn-t-delete-associated-files
        if fpath.exists():
            fpath.unlink()
        return res


class ChallengeFileDetailView(LoginRequiredMixin, SuccessMessageMixin, DetailView):
    model = ChallengeFile
    template_name = "ctfpad/challenges/files/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    initial = {}

    def get(self, request, *args, **kwargs):
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})

