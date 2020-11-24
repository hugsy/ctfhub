from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User

from django import forms
from django.forms import widgets

from ctfpad.models import Challenge, ChallengeCategory, ChallengeFile, Ctf, Member, Team

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
            "ctf",
            "flag",
            "last_update_by",
            "solvers",
        ]

    is_update = True


class ChallengeSetFlagForm(forms.ModelForm):
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



class MemberMarkAsSelectedForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "selected_ctf",
        ]