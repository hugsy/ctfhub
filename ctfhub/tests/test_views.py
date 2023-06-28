from typing import Union


from django.test import Client, TestCase
from django.urls import reverse

import ctfhub.urls
from ctfhub.models import Team
from ctfhub.tests.utils import (
    MockTeam,
    MockTeamWithMembers,
    get_messages,
)


class TestAuthView(TestCase):
    def test_required_login_no_team(self):
        #
        # All pages require authentication
        #
        client = Client()
        except_list = (
            "ctfhub:home",
            "ctfhub:team-register",
            "ctfhub:users-register",
            "ctfhub:user-login",
            "ctfhub:user-password-reset",
            "ctfhub:user-password-change",
        )

        valid_redirect_targets = (
            reverse("ctfhub:team-register"),
            reverse("ctfhub:user-login"),
        )

        for path in ctfhub.urls.urlpatterns:
            if not path.name:
                continue

            reverse_name = f"ctfhub:{path.name}"
            if reverse_name in except_list:
                continue

            #
            # set fake arguments
            #
            kwargs = {}
            if "<int:pk>" in path.pattern._route:
                kwargs["pk"] = 1
            if "<uuid:pk>" in path.pattern._route:
                kwargs["pk"] = "11111111-1111-1111-1111-111111111111"
            if "<uuid:ctf>" in path.pattern._route:
                kwargs["ctf"] = "11111111-1111-1111-1111-111111111111"
            if "<uuid:challenge_id>" in path.pattern._route:
                kwargs["challenge_id"] = "11111111-1111-1111-1111-111111111111"

            url = reverse(reverse_name, kwargs=kwargs)
            response = client.get(url)

            #
            # Expect redirect to login page
            #
            assert (
                response.status_code == 302
            ), f"Unexpected status code {response.status_code} to {url}"
            hdr = response.get("location") or ""
            assert hdr
            assert any(map(lambda x: hdr.startswith(x), valid_redirect_targets))


class TestTeamView(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        return super().setUp()

    def tearDown(self) -> None:
        return super().tearDown()

    def test_team_register_get(self):
        url = reverse("ctfhub:team-register")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.templates[0].name == "team/create.html"

    def test_team_register_post(self):
        #
        # Create a first team, expect success
        #
        url = reverse("ctfhub:team-register")
        team_info = {
            "name": "TestTeam",
            "email": "test@test.com",
        }

        response = self.client.post(url, data=team_info)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Team.objects.all().count(), 1)
        self.assertEqual(response.url, reverse("ctfhub:dashboard"))

        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        messages = get_messages(response)
        self.assertEqual(len(messages), 1)
        self.assertIn(
            f"Team '{team_info['name']}' successfully created!Use the API key '",
            messages[0],
        )

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
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Team.objects.all().count(), 1)
        self.assertEqual(response.url, reverse("ctfhub:home"))
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
        self.assertEqual(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

        response = self.client.post(url, {"email": "new.email@test.com"})
        self.assertEqual(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

    def test_team_delete(self):
        #
        # Should fail, no admin
        #
        team = MockTeam()
        url = reverse("ctfhub:team-delete")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))

        response = self.client.post(url, {"id": team.pk})
        self.assertEqual(response.status_code, 302)
        assert response.url.startswith(reverse("ctfhub:user-login"))


class TestAdminView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team = MockTeam()

    def test_admin_get(self):
        url = reverse("ctfhub:users-register")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
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
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ctfhub:user-login"))
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        messages = get_messages(response)
        self.assertIn(f"Member '{data['username']}' successfully created", messages)

    def test_admin_post_missing_fields(self):
        url = reverse("ctfhub:users-register")
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 200)
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
        self.assertEqual(response.status_code, 200)
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
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        messages = get_messages(response)
        self.assertEqual(len(messages), 1)
        self.assertIn(f"The API key for team '{self.team.name}' is invalid", messages)


class TestMemberViewAsMember(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()
        member = self.members[1]
        assert not member.has_superpowers
        assert self.client.login(username=member.username, password=member.username)

    def tearDown(self) -> None:
        self.client.logout()
        return super().tearDown()

    def test_member_cannot_access_team_settings_page(self):
        url = reverse(
            "ctfhub:team-edit",
            args=[
                self.team.pk,
            ],
        )

        response = self.client.get(
            url,
        )
        assert response.status_code == 403

        response = self.client.post(url, data={})
        assert response.status_code == 403

        url = reverse("ctfhub:team-delete")

        response = self.client.get(
            url,
        )
        assert response.status_code == 403

        response = self.client.post(url, data={})
        assert response.status_code == 403


class TestCtfView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()


class TestChallengeView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()
