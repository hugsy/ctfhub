from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.urls.base import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView

from ctfhub.forms import TagCreateForm
from ctfhub.mixins import MembersOnlyMixin
from ctfhub.models import Tag


class TagCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Tag
    template_name = "ctfhub/tags/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = TagCreateForm
    success_message = "Tag '%(name)s' added!"
    initial = {
        "name": "",
    }

    def get(self, request, *args, **kwargs):
        assert self.form_class
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {"form": form})

    def form_valid(self, form: TagCreateForm):
        form.cleaned_data["name"] = form.instance.name.strip().lower()
        return super().form_valid(form)

    def get_success_url(self):
        redirect_to = self.request.META.get("HTTP_REFERER") or reverse(
            "ctfhub:dashboard"
        )
        return redirect_to


class TagListView(LoginRequiredMixin, MembersOnlyMixin, ListView):
    model = Tag
    template_name = "ctfhub/tags/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx |= {
            "add_tag_form": TagCreateForm(),
        }
        return ctx


class TagDeleteView(
    LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, DeleteView
):
    model = Tag
    template_name = "ctfhub/tags/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Tag deleted successfully"
    success_url = reverse_lazy("ctfhub:tags-list")
