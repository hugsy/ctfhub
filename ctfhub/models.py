import hashlib
import os
import pathlib
import tempfile
import uuid
import zipfile
from django.conf import settings
import requests

from collections import Counter, namedtuple
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING, Optional, OrderedDict
from urllib.parse import quote

import django.db.models.manager

from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls.base import reverse
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from model_utils import Choices, FieldTracker
from model_utils.fields import MonitorField, StatusField
from ctfhub import helpers
from ctfhub.exceptions import ExternalError

from ctfhub.helpers import (
    ctftime_ctfs,
    ctftime_get_ctf_logo_url,
    generate_excalidraw_room_id,
    generate_excalidraw_room_key,
    get_challenge_upload_path,
    get_file_magic,
    get_file_mime,
    get_named_storage,
    get_random_string_128,
    get_random_string_64,
    which_hedgedoc,
)
from ctfhub.validators import challenge_file_max_size_validator
from ctfhub_project.settings import (
    CTF_CHALLENGE_FILE_ROOT,
    CTFHUB_DEFAULT_COUNTRY_LOGO,
    CTFTIME_URL,
    EXCALIDRAW_ROOM_ID_REGEX,
    EXCALIDRAW_ROOM_KEY_REGEX,
    EXCALIDRAW_URL,
    IMAGE_URL,
    JITSI_URL,
    USERS_FILE_PATH,
)

if TYPE_CHECKING:
    from django.db.models.manager import Manager


