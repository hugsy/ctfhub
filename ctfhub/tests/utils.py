import uuid

import django.contrib.messages.api

from ctfhub.models import Member, Team


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


def MockTeamWithMembers(nb: int = 10) -> tuple[Team, list[Member]]:
    members = []

    team, admin = MockTeamWithAdmin()
    members.append(admin)
    assert admin.has_superpowers

    for _ in range(nb):
        member = Member.objects.create()
        assert not member.has_superpowers
        members.append(member)

    return (team, members)
