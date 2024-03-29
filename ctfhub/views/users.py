import django.contrib.auth.models
from django.contrib import auth, messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.forms.models import BaseModelForm
from django.http.request import HttpRequest
from django.http.response import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ctfhub import helpers
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
    model = django.contrib.auth.models.User
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "users/edit_advanced.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "User settings successfully updated"
    form_class = UserUpdateForm

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        member = Member.objects.get(user=request.user)

        if not member.has_superpowers:
            # Not admin
            return HttpResponseForbidden()

        if obj.pk != member.pk:
            # Trying to edit a different user/member
            return HttpResponseForbidden()

        return super().get(request, *args, **kwargs)

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        password = form.cleaned_data["current_password"]
        if not self.request.user.check_password(password):
            messages.error(self.request, "Incorrect password")
            return super().form_invalid(form)
        return super().form_valid(form)


class UserPasswordUpdateView(
    LoginRequiredMixin, SuccessMessageMixin, PasswordChangeView
):
    model = django.contrib.auth.models.User
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

    def form_valid(self, form: MemberCreateForm):
        # validate passwords
        if form.cleaned_data["password1"] != form.cleaned_data["password2"]:
            messages.error(self.request, "Password mismatch")
            return self.form_invalid(form)

        # validate team and get api_key
        team = Team.objects.first()
        if not team:
            return redirect("ctfhub:team-register")

        if team.api_key != form.cleaned_data["api_key"]:
            messages.error(
                self.request, f"The API key for team '{team.name}' is invalid"
            )
            return self.form_invalid(form)

        # validate user uniqueness
        user_cnt = django.contrib.auth.models.User.objects.all().count()
        users = django.contrib.auth.models.User.objects.filter(
            username=form.cleaned_data["username"]
        )
        if users.count() > 0:
            form.errors["name"] = "UsernameAlreadyExistError"
            messages.error(
                self.request, "Username already exists, try logging in instead"
            )
            return self.form_invalid(form)

        # create the django user
        user = django.contrib.auth.models.User.objects.create_user(
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
        if django.contrib.auth.models.User.objects.all().count() == 1:
            return reverse("ctfhub:user-login")
        return reverse("ctfhub:dashboard")


class MemberUpdateView(
    UserPassesTestMixin, LoginRequiredMixin, SuccessMessageMixin, UpdateView
):
    model = Member
    success_url = reverse_lazy("ctfhub:dashboard")
    template_name = "users/edit.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Member successfully updated"
    form_class = MemberUpdateForm

    def test_func(self) -> bool:
        obj = self.get_object()
        member = Member.objects.get(user=self.request.user)
        return member.has_superpowers or obj.pk == member.pk

    def get_context_data(self, **kwargs):
        obj = self.get_object()
        assert isinstance(obj, Member)
        if "form" not in kwargs:
            kwargs["form"] = self.get_form()
        kwargs["form"].initial["has_superpowers"] = obj.has_superpowers
        return super().get_context_data(**kwargs)

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        member = Member.objects.get(user=self.request.user)
        if member.has_superpowers and "has_superpowers" in form.cleaned_data:
            if form.cleaned_data["has_superpowers"] is True:
                # any superuser can make another user become a superuser
                member.user.is_superuser = True
            else:
                # any superuser can be downgraded to user, except user_id = 1
                if member.user.pk != 1:
                    member.user.is_superuser = False
            member.user.save()
        return super().form_valid(form)


class MemberMarkAsSelectedView(MemberUpdateView):
    form_class = MemberMarkAsSelectedForm

    def get_success_url(self):
        obj: Member = self.object  # type: ignore
        assert obj.selected_ctf, "CTF was just assigned, should not be None"
        return reverse("ctfhub:ctfs-detail", kwargs={"pk": obj.selected_ctf.pk})

    def get_success_message(self, cleaned_data):
        return f"Marked as Working On CTF {cleaned_data['selected_ctf']}"


class MemberDeleteView(
    LoginRequiredMixin, RequireSuperPowersMixin, SuccessMessageMixin, DeleteView
):
    model = Member
    success_url = reverse_lazy("ctfhub:stats-detail")
    template_name = "users/confirm_delete.html"
    login_url = "/users/login/"
    redirect_field_name = "redirect_to"
    success_message = "Member successfully deleted"

    def post(self, request, *args, **kwargs):
        member: Member = self.get_object()  # type: ignore
        if member.has_superpowers:
            messages.error(request, "Refusing to delete super-user")
            return redirect("ctfhub:home")

        # rotate the team api key as it might have been shared with the to-be deleted user
        team = Team.objects.first()
        assert team
        team.api_key = get_random_string_128()
        team.save()

        # delete the hedgedoc user
        cli = helpers.HedgeDoc((member.hedgedoc_username, member.hedgedoc_password))
        assert cli.login()
        cli.delete()

        # propagate to the super() method to trigger the deletion
        return super().post(request, *args, **kwargs)


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
        context = super().get_context_data(**kwargs)
        return context


class UserResetPassword(SuccessMessageMixin, PasswordResetView):
    model = django.contrib.auth.models.User
    template_name = "users/password_reset.html"
    success_message = "If a match was found, an email will be received with the password reset procedure."
    success_url = reverse_lazy("ctfhub:user-login")
    email_template_name = "users/password_reset_email.txt"
    subject_template_name = "users/password_reset_subject.txt"
    title = "Password Reset"


class UserChangePassword(SuccessMessageMixin, PasswordResetConfirmView):
    model = django.contrib.auth.models.User
    template_name = "users/password_change.html"
    success_message = "Password successfully changed."
    success_url = reverse_lazy("ctfhub:user-login")
    title = "Password changed"
