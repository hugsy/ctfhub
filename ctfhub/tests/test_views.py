from typing import Union

from django.test import Client, TestCase
from django.urls import reverse

from ctfhub.models import Team
from ctfhub.tests.utils import (
    MockTeam,
    MockTeamWithMembers,
    get_messages,
)


class TestTeamView(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        return super().setUp()

    def tearDown(self) -> None:
        return super().tearDown()

    def test_team_register_get(self):
        url = reverse("ctfhub:team-register")
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "team/create.html")

    def test_team_register_post(self):
        #
        # Create a first team, expect success
        #
        url = reverse("ctfhub:team-register")
        response = self.client.post(
            url,
            {
                "name": "TestTeam",
                "email": "test@test.com",
            },
        )
        self.assertEquals(response.status_code, 302)
        self.assertEquals(Team.objects.all().count(), 1)
        self.assertEquals(response.url, reverse("ctfhub:dashboard"))

        response = self.client.get(response.url)
        self.assertEquals(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("ctfhub:user-login")))

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
        self.assertEquals(response.url, reverse("ctfhub:home"))
        return

    def test_team_edit(self):
        #
        # Should fail, no admin
        #
        team = MockTeam()
        url = reverse(
            "ctfhub:team-edit",
            args=[
                team.pk,
            ],
        )
        response = self.client.get(url)
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

        response = self.client.post(url, {"email": "new.email@test.com"})
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

    def test_team_delete(self):
        #
        # Should fail, no admin
        #
        team = MockTeam()
        url = reverse("ctfhub:team-delete")
        response = self.client.get(url)
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

        response = self.client.post(url, {"id": team.pk})
        self.assertEquals(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))


class TestAdminView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team = MockTeam()

    def test_admin_get(self):
        url = reverse("ctfhub:users-register")
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")

    def test_admin_post(self):
        data: dict[str, Union[str, int]] = {
            "username": "testuser",
            "email": "admin@test.com",
            "password1": "testtesttest",
            "password2": "testtesttest",
            "api_key": self.team.api_key,
        }
        url = reverse("ctfhub:users-register")
        response = self.client.post(url, data)
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response.url, reverse("ctfhub:user-login"))
        response = self.client.get(response.url)
        self.assertEquals(response.status_code, 200)
        messages = get_messages(response)
        self.assertIn(f"Member '{data['username']}' successfully created", messages)

    def test_admin_post_missing_fields(self):
        url = reverse("ctfhub:users-register")
        response = self.client.post(url, {})
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        self.assertEqual(len(response.context["errors"]), 5)

    def test_admin_post_password_mismatch(self):
        data: dict[str, Union[str, int]] = {
            "username": "testuser",
            "email": "admin@test.com",
            "password1": "testtesttest",
            "password2": "TESTTESTTEST",
            "api_key": 1234,
        }
        url = reverse("ctfhub:users-register")
        response = self.client.post(url, data)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        messages = get_messages(response)
        self.assertEqual(len(messages), 1)
        self.assertIn("Password mismatch", messages)

    def test_admin_post_bad_api_key(self):
        url = reverse("ctfhub:users-register")
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
        self.team, self.members = MockTeamWithMembers()


class TestCtfView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()


class TestChallengeView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()
