import hashlib
import os
import tempfile
import uuid
import zipfile
from collections import Counter, namedtuple
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import OrderedDict
from urllib.parse import quote
import zoneinfo

import django.db.models.manager
import requests
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls.base import reverse
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from model_utils import Choices, FieldTracker
from model_utils.fields import MonitorField, StatusField

from ctfhub.helpers import (
    create_new_note,
    ctftime_ctfs,
    ctftime_get_ctf_logo_url,
    generate_excalidraw_room_id,
    generate_excalidraw_room_key,
    get_file_magic,
    get_file_mime,
    get_random_string_128,
    register_new_hedgedoc_user,
)
from ctfhub.validators import challenge_file_max_size_validator
from ctfhub_project.settings import (
    CTF_CHALLENGE_FILE_PATH,
    CTF_CHALLENGE_FILE_ROOT,
    CTFHUB_DEFAULT_COUNTRY_LOGO,
    CTFTIME_URL,
    EXCALIDRAW_ROOM_ID_REGEX,
    EXCALIDRAW_ROOM_KEY_REGEX,
    EXCALIDRAW_URL,
    HEDGEDOC_URL,
    IMAGE_URL,
    JITSI_URL,
    USERS_FILE_PATH,
)

# Create your models here.


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
    avatar = models.ImageField(blank=True, upload_to=USERS_FILE_PATH)
    ctftime_id = models.IntegerField(default=0, blank=True, null=True)

    def __str__(self) -> str:
        return self.name

    @property
    def ctftime_url(self) -> str:
        return f"{CTFTIME_URL}/team/{self.ctftime_id}"

    @property
    def members(self):
        _members: django.db.models.manager.Manager[Member] = self.member_set.all()
        members = sorted(_members.filter(status="member"), key=lambda x: x.username)
        members += sorted(_members.filter(status="guest"), key=lambda x: x.username)
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
    weight = models.FloatField(default=1.0)
    rating = models.FloatField(default=0.0)
    note_id = models.CharField(default=create_new_note, max_length=38, blank=True)

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
        return self.visibility == "public"

    @property
    def is_private(self) -> bool:
        return self.visibility == "private"

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
        l = self.challenges.count()
        if l == 0:
            return 0
        return int(float(self.solved_challenges.count() / l) * 100)

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
        assert self.end_date and self.start_date
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
        return ctftime_get_ctf_logo_url(self.ctftime_id)

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

    def export_notes_as_zipstream(self, stream, member=None):
        zip_file = zipfile.ZipFile(stream, "w")
        now = datetime.now()
        ts = (now.year, now.month, now.day, 0, 0, 0)

        session = requests.Session()

        #
        # try impersonating requesting user on HedgeDoc, this way we're sure anonymous & unauthorized users
        # can't dump data
        #
        if member:
            session.post(
                f"{HEDGEDOC_URL}/login",
                data={
                    "email": member.hedgedoc_username,
                    "password": member.hedgedoc_password,
                },
            )

        # add ctf notes
        fname = slugify(f"{self.name}.md")
        with tempfile.TemporaryFile():
            result = session.get(f"{HEDGEDOC_URL}{self.note_id}/download")
            zip_file.writestr(
                zipfile.ZipInfo(filename=fname, date_time=ts), result.text
            )

        # add challenge notes
        for challenge in self.challenges:
            fname = slugify(f"{self.name}-{challenge.name}.md")
            with tempfile.TemporaryFile():
                result = session.get(f"{HEDGEDOC_URL}{challenge.note_id}/download")
                if result.status_code != requests.codes.ok:
                    continue
                zinfo = zipfile.ZipInfo(filename=fname, date_time=ts)
                zip_file.writestr(zinfo, result.text)

        if member:
            session.post(f"{HEDGEDOC_URL}/logout")

        return f"{slugify(self.name)}-notes.zip"

    @property
    def note_url(self) -> str:
        note_id = self.note_id or "/"
        return f"{HEDGEDOC_URL}{note_id}"

    def get_absolute_url(self):
        return reverse(
            "ctfhub:ctfs-detail",
            args=[
                str(self.id),
            ],
        )

    @property
    def team(self):
        return self.players.all()


