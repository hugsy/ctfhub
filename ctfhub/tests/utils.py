from functools import wraps

import django.contrib.auth
import django.contrib.messages.api
import django.utils.crypto
from django.conf import settings
from django.contrib.auth.models import User  # pylint: disable=imported-auth-user

from ctfhub.helpers import HedgeDoc
from ctfhub.models import Ctf, Member, Team


def django_set_temporary_setting(setting_name, temporary_value):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            original_value = getattr(settings, setting_name)
            setattr(settings, setting_name, temporary_value)
            try:
                return func(*args, **kwargs)
            finally:
                setattr(settings, setting_name, original_value)

        return wrapper

    return decorator


def get_messages(response) -> list[str]:
    request = response.context["request"]
    messages = django.contrib.messages.api.get_messages(request)
    messages_as_str = [str(msg) for msg in messages]
    return messages_as_str


class MockTeam:
    def __init__(self):
        self.team = Team.objects.create(
            name="TestTeam",
            email="test@test.com",
            ctftime_id=1234,
        )
        self.admins = []
        self.members = []
        self.__i = 1

    def __del__(self):
        self.team.delete()

    def add_admin(self):
        admin = Member.objects.create(
            user=User.objects.create_superuser(
                username=f"superuser{self.__i}",
                password=f"superuser{self.__i}",
                email=f"superuser{self.__i}@superusers.com",
            ),
            team=self.team,
        )
        assert admin.has_superpowers
        self.__i += 1
        self.admins.append(admin)

    def add_members(self, number: int = 2):
        members = []
        for i in range(self.__i, self.__i + number):
            member = Member.objects.create(
                user=User.objects.create_user(
                    username=f"user{i}",
                    password=f"user{i}",
                    email=f"user{i}@user.com",
                ),
                team=self.team,
            )
            assert not member.has_superpowers
            self.__i += 1
            members.append(member)
        self.members += members

    @staticmethod
    def create_team_with_members() -> "MockTeam":
        mock = MockTeam()
        mock.add_admin()
        mock.add_members(2)
        return mock


class MockCtf:
    def __init__(self):
        self.ctf = Ctf.objects.create(
            name=django.utils.crypto.get_random_string(10),
        )

    def __del__(self):
        self.ctf.delete()


def clean_slate():
    """Clean team, members and hedgedoc account"""
    team = Team.objects.first()
    if team:
        for member in team.members:
            cli = HedgeDoc(member)
            cli.login()
            cli.delete()
            member.delete()

        # dont care if those fail
        for login, password in (
            ("testtesttest", "passpasspass"),
            (
                "testuser",
                "testtesttest",
            ),
        ):
            cli = HedgeDoc((login + "@ctfhub.localdomain", password))
            cli.login()
            cli.delete()
        team.delete()
