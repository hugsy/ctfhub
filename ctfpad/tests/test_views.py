import uuid
from typing import Union

import django.contrib.messages.api
from django.test import Client, TestCase
from django.urls import reverse

from ctfpad.models import Member, Team
from ctfpad.views.teams import (
    MESSAGE_ERROR_MULTIPLE_TEAM_CREATE,
    MESSAGE_SUCCESS_TEAM_CREATED,
)


def get_messages(response) -> list[str]:
    request = response.context["request"]
    messages = django.contrib.messages.api.get_messages(request)
    messages_as_str = [str(msg) for msg in messages]
    return messages_as_str


def MockTeam() -> Team:
    team = Team.objects.create(
        name="TestTeam",
        email="test@test.com",
        api_key=str(uuid.uuid4()),
        ctftime_id=1234,
    )
    return team


def MockTeamWithAdmin() -> tuple[Team, Member]:
    team = Team.objects.create(
        name="TestTeam",
        email="test@test.com",
        api_key=str(uuid.uuid4()),
        ctftime_id=1234,
    )
    admin = Member.objects.create()
    return (team, admin)


class TestTeamView(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        return super().setUp()

    def tearDown(self) -> None:
        return super().tearDown()

    def test_team_register_get(self):
        url = reverse("ctfpad:team-register")
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "team/create.html")

    def test_team_register_post(self):
        #
        # Create a first team, expect success
        #
        url = reverse("ctfpad:team-register")
        response = self.client.post(
            url,
            {
                "name": "TestTeam",
                "email": "test@test.com",
            },
        )
        self.assertEquals(response.status_code, 302)
        self.assertEquals(Team.objects.all().count(), 1)
        self.assertEquals(response.url, reverse("ctfpad:dashboard"))

        response = self.client.get(response.url)
        self.assertEquals(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("ctfpad:user-login")))

        response = self.client.get(response.url)
        self.assertEquals(response.status_code, 200)
        messages = get_messages(response)
        self.assertEqual(len(messages), 2)
        self.assertTrue("successfully created!" in messages[0])
        self.assertEqual("You must be authenticated!", messages[1])

        #
        # Create a second team, expect failure
        #
        response = self.client.post(
            url,
            {
                "name": "TestTeam2",
                "email": "test2@test2.com",
            },
        )
        self.assertEquals(response.status_code, 302)
        self.assertEquals(Team.objects.all().count(), 1)
        self.assertEquals(response.url, reverse("ctfpad:home"))
        return

    def test_team_edit(self):
        #
        # Should fail, no admin
        #
        team = MockTeam()
        url = reverse(
            "ctfpad:team-edit",
            args=[
                team.pk,
            ],
        )
        response = self.client.get(url)
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfpad:user-login"))

        response = self.client.post(url, {"email": "new.email@test.com"})
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfpad:user-login"))

    def test_team_delete(self):
        #
        # Should fail, no admin
        #
        team = MockTeam()
        url = reverse("ctfpad:team-delete")
        response = self.client.get(url)
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfpad:user-login"))

        response = self.client.post(url, {"id": team.pk})
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfpad:user-login"))


class TestAdminView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team = MockTeam()

    def test_team_create_user_get(self):
        url = reverse("ctfpad:users-register")
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")

    def test_team_create_user_post(self):
        data: dict[str, Union[str, int]] = {
            "username": "testuser",
            "email": "admin@test.com",
            "password1": "testtesttest",
            "password2": "testtesttest",
            "api_key": self.team.api_key,
        }
        url = reverse("ctfpad:users-register")
        response = self.client.post(url, data)
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response.url, reverse("ctfpad:user-login"))
        response = self.client.get(response.url)
        self.assertEquals(response.status_code, 200)
        messages = get_messages(response)
        self.assertIn(f"Member '{data['username']}' successfully created", messages)

    def test_team_create_user_post_missing_fields(self):
        url = reverse("ctfpad:users-register")
        response = self.client.post(url, {})
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        self.assertEqual(len(response.context["errors"]), 5)

    def test_team_create_user_post_password_mismatch(self):
        data: dict[str, Union[str, int]] = {
            "username": "testuser",
            "email": "admin@test.com",
            "password1": "testtesttest",
            "password2": "TESTTESTTEST",
            "api_key": 1234,
        }
        url = reverse("ctfpad:users-register")
        response = self.client.post(url, data)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        messages = get_messages(response)
        self.assertEqual(len(messages), 1)
        self.assertIn("Password mismatch", messages)

    def test_team_create_user_post_bad_api_key(self):
        url = reverse("ctfpad:users-register")
        data: dict[str, Union[str, int]] = {
            "username": "testuser",
            "email": "admin@test.com",
            "password1": "testtesttest",
            "password2": "testtesttest",
            "api_key": 1234,
        }
        data["api_key"] = 1234
        response = self.client.post(url, data)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        messages = get_messages(response)
        self.assertEqual(len(messages), 1)
        self.assertIn(f"The API key for team '{self.team.name}' is invalid", messages)


class TestMemberView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.admin = MockTeamWithAdmin()


class TestCtfView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.admin = MockTeamWithAdmin()


class TestChallengeView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.admin = MockTeamWithAdmin()