class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    ``created`` and ``modified`` fields.
    """

    creation_time = models.DateTimeField(auto_now_add=True)
    last_modification_time = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Team(TimeStampedModel):
    """
    CTF team model
    """

    name = models.CharField(max_length=64)
    email = models.EmailField(max_length=256, unique=True)
    twitter_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    blog_url = models.URLField(blank=True)
    api_key = models.CharField(max_length=128, default=get_random_string_128)
    avatar = models.ImageField(
        null=True,
        upload_to=USERS_FILE_PATH,
        storage=get_named_storage("MEDIA"),
        validators=[
            challenge_file_max_size_validator,
        ],
    )
    ctftime_id = models.IntegerField(default=0, blank=True, null=True)

    #
    # Typing
    #
    member_set: django.db.models.manager.Manager["Member"]

    def __str__(self) -> str:
        return self.name

    @property
    def ctftime_url(self) -> str:
        if not self.ctftime_id:
            return "#"
        return f"{CTFTIME_URL}/team/{self.ctftime_id}"

    @property
    def members(self):
        _members = self.member_set.all()
        members = sorted(
            _members.filter(status=Member.StatusType.MEMBER),
            key=lambda member: member.username,
        )
        members += sorted(
            _members.filter(status=Member.StatusType.GUEST),
            key=lambda member: member.username,
        )
        return members


class Ctf(TimeStampedModel):
    """
    CTF model class
    """

    class VisibilityType(models.TextChoices):
        PUBLIC = "OPEN", _("Public")
        PRIVATE = "PRIV", _("Private")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    created_by = models.ForeignKey(
        "ctfhub.Member", on_delete=models.CASCADE, blank=True, null=True
    )
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    flag_prefix = models.CharField(max_length=64, blank=True)
    team_login = models.CharField(max_length=128, blank=True)
    team_password = models.CharField(max_length=128, blank=True)
    ctftime_id = models.IntegerField(default=0, blank=True, null=True)
    visibility = models.CharField(
        max_length=4, choices=VisibilityType.choices, default=VisibilityType.PUBLIC
    )
    weight = models.FloatField(default=1.0, blank=False, null=False)
    rating = models.FloatField(default=0.0, blank=False, null=False)
    note_id = models.UUIDField(default=uuid.uuid4, editable=True)

    #
    # Typing
    #

    challenge_set: django.db.models.manager.Manager["Challenge"]
    players: django.db.models.manager.Manager["Member"]
    member_points: dict["Member", float]
    member_percents: dict["Member", float]
    ranking: list[tuple["Member", float]]

    def __str__(self) -> str:
        return self.name

    @property
    def is_time_limited(self) -> bool:
        """Indicates whether a CTF is time-limited (24h, 48h, etc.). This requires both
        `start_date` and `end_date` fields to be populated.

        Returns:
            bool: true if both fields are set
        """
        return self.start_date is not None and self.end_date is not None

    @property
    def is_permanent(self) -> bool:
        """Indicates whether a CTF is permanent. This requires both
        `start_date` and `end_date` fields to be None.

        Returns:
            bool: true if both fields are None
        """
        return self.start_date is None and self.end_date is None

    @property
    def is_public(self) -> bool:
        return self.visibility == Ctf.VisibilityType.PUBLIC

    @property
    def is_private(self) -> bool:
        return self.visibility == Ctf.VisibilityType.PRIVATE

    @property
    def challenges(self):
        return self.challenge_set.all()

    @property
    def solved_challenges(self):
        return self.challenge_set.filter(status="solved").order_by("-solved_time")

    @property
    def unsolved_challenges(self):
        return self.challenge_set.filter(status="unsolved")

    @property
    def solved_challenges_as_percent(self):
        cnt = self.challenges.count()
        if cnt == 0:
            return 0
        return int(float(self.solved_challenges.count() / cnt) * 100)

    @property
    def total_points(self):
        return self.challenges.aggregate(Sum("points"))["points__sum"] or 0

    @property
    def scored_points(self):
        return self.solved_challenges.aggregate(Sum("points"))["points__sum"] or 0

    @property
    def scored_points_as_percent(self):
        if self.total_points == 0:
            return 0
        return int(float(self.scored_points / self.total_points) * 100)

    @property
    def duration(self) -> timedelta:
        """Returns the total duration of a CTF. Note that this can only apply to a time-limited CTF, if not this will
        raise an exception

        Raises:
            AttributeError: _description_

        Returns:
            _type_: _description_
        """
        if not self.is_time_limited:
            raise AttributeError(
                f"CTF {str(self)} is not time-limited (i.e. `duration` has no meaning)"
            )
        if not self.end_date or not self.start_date:
            raise AttributeError
        return self.end_date - self.start_date

    @property
    def is_running(self) -> bool:
        """Indicates whether the CTF is currently running. A permanent CTF is always running.

        Raises:
            AttributeError: if the CTF is neither `permanent` or `time_limited`

        Returns:
            bool: true if the CTF is running
        """
        if self.is_permanent:
            return True

        if not self.is_time_limited:
            raise AttributeError

        assert self.end_date and self.start_date
        now = datetime.now()
        return self.start_date <= now < self.end_date

    @property
    def is_finished(self) -> bool:
        """Indicates whether the CTF is finished. A permanent CTF never finishes.

        Raises:
            AttributeError: if the CTF is neither `permanent` or `time_limited`

        Returns:
            bool: _description_
        """
        if self.is_permanent:
            return True
        if not self.is_time_limited:
            raise AttributeError

        assert self.end_date
        now = datetime.now()
        return now >= self.end_date

    @cached_property
    def ctftime_url(self):
        return f"{CTFTIME_URL}/event/{self.ctftime_id}"

    @cached_property
    def ctftime_logo_url(self):
        try:
            return ctftime_get_ctf_logo_url(self.ctftime_id)
        except (RuntimeError, requests.exceptions.ReadTimeout):
            return f"{IMAGE_URL}/blank-ctf.png"

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.id}"

    def team_timeline(self):
        challs = (
            self.challenge_set.prefetch_related("solvers__user")
            .filter(status="solved", solvers__isnull=False)
            .order_by("solved_time")
            .distinct("solved_time", "id")
            .all()
        )

        members = []
        for chall in challs:
            for member in chall.solvers.all():
                if member in members:
                    continue
                member.accu = 0
                member.challs = OrderedDict()
                members.append(member)

        for chall in challs:
            solvers = chall.solvers.all()
            for member in members:
                points = 0
                if member in solvers:
                    points = chall.points / len(solvers)
                member.accu += points
                member.challs[chall] = member.accu

        return members

    def export_notes_as_zipstream(
        self, stream: pathlib.Path, member: "Member", include_files: bool = False
    ) -> str:
        """Export the CTF as a ZIP arhchive

        Returns:
            str: the file name of the archive
        """
        archive = zipfile.ZipFile(stream, "w")
        now = datetime.now()
        ts = (now.year, now.month, now.day, 0, 0, 0)

        cli = helpers.HedgeDoc(member)
        if not cli.login():
            raise RuntimeError(f"Failed to authenticate {member}")

        #
        # Add the CTF notes
        #
        fname = f"{slugify(self.name)}.md"
        with tempfile.TemporaryFile():
            text = cli.export_note(self.note_id)
            archive.writestr(zipfile.ZipInfo(filename=fname, date_time=ts), text)

        #
        # Add the notes of every challenge
        #
        for challenge in self.challenges:
            fname = f"{slugify(self.name)}-{slugify(challenge.name)}.md"
            with tempfile.TemporaryFile():
                data = cli.export_note(challenge.note_id)
                sub_stream = zipfile.ZipInfo(filename=fname, date_time=ts)
                archive.writestr(sub_stream, data)

            if include_files:
                #
                # Add all the challenge files
                #
                fname = f"{slugify(self.name)}-{slugify(challenge.name)}"
                for challenge_file in challenge.challengefile_set:
                    fname += f"-{challenge_file.name}.bin"
                    with tempfile.TemporaryFile():
                        data = challenge_file.file.open("rb").read()
                        sub_stream = zipfile.ZipInfo(filename=fname, date_time=ts)
                        archive.writestr(sub_stream, data)

        suffix = "notes" if not include_files else "full"
        return f"{slugify(self.name)}-{suffix}.zip"

    @property
    def note_url(self) -> str:
        return f"{settings.HEDGEDOC_URL}/{self.note_id}"

    def get_absolute_url(self):
        return reverse(
            "ctfhub:ctfs-detail",
            args=[
                str(self.id),
            ],
        )

    @property
    def team(self) -> "Manager[Member]":
        return self.players.all()


class Member(TimeStampedModel):
    """
    CTF team member model
    """

    class StatusType(models.IntegerChoices):
        MEMBER = 0, _("Member")
        GUEST = 1, _("Guest")
        INACTIVE = 2, _("Inactive")

    class Country(models.TextChoices):
        ANDORRA = "AD", _("Andorra")
        UNITEDARABEMIRATES = "AE", _("United Arab Emirates")
        AFGHANISTAN = "AF", _("Afghanistan")
        ANTIGUABARBUDA = "AG", _("Antigua and Barbuda")
        ANGUILLA = "AI", _("Anguilla")
        ALBANIA = "AL", _("Albania")
        ARMENIA = "AM", _("Armenia")
        ANGOLA = "AO", _("Angola")
        ANTARCTICA = "AQ", _("Antarctica")
        ARGENTINA = "AR", _("Argentina")
        AMERICAN = "AS", _("American Samoa")
        AUSTRIA = "AT", _("Austria")
        AUSTRALIA = "AU", _("Australia")
        ARUBA = "AW", _("Aruba")
        AZERBAIJAN = "AZ", _("Azerbaijan")
        BOSNIAHERZEGOVINA = "BA", _("Bosnia and Herzegovina")
        BARBADOS = "BB", _("Barbados")
        BANGLADESH = "BD", _("Bangladesh")
        BELGIUM = "BE", _("Belgium")
        BURKINAFASO = "BF", _("Burkina Faso")
        BULGARIA = "BG", _("Bulgaria")
        BAHRAIN = "BH", _("Bahrain")
        BURUNDI = "BI", _("Burundi")
        BENIN = "BJ", _("Benin")
        SAINTBARTHELEMY = "BL", _("Saint Barthélemy")
        BERMUDA = "BM", _("Bermuda")
        BRUNEI = "BN", _("Brunei")
        BOLIVIA = "BO", _("Bolivia")
        CARIBBEANNETHERLANDS = "BQ", _("Caribbean Netherlands")
        BRAZIL = "BR", _("Brazil")
        BAHAMAS = "BS", _("Bahamas")
        BHUTAN = "BT", _("Bhutan")
        BOUVETISLAND = "BV", _("Bouvet Island")
        BOTSWANA = "BW", _("Botswana")
        BELARUS = "BY", _("Belarus")
        BELIZE = "BZ", _("Belize")
        CANADA = "CA", _("Canada")
        COCOSISLANDS = "CC", _("Cocos (Keeling) Islands")
        DRCONGO = "CD", _("DR Congo")
        CENTRALAFRICANREPUBLIC = "CF", _("Central African Republic")
        REPUBLICOFTHECONGO = "CG", _("Republic of the Congo")
        SWITZERLAND = "CH", _("Switzerland")
        COTEDIVOIRE = "CI", _("Côte d'Ivoire (Ivory Coast)")
        COOKISLANDS = "CK", _("Cook Islands")
        CHILE = "CL", _("Chile")
        CAMEROON = "CM", _("Cameroon")
        CHINA = "CN", _("China")
        COLOMBIA = "CO", _("Colombia")
        COSTARICA = "CR", _("Costa Rica")
        CUBA = "CU", _("Cuba")
        CAPEVERDE = "CV", _("Cape Verde")
        CURACAO = "CW", _("Curaçao")
        CHRISTMASISLAND = "CX", _("Christmas Island")
        CYPRUS = "CY", _("Cyprus")
        CZECHIA = "CZ", _("Czechia")
        GERMANY = "DE", _("Germany")
        DJIBOUTI = "DJ", _("Djibouti")
        DENMARK = "DK", _("Denmark")
        DOMINICA = "DM", _("Dominica")
        DOMINICANREPUBLIC = "DO", _("Dominican Republic")
        ALGERIA = "DZ", _("Algeria")
        ECUADOR = "EC", _("Ecuador")
        ESTONIA = "EE", _("Estonia")
        EGYPT = "EG", _("Egypt")
        WESTERNSAHARA = "EH", _("Western Sahara")
        ERITREA = "ER", _("Eritrea")
        SPAIN = "ES", _("Spain")
        ETHIOPIA = "ET", _("Ethiopia")
        EUROPEANUNION = "EU", _("European Union")
        FINLAND = "FI", _("Finland")
        FIJI = "FJ", _("Fiji")
        FALKLANDISLANDS = "FK", _("Falkland Islands")
        MICRONESIA = "FM", _("Micronesia")
        FAROEISLANDS = "FO", _("Faroe Islands")
        FRANCE = "FR", _("France")
        GABON = "GA", _("Gabon")
        UNITEDKINGDOM = "GB", _("United Kingdom")
        GRENADA = "GD", _("Grenada")
        GEORGIA = "GE", _("Georgia")
        FRENCHGUIANA = "GF", _("French Guiana")
        GUERNSEY = "GG", _("Guernsey")
        GHANA = "GH", _("Ghana")
        GIBRALTAR = "GI", _("Gibraltar")
        GREENLAND = "GL", _("Greenland")
        GAMBIA = "GM", _("Gambia")
        GUINEA = "GN", _("Guinea")
        GUADELOUPE = "GP", _("Guadeloupe")
        EQUATORIALGUINEA = "GQ", _("Equatorial Guinea")
        GREECE = "GR", _("Greece")
        SOUTHGEORGIA = "GS", _("South Georgia")
        GUATEMALA = "GT", _("Guatemala")
        GUAM = "GU", _("Guam")
        GUINEABISSAU = "GW", _("Guinea-Bissau")
        GUYANA = "GY", _("Guyana")
        HONGKONG = "HK", _("Hong Kong")
        HEARDISLANDANDMCDONALDISLANDS = "HM", _("Heard Island and McDonald Islands")
        HONDURAS = "HN", _("Honduras")
        CROATIA = "HR", _("Croatia")
        HAITI = "HT", _("Haiti")
        HUNGARY = "HU", _("Hungary")
        INDONESIA = "ID", _("Indonesia")
        IRELAND = "IE", _("Ireland")
        ISRAEL = "IL", _("Israel")
        ISLEOFMAN = "IM", _("Isle of Man")
        INDIA = "IN", _("India")
        BRITISHINDIANOCEANTERRITORY = "IO", _("British Indian Ocean Territory")
        IRAQ = "IQ", _("Iraq")
        IRAN = "IR", _("Iran")
        ICELAND = "IS", _("Iceland")
        ITALY = "IT", _("Italy")
        JERSEY = "JE", _("Jersey")
        JAMAICA = "JM", _("Jamaica")
        JORDAN = "JO", _("Jordan")
        JAPAN = "JP", _("Japan")
        KENYA = "KE", _("Kenya")
        KYRGYZSTAN = "KG", _("Kyrgyzstan")
        CAMBODIA = "KH", _("Cambodia")
        KIRIBATI = "KI", _("Kiribati")
        COMOROS = "KM", _("Comoros")
        SAINTKITTSANDNEVIS = "KN", _("Saint Kitts and Nevis")
        NORTHKOREA = "KP", _("North Korea")
        SOUTHKOREA = "KR", _("South Korea")
        KUWAIT = "KW", _("Kuwait")
        CAYMANISLANDS = "KY", _("Cayman Islands")
        KAZAKHSTAN = "KZ", _("Kazakhstan")
        LAOS = "LA", _("Laos")
        LEBANON = "LB", _("Lebanon")
        SAINTLUCIA = "LC", _("Saint Lucia")
        LIECHTENSTEIN = "LI", _("Liechtenstein")
        SRILANKA = "LK", _("Sri Lanka")
        LIBERIA = "LR", _("Liberia")
        LESOTHO = "LS", _("Lesotho")
        LITHUANIA = "LT", _("Lithuania")
        LUXEMBOURG = "LU", _("Luxembourg")
        LATVIA = "LV", _("Latvia")
        LIBYA = "LY", _("Libya")
        MOROCCO = "MA", _("Morocco")
        MONACO = "MC", _("Monaco")
        MOLDOVA = "MD", _("Moldova")
        MONTENEGRO = "ME", _("Montenegro")
        SAINTMARTIN = "MF", _("Saint Martin")
        MADAGASCAR = "MG", _("Madagascar")
        MARSHALLISLANDS = "MH", _("Marshall Islands")
        NORTHMACEDONIA = "MK", _("North Macedonia")
        MALI = "ML", _("Mali")
        MYANMAR = "MM", _("Myanmar")
        MONGOLIA = "MN", _("Mongolia")
        MACAU = "MO", _("Macau")
        NORTHERNMARIANAISLANDS = "MP", _("Northern Mariana Islands")
        MARTINIQUE = "MQ", _("Martinique")
        MAURITANIA = "MR", _("Mauritania")
        MONTSERRAT = "MS", _("Montserrat")
        MALTA = "MT", _("Malta")
        MAURITIUS = "MU", _("Mauritius")
        MALDIVES = "MV", _("Maldives")
        MALAWI = "MW", _("Malawi")
        MEXICO = "MX", _("Mexico")
        MALAYSIA = "MY", _("Malaysia")
        MOZAMBIQUE = "MZ", _("Mozambique")
        NAMIBIA = "NA", _("Namibia")
        NEWCALEDONIA = "NC", _("New Caledonia")
        NIGER = "NE", _("Niger")
        NORFOLKISLAND = "NF", _("Norfolk Island")
        NIGERIA = "NG", _("Nigeria")
        NICARAGUA = "NI", _("Nicaragua")
        NETHERLANDS = "NL", _("Netherlands")
        NORWAY = "NO", _("Norway")
        NEPAL = "NP", _("Nepal")
        NAURU = "NR", _("Nauru")
        NIUE = "NU", _("Niue")
        NEWZEALAND = "NZ", _("New Zealand")
        OMAN = "OM", _("Oman")
        PANAMA = "PA", _("Panama")
        PERU = "PE", _("Peru")
        FRENCHPOLYNESIA = "PF", _("French Polynesia")
        PAPUANEWGUINEA = "PG", _("Papua New Guinea")
        PHILIPPINES = "PH", _("Philippines")
        PAKISTAN = "PK", _("Pakistan")
        POLAND = "PL", _("Poland")
        SAINTPIERREANDMIQUELON = "PM", _("Saint Pierre and Miquelon")
        PITCAIRNISLANDS = "PN", _("Pitcairn Islands")
        PUERTORICO = "PR", _("Puerto Rico")
        PALESTINE = "PS", _("Palestine")
        PORTUGAL = "PT", _("Portugal")
        PALAU = "PW", _("Palau")
        PARAGUAY = "PY", _("Paraguay")
        QATAR = "QA", _("Qatar")
        RÉUNION = "RE", _("Réunion")
        ROMANIA = "RO", _("Romania")
        SERBIA = "RS", _("Serbia")
        RUSSIA = "RU", _("Russia")
        RWANDA = "RW", _("Rwanda")
        SAUDIARABIA = "SA", _("Saudi Arabia")
        SOLOMONISLANDS = "SB", _("Solomon Islands")
        SEYCHELLES = "SC", _("Seychelles")
        SUDAN = "SD", _("Sudan")
        SWEDEN = "SE", _("Sweden")
        SINGAPORE = "SG", _("Singapore")
        SAINTHELENAASCENSIONANDTRISTANDACUNHA = "SH", _(
            "Saint Helena, Ascension and Tristan da Cunha"
        )
        SLOVENIA = "SI", _("Slovenia")
        SVALBARDANDJANMAYEN = "SJ", _("Svalbard and Jan Mayen")
        SLOVAKIA = "SK", _("Slovakia")
        SIERRALEONE = "SL", _("Sierra Leone")
        SANMARINO = "SM", _("San Marino")
        SENEGAL = "SN", _("Senegal")
        SOMALIA = "SO", _("Somalia")
        SURINAME = "SR", _("Suriname")
        SOUTHSUDAN = "SS", _("South Sudan")
        SAOTOMEANDPRINCIPE = "ST", _("São Tomé and Príncipe")
        ELSALVADOR = "SV", _("El Salvador")
        SINTMAARTEN = "SX", _("Sint Maarten")
        SYRIA = "SY", _("Syria")
        ESWATINI = "SZ", _("Eswatini (Swaziland)")
        TURKSANDCAICOSISLANDS = "TC", _("Turks and Caicos Islands")
        CHAD = "TD", _("Chad")
        FRENCHSOUTHERNANDANTARCTICLANDS = "TF", _("French Southern and Antarctic Lands")
        TOGO = "TG", _("Togo")
        THAILAND = "TH", _("Thailand")
        TAJIKISTAN = "TJ", _("Tajikistan")
        TOKELAU = "TK", _("Tokelau")
        TIMORLESTE = "TL", _("Timor-Leste")
        TURKMENISTAN = "TM", _("Turkmenistan")
        TUNISIA = "TN", _("Tunisia")
        TONGA = "TO", _("Tonga")
        TURKEY = "TR", _("Turkey")
        TRINIDADANDTOBAGO = "TT", _("Trinidad and Tobago")
        TUVALU = "TV", _("Tuvalu")
        TAIWAN = "TW", _("Taiwan")
        TANZANIA = "TZ", _("Tanzania")
        UKRAINE = "UA", _("Ukraine")
        UGANDA = "UG", _("Uganda")
        UNITEDSTATESMINOROUTLYINGISLANDS = "UM", _(
            "United States Minor Outlying Islands"
        )
        UNITEDNATIONS = "UN", _("United Nations")
        UNITEDSTATES = "US", _("United States")
        URUGUAY = "UY", _("Uruguay")
        UZBEKISTAN = "UZ", _("Uzbekistan")
        VATICANCITY = "VA", _("Vatican City")
        SAINTVINCENTANDTHEGRENADINES = "VC", _("Saint Vincent and the Grenadines")
        VENEZUELA = "VE", _("Venezuela")
        BRITISHVIRGINISLANDS = "VG", _("British Virgin Islands")
        UNITEDSTATESVIRGINISLANDS = "VI", _("United States Virgin Islands")
        VIETNAM = "VN", _("Vietnam")
        VANUATU = "VU", _("Vanuatu")
        WALLISANDFUTUNA = "WF", _("Wallis and Futuna")
        SAMOA = "WS", _("Samoa")
        KOSOVO = "XK", _("Kosovo")
        YEMEN = "YE", _("Yemen")
        MAYOTTE = "YT", _("Mayotte")
        SOUTHAFRICA = "ZA", _("South Africa")
        ZAMBIA = "ZM", _("Zambia")
        ZIMBABWE = "ZW", _("Zimbabwe")

    Timezones: list[tuple[str, str]] = [
        (
            "America/North_Dakota/New_Salem",
            "America/North Dakota/New Salem",
        ),
        (
            "America/Argentina/Buenos_Aires",
            "America/Argentina/Buenos Aires",
        ),
        (
            "America/Argentina/ComodRivadavia",
            "America/Argentina/Comodrivadavia",
        ),
        (
            "America/Argentina/Rio_Gallegos",
            "America/Argentina/Rio Gallegos",
        ),
        ("Africa/Abidjan", "Africa/Abidjan"),
        ("Africa/Accra", "Africa/Accra"),
        ("Africa/Addis_Ababa", "Africa/Addis Ababa"),
        ("Africa/Algiers", "Africa/Algiers"),
        ("Africa/Asmara", "Africa/Asmara"),
        ("Africa/Asmera", "Africa/Asmera"),
        ("Africa/Bamako", "Africa/Bamako"),
        ("Africa/Bangui", "Africa/Bangui"),
        ("Africa/Banjul", "Africa/Banjul"),
        ("Africa/Bissau", "Africa/Bissau"),
        ("Africa/Blantyre", "Africa/Blantyre"),
        ("Africa/Brazzaville", "Africa/Brazzaville"),
        ("Africa/Bujumbura", "Africa/Bujumbura"),
        ("Africa/Cairo", "Africa/Cairo"),
        ("Africa/Casablanca", "Africa/Casablanca"),
        ("Africa/Ceuta", "Africa/Ceuta"),
        ("Africa/Conakry", "Africa/Conakry"),
        ("Africa/Dakar", "Africa/Dakar"),
        ("Africa/Dar_es_Salaam", "Africa/Dar Es Salaam"),
        ("Africa/Djibouti", "Africa/Djibouti"),
        ("Africa/Douala", "Africa/Douala"),
        ("Africa/El_Aaiun", "Africa/El Aaiun"),
        ("Africa/Freetown", "Africa/Freetown"),
        ("Africa/Gaborone", "Africa/Gaborone"),
        ("Africa/Harare", "Africa/Harare"),
        ("Africa/Johannesburg", "Africa/Johannesburg"),
        ("Africa/Juba", "Africa/Juba"),
        ("Africa/Kampala", "Africa/Kampala"),
        ("Africa/Khartoum", "Africa/Khartoum"),
        ("Africa/Kigali", "Africa/Kigali"),
        ("Africa/Kinshasa", "Africa/Kinshasa"),
        ("Africa/Lagos", "Africa/Lagos"),
        ("Africa/Libreville", "Africa/Libreville"),
        ("Africa/Lome", "Africa/Lome"),
        ("Africa/Luanda", "Africa/Luanda"),
        ("Africa/Lubumbashi", "Africa/Lubumbashi"),
        ("Africa/Lusaka", "Africa/Lusaka"),
        ("Africa/Malabo", "Africa/Malabo"),
        ("Africa/Maputo", "Africa/Maputo"),
        ("Africa/Maseru", "Africa/Maseru"),
        ("Africa/Mbabane", "Africa/Mbabane"),
        ("Africa/Mogadishu", "Africa/Mogadishu"),
        ("Africa/Monrovia", "Africa/Monrovia"),
        ("Africa/Nairobi", "Africa/Nairobi"),
        ("Africa/Ndjamena", "Africa/Ndjamena"),
        ("Africa/Niamey", "Africa/Niamey"),
        ("Africa/Nouakchott", "Africa/Nouakchott"),
        ("Africa/Ouagadougou", "Africa/Ouagadougou"),
        ("Africa/Porto-Novo", "Africa/Porto-Novo"),
        ("Africa/Sao_Tome", "Africa/Sao Tome"),
        ("Africa/Timbuktu", "Africa/Timbuktu"),
        ("Africa/Tripoli", "Africa/Tripoli"),
        ("Africa/Tunis", "Africa/Tunis"),
        ("Africa/Windhoek", "Africa/Windhoek"),
        ("America/Adak", "America/Adak"),
        ("America/Anchorage", "America/Anchorage"),
        ("America/Anguilla", "America/Anguilla"),
        ("America/Antigua", "America/Antigua"),
        ("America/Araguaina", "America/Araguaina"),
        ("America/Argentina/Catamarca", "America/Argentina/Catamarca"),
        ("America/Argentina/Cordoba", "America/Argentina/Cordoba"),
        ("America/Argentina/Jujuy", "America/Argentina/Jujuy"),
        ("America/Argentina/La_Rioja", "America/Argentina/La Rioja"),
        ("America/Argentina/Mendoza", "America/Argentina/Mendoza"),
        ("America/Argentina/Salta", "America/Argentina/Salta"),
        ("America/Argentina/San_Juan", "America/Argentina/San Juan"),
        ("America/Argentina/San_Luis", "America/Argentina/San Luis"),
        ("America/Argentina/Tucuman", "America/Argentina/Tucuman"),
        ("America/Argentina/Ushuaia", "America/Argentina/Ushuaia"),
        ("America/Aruba", "America/Aruba"),
        ("America/Asuncion", "America/Asuncion"),
        ("America/Atikokan", "America/Atikokan"),
        ("America/Atka", "America/Atka"),
        ("America/Bahia_Banderas", "America/Bahia Banderas"),
        ("America/Bahia", "America/Bahia"),
        ("America/Barbados", "America/Barbados"),
        ("America/Belem", "America/Belem"),
        ("America/Belize", "America/Belize"),
        ("America/Blanc-Sablon", "America/Blanc-Sablon"),
        ("America/Boa_Vista", "America/Boa Vista"),
        ("America/Bogota", "America/Bogota"),
        ("America/Boise", "America/Boise"),
        ("America/Buenos_Aires", "America/Buenos Aires"),
        ("America/Cambridge_Bay", "America/Cambridge Bay"),
        ("America/Campo_Grande", "America/Campo Grande"),
        ("America/Cancun", "America/Cancun"),
        ("America/Caracas", "America/Caracas"),
        ("America/Catamarca", "America/Catamarca"),
        ("America/Cayenne", "America/Cayenne"),
        ("America/Cayman", "America/Cayman"),
        ("America/Chicago", "America/Chicago"),
        ("America/Chihuahua", "America/Chihuahua"),
        ("America/Ciudad_Juarez", "America/Ciudad Juarez"),
        ("America/Coral_Harbour", "America/Coral Harbour"),
        ("America/Cordoba", "America/Cordoba"),
        ("America/Costa_Rica", "America/Costa Rica"),
        ("America/Creston", "America/Creston"),
        ("America/Cuiaba", "America/Cuiaba"),
        ("America/Curacao", "America/Curacao"),
        ("America/Danmarkshavn", "America/Danmarkshavn"),
        ("America/Dawson_Creek", "America/Dawson Creek"),
        ("America/Dawson", "America/Dawson"),
        ("America/Denver", "America/Denver"),
        ("America/Detroit", "America/Detroit"),
        ("America/Dominica", "America/Dominica"),
        ("America/Edmonton", "America/Edmonton"),
        ("America/Eirunepe", "America/Eirunepe"),
        ("America/El_Salvador", "America/El Salvador"),
        ("America/Ensenada", "America/Ensenada"),
        ("America/Fort_Nelson", "America/Fort Nelson"),
        ("America/Fort_Wayne", "America/Fort Wayne"),
        ("America/Fortaleza", "America/Fortaleza"),
        ("America/Glace_Bay", "America/Glace Bay"),
        ("America/Godthab", "America/Godthab"),
        ("America/Goose_Bay", "America/Goose Bay"),
        ("America/Grand_Turk", "America/Grand Turk"),
        ("America/Grenada", "America/Grenada"),
        ("America/Guadeloupe", "America/Guadeloupe"),
        ("America/Guatemala", "America/Guatemala"),
        ("America/Guayaquil", "America/Guayaquil"),
        ("America/Guyana", "America/Guyana"),
        ("America/Halifax", "America/Halifax"),
        ("America/Havana", "America/Havana"),
        ("America/Hermosillo", "America/Hermosillo"),
        ("America/Indiana/Indianapolis", "America/Indiana/Indianapolis"),
        ("America/Indiana/Knox", "America/Indiana/Knox"),
        ("America/Indiana/Marengo", "America/Indiana/Marengo"),
        ("America/Indiana/Petersburg", "America/Indiana/Petersburg"),
        ("America/Indiana/Tell_City", "America/Indiana/Tell City"),
        ("America/Indiana/Vevay", "America/Indiana/Vevay"),
        ("America/Indiana/Vincennes", "America/Indiana/Vincennes"),
        ("America/Indiana/Winamac", "America/Indiana/Winamac"),
        ("America/Indianapolis", "America/Indianapolis"),
        ("America/Inuvik", "America/Inuvik"),
        ("America/Iqaluit", "America/Iqaluit"),
        ("America/Jamaica", "America/Jamaica"),
        ("America/Jujuy", "America/Jujuy"),
        ("America/Juneau", "America/Juneau"),
        ("America/Kentucky/Louisville", "America/Kentucky/Louisville"),
        ("America/Kentucky/Monticello", "America/Kentucky/Monticello"),
        ("America/Knox_IN", "America/Knox In"),
        ("America/Kralendijk", "America/Kralendijk"),
        ("America/La_Paz", "America/La Paz"),
        ("America/Lima", "America/Lima"),
        ("America/Los_Angeles", "America/Los Angeles"),
        ("America/Louisville", "America/Louisville"),
        ("America/Lower_Princes", "America/Lower Princes"),
        ("America/Maceio", "America/Maceio"),
        ("America/Managua", "America/Managua"),
        ("America/Manaus", "America/Manaus"),
        ("America/Marigot", "America/Marigot"),
        ("America/Martinique", "America/Martinique"),
        ("America/Matamoros", "America/Matamoros"),
        ("America/Mazatlan", "America/Mazatlan"),
        ("America/Mendoza", "America/Mendoza"),
        ("America/Menominee", "America/Menominee"),
        ("America/Merida", "America/Merida"),
        ("America/Metlakatla", "America/Metlakatla"),
        ("America/Mexico_City", "America/Mexico City"),
        ("America/Miquelon", "America/Miquelon"),
        ("America/Moncton", "America/Moncton"),
        ("America/Monterrey", "America/Monterrey"),
        ("America/Montevideo", "America/Montevideo"),
        ("America/Montreal", "America/Montreal"),
        ("America/Montserrat", "America/Montserrat"),
        ("America/Nassau", "America/Nassau"),
        ("America/New_York", "America/New York"),
        ("America/Nipigon", "America/Nipigon"),
        ("America/Nome", "America/Nome"),
        ("America/Noronha", "America/Noronha"),
        ("America/North_Dakota/Beulah", "America/North Dakota/Beulah"),
        ("America/North_Dakota/Center", "America/North Dakota/Center"),
        ("America/Nuuk", "America/Nuuk"),
        ("America/Ojinaga", "America/Ojinaga"),
        ("America/Panama", "America/Panama"),
        ("America/Pangnirtung", "America/Pangnirtung"),
        ("America/Paramaribo", "America/Paramaribo"),
        ("America/Phoenix", "America/Phoenix"),
        ("America/Port_of_Spain", "America/Port Of Spain"),
        ("America/Port-au-Prince", "America/Port-Au-Prince"),
        ("America/Porto_Acre", "America/Porto Acre"),
        ("America/Porto_Velho", "America/Porto Velho"),
        ("America/Puerto_Rico", "America/Puerto Rico"),
        ("America/Punta_Arenas", "America/Punta Arenas"),
        ("America/Rainy_River", "America/Rainy River"),
        ("America/Rankin_Inlet", "America/Rankin Inlet"),
        ("America/Recife", "America/Recife"),
        ("America/Regina", "America/Regina"),
        ("America/Resolute", "America/Resolute"),
        ("America/Rio_Branco", "America/Rio Branco"),
        ("America/Rosario", "America/Rosario"),
        ("America/Santa_Isabel", "America/Santa Isabel"),
        ("America/Santarem", "America/Santarem"),
        ("America/Santiago", "America/Santiago"),
        ("America/Santo_Domingo", "America/Santo Domingo"),
        ("America/Sao_Paulo", "America/Sao Paulo"),
        ("America/Scoresbysund", "America/Scoresbysund"),
        ("America/Shiprock", "America/Shiprock"),
        ("America/Sitka", "America/Sitka"),
        ("America/St_Barthelemy", "America/St Barthelemy"),
        ("America/St_Johns", "America/St Johns"),
        ("America/St_Kitts", "America/St Kitts"),
        ("America/St_Lucia", "America/St Lucia"),
        ("America/St_Thomas", "America/St Thomas"),
        ("America/St_Vincent", "America/St Vincent"),
        ("America/Swift_Current", "America/Swift Current"),
        ("America/Tegucigalpa", "America/Tegucigalpa"),
        ("America/Thule", "America/Thule"),
        ("America/Thunder_Bay", "America/Thunder Bay"),
        ("America/Tijuana", "America/Tijuana"),
        ("America/Toronto", "America/Toronto"),
        ("America/Tortola", "America/Tortola"),
        ("America/Vancouver", "America/Vancouver"),
        ("America/Virgin", "America/Virgin"),
        ("America/Whitehorse", "America/Whitehorse"),
        ("America/Winnipeg", "America/Winnipeg"),
        ("America/Yakutat", "America/Yakutat"),
        ("America/Yellowknife", "America/Yellowknife"),
        ("Antarctica/Casey", "Antarctica/Casey"),
        ("Antarctica/Davis", "Antarctica/Davis"),
        ("Antarctica/DumontDUrville", "Antarctica/Dumontdurville"),
        ("Antarctica/Macquarie", "Antarctica/Macquarie"),
        ("Antarctica/Mawson", "Antarctica/Mawson"),
        ("Antarctica/McMurdo", "Antarctica/Mcmurdo"),
        ("Antarctica/Palmer", "Antarctica/Palmer"),
        ("Antarctica/Rothera", "Antarctica/Rothera"),
        ("Antarctica/South_Pole", "Antarctica/South Pole"),
        ("Antarctica/Syowa", "Antarctica/Syowa"),
        ("Antarctica/Troll", "Antarctica/Troll"),
        ("Antarctica/Vostok", "Antarctica/Vostok"),
        ("Arctic/Longyearbyen", "Arctic/Longyearbyen"),
        ("Asia/Aden", "Asia/Aden"),
        ("Asia/Almaty", "Asia/Almaty"),
        ("Asia/Amman", "Asia/Amman"),
        ("Asia/Anadyr", "Asia/Anadyr"),
        ("Asia/Aqtau", "Asia/Aqtau"),
        ("Asia/Aqtobe", "Asia/Aqtobe"),
        ("Asia/Ashgabat", "Asia/Ashgabat"),
        ("Asia/Ashkhabad", "Asia/Ashkhabad"),
        ("Asia/Atyrau", "Asia/Atyrau"),
        ("Asia/Baghdad", "Asia/Baghdad"),
        ("Asia/Bahrain", "Asia/Bahrain"),
        ("Asia/Baku", "Asia/Baku"),
        ("Asia/Bangkok", "Asia/Bangkok"),
        ("Asia/Barnaul", "Asia/Barnaul"),
        ("Asia/Beirut", "Asia/Beirut"),
        ("Asia/Bishkek", "Asia/Bishkek"),
        ("Asia/Brunei", "Asia/Brunei"),
        ("Asia/Calcutta", "Asia/Calcutta"),
        ("Asia/Chita", "Asia/Chita"),
        ("Asia/Choibalsan", "Asia/Choibalsan"),
        ("Asia/Chongqing", "Asia/Chongqing"),
        ("Asia/Chungking", "Asia/Chungking"),
        ("Asia/Colombo", "Asia/Colombo"),
        ("Asia/Dacca", "Asia/Dacca"),
        ("Asia/Damascus", "Asia/Damascus"),
        ("Asia/Dhaka", "Asia/Dhaka"),
        ("Asia/Dili", "Asia/Dili"),
        ("Asia/Dubai", "Asia/Dubai"),
        ("Asia/Dushanbe", "Asia/Dushanbe"),
        ("Asia/Famagusta", "Asia/Famagusta"),
        ("Asia/Gaza", "Asia/Gaza"),
        ("Asia/Harbin", "Asia/Harbin"),
        ("Asia/Hebron", "Asia/Hebron"),
        ("Asia/Ho_Chi_Minh", "Asia/Ho Chi Minh"),
        ("Asia/Hong_Kong", "Asia/Hong Kong"),
        ("Asia/Hovd", "Asia/Hovd"),
        ("Asia/Irkutsk", "Asia/Irkutsk"),
        ("Asia/Istanbul", "Asia/Istanbul"),
        ("Asia/Jakarta", "Asia/Jakarta"),
        ("Asia/Jayapura", "Asia/Jayapura"),
        ("Asia/Jerusalem", "Asia/Jerusalem"),
        ("Asia/Kabul", "Asia/Kabul"),
        ("Asia/Kamchatka", "Asia/Kamchatka"),
        ("Asia/Karachi", "Asia/Karachi"),
        ("Asia/Kashgar", "Asia/Kashgar"),
        ("Asia/Kathmandu", "Asia/Kathmandu"),
        ("Asia/Katmandu", "Asia/Katmandu"),
        ("Asia/Khandyga", "Asia/Khandyga"),
        ("Asia/Kolkata", "Asia/Kolkata"),
        ("Asia/Krasnoyarsk", "Asia/Krasnoyarsk"),
        ("Asia/Kuala_Lumpur", "Asia/Kuala Lumpur"),
        ("Asia/Kuching", "Asia/Kuching"),
        ("Asia/Kuwait", "Asia/Kuwait"),
        ("Asia/Macao", "Asia/Macao"),
        ("Asia/Macau", "Asia/Macau"),
        ("Asia/Magadan", "Asia/Magadan"),
        ("Asia/Makassar", "Asia/Makassar"),
        ("Asia/Manila", "Asia/Manila"),
        ("Asia/Muscat", "Asia/Muscat"),
        ("Asia/Nicosia", "Asia/Nicosia"),
        ("Asia/Novokuznetsk", "Asia/Novokuznetsk"),
        ("Asia/Novosibirsk", "Asia/Novosibirsk"),
        ("Asia/Omsk", "Asia/Omsk"),
        ("Asia/Oral", "Asia/Oral"),
        ("Asia/Phnom_Penh", "Asia/Phnom Penh"),
        ("Asia/Pontianak", "Asia/Pontianak"),
        ("Asia/Pyongyang", "Asia/Pyongyang"),
        ("Asia/Qatar", "Asia/Qatar"),
        ("Asia/Qostanay", "Asia/Qostanay"),
        ("Asia/Qyzylorda", "Asia/Qyzylorda"),
        ("Asia/Rangoon", "Asia/Rangoon"),
        ("Asia/Riyadh", "Asia/Riyadh"),
        ("Asia/Saigon", "Asia/Saigon"),
        ("Asia/Sakhalin", "Asia/Sakhalin"),
        ("Asia/Samarkand", "Asia/Samarkand"),
        ("Asia/Seoul", "Asia/Seoul"),
        ("Asia/Shanghai", "Asia/Shanghai"),
        ("Asia/Singapore", "Asia/Singapore"),
        ("Asia/Srednekolymsk", "Asia/Srednekolymsk"),
        ("Asia/Taipei", "Asia/Taipei"),
        ("Asia/Tashkent", "Asia/Tashkent"),
        ("Asia/Tbilisi", "Asia/Tbilisi"),
        ("Asia/Tehran", "Asia/Tehran"),
        ("Asia/Tel_Aviv", "Asia/Tel Aviv"),
        ("Asia/Thimbu", "Asia/Thimbu"),
        ("Asia/Thimphu", "Asia/Thimphu"),
        ("Asia/Tokyo", "Asia/Tokyo"),
        ("Asia/Tomsk", "Asia/Tomsk"),
        ("Asia/Ujung_Pandang", "Asia/Ujung Pandang"),
        ("Asia/Ulaanbaatar", "Asia/Ulaanbaatar"),
        ("Asia/Ulan_Bator", "Asia/Ulan Bator"),
        ("Asia/Urumqi", "Asia/Urumqi"),
        ("Asia/Ust-Nera", "Asia/Ust-Nera"),
        ("Asia/Vientiane", "Asia/Vientiane"),
        ("Asia/Vladivostok", "Asia/Vladivostok"),
        ("Asia/Yakutsk", "Asia/Yakutsk"),
        ("Asia/Yangon", "Asia/Yangon"),
        ("Asia/Yekaterinburg", "Asia/Yekaterinburg"),
        ("Asia/Yerevan", "Asia/Yerevan"),
        ("Atlantic/Azores", "Atlantic/Azores"),
        ("Atlantic/Bermuda", "Atlantic/Bermuda"),
        ("Atlantic/Canary", "Atlantic/Canary"),
        ("Atlantic/Cape_Verde", "Atlantic/Cape Verde"),
        ("Atlantic/Faeroe", "Atlantic/Faeroe"),
        ("Atlantic/Faroe", "Atlantic/Faroe"),
        ("Atlantic/Jan_Mayen", "Atlantic/Jan Mayen"),
        ("Atlantic/Madeira", "Atlantic/Madeira"),
        ("Atlantic/Reykjavik", "Atlantic/Reykjavik"),
        ("Atlantic/South_Georgia", "Atlantic/South Georgia"),
        ("Atlantic/St_Helena", "Atlantic/St Helena"),
        ("Atlantic/Stanley", "Atlantic/Stanley"),
        ("Australia/ACT", "Australia/Act"),
        ("Australia/Adelaide", "Australia/Adelaide"),
        ("Australia/Brisbane", "Australia/Brisbane"),
        ("Australia/Broken_Hill", "Australia/Broken Hill"),
        ("Australia/Canberra", "Australia/Canberra"),
        ("Australia/Currie", "Australia/Currie"),
        ("Australia/Darwin", "Australia/Darwin"),
        ("Australia/Eucla", "Australia/Eucla"),
        ("Australia/Hobart", "Australia/Hobart"),
        ("Australia/LHI", "Australia/Lhi"),
        ("Australia/Lindeman", "Australia/Lindeman"),
        ("Australia/Lord_Howe", "Australia/Lord Howe"),
        ("Australia/Melbourne", "Australia/Melbourne"),
        ("Australia/North", "Australia/North"),
        ("Australia/NSW", "Australia/Nsw"),
        ("Australia/Perth", "Australia/Perth"),
        ("Australia/Queensland", "Australia/Queensland"),
        ("Australia/South", "Australia/South"),
        ("Australia/Sydney", "Australia/Sydney"),
        ("Australia/Tasmania", "Australia/Tasmania"),
        ("Australia/Victoria", "Australia/Victoria"),
        ("Australia/West", "Australia/West"),
        ("Australia/Yancowinna", "Australia/Yancowinna"),
        ("Brazil/Acre", "Brazil/Acre"),
        ("Brazil/DeNoronha", "Brazil/Denoronha"),
        ("Brazil/East", "Brazil/East"),
        ("Brazil/West", "Brazil/West"),
        ("Canada/Atlantic", "Canada/Atlantic"),
        ("Canada/Central", "Canada/Central"),
        ("Canada/Eastern", "Canada/Eastern"),
        ("Canada/Mountain", "Canada/Mountain"),
        ("Canada/Newfoundland", "Canada/Newfoundland"),
        ("Canada/Pacific", "Canada/Pacific"),
        ("Canada/Saskatchewan", "Canada/Saskatchewan"),
        ("Canada/Yukon", "Canada/Yukon"),
        ("CET", "Cet"),
        ("Chile/Continental", "Chile/Continental"),
        ("Chile/EasterIsland", "Chile/Easterisland"),
        ("CST6CDT", "Cst6Cdt"),
        ("Cuba", "Cuba"),
        ("EET", "Eet"),
        ("Egypt", "Egypt"),
        ("Eire", "Eire"),
        ("EST", "Est"),
        ("EST5EDT", "Est5Edt"),
        ("Etc/GMT-0", "Etc/Gmt-0"),
        ("Etc/GMT-1", "Etc/Gmt-1"),
        ("Etc/GMT-10", "Etc/Gmt-10"),
        ("Etc/GMT-11", "Etc/Gmt-11"),
        ("Etc/GMT-12", "Etc/Gmt-12"),
        ("Etc/GMT-13", "Etc/Gmt-13"),
        ("Etc/GMT-14", "Etc/Gmt-14"),
        ("Etc/GMT-2", "Etc/Gmt-2"),
        ("Etc/GMT-3", "Etc/Gmt-3"),
        ("Etc/GMT-4", "Etc/Gmt-4"),
        ("Etc/GMT-5", "Etc/Gmt-5"),
        ("Etc/GMT-6", "Etc/Gmt-6"),
        ("Etc/GMT-7", "Etc/Gmt-7"),
        ("Etc/GMT-8", "Etc/Gmt-8"),
        ("Etc/GMT-9", "Etc/Gmt-9"),
        ("Etc/GMT", "Etc/Gmt"),
        ("Etc/GMT+0", "Etc/Gmt+0"),
        ("Etc/GMT+1", "Etc/Gmt+1"),
        ("Etc/GMT+10", "Etc/Gmt+10"),
        ("Etc/GMT+11", "Etc/Gmt+11"),
        ("Etc/GMT+12", "Etc/Gmt+12"),
        ("Etc/GMT+2", "Etc/Gmt+2"),
        ("Etc/GMT+3", "Etc/Gmt+3"),
        ("Etc/GMT+4", "Etc/Gmt+4"),
        ("Etc/GMT+5", "Etc/Gmt+5"),
        ("Etc/GMT+6", "Etc/Gmt+6"),
        ("Etc/GMT+7", "Etc/Gmt+7"),
        ("Etc/GMT+8", "Etc/Gmt+8"),
        ("Etc/GMT+9", "Etc/Gmt+9"),
        ("Etc/GMT0", "Etc/Gmt0"),
        ("Etc/Greenwich", "Etc/Greenwich"),
        ("Etc/UCT", "Etc/Uct"),
        ("Etc/Universal", "Etc/Universal"),
        ("Etc/UTC", "Etc/Utc"),
        ("Etc/Zulu", "Etc/Zulu"),
        ("Europe/Amsterdam", "Europe/Amsterdam"),
        ("Europe/Andorra", "Europe/Andorra"),
        ("Europe/Astrakhan", "Europe/Astrakhan"),
        ("Europe/Athens", "Europe/Athens"),
        ("Europe/Belfast", "Europe/Belfast"),
        ("Europe/Belgrade", "Europe/Belgrade"),
        ("Europe/Berlin", "Europe/Berlin"),
        ("Europe/Bratislava", "Europe/Bratislava"),
        ("Europe/Brussels", "Europe/Brussels"),
        ("Europe/Bucharest", "Europe/Bucharest"),
        ("Europe/Budapest", "Europe/Budapest"),
        ("Europe/Busingen", "Europe/Busingen"),
        ("Europe/Chisinau", "Europe/Chisinau"),
        ("Europe/Copenhagen", "Europe/Copenhagen"),
        ("Europe/Dublin", "Europe/Dublin"),
        ("Europe/Gibraltar", "Europe/Gibraltar"),
        ("Europe/Guernsey", "Europe/Guernsey"),
        ("Europe/Helsinki", "Europe/Helsinki"),
        ("Europe/Isle_of_Man", "Europe/Isle Of Man"),
        ("Europe/Istanbul", "Europe/Istanbul"),
        ("Europe/Jersey", "Europe/Jersey"),
        ("Europe/Kaliningrad", "Europe/Kaliningrad"),
        ("Europe/Kiev", "Europe/Kiev"),
        ("Europe/Kirov", "Europe/Kirov"),
        ("Europe/Lisbon", "Europe/Lisbon"),
        ("Europe/Ljubljana", "Europe/Ljubljana"),
        ("Europe/London", "Europe/London"),
        ("Europe/Luxembourg", "Europe/Luxembourg"),
        ("Europe/Madrid", "Europe/Madrid"),
        ("Europe/Malta", "Europe/Malta"),
        ("Europe/Mariehamn", "Europe/Mariehamn"),
        ("Europe/Minsk", "Europe/Minsk"),
        ("Europe/Monaco", "Europe/Monaco"),
        ("Europe/Moscow", "Europe/Moscow"),
        ("Europe/Nicosia", "Europe/Nicosia"),
        ("Europe/Oslo", "Europe/Oslo"),
        ("Europe/Paris", "Europe/Paris"),
        ("Europe/Podgorica", "Europe/Podgorica"),
        ("Europe/Prague", "Europe/Prague"),
        ("Europe/Riga", "Europe/Riga"),
        ("Europe/Rome", "Europe/Rome"),
        ("Europe/Samara", "Europe/Samara"),
        ("Europe/San_Marino", "Europe/San Marino"),
        ("Europe/Sarajevo", "Europe/Sarajevo"),
        ("Europe/Saratov", "Europe/Saratov"),
        ("Europe/Simferopol", "Europe/Simferopol"),
        ("Europe/Skopje", "Europe/Skopje"),
        ("Europe/Sofia", "Europe/Sofia"),
        ("Europe/Stockholm", "Europe/Stockholm"),
        ("Europe/Tallinn", "Europe/Tallinn"),
        ("Europe/Tirane", "Europe/Tirane"),
        ("Europe/Tiraspol", "Europe/Tiraspol"),
        ("Europe/Ulyanovsk", "Europe/Ulyanovsk"),
        ("Europe/Uzhgorod", "Europe/Uzhgorod"),
        ("Europe/Vaduz", "Europe/Vaduz"),
        ("Europe/Vatican", "Europe/Vatican"),
        ("Europe/Vienna", "Europe/Vienna"),
        ("Europe/Vilnius", "Europe/Vilnius"),
        ("Europe/Volgograd", "Europe/Volgograd"),
        ("Europe/Warsaw", "Europe/Warsaw"),
        ("Europe/Zagreb", "Europe/Zagreb"),
        ("Europe/Zaporozhye", "Europe/Zaporozhye"),
        ("Europe/Zurich", "Europe/Zurich"),
        ("Factory", "Factory"),
        ("GB-Eire", "Gb-Eire"),
        ("GB", "Gb"),
        ("GMT-0", "Gmt-0"),
        ("GMT", "Gmt"),
        ("GMT+0", "Gmt+0"),
        ("GMT0", "Gmt0"),
        ("Greenwich", "Greenwich"),
        ("Hongkong", "Hongkong"),
        ("HST", "Hst"),
        ("Iceland", "Iceland"),
        ("Indian/Antananarivo", "Indian/Antananarivo"),
        ("Indian/Chagos", "Indian/Chagos"),
        ("Indian/Christmas", "Indian/Christmas"),
        ("Indian/Cocos", "Indian/Cocos"),
        ("Indian/Comoro", "Indian/Comoro"),
        ("Indian/Kerguelen", "Indian/Kerguelen"),
        ("Indian/Mahe", "Indian/Mahe"),
        ("Indian/Maldives", "Indian/Maldives"),
        ("Indian/Mauritius", "Indian/Mauritius"),
        ("Indian/Mayotte", "Indian/Mayotte"),
        ("Indian/Reunion", "Indian/Reunion"),
        ("Iran", "Iran"),
        ("Israel", "Israel"),
        ("Jamaica", "Jamaica"),
        ("Japan", "Japan"),
        ("Kwajalein", "Kwajalein"),
        ("Libya", "Libya"),
        ("localtime", "Localtime"),
        ("MET", "Met"),
        ("Mexico/BajaNorte", "Mexico/Bajanorte"),
        ("Mexico/BajaSur", "Mexico/Bajasur"),
        ("Mexico/General", "Mexico/General"),
        ("MST", "Mst"),
        ("MST7MDT", "Mst7Mdt"),
        ("Navajo", "Navajo"),
        ("NZ-CHAT", "Nz-Chat"),
        ("NZ", "Nz"),
        ("Pacific/Apia", "Pacific/Apia"),
        ("Pacific/Auckland", "Pacific/Auckland"),
        ("Pacific/Bougainville", "Pacific/Bougainville"),
        ("Pacific/Chatham", "Pacific/Chatham"),
        ("Pacific/Chuuk", "Pacific/Chuuk"),
        ("Pacific/Easter", "Pacific/Easter"),
        ("Pacific/Efate", "Pacific/Efate"),
        ("Pacific/Enderbury", "Pacific/Enderbury"),
        ("Pacific/Fakaofo", "Pacific/Fakaofo"),
        ("Pacific/Fiji", "Pacific/Fiji"),
        ("Pacific/Funafuti", "Pacific/Funafuti"),
        ("Pacific/Galapagos", "Pacific/Galapagos"),
        ("Pacific/Gambier", "Pacific/Gambier"),
        ("Pacific/Guadalcanal", "Pacific/Guadalcanal"),
        ("Pacific/Guam", "Pacific/Guam"),
        ("Pacific/Honolulu", "Pacific/Honolulu"),
        ("Pacific/Johnston", "Pacific/Johnston"),
        ("Pacific/Kiritimati", "Pacific/Kiritimati"),
        ("Pacific/Kosrae", "Pacific/Kosrae"),
        ("Pacific/Kwajalein", "Pacific/Kwajalein"),
        ("Pacific/Majuro", "Pacific/Majuro"),
        ("Pacific/Marquesas", "Pacific/Marquesas"),
        ("Pacific/Midway", "Pacific/Midway"),
        ("Pacific/Nauru", "Pacific/Nauru"),
        ("Pacific/Niue", "Pacific/Niue"),
        ("Pacific/Norfolk", "Pacific/Norfolk"),
        ("Pacific/Noumea", "Pacific/Noumea"),
        ("Pacific/Pago_Pago", "Pacific/Pago Pago"),
        ("Pacific/Palau", "Pacific/Palau"),
        ("Pacific/Pitcairn", "Pacific/Pitcairn"),
        ("Pacific/Pohnpei", "Pacific/Pohnpei"),
        ("Pacific/Ponape", "Pacific/Ponape"),
        ("Pacific/Port_Moresby", "Pacific/Port Moresby"),
        ("Pacific/Rarotonga", "Pacific/Rarotonga"),
        ("Pacific/Saipan", "Pacific/Saipan"),
        ("Pacific/Samoa", "Pacific/Samoa"),
        ("Pacific/Tahiti", "Pacific/Tahiti"),
        ("Pacific/Tarawa", "Pacific/Tarawa"),
        ("Pacific/Tongatapu", "Pacific/Tongatapu"),
        ("Pacific/Truk", "Pacific/Truk"),
        ("Pacific/Wake", "Pacific/Wake"),
        ("Pacific/Wallis", "Pacific/Wallis"),
        ("Pacific/Yap", "Pacific/Yap"),
        ("Poland", "Poland"),
        ("Portugal", "Portugal"),
        ("PRC", "Prc"),
        ("PST8PDT", "Pst8Pdt"),
        ("ROC", "Roc"),
        ("ROK", "Rok"),
        ("Singapore", "Singapore"),
        ("SystemV/AST4", "Systemv/Ast4"),
        ("SystemV/AST4ADT", "Systemv/Ast4Adt"),
        ("SystemV/CST6", "Systemv/Cst6"),
        ("SystemV/CST6CDT", "Systemv/Cst6Cdt"),
        ("SystemV/EST5", "Systemv/Est5"),
        ("SystemV/EST5EDT", "Systemv/Est5Edt"),
        ("SystemV/HST10", "Systemv/Hst10"),
        ("SystemV/MST7", "Systemv/Mst7"),
        ("SystemV/MST7MDT", "Systemv/Mst7Mdt"),
        ("SystemV/PST8", "Systemv/Pst8"),
        ("SystemV/PST8PDT", "Systemv/Pst8Pdt"),
        ("SystemV/YST9", "Systemv/Yst9"),
        ("SystemV/YST9YDT", "Systemv/Yst9Ydt"),
        ("Turkey", "Turkey"),
        ("UCT", "Uct"),
        ("Universal", "Universal"),
        ("US/Alaska", "Us/Alaska"),
        ("US/Aleutian", "Us/Aleutian"),
        ("US/Arizona", "Us/Arizona"),
        ("US/Central", "Us/Central"),
        ("US/East-Indiana", "Us/East-Indiana"),
        ("US/Eastern", "Us/Eastern"),
        ("US/Hawaii", "Us/Hawaii"),
        ("US/Indiana-Starke", "Us/Indiana-Starke"),
        ("US/Michigan", "Us/Michigan"),
        ("US/Mountain", "Us/Mountain"),
        ("US/Pacific-New", "Us/Pacific-New"),
        ("US/Pacific", "Us/Pacific"),
        ("US/Samoa", "Us/Samoa"),
        ("UTC", "Utc"),
        ("W-SU", "W-Su"),
        ("WET", "Wet"),
        ("Zulu", "Zulu"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    avatar = models.ImageField(
        blank=True, upload_to=USERS_FILE_PATH, storage=get_named_storage("MEDIA")
    )
    description = models.TextField(blank=True)
    country = models.CharField(
        default=Country.UNITEDNATIONS, choices=Country.choices, max_length=2
    )
    timezone = models.CharField(max_length=64, default="UTC", choices=Timezones)
    last_scored = models.DateTimeField(null=True)
    show_pending_notifications = models.BooleanField(default=False)
    last_active_notification = models.DateTimeField(null=True)
    joined_time = models.DateTimeField(null=True)
    hedgedoc_password = models.CharField(
        max_length=64, editable=False, default=get_random_string_64
    )
    twitter_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    blog_url = models.URLField(blank=True)
    selected_ctf = models.ForeignKey(
        Ctf,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="players",
        related_query_name="player",
    )
    status = models.IntegerField(default=StatusType.MEMBER, choices=StatusType.choices)

    #
    # Typing
    #
    solved_challenges: django.db.models.manager.Manager["Challenge"]

    @property
    def username(self) -> str:
        assert self.user
        return self.user.username

    @property
    def email(self) -> str:
        assert self.user
        return self.user.email

    @property
    def has_superpowers(self):
        assert self.user
        return self.user.is_superuser

    def __str__(self):
        return self.username

    @property
    def is_active(self):
        if self.status == Member.StatusType.GUEST:
            return True

        last = self.last_solved_challenge
        if not last:
            return False

        now = datetime.now()
        return last.solved_time - now < timedelta(days=365)

    @cached_property
    def solved_public_challenges(self) -> "Manager[Challenge]":
        return self.solved_challenges.filter(ctf__visibility="public").order_by(
            "solved_time"
        )

    @cached_property
    def solved_categories(self):
        return (
            self.solved_public_challenges.values("category__name")
            .annotate(Count("category"))
            .order_by("category")
        )

    @cached_property
    def last_solved_challenge(self) -> Optional["Challenge"]:
        return self.solved_public_challenges.last()

    @property
    def last_logged_in(self) -> Optional[datetime]:
        return self.user.last_login

    @property
    def hedgedoc_username(self):
        return f"{self.username}@ctfhub.localdomain"

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        url = "https://www.gravatar.com/avatar/{}?d={}".format(
            hashlib.md5(self.email.encode()).hexdigest(),
            quote(f"https://eu.ui-avatars.com/api/{self.username}/64/random/", safe=""),
        )
        return url

    def save(self, **kwargs):
        #
        # Validate the hedgedoc user is registered
        #
        hedgedoc_cli = helpers.HedgeDoc(
            (self.hedgedoc_username, self.hedgedoc_password)
        )
        if hedgedoc_cli.login() == False:
            print(
                f"not logged in, registering {self.hedgedoc_username}/{self.hedgedoc_password}"
            )
            if not hedgedoc_cli.register():
                #
                # Register the user in hedgedoc failed, delete the user, and raise
                #
                raise ExternalError(
                    f"Registration of user {self.hedgedoc_username} on hedgedoc failed"
                )
        else:
            print(
                f"logged in, registering {self.hedgedoc_username}/{self.hedgedoc_password}"
            )

        #
        # Create/save the user
        #
        super(Member, self).save(**kwargs)

        return

    @property
    def country_flag_url(self):
        url_prefix = f"{IMAGE_URL}flags"
        if not self.country:
            return f"{url_prefix}/{CTFHUB_DEFAULT_COUNTRY_LOGO}"
        return f"{url_prefix}/{slugify(Member.Country(self.country).label)}.png"

    @property
    def is_guest(self):
        return self.status == Member.StatusType.GUEST

    @property
    def is_member(self):
        return self.status == Member.StatusType.MEMBER

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{str(self)}"

    @cached_property
    def private_ctfs(self):
        if self.is_guest:
            if not self.selected_ctf:
                raise AttributeError
            return Ctf.objects.filter(
                id=self.selected_ctf.id, visibility=Ctf.VisibilityType.PRIVATE
            )
        return Ctf.objects.filter(
            visibility=Ctf.VisibilityType.PRIVATE, created_by=self
        )

    @cached_property
    def public_ctfs(self):
        if self.is_guest:
            if not self.selected_ctf:
                raise AttributeError
            return Ctf.objects.filter(
                id=self.selected_ctf.id, visibility=Ctf.VisibilityType.PUBLIC
            )
        return Ctf.objects.filter(visibility=Ctf.VisibilityType.PUBLIC)

    @cached_property
    def ctfs(self):
        return self.private_ctfs | self.public_ctfs

    def get_absolute_url(self):
        return reverse(
            "ctfhub:users-detail",
            args=[
                str(self.pk),
            ],
        )

    def best_category(self, year: Optional[int] = None) -> str:
        """Get the name of the ChallengeCategory where the current member excels

        Args:
            year (_type_, optional): if given, specify for which year calculate the score

        Returns:
            str: _description_
        """
        qs = (
            self.solved_public_challenges.values("category__name")
            .annotate(Sum("points"))
            .order_by("-points__sum")
        )

        if year:
            qs = qs.filter(solved_time__year=year)

        if not qs:
            return ""

        entry = qs.first()
        assert entry
        return entry["category__name"]


class ChallengeCategory(TimeStampedModel):
    """
    CTF challenge category model

    The category for a specific challenge. This approach is better than using choices because
    we can't predict all existing categories for CTFs.
    """

    name = models.CharField(max_length=128, unique=True)

    #
    # Typing
    #
    challenge_set: django.db.models.manager.Manager["Challenge"]

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Challenge(TimeStampedModel):
    """
    CTF challenge model
    """

    STATUS = Choices(
        "unsolved",
        "solved",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=256)
    points = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ChallengeCategory, on_delete=models.DO_NOTHING, null=True
    )
    note_id = models.UUIDField(default=uuid.uuid4, editable=True)
    excalidraw_room_id = models.CharField(
        default=generate_excalidraw_room_id,
        validators=[
            RegexValidator(
                regex=EXCALIDRAW_ROOM_ID_REGEX,
                message=f"Please follow regex format {EXCALIDRAW_ROOM_ID_REGEX}",
                code="nomatch",
            )
        ],
    )
    excalidraw_room_key = models.CharField(
        default=generate_excalidraw_room_key,
        validators=[
            RegexValidator(
                regex=EXCALIDRAW_ROOM_KEY_REGEX,
                message=f"Please follow regex format {EXCALIDRAW_ROOM_KEY_REGEX}",
                code="nomatch",
            )
        ],
    )
    ctf = models.ForeignKey(Ctf, on_delete=models.CASCADE)
    last_update_by = models.ForeignKey(
        Member, on_delete=models.DO_NOTHING, null=True, related_name="last_updater"
    )
    flag = models.CharField(max_length=128, blank=True)
    flag_tracker = FieldTracker(
        fields=[
            "flag",
        ]
    )
    status = StatusField()
    solved_time = MonitorField(
        monitor="status",
        when=[
            "solved",
        ],
    )  # type: ignore
    solvers = models.ManyToManyField(
        "ctfhub.Member", blank=True, related_name="solved_challenges"
    )
    tags = models.ManyToManyField("ctfhub.Tag", blank=True, related_name="challenges")
    assigned_members = models.ManyToManyField(
        "ctfhub.Member", blank=True, related_name="assigned_challenges"
    )

    #
    # Typing
    #

    challengefile_set: django.db.models.manager.Manager["ChallengeFile"]

    @property
    def solved(self) -> bool:
        return self.status == "solved"

    @property
    def is_public(self) -> bool:
        return self.ctf.visibility == "public"

    @property
    def note_url(self) -> str:
        note_id = self.note_id or ""
        return f"{settings.HEDGEDOC_URL}/{note_id}"

    def get_excalidraw_url(self, member=None) -> str:
        """
        Ensure presence of a trailing slash at the end
        """
        url = os.path.join(EXCALIDRAW_URL, "")
        url += f"#room={self.excalidraw_room_id},{self.excalidraw_room_key}"
        return url

    @cached_property
    def files(self):
        return self.challengefile_set.all()

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.ctf.id}--{self.id}"

    def save(self, **kwargs):
        if self.flag_tracker.has_changed("flag"):  # type: ignore
            self.status = "solved" if self.flag else "unsolved"
            self.solvers.add(self.last_update_by)

        super(Challenge, self).save()
        return

    def get_absolute_url(self):
        return reverse(
            "ctfhub:challenges-detail",
            args=[
                str(self.id),
            ],
        )


class ChallengeFile(TimeStampedModel):
    """
    CTF file model, for a file associated with a challenge
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(
        null=True,
        upload_to=get_challenge_upload_path,
        storage=get_named_storage("MEDIA"),
        validators=[
            challenge_file_max_size_validator,
        ],
    )
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    mime = models.CharField(max_length=128)
    type = models.CharField(max_length=512)
    hash = models.CharField(max_length=64)  # sha256 -> 32*2

    @property
    def name(self):
        return os.path.basename(self.file.name)

    @property
    def size(self):
        return self.file.size

    @property
    def url(self):
        return self.file.url

    def save(self, **kwargs):
        #
        # save() to commit files to proper location
        #
        super().save()

        #
        # update missing properties
        #
        fpath = Path(CTF_CHALLENGE_FILE_ROOT) / self.name
        if fpath.exists():
            abs_path = str(fpath.absolute())
            if not self.mime:
                self.mime = get_file_mime(fpath)
            if not self.type:
                self.type = get_file_magic(fpath)
            if not self.hash:
                self.hash = hashlib.sha256(open(abs_path, "rb").read()).hexdigest()
            super(ChallengeFile, self).save()
        return


