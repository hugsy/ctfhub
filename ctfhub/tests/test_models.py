import datetime
from unittest import TestCase

from django.test import Client
import pytest
from ctfhub import helpers
from ctfhub.models import Ctf, Member, Team

from ctfhub.tests.utils import MockCtf, MockTeamWithMembers, clean_slate


@pytest.mark.django_db
class TestMemberView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()

    def tearDown(self) -> None:
        clean_slate()
        return super().tearDown()

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

    def test_team_basic(self):
        self.team.ctftime_id = None
        self.team.save()
        assert self.team.ctftime_url == "#"
        assert len(self.team.api_key) == 128

    def test_ctf_basic(self):
        ctf = Ctf.objects.create(name="CtfUser")

        # no dates => permanent
        assert ctf.is_permanent

        # both dates => time limited
        ctf.start_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
        ctf.end_date = datetime.datetime(1971, 1, 1, 0, 0, 0)
        ctf.save()
        assert ctf.is_time_limited

        # one missing => AttributeError
        with pytest.raises(AttributeError):
            ctf.start_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
            ctf.end_date = None
            ctf.save()
            assert ctf.duration
            assert ctf.is_running
            assert ctf.is_finished

            ctf.end_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
            ctf.start_date = None
            ctf.save()
            assert ctf.duration
            assert ctf.is_running
            assert ctf.is_finished

        # finished => time limited + end date is past
        ctf.start_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
        ctf.end_date = datetime.datetime(1971, 1, 1, 0, 0, 0)
        assert ctf.is_finished

        # running => time limited + start date is past + end date is future
        ctf.start_date = datetime.datetime(1970, 1, 1, 0, 0, 0)
        ctf.end_date = datetime.datetime(2971, 1, 1, 0, 0, 0)
        assert ctf.is_running

    def test_member_basic(self):
        member = self.members[1]
        guest = self.members[2]

        ctf1 = Ctf.objects.create(name="Ctf1", visibility=Ctf.VisibilityType.PUBLIC)
        ctf2 = Ctf.objects.create(name="Ctf2", visibility=Ctf.VisibilityType.PUBLIC)
        ctf3 = Ctf.objects.create(
            name="Ctf3", visibility=Ctf.VisibilityType.PRIVATE, created_by=member
        )

        assert not member.has_superpowers
        assert member.status == Member.StatusType.MEMBER

        guest.status = Member.StatusType.GUEST
        guest.selected_ctf = ctf1
        guest.save()
        assert not guest.has_superpowers
        assert guest.is_guest
        assert len(guest.public_ctfs) == 1
        assert guest.public_ctfs[0].pk == ctf1.pk

        member.status = Member.StatusType.MEMBER
        member.selected_ctf = ctf1
        member.save()
        assert not member.has_superpowers
        assert len(member.public_ctfs) == 2
        assert member.public_ctfs[0].pk == ctf1.pk
        assert member.public_ctfs[1].pk == ctf2.pk

        member.selected_ctf = ctf3
        member.save()
        assert len(member.private_ctfs) == 1
        assert member.private_ctfs[0].pk == ctf3.pk

        assert len(member.ctfs) == 3
        assert member.ctfs[0].pk == ctf1.pk
        assert member.ctfs[1].pk == ctf2.pk
        assert member.ctfs[2].pk == ctf3.pk
