from unittest import TestCase

from django.test import Client

from ctfpad.tests.utils import MockTeamWithMembers


class TestMemberView(TestCase):
    def setUp(self):
        self.client = Client()
        self.team, self.members = MockTeamWithMembers()