class Tag(TimeStampedModel):
    """
    Internal notification system
    """

    name = models.TextField(unique=True)

    #
    # Typing
    #

    challenges: django.db.models.manager.Manager["Challenge"]

    def __str__(self):
        return self.name


class CtfStats:
    """
    Statistic collection class
    """

    def __init__(self, year):
        self.year = year

    def members(self):
        return Member.objects.select_related("user").filter(
            creation_time__year__lte=self.year
        )

    def player_activity(self):
        """Return the number of ctfs played per member"""
        return (
            Member.objects.select_related("user")
            .filter(
                solved_challenges__isnull=False,
                solved_challenges__ctf__start_date__year=self.year,
            )
            .annotate(play_count=Count("solved_challenges__ctf", distinct=True))
        )

    def category_stats(self):
        """Return the total number of challenges solved per category"""
        return (
            Challenge.objects.filter(
                solvers__isnull=False, ctf__start_date__year=self.year
            )
            .values("category__name")
            .annotate(Count("category"))
        )

    def ctf_stats(self) -> dict:
        """Return a monthly count of public CTFs played"""
        ctfs = (
            Ctf.objects.filter(
                challenge__isnull=False,
                start_date__year=self.year,
            )
            .annotate(month=TruncMonth("start_date"))
            .order_by("start_date")
            .distinct()
        )

        monthly_counts = [
            (k.strftime("%Y/%m"), v)
            for k, v in sorted(
                Counter(ctf.start_date for ctf in ctfs if ctf.start_date).items()
            )
        ]

        return {"monthly_counts": monthly_counts}

    def year_stats(self):
        """Return a yearly count of public CTFs played"""
        return (
            Ctf.objects.filter(start_date__isnull=False, visibility="public")
            .values_list("start_date__year")
            .annotate(Count("start_date__year"))
        )

    def ranking_stats(self) -> dict:
        """Return the all time and last CTFs rankings"""
        qs = (
            Ctf.objects.prefetch_related(
                "challenge_set",
                "challenge_set__solvers",
                "challenge_set__solvers__user",
            )
            .filter(
                visibility="public",
                rating__gt=0,
                end_date__lt=datetime.now(),  # finished ctfs only
                start_date__year=self.year,
                challenge__solvers__isnull=False,
                challenge__status="solved",
            )
            .order_by("start_date")
            .distinct()
        )

        members = set()
        ctfs: list[Ctf] = []

        for ctf in qs:
            ctf.member_points = {}

            for chall in ctf.challenge_set.all():
                for member in chall.solvers.all():
                    if member not in ctf.member_points:
                        ctf.member_points[member] = 0
                        members.add(member)

                    points = chall.points / len(chall.solvers.all())
                    ctf.member_points[member] += points

            ctfs.append(ctf)

        for member in members:
            member.percents = OrderedDict()
            member.ratings = OrderedDict()
            member.rating_accu = 0

        for ctf in ctfs:
            ctf.member_percents = {}

            max(ctf.member_points.values())
            total_points = sum(ctf.member_points.values())

            for member in members:
                percent = 0
                rating = 0

                if member in ctf.member_points:
                    points = ctf.member_points[member]
                    rating = ctf.rating * points / total_points
                    percent = 100 * points / total_points

                member.rating_accu = round(member.rating_accu + rating, 2)
                member.ratings[ctf] = member.rating_accu
                member.percents[ctf] = percent

                ctf.member_percents[member] = percent

        # alltime ranking and timeline
        for member in members:
            member.percent = round(mean(member.percents.values()), 2)

        alltime_ranking = sorted(members, key=lambda x: x.rating_accu, reverse=True)

        # last CTFs
        for ctf in ctfs:
            # Ranking = sorted scoring members in descending order
            ctf.ranking = sorted(
                ctf.member_percents.items(), key=lambda x: x[1], reverse=True
            )

        return {"alltime": alltime_ranking, "last_ctfs": ctfs[::-1]}


