from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView
from django_sendfile import sendfile

from ctfhub.forms import ChallengeFileCreateForm
from ctfhub.models import Challenge, ChallengeFile


class ChallengeFileCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = ChallengeFile
    template_name = "ctfhub/challenges/files/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = ChallengeFileCreateForm
    success_message = "File added!"

    def get_success_url(self):
        obj: ChallengeFile = self.object  # type: ignore
        return reverse("ctfhub:challenges-detail", kwargs={"pk": obj.challenge.id})


class ChallengeFileDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ChallengeFile
    template_name = "ctfhub/challenges/files/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "File deleted!"

    def get_success_url(self):
        obj = self.get_object()
        assert isinstance(obj, ChallengeFile)
        return reverse("ctfhub:challenges-detail", kwargs={"pk": obj.challenge.id})

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        assert isinstance(obj, ChallengeFile)
        fpath = Path(obj.file.path)
        res = self.delete(request, *args, **kwargs)
        # delete the file on-disk
        # https://docs.djangoproject.com/en/3.1/releases/1.3/#deleting-a-model-doesn-t-delete-associated-files
        if fpath.exists():
            fpath.unlink()
        return res


class ChallengeFileDetailView(LoginRequiredMixin, SuccessMessageMixin, DetailView):
    model = ChallengeFile
    template_name = "ctfhub/challenges/files/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"form": {}})


@login_required
def challenge_file_download_view(request: HttpRequest, challenge_id: int, pk: int):
    """Download a file from its

    Args:
        request (HttpRequest): _description_
        challenge_id (int): _description_

    Raises:
        AssertionError: if there's a mismatch between the file challenge and the challenge associated to it
        (sanity check)

    Returns:
        _type_: _description_
    """
    challenge = get_object_or_404(Challenge, pk=challenge_id)
    challenge_file = get_object_or_404(ChallengeFile, pk=pk)
    assert challenge_file.challenge == challenge
    return sendfile(request, challenge_file.file.path, mimetype=challenge_file.mime)
