import datetime
import pytest

from django.test import TestCase
import requests
from ctfhub import helpers
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
            ctfs = helpers.ctftime_fetch_ctfs(5)
            assert len(ctfs) == 5
            for ctf in ctfs:
                assert isinstance(ctf["organizers"], list)
                assert isinstance(ctf["onsite"], bool)
                assert isinstance(ctf["description"], str)
                assert isinstance(ctf["weight"], float)
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