class Member(TimeStampedModel):
    """
    CTF team member model
    """

    class StatusType(models.IntegerChoices):
        MEMBER = 0, _("Member")
        GUEST = 1, _("Guest")

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

    Timezones = models.TextChoices(
        "Timezones", " ".join(zoneinfo.available_timezones())
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    avatar = models.ImageField(blank=True, upload_to=USERS_FILE_PATH)
    description = models.TextField(blank=True)
    country = models.CharField(
        default=Country.UNITEDNATIONS, choices=Country.choices, max_length=2
    )
    timezone = models.CharField(max_length=64, default="UTC", choices=Timezones.choices)
    last_scored = models.DateTimeField(null=True)
    show_pending_notifications = models.BooleanField(default=False)
    last_active_notification = models.DateTimeField(null=True)
    joined_time = models.DateTimeField(null=True)
    hedgedoc_password = models.CharField(max_length=64, null=True)
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
        if self.status == "guest":
            return True

        last = self.last_solved_challenge
        if not last:
            return False

        now = datetime.now()
        return last.solved_time - now < timedelta(days=365)

    @cached_property
    def solved_public_challenges(self):
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
    def last_solved_challenge(self):
        return self.solved_public_challenges.last()

    @property
    def last_logged_in(self):
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
        if not self.hedgedoc_password:
            # create the hedgedoc user
            self.hedgedoc_password = get_random_string(64)
            if not register_new_hedgedoc_user(
                self.hedgedoc_username, self.hedgedoc_password
            ):
                # password empty == anonymous mode under HedgeDoc
                self.hedgedoc_password = ""

        super(Member, self).save()
        return

    @property
    def country_flag_url(self):
        url_prefix = f"{IMAGE_URL}flags"
        if not self.country:
            return f"{url_prefix}/{CTFHUB_DEFAULT_COUNTRY_LOGO}"
        return f"{url_prefix}/{slugify(Member.Country(self.country).label)}.png"

    @property
    def is_guest(self):
        return self.status == "guest"

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{str(self)}"

    @cached_property
    def private_ctfs(self):
        if self.is_guest:
            return Ctf.objects.none()
        return Ctf.objects.filter(visibility="private", created_by=self)

    @cached_property
    def public_ctfs(self):
        if self.is_guest:
            return Ctf.objects.filter(id=self.selected_ctf)
        return Ctf.objects.filter(visibility="public")

    @cached_property
    def ctfs(self):
        return self.private_ctfs | self.public_ctfs

    def get_absolute_url(self):
        return reverse(
            "ctfhub:users-detail",
            args=[
                str(id(self)),
            ],
        )

    def best_category(self, year=None):
        qs = (
            self.solved_public_challenges.values("category__name")
            .annotate(Sum("points"))
            .order_by("-points__sum")
        )

        if year:
            qs = qs.filter(solved_time__year=year)

        if not qs:
            return ""

        return qs.first()["category__name"]


class ChallengeCategory(TimeStampedModel):
    """
    CTF challenge category model

    The category for a specific challenge. This approach is better than using choices because
    we can't predict all existing categories for CTFs.
    """

    name = models.CharField(max_length=128, unique=True)

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
    note_id = models.CharField(default=create_new_note, max_length=38, blank=True)
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
    )
    solvers = models.ManyToManyField(
        "ctfhub.Member", blank=True, related_name="solved_challenges"
    )
    tags = models.ManyToManyField("ctfhub.Tag", blank=True, related_name="challenges")

    @property
    def solved(self) -> bool:
        return self.status == "solved"

    @property
    def is_public(self) -> bool:
        return self.ctf.visibility == "public"

    @property
    def note_url(self) -> str:
        note_id = self.note_id or "/"
        return f"{HEDGEDOC_URL}{note_id}"

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
        if self.flag_tracker.has_changed("flag"):
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
        upload_to=CTF_CHALLENGE_FILE_PATH,
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
        # save() to commit files to proper location
        super(ChallengeFile, self).save()

        # update missing properties
        p = Path(CTF_CHALLENGE_FILE_ROOT) / self.name
        if p.exists():
            abs_path = str(p.absolute())
            if not self.mime:
                self.mime = get_file_mime(p)
            if not self.type:
                self.type = get_file_magic(p)
            if not self.hash:
                self.hash = hashlib.sha256(open(abs_path, "rb").read()).hexdigest()
            super(ChallengeFile, self).save()
        return


class Tag(TimeStampedModel):
    """
    Internal notification system
    """

    name = models.TextField(unique=True)

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

    def player_activity(self) -> dict:
        """Return the number of ctfs played per member"""
        return (
            Member.objects.select_related("user")
            .filter(
                solved_challenges__isnull=False,
                solved_challenges__ctf__start_date__year=self.year,
            )
            .annotate(play_count=Count("solved_challenges__ctf", distinct=True))
        )

    def category_stats(self) -> dict:
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
            for k, v in sorted(Counter(ctf.month for ctf in ctfs).items())
        ]

        return {"monthly_counts": monthly_counts}

    def year_stats(self) -> list:
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
        ctfs = []

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
                    reverse("ctfhub:users-detail", kwargs={"pk": entry.id}),
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
