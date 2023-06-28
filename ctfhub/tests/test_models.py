import datetime
from unittest import TestCase

from django.test import Client
import pytest

from ctfhub.tests.utils import MockCtf, MockTeamWithMembers


@pytest.mark.django_db
class TestMemberView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()

    def test_ctf_is_permanent(self):
        #
        # regression test for issue #56
        #

        # no date => permanent
        ctf = MockCtf()
        assert not ctf.start_date and not ctf.end_date
        assert ctf.is_permanent
        assert not ctf.is_time_limited

        # both date => not permanent
        ctf.start_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
        ctf.end_date = datetime.datetime(1971, 1, 1, 0, 0, 0)
        ctf.save()
        assert ctf.start_date and ctf.end_date
        assert not ctf.is_permanent
        assert ctf.is_time_limited

        # either field missing => raise exception
        with pytest.raises(AttributeError):
            ctf.start_date = None
            ctf.end_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
            ctf.save()
            assert not ctf.start_date
            ctf.duration  # trigger

        with pytest.raises(AttributeError):
            ctf.start_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
            ctf.end_date = None
            ctf.save()
            assert not ctf.end_date
            ctf.duration  # trigger