SearchResult = namedtuple("SearchResult", "category name description link")


class SearchEngine:
    """A very basic^Mbad search engine"""

    def __init__(self, query, *args, **kwargs):
        query = query.lower()
        patterns = query.split()
        self.selected_category = None

        # if a specific category was selected, use it
        for p in patterns:
            if p.startswith("cat:"):
                category = p.split(":", 1)[1]
                if category in VALID_SEARCH_CATEGORIES:
                    self.selected_category = category
                    patterns.remove(p)
                    break

        query = " ".join(patterns)
        self.results = []

        if self.selected_category is None:
            for cat in VALID_SEARCH_CATEGORIES:
                handle = VALID_SEARCH_CATEGORIES[cat]
                self.results.extend(handle(query))
        else:
            handle = VALID_SEARCH_CATEGORIES[self.selected_category]
            self.results.extend(handle(query))
        return

    @classmethod
    def search_in_ctfs(cls, query: str) -> list:
        """search in ctf name & description

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in Ctf.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        ):
            if query.lower() in entry.name:
                description = entry.name
            else:
                description = entry.description[50:]
            results.append(
                SearchResult(
                    "ctf",
                    entry.name,
                    description,
                    reverse("ctfhub:ctfs-detail", kwargs={"pk": entry.id}),
                )
            )
        return results

    @classmethod
    def search_in_challenges(cls, query: str) -> list:
        """search in challenge name & description

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in Challenge.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        ):
            if query.lower() in entry.name:
                description = entry.name
            else:
                description = entry.description[50:]
            results.append(
                SearchResult(
                    "challenge",
                    entry.name,
                    description,
                    reverse("ctfhub:challenges-detail", kwargs={"pk": entry.id}),
                )
            )
        return results

    @classmethod
    def search_in_members(cls, query: str) -> list:
        """search members

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in Member.objects.filter(
            Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(description__icontains=query)
        ):
            results.append(
                SearchResult(
                    "member",
                    entry.username,
                    entry.description,
                    reverse("ctfhub:users-detail", kwargs={"pk": entry.pk}),
                )
            )
        return results

    @classmethod
    def search_in_categories(cls, query: str) -> list:
        """search pattern in categories

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in ChallengeCategory.objects.filter(Q(name__icontains=query)):
            for challenge in entry.challenge_set.all():
                results.append(
                    SearchResult(
                        "category",
                        challenge.name,
                        f"{challenge.name} - ({challenge.ctf})",
                        reverse(
                            "ctfhub:challenges-detail", kwargs={"pk": challenge.id}
                        ),
                    )
                )
        return results

    @classmethod
    def search_in_tags(cls, query: str) -> list:
        """search tags

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in Tag.objects.filter(Q(name__icontains=query)):
            for challenge in entry.challenges.all():
                results.append(
                    SearchResult(
                        "tag",
                        challenge.name,
                        f"{challenge.name} - ({challenge.ctf})",
                        reverse(
                            "ctfhub:challenges-detail", kwargs={"pk": challenge.id}
                        ),
                    )
                )
        return results

    @classmethod
    def search_in_ctftime(cls, query: str) -> list:
        """search ctfs in ctftime

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in ctftime_ctfs(running=False, future=True):
            if query in entry["title"].lower() or query in entry["description"].lower():
                results.append(
                    SearchResult(
                        "ctftime",
                        entry["title"],
                        entry["description"],
                        reverse("ctfhub:ctfs-import") + f"?ctftime_id={entry['id']}",
                    )
                )
        return results


VALID_SEARCH_CATEGORIES = {
    "ctf": SearchEngine.search_in_ctfs,
    "challenge": SearchEngine.search_in_challenges,
    "member": SearchEngine.search_in_members,
    "category": SearchEngine.search_in_categories,
    "tag": SearchEngine.search_in_tags,
    "ctftime": SearchEngine.search_in_ctftime,
}
