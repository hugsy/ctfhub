from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from django import forms
from django.forms import widgets

from ctfpad.models import Challenge, ChallengeCategory, ChallengeFile, Ctf, Member, Tag, Team


class UserUpdateForm(UserChangeForm):
    class Meta:
        model = User
        fields = [
            "username",
            "email",
        ]
    current_password = forms.CharField(label="Current password", widget=forms.PasswordInput, required=True)



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
        exclude = [
            "user",
            "team",
            "country",
            "timezone",
            "last_scored",
            "last_ip",
            "last_active_notification",
            "last_logged_in",
            "hedgedoc_password",
            "joined_time",
            "twitter_url",
            "github_url",
            "blog_url",
            "selected_ctf",
        ]

    username = forms.CharField(required=True, widget=forms.TextInput(attrs={'placeholder': 'Username'}))
    email = forms.CharField(required=True, widget=forms.TextInput(attrs={'placeholder': 'Email address'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Repeat the password'}))
    api_key = forms.CharField(required = True, label = "api_key", widget=forms.TextInput(attrs={'placeholder': 'Team API key'}))


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
        ]

    has_superpowers = forms.BooleanField(required=False, label="Has Super-Powers?")


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
            "visibility",
            "whiteboard_access_token",
        ]


class ChallengeCreateForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = [
            "name",
            "points",
            "description",
            "category",
            "note_id",
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
            "whiteboard_id",
            "ctf",
            "flag",
            "last_update_by",
            "solvers",
            "tags",
        ]

    def cleaned_tags(self):
        data = [x.lower() for x in self.cleaned_data['tags'].split()]
        return data

    def clean_flag(self):
        flag = self.cleaned_data.get("flag")
        prefix = self.instance.ctf.flag_prefix

        if flag and prefix and not flag.startswith(prefix):
            self.add_error("flag", f"Unexpected format for flag (missing '{prefix}')")

        return flag


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