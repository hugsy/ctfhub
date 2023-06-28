from ctfhub.forms import CategoryCreateForm
from ctfhub.mixins import MembersOnlyMixin
from ctfhub.models import ChallengeCategory
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.urls.base import reverse
from django.views.generic.edit import CreateView


class CategoryCreateView(
    LoginRequiredMixin, MembersOnlyMixin, SuccessMessageMixin, CreateView
):
    model = ChallengeCategory
    template_name = "ctfhub/categories/create.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    form_class = CategoryCreateForm
    success_message = "Category '%(name)s' successfully was created!"
    initial = {
        "name": "",
    }

    def get(self, request, *args, **kwargs):
        assert self.form_class
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {"form": form})

    def form_valid(self, form: CategoryCreateForm):
        category_name = form.instance.name.strip().lower()
        form.cleaned_data["name"] = category_name
        return super().form_valid(form)

    def get_success_url(self):
        redirect_to = self.request.META.get("HTTP_REFERER") or reverse(
            "ctfhub:dashboard"
        )
        return redirect_to
