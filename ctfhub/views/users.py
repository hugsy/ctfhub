from django.contrib import auth, messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.forms.models import BaseModelForm
from django.http.request import HttpRequest
from django.http.response import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ctfhub.forms import (
    MemberCreateForm,
    MemberMarkAsSelectedForm,
    MemberUpdateForm,
    UserUpdateForm,
)
from ctfhub.helpers import get_random_string_128
from ctfhub.mixins import RequireSuperPowersMixin
from ctfhub.models import Member, Team


class CtfhubLogin(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = False
    redirect_field_name = "redirect_to"


@login_required
def logout(request: HttpRequest) -> HttpResponse:
    """Log out from current session. CBV is not necessary for logging out.

    Args:
        request (HttpRequest): [description]

    Returns:
        HttpResponse: [description]
    """
    auth.logout(request)
    return redirect("ctfhub:home")


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "users/edit_advanced.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "User settings successfully updated"
    form_class = UserUpdateForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if (
            not request.user.member.has_superpowers
            and self.object.pk != request.user.id
        ):
            raise Http404()
        return super().get(request, *args, **kwargs)

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        password = form.cleaned_data["current_password"]
        if not self.request.user.check_password(password):
            messages.error(self.request, "Incorrect password")
            return redirect("ctfhub:users-update-advanced", self.request.user.member.id)
        return super().form_valid(form)


class UserPasswordUpdateView(
    LoginRequiredMixin, SuccessMessageMixin, PasswordChangeView
):
    model = User
    success_url = reverse_lazy("ctfhub:user-logout")
    template_name = "users/edit_advanced_change_password.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Password successfully updated, please log back in."


class MemberCreateView(SuccessMessageMixin, CreateView):
    model = Member
    template_name = "users/register.html"
    form_class = MemberCreateForm
    success_message = "Member '%(username)s' successfully created"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def form_valid(self, form):
        # validate team presence
        teams = Team.objects.all()
        if teams.count() == 0:
            messages.error(self.request, "A team must be registered first!")
            return redirect("ctfhub:team-register")

        # validate passwords
        if form.cleaned_data["password1"] != form.cleaned_data["password2"]:
            messages.error(self.request, "Password mismatch")
            return self.form_invalid(form)

        # validate api_key
        team = teams.first()
        if not team:
            return redirect("ctfhub:team-register")

        if team.api_key != form.cleaned_data["api_key"]:
            messages.error(
                self.request, f"The API key for team '{team.name}' is invalid"
            )
            return self.form_invalid(form)

        # validate user uniqueness
        user_cnt = User.objects.all().count()
        users = User.objects.filter(username=form.cleaned_data["username"])
        if users.count() > 0:
            form.errors["name"] = "UsernameAlreadyExistError"
            messages.error(
                self.request, "Username already exists, try logging in instead"
            )
            return self.form_invalid(form)

        # create the django user
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password1"],
            email=form.cleaned_data["email"],
        )
        user.save()

        # populate the missing required fields
        form.instance.user = user
        form.instance.team = team

        if user_cnt == 0:
            # if we created the first user, mark it as superuser
            user.is_superuser = True
            user.save()

        # process
        return super().form_valid(form)

    def get_success_url(self):
        if User.objects.all().count() == 1:
            return reverse("ctfhub:user-login")
        return reverse("ctfhub:dashboard")


class MemberUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "users/edit.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Member successfully updated"
    form_class = MemberUpdateForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if (
            not request.user.member.has_superpowers
            and self.object.pk != request.user.member.id
        ):
            raise Http404()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        if "form" not in kwargs:
            kwargs["form"] = self.get_form()
        kwargs["form"].initial["has_superpowers"] = self.get_object().has_superpowers
        return super().get_context_data(**kwargs)

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        if (
            self.request.user.member.has_superpowers
            and "has_superpowers" in form.cleaned_data
        ):
            member = self.get_object()
            if form.cleaned_data["has_superpowers"] is True:
                # any superuser can make another user become a superuser
                member.user.is_superuser = True
            else:
                # any superuser can be downgraded to user, except user_id = 1
                if member.user.id != 1:
                    member.user.is_superuser = False
            member.user.save()
        return super().form_valid(form)


class MemberMarkAsSelectedView(MemberUpdateView):
    form_class = MemberMarkAsSelectedForm

    def get_success_url(self):
        return reverse("ctfhub:ctfs-detail", kwargs={"pk": self.object.selected_ctf.id})

    def get_success_message(self, cleaned_data):
        return f"CTF {cleaned_data['selected_ctf']} mark as Current"


class MemberDeleteView(
    LoginRequiredMixin, RequireSuperPowersMixin, SuccessMessageMixin, DeleteView
):
    model = Member
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "users/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Member successfully deleted"

    def post(self, request, *args, **kwargs):
        member = self.get_object()
        if member.has_superpowers:
            messages.error(request, "Refusing to delete super-user")
            return redirect("ctfhub:home")

        # rotate the team api key
        t = Team.objects.first()
        t.api_key = get_random_string_128()
        t.save()

        # delete the associated django user
        member.user.delete()

        # delete the member entry
        return self.delete(request, *args, **kwargs)


class MemberListView(LoginRequiredMixin, RequireSuperPowersMixin, ListView):
    model = Member
    template_name = "users/list.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    paginate_by = 10
    ordering = ["user_id"]


class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = "users/detail.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        context = super(MemberDetailView, self).get_context_data(**kwargs)
        return context


class UserResetPassword(SuccessMessageMixin, PasswordResetView):
    model = User
    template_name = "users/password_reset.html"
    success_message = "If a match was found, an email will be received with the password reset procedure."
    success_url = reverse_lazy("ctfhub:user-login")
    email_template_name = "users/password_reset_email.txt"
    subject_template_name = "users/password_reset_subject.txt"
    title = "Password Reset"


class UserChangePassword(SuccessMessageMixin, PasswordResetConfirmView):
    model = User
    template_name = "users/password_change.html"
    success_message = "Password successfully changed."
    success_url = reverse_lazy("ctfhub:user-login")
    title = "Password changed"
