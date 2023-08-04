import datetime
from django.forms import ValidationError
import pytest

from django.test import TestCase
import requests
from ctfhub import helpers
from ctfhub.tests.utils import django_set_temporary_setting
from ctfhub_project import settings


class TestHelpers(TestCase):
    def test_helpers_generators(self):
        assert len(helpers.get_random_string_64()) == 64
        assert len(helpers.get_random_string_128()) == 128

        excalidraw_room_id = helpers.generate_excalidraw_room_id()
        assert len(excalidraw_room_id) == settings.EXCALIDRAW_ROOM_ID_LENGTH
        assert all(
            map(lambda x: x in settings.EXCALIDRAW_ROOM_ID_CHARSET, excalidraw_room_id)
        )

        excalidraw_room_key = helpers.generate_excalidraw_room_key()
        assert len(excalidraw_room_key) == settings.EXCALIDRAW_ROOM_KEY_LENGTH
        assert all(
            map(
                lambda x: x in settings.EXCALIDRAW_ROOM_KEY_CHARSET, excalidraw_room_key
            )
        )

    def test_helpers_ctftime(self):
        try:
            ctfs = helpers.CtfTime.fetch_ctfs(5)
            assert len(ctfs) == 5
            for ctf in ctfs:
                assert isinstance(ctf["organizers"], list)
                assert isinstance(ctf["onsite"], bool)
                assert isinstance(ctf["description"], str)
                assert isinstance(ctf["weight"], int) or isinstance(
                    ctf["weight"], float
                )
                assert isinstance(ctf["title"], str)
                assert isinstance(ctf["url"], str)
                assert isinstance(ctf["is_votable_now"], bool)
                assert isinstance(ctf["restrictions"], str)
                assert isinstance(ctf["format"], str) and ctf["format"].lower() in (
                    "jeopardy",
                    "attack-defense",
                )
                assert isinstance(ctf["participants"], int)
                assert isinstance(ctf["ctftime_url"], str)
                assert isinstance(ctf["location"], str)
                assert isinstance(ctf["live_feed"], str)
                assert isinstance(ctf["public_votable"], bool)
                assert isinstance(ctf["logo"], str)
                assert isinstance(ctf["format_id"], int)
                assert isinstance(ctf["id"], int)
                assert isinstance(ctf["ctf_id"], int)
                assert isinstance(ctf["start"], datetime.datetime)
                assert isinstance(ctf["finish"], datetime.datetime)
                assert isinstance(ctf["duration"], datetime.timedelta)
        except (RuntimeError, requests.exceptions.ReadTimeout):
            # CTFTime is probably down, discard test
            pytest.skip("CTFTime.org is not responding")


class TestUnauthHedgedocHelper(TestCase):
    def setUp(self) -> None:
        self.email: str = "unittestuser1@ctfhub.localdomain"
        self.password: str = "unittestuser1"
        return super().setUp()

    def tearDown(self) -> None:
        return super().tearDown()

    @django_set_temporary_setting("HEDGEDOC_URL", "http://IShouldNotWork.com:3000")
    def test_hedgedoc_url_valid(self):
        cli = helpers.HedgeDoc((self.email, self.password))

        with pytest.raises(ValidationError):
            assert cli.public_url == cli.url  # should raise

    def test_hedgedoc_ping(self):
        assert helpers.HedgeDoc((self.email, self.password)).ping(
            url="https://google.com"
        )

        cli = helpers.HedgeDoc((self.email, self.password))
        assert not cli.ping(url="http://meh:1337")

    def test_hedgedoc_register(self):
        valid_client = helpers.HedgeDoc((self.email, self.password))
        self.assertTrue(valid_client.register())
        self.assertTrue(valid_client.logged_in)
        self.assertTrue(valid_client.delete())

        invalid_client = helpers.HedgeDoc(("bad_user_name!!", "1234"))
        self.assertFalse(invalid_client.register())
        self.assertFalse(invalid_client.logged_in)


class TestAuthHedgedocHelper(TestCase):
    def setUp(self) -> None:
        self.email: str = "unittestuser2@ctfhub.localdomain"
        self.password: str = "unittestuser2"
        self.cli = helpers.HedgeDoc((self.email, self.password))
        assert self.cli.register()
        assert self.cli.logged_in
        return super().setUp()

    def tearDown(self) -> None:
        assert self.cli.delete()
        return super().tearDown()

    def test_hedgedoc_login_logout(self):
        assert self.cli.logout()
        assert not self.cli.logged_in

        for _ in range(10):
            # do a bunch of login/logout to make sure the session cookies are properly rotated
            assert self.cli.login()
            assert self.cli.logged_in
            assert self.cli.logout()
            assert not self.cli.logged_in

        assert self.cli.login()  # must stay because of the destructor

    def test_hedgedoc_info(self):
        data = self.cli.info()
        username = self.email[: self.email.find("@")]
        assert data
        assert data["status"] == "ok"
        assert data["name"] == username
