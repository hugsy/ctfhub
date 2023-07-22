import json

from django import forms
import django.contrib.auth
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from ctfhub.models import (
    Challenge,
    ChallengeCategory,
    ChallengeFile,
    Ctf,
    Member,
    Tag,
    Team,
)


class UserUpdateForm(UserChangeForm):
    class Meta:
        model = django.contrib.auth.get_user_model()
        fields = [
            "username",
            "email",
        ]

    current_password = forms.CharField(
        label="Current password", widget=forms.PasswordInput, required=True
    )


class TeamCreateUpdateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = [
            "name",
            "email",
            "twitter_url",
            "github_url",
            "youtube_url",
            "blog_url",
            "avatar",
            "ctftime_id",
        ]


class MemberCreateForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["username", "email", "password1", "password2", "api_key"]

    username = forms.CharField(
        required=True, widget=forms.TextInput(attrs={"placeholder": "Username"})
    )
    email = forms.CharField(
        required=True, widget=forms.TextInput(attrs={"placeholder": "Email address"})
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Password"})
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Repeat the password"})
    )
    api_key = forms.CharField(
        required=True,
        label="api_key",
        widget=forms.TextInput(attrs={"placeholder": "Team API key"}),
    )


class MemberUpdateForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "avatar",
            "description",
            "country",
            "timezone",
            "joined_time",
            "twitter_url",
            "github_url",
            "blog_url",
            "selected_ctf",
            "status",
        ]

    has_superpowers = forms.BooleanField(required=False, label="Has Super-Powers?")

    def clean(self):
        if "status" in self.cleaned_data:
            status = self.cleaned_data["status"]
            if (
                status == Member.StatusType.GUEST.value
                and not self.cleaned_data["selected_ctf"]
            ):
                raise ValidationError("Guests MUST have a selected_ctf")
        return super().clean()


class CtfCreateUpdateForm(forms.ModelForm):
    class Meta:
        model = Ctf
        fields = [
            "name",
            "url",
            "description",
            "start_date",
            "end_date",
            "flag_prefix",
            "team_login",
            "team_password",
            "ctftime_id",
            "weight",
            "rating",
            "visibility",
        ]

    weight = forms.FloatField(min_value=1.0, required=True)
    rating = forms.FloatField(min_value=0.0, required=True)


class ChallengeCreateForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = [
            "name",
            "points",
            "description",
            "category",
            "ctf",
        ]


class ChallengeUpdateForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = [
            "name",
            "points",
            "description",
            "category",
            "note_id",
            "excalidraw_room_id",
            "excalidraw_room_key",
            "ctf",
            "flag",
            "last_update_by",
            "solvers",
            "tags",
        ]

    def cleaned_tags(self):
        data = [x.lower() for x in self.cleaned_data["tags"].split()]
        return data


class ChallengeImportForm(forms.Form):
    FORMAT_CHOICES = (
        ("RAW", "RAW"),
        ("CTFd", "CTFd"),
        ("rCTF", "rCTF"),
    )
    format = forms.ChoiceField(choices=FORMAT_CHOICES, initial="CTFd")
    data = forms.CharField(widget=forms.Textarea)  # type: ignore  ## See https://docs.djangoproject.com/en/4.2/ref/forms/widgets/#specifying-widgets

    def clean_data(self):
        data = self.cleaned_data["data"]

        # Choose the cleaning method based on the format field.
        if not self.cleaned_data["format"] in ("RAW", "CTFd", "rCTF"):
            raise forms.ValidationError(
                _("Invalid data format: must be in %(formats)s"),
                params={"formats": str([x[0] for x in self.FORMAT_CHOICES])},
            )

        match self.cleaned_data["format"]:
            case "RAW":
                return self._clean_raw_data(data)
            case "CTFd":
                return self._clean_ctfd_data(data)
            case "rCTF":
                return self._clean_rctf_data(data)

    @staticmethod
    def _clean_raw_data(data):
        challenges: list[dict[str, str]] = []
        for num, line in enumerate(data.splitlines()):
            parts = line.split("|")
            if len(parts) != 2:
                raise forms.ValidationError(
                    _(
                        "RAW must respect a two-part format with | as separator: line %(linum)s - %(data)s"
                    ),
                    params={"linum": str(num + 1), "data": line},
                )
            challenges.append(
                {
                    "name": parts[0].strip(),
                    "category": parts[1].strip(),
                }
            )
        return challenges

    @staticmethod
    def _clean_ctfd_data(data):
        try:
            json_data = json.loads(data)
            if not json_data.get("success") or "data" not in json_data:
                raise ValidationError(
                    "Invalid JSON format. Please provide valid CTFd JSON data."
                )
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Invalid JSON format. Please provide valid CTFd JSON data."
            ) from exc

        return json_data["data"]

    @staticmethod
    def _clean_rctf_data(data):
        try:
            json_data = json.loads(data)
            if "successful" not in json_data.get("message") or "data" not in json_data:
                raise ValidationError(
                    "Invalid JSON format. Please provide valid rCTF JSON data."
                )
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Invalid JSON format. Please provide valid rCTF JSON data."
            ) from exc

        return json_data["data"]


class ChallengeSetFlagForm(ChallengeUpdateForm):
    class Meta:
        model = Challenge
        fields = [
            "flag",
            "last_update_by",
        ]


class ChallengeFileCreateForm(forms.ModelForm):
    class Meta:
        model = ChallengeFile
        fields = [
            "file",
            "challenge",
        ]


class CategoryCreateForm(forms.ModelForm):
    class Meta:
        model = ChallengeCategory
        fields = [
            "name",
        ]


class TagCreateForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = [
            "name",
        ]


class MemberMarkAsSelectedForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "selected_ctf",
        ]
