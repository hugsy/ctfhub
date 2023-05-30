from typing import OrderedDict
import uuid
import os
import hashlib
from urllib.parse import quote
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import namedtuple, Counter
from statistics import mean
import zipfile
import requests
import tempfile

from django.contrib.sites.models import Site
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.urls.base import reverse
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from model_utils.fields import MonitorField, StatusField
from model_utils import Choices, FieldTracker

from ctfpad.helpers import ctftime_ctfs

from ctftools.settings import (
    EXCALIDRAW_ROOM_ID_PATTERN, EXCALIDRAW_ROOM_KEY_PATTERN, HEDGEDOC_URL, SHORT_DATETIME_FORMAT,
    EXCALIDRAW_URL,
    CTF_CHALLENGE_FILE_PATH,
    CTF_CHALLENGE_FILE_ROOT, STATIC_URL,
    USERS_FILE_PATH,
    CTFTIME_URL,
    JITSI_URL,
)
from ctfpad.validators import challenge_file_max_size_validator
from ctfpad.helpers import (
    get_random_string_128, get_random_string_64, register_new_hedgedoc_user,
    create_new_note,
    get_file_magic,
    get_file_mime,
    ctftime_get_ctf_logo_url,
    generate_excalidraw_room_id,
    generate_excalidraw_room_key,
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
        members = sorted(self.member_set.filter(status="member"), key=lambda x: x.username)
        members += sorted(self.member_set.filter(status="guest"), key=lambda x: x.username)
        return members


class Ctf(TimeStampedModel):
    """
    CTF model class
    """
    VISIBILITY = Choices("public", "private")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    created_by = models.ForeignKey("ctfpad.Member", on_delete=models.CASCADE, blank=True, null=True)
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    flag_prefix = models.CharField(max_length=64, blank=True)
    team_login = models.CharField(max_length=128, blank=True)
    team_password = models.CharField(max_length=128, blank=True)
    ctftime_id = models.IntegerField(default=0, blank=True, null=True)
    visibility = StatusField(choices_name="VISIBILITY")
    weight = models.FloatField(default=1.0)
    rating = models.FloatField(default=0.0)
    note_id = models.CharField(default=create_new_note, max_length=38, blank=True)

    def __str__(self) -> str:
        return self.name

    @property
    def is_permanent(self) -> bool:
        return not self.start_date and not self.end_date

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
        if l == 0: return 0
        return int(float(self.solved_challenges.count() / l) * 100)

    @property
    def total_points(self):
        return self.challenges.aggregate(Sum("points"))["points__sum"] or 0

    @property
    def scored_points(self):
        return self.solved_challenges.aggregate(Sum("points"))["points__sum"] or 0

    @property
    def scored_points_as_percent(self):
        if self.total_points == 0: return 0
        return int(float(self.scored_points / self.total_points) * 100)

    @property
    def duration(self):
        if self.is_permanent: return 0
        return self.end_date - self.start_date

    @property
    def is_running(self):
        if self.is_permanent:
            return True
        now = datetime.now()
        return self.start_date <= now < self.end_date

    @property
    def is_finished(self):
        if self.is_permanent:
            return False
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
        challs = self.challenge_set.prefetch_related(
            'solvers__user'
        ).filter(
            status='solved',
            solvers__isnull=False
        ).order_by(
            'solved_time'
        ).distinct(
            'solved_time',
            'id'
        ).all()

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
        zip_file = zipfile.ZipFile(stream, 'w')
        now = datetime.now()
        ts = (now.year, now.month, now.day, 0, 0, 0)

        session = requests.Session()

        #
        # try impersonating requesting user on HedgeDoc, this way we're sure anonymous & unauthorized users
        # can't dump data
        #
        if member:
            t = session.post(f"{HEDGEDOC_URL}/login",
                             data={"email": member.hedgedoc_username, "password": member.hedgedoc_password})

        # add ctf notes
        fname = slugify(f"{self.name}.md")
        with tempfile.TemporaryFile() as fp:
            result = session.get(f"{HEDGEDOC_URL}{self.note_id}/download")
            zip_file.writestr(zipfile.ZipInfo(filename=fname, date_time=ts), result.text)

        # add challenge notes
        for challenge in self.challenges:
            fname = slugify(f"{self.name}-{challenge.name}.md")
            with tempfile.TemporaryFile() as fp:
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
        return reverse('ctfpad:ctfs-detail', args=[str(self.id), ])

    @property
    def team(self):
        return self.players.all()


class Member(TimeStampedModel):
    """
    CTF team member model
    """
    STATUS = Choices('member', 'guest', )
    COUNTRIES = Choices("Afghanistan", "Alabama", "Alaska", "Albania", "Algeria", "American Samoa", "Andorra", "Angola",
                        "Anguilla", "Antarctica", "Antigua and Barbuda", "Argentina", "Arizona", "Arkansas", "Armenia",
                        "Aruba", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados",
                        "Belarus", "Belgium", "Belize", "Benin", "Bermuda", "Bhutan", "Bolivia",
                        "Bosnia and Herzegovina", "Botswana", "Bouvet Island", "Brazil",
                        "British Indian Ocean Territory", "British Virgin Islands", "Brunei", "Bulgaria",
                        "Burkina Faso", "Burundi", "California", "Cambodia", "Cameroon", "Canada", "Cape Verde",
                        "Caribbean Netherlands", "Cayman Islands", "Central African Republic", "Chad", "Chile", "China",
                        "Christmas Island", "Cocos (Keeling) Islands", "Colombia", "Colorado", "Comoros", "Connecticut",
                        "Cook Islands", "Costa Rica", "Croatia", "Cuba", "Curaçao", "Cyprus", "Czechia",
                        "Côte d\'Ivoire (Ivory Coast)", "DR Congo", "Delaware", "Denmark", "Djibouti", "Dominica",
                        "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "England", "Equatorial Guinea",
                        "Eritrea", "Estonia", "Eswatini (Swaziland)", "Ethiopia", "European Union", "Falkland Islands",
                        "Faroe Islands", "Fiji", "Finland", "Florida", "France", "French Guiana", "French Polynesia",
                        "French Southern and Antarctic Lands", "Gabon", "Gambia", "Georgia", "Georgia", "Germany",
                        "Ghana", "Gibraltar", "Greece", "Greenland", "Grenada", "Guadeloupe", "Guam", "Guatemala",
                        "Guernsey", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Hawaii",
                        "Heard Island and McDonald Islands", "Honduras", "Hong Kong", "Hungary", "Iceland", "Idaho",
                        "Illinois", "India", "Indiana", "Indonesia", "Iowa", "Iran", "Iraq", "Ireland", "Isle of Man",
                        "Israel", "Italy", "Jamaica", "Japan", "Jersey", "Jordan", "Kansas", "Kazakhstan", "Kentucky",
                        "Kenya", "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho",
                        "Liberia", "Libya", "Liechtenstein", "Lithuania", "Louisiana", "Luxembourg", "Macau",
                        "Madagascar", "Maine", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands",
                        "Martinique", "Maryland", "Massachusetts", "Mauritania", "Mauritius", "Mayotte", "Mexico",
                        "Michigan", "Micronesia", "Minnesota", "Mississippi", "Missouri", "Moldova", "Monaco",
                        "Mongolia", "Montana", "Montenegro", "Montserrat", "Morocco", "Mozambique", "Myanmar",
                        "Namibia", "Nauru", "Nebraska", "Nepal", "Netherlands", "Nevada", "New Caledonia",
                        "New Hampshire", "New Jersey", "New Mexico", "New York", "New Zealand", "Nicaragua", "Niger",
                        "Nigeria", "Niue", "Norfolk Island", "North Carolina", "North Dakota", "North Korea",
                        "North Macedonia", "Northern Ireland", "Northern Mariana Islands", "Norway", "Ohio", "Oklahoma",
                        "Oman", "Oregon", "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay",
                        "Pennsylvania", "Peru", "Philippines", "Pitcairn Islands", "Poland", "Portugal", "Puerto Rico",
                        "Qatar", "Republic of the Congo", "Rhode Island", "Romania", "Russia", "Rwanda", "Réunion",
                        "Saint Barthélemy", "Saint Helena, Ascension and Tristan da Cunha", "Saint Kitts and Nevis",
                        "Saint Lucia", "Saint Martin", "Saint Pierre and Miquelon", "Saint Vincent and the Grenadines",
                        "Samoa", "San Marino", "Saudi Arabia", "Scotland", "Senegal", "Serbia", "Seychelles",
                        "Sierra Leone", "Singapore", "Sint Maarten", "Slovakia", "Slovenia", "Solomon Islands",
                        "Somalia", "South Africa", "South Carolina", "South Dakota", "South Georgia", "South Korea",
                        "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Svalbard and Jan Mayen", "Sweden",
                        "Switzerland", "Syria", "São Tomé and Príncipe", "Taiwan", "Tajikistan", "Tanzania",
                        "Tennessee", "Texas", "Thailand", "Timor-Leste", "Togo", "Tokelau", "Tonga",
                        "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Turks and Caicos Islands",
                        "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United Nations",
                        "United States", "United States Minor Outlying Islands", "United States Virgin Islands",
                        "Uruguay", "Utah", "Uzbekistan", "Vanuatu", "Vatican City (Holy See)", "Venezuela", "Vermont",
                        "Vietnam", "Virginia", "Wales", "Wallis and Futuna", "Washington", "West Virginia",
                        "Western Sahara", "Wisconsin", "Wyoming", "Yemen", "Zambia", "Zimbabwe")
    # pytz.common_timezones
    TIMEZONES = Choices('UTC', 'Africa/Abidjan', 'Africa/Accra', 'Africa/Addis_Ababa', 'Africa/Algiers',
                        'Africa/Asmara', 'Africa/Bamako', 'Africa/Bangui', 'Africa/Banjul', 'Africa/Bissau',
                        'Africa/Blantyre', 'Africa/Brazzaville', 'Africa/Bujumbura', 'Africa/Cairo',
                        'Africa/Casablanca', 'Africa/Ceuta', 'Africa/Conakry', 'Africa/Dakar', 'Africa/Dar_es_Salaam',
                        'Africa/Djibouti', 'Africa/Douala', 'Africa/El_Aaiun', 'Africa/Freetown', 'Africa/Gaborone',
                        'Africa/Harare', 'Africa/Johannesburg', 'Africa/Juba', 'Africa/Kampala', 'Africa/Khartoum',
                        'Africa/Kigali', 'Africa/Kinshasa', 'Africa/Lagos', 'Africa/Libreville', 'Africa/Lome',
                        'Africa/Luanda', 'Africa/Lubumbashi', 'Africa/Lusaka', 'Africa/Malabo', 'Africa/Maputo',
                        'Africa/Maseru', 'Africa/Mbabane', 'Africa/Mogadishu', 'Africa/Monrovia', 'Africa/Nairobi',
                        'Africa/Ndjamena', 'Africa/Niamey', 'Africa/Nouakchott', 'Africa/Ouagadougou',
                        'Africa/Porto-Novo', 'Africa/Sao_Tome', 'Africa/Tripoli', 'Africa/Tunis', 'Africa/Windhoek',
                        'America/Adak', 'America/Anchorage', 'America/Anguilla', 'America/Antigua', 'America/Araguaina',
                        'America/Argentina/Buenos_Aires', 'America/Argentina/Catamarca', 'America/Argentina/Cordoba',
                        'America/Argentina/Jujuy', 'America/Argentina/La_Rioja', 'America/Argentina/Mendoza',
                        'America/Argentina/Rio_Gallegos', 'America/Argentina/Salta', 'America/Argentina/San_Juan',
                        'America/Argentina/San_Luis', 'America/Argentina/Tucuman', 'America/Argentina/Ushuaia',
                        'America/Aruba', 'America/Asuncion', 'America/Atikokan', 'America/Bahia',
                        'America/Bahia_Banderas', 'America/Barbados', 'America/Belem', 'America/Belize',
                        'America/Blanc-Sablon', 'America/Boa_Vista', 'America/Bogota', 'America/Boise',
                        'America/Cambridge_Bay', 'America/Campo_Grande', 'America/Cancun', 'America/Caracas',
                        'America/Cayenne', 'America/Cayman', 'America/Chicago', 'America/Chihuahua',
                        'America/Costa_Rica', 'America/Creston', 'America/Cuiaba', 'America/Curacao',
                        'America/Danmarkshavn', 'America/Dawson', 'America/Dawson_Creek', 'America/Denver',
                        'America/Detroit', 'America/Dominica', 'America/Edmonton', 'America/Eirunepe',
                        'America/El_Salvador', 'America/Fort_Nelson', 'America/Fortaleza', 'America/Glace_Bay',
                        'America/Goose_Bay', 'America/Grand_Turk', 'America/Grenada', 'America/Guadeloupe',
                        'America/Guatemala', 'America/Guayaquil', 'America/Guyana', 'America/Halifax', 'America/Havana',
                        'America/Hermosillo', 'America/Indiana/Indianapolis', 'America/Indiana/Knox',
                        'America/Indiana/Marengo', 'America/Indiana/Petersburg', 'America/Indiana/Tell_City',
                        'America/Indiana/Vevay', 'America/Indiana/Vincennes', 'America/Indiana/Winamac',
                        'America/Inuvik', 'America/Iqaluit', 'America/Jamaica', 'America/Juneau',
                        'America/Kentucky/Louisville', 'America/Kentucky/Monticello', 'America/Kralendijk',
                        'America/La_Paz', 'America/Lima', 'America/Los_Angeles', 'America/Lower_Princes',
                        'America/Maceio', 'America/Managua', 'America/Manaus', 'America/Marigot', 'America/Martinique',
                        'America/Matamoros', 'America/Mazatlan', 'America/Menominee', 'America/Merida',
                        'America/Metlakatla', 'America/Mexico_City', 'America/Miquelon', 'America/Moncton',
                        'America/Monterrey', 'America/Montevideo', 'America/Montserrat', 'America/Nassau',
                        'America/New_York', 'America/Nipigon', 'America/Nome', 'America/Noronha',
                        'America/North_Dakota/Beulah', 'America/North_Dakota/Center', 'America/North_Dakota/New_Salem',
                        'America/Nuuk', 'America/Ojinaga', 'America/Panama', 'America/Pangnirtung',
                        'America/Paramaribo', 'America/Phoenix', 'America/Port-au-Prince', 'America/Port_of_Spain',
                        'America/Porto_Velho', 'America/Puerto_Rico', 'America/Punta_Arenas', 'America/Rainy_River',
                        'America/Rankin_Inlet', 'America/Recife', 'America/Regina', 'America/Resolute',
                        'America/Rio_Branco', 'America/Santarem', 'America/Santiago', 'America/Santo_Domingo',
                        'America/Sao_Paulo', 'America/Scoresbysund', 'America/Sitka', 'America/St_Barthelemy',
                        'America/St_Johns', 'America/St_Kitts', 'America/St_Lucia', 'America/St_Thomas',
                        'America/St_Vincent', 'America/Swift_Current', 'America/Tegucigalpa', 'America/Thule',
                        'America/Thunder_Bay', 'America/Tijuana', 'America/Toronto', 'America/Tortola',
                        'America/Vancouver', 'America/Whitehorse', 'America/Winnipeg', 'America/Yakutat',
                        'America/Yellowknife', 'Antarctica/Casey', 'Antarctica/Davis', 'Antarctica/DumontDUrville',
                        'Antarctica/Macquarie', 'Antarctica/Mawson', 'Antarctica/McMurdo', 'Antarctica/Palmer',
                        'Antarctica/Rothera', 'Antarctica/Syowa', 'Antarctica/Troll', 'Antarctica/Vostok',
                        'Arctic/Longyearbyen', 'Asia/Aden', 'Asia/Almaty', 'Asia/Amman', 'Asia/Anadyr', 'Asia/Aqtau',
                        'Asia/Aqtobe', 'Asia/Ashgabat', 'Asia/Atyrau', 'Asia/Baghdad', 'Asia/Bahrain', 'Asia/Baku',
                        'Asia/Bangkok', 'Asia/Barnaul', 'Asia/Beirut', 'Asia/Bishkek', 'Asia/Brunei', 'Asia/Chita',
                        'Asia/Choibalsan', 'Asia/Colombo', 'Asia/Damascus', 'Asia/Dhaka', 'Asia/Dili', 'Asia/Dubai',
                        'Asia/Dushanbe', 'Asia/Famagusta', 'Asia/Gaza', 'Asia/Hebron', 'Asia/Ho_Chi_Minh',
                        'Asia/Hong_Kong', 'Asia/Hovd', 'Asia/Irkutsk', 'Asia/Jakarta', 'Asia/Jayapura',
                        'Asia/Jerusalem', 'Asia/Kabul', 'Asia/Kamchatka', 'Asia/Karachi', 'Asia/Kathmandu',
                        'Asia/Khandyga', 'Asia/Kolkata', 'Asia/Krasnoyarsk', 'Asia/Kuala_Lumpur', 'Asia/Kuching',
                        'Asia/Kuwait', 'Asia/Macau', 'Asia/Magadan', 'Asia/Makassar', 'Asia/Manila', 'Asia/Muscat',
                        'Asia/Nicosia', 'Asia/Novokuznetsk', 'Asia/Novosibirsk', 'Asia/Omsk', 'Asia/Oral',
                        'Asia/Phnom_Penh', 'Asia/Pontianak', 'Asia/Pyongyang', 'Asia/Qatar', 'Asia/Qostanay',
                        'Asia/Qyzylorda', 'Asia/Riyadh', 'Asia/Sakhalin', 'Asia/Samarkand', 'Asia/Seoul',
                        'Asia/Shanghai', 'Asia/Singapore', 'Asia/Srednekolymsk', 'Asia/Taipei', 'Asia/Tashkent',
                        'Asia/Tbilisi', 'Asia/Tehran', 'Asia/Thimphu', 'Asia/Tokyo', 'Asia/Tomsk', 'Asia/Ulaanbaatar',
                        'Asia/Urumqi', 'Asia/Ust-Nera', 'Asia/Vientiane', 'Asia/Vladivostok', 'Asia/Yakutsk',
                        'Asia/Yangon', 'Asia/Yekaterinburg', 'Asia/Yerevan', 'Atlantic/Azores', 'Atlantic/Bermuda',
                        'Atlantic/Canary', 'Atlantic/Cape_Verde', 'Atlantic/Faroe', 'Atlantic/Madeira',
                        'Atlantic/Reykjavik', 'Atlantic/South_Georgia', 'Atlantic/St_Helena', 'Atlantic/Stanley',
                        'Australia/Adelaide', 'Australia/Brisbane', 'Australia/Broken_Hill', 'Australia/Darwin',
                        'Australia/Eucla', 'Australia/Hobart', 'Australia/Lindeman', 'Australia/Lord_Howe',
                        'Australia/Melbourne', 'Australia/Perth', 'Australia/Sydney', 'Canada/Atlantic',
                        'Canada/Central', 'Canada/Eastern', 'Canada/Mountain', 'Canada/Newfoundland', 'Canada/Pacific',
                        'Europe/Amsterdam', 'Europe/Andorra', 'Europe/Astrakhan', 'Europe/Athens', 'Europe/Belgrade',
                        'Europe/Berlin', 'Europe/Bratislava', 'Europe/Brussels', 'Europe/Bucharest', 'Europe/Budapest',
                        'Europe/Busingen', 'Europe/Chisinau', 'Europe/Copenhagen', 'Europe/Dublin', 'Europe/Gibraltar',
                        'Europe/Guernsey', 'Europe/Helsinki', 'Europe/Isle_of_Man', 'Europe/Istanbul', 'Europe/Jersey',
                        'Europe/Kaliningrad', 'Europe/Kiev', 'Europe/Kirov', 'Europe/Lisbon', 'Europe/Ljubljana',
                        'Europe/London', 'Europe/Luxembourg', 'Europe/Madrid', 'Europe/Malta', 'Europe/Mariehamn',
                        'Europe/Minsk', 'Europe/Monaco', 'Europe/Moscow', 'Europe/Oslo', 'Europe/Paris',
                        'Europe/Podgorica', 'Europe/Prague', 'Europe/Riga', 'Europe/Rome', 'Europe/Samara',
                        'Europe/San_Marino', 'Europe/Sarajevo', 'Europe/Saratov', 'Europe/Simferopol', 'Europe/Skopje',
                        'Europe/Sofia', 'Europe/Stockholm', 'Europe/Tallinn', 'Europe/Tirane', 'Europe/Ulyanovsk',
                        'Europe/Uzhgorod', 'Europe/Vaduz', 'Europe/Vatican', 'Europe/Vienna', 'Europe/Vilnius',
                        'Europe/Volgograd', 'Europe/Warsaw', 'Europe/Zagreb', 'Europe/Zaporozhye', 'Europe/Zurich',
                        'GMT', 'Indian/Antananarivo', 'Indian/Chagos', 'Indian/Christmas', 'Indian/Cocos',
                        'Indian/Comoro', 'Indian/Kerguelen', 'Indian/Mahe', 'Indian/Maldives', 'Indian/Mauritius',
                        'Indian/Mayotte', 'Indian/Reunion', 'Pacific/Apia', 'Pacific/Auckland', 'Pacific/Bougainville',
                        'Pacific/Chatham', 'Pacific/Chuuk', 'Pacific/Easter', 'Pacific/Efate', 'Pacific/Enderbury',
                        'Pacific/Fakaofo', 'Pacific/Fiji', 'Pacific/Funafuti', 'Pacific/Galapagos', 'Pacific/Gambier',
                        'Pacific/Guadalcanal', 'Pacific/Guam', 'Pacific/Honolulu', 'Pacific/Kiritimati',
                        'Pacific/Kosrae', 'Pacific/Kwajalein', 'Pacific/Majuro', 'Pacific/Marquesas', 'Pacific/Midway',
                        'Pacific/Nauru', 'Pacific/Niue', 'Pacific/Norfolk', 'Pacific/Noumea', 'Pacific/Pago_Pago',
                        'Pacific/Palau', 'Pacific/Pitcairn', 'Pacific/Pohnpei', 'Pacific/Port_Moresby',
                        'Pacific/Rarotonga', 'Pacific/Saipan', 'Pacific/Tahiti', 'Pacific/Tarawa', 'Pacific/Tongatapu',
                        'Pacific/Wake', 'Pacific/Wallis', 'US/Alaska', 'US/Arizona', 'US/Central', 'US/Eastern',
                        'US/Hawaii', 'US/Mountain', 'US/Pacific')

    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True)
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    avatar = models.ImageField(blank=True, upload_to=USERS_FILE_PATH)
    description = models.TextField(blank=True)
    country = StatusField(choices_name='COUNTRIES')
    timezone = StatusField(choices_name='TIMEZONES')
    last_scored = models.DateTimeField(null=True)
    show_pending_notifications = models.BooleanField(default=False)
    last_active_notification = models.DateTimeField(null=True)
    joined_time = models.DateTimeField(null=True)
    hedgedoc_password = models.CharField(max_length=64, null=True)
    twitter_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    blog_url = models.URLField(blank=True)
    selected_ctf = models.ForeignKey(Ctf, on_delete=models.SET_NULL, null=True, blank=True, related_name="players",
                                     related_query_name="player")
    status = StatusField()

    @property
    def username(self):
        return self.user.username

    @property
    def email(self):
        return self.user.email

    @property
    def has_superpowers(self):
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
        return self.solved_challenges.filter(
            ctf__visibility="public"
        ).order_by("solved_time")

    @cached_property
    def solved_categories(self):
        return self.solved_public_challenges.values(
            "category__name"
        ).annotate(
            Count("category")
        ).order_by("category")

    @cached_property
    def last_solved_challenge(self):
        return self.solved_public_challenges.last()

    @property
    def last_logged_in(self):
        return self.user.last_login

    @property
    def hedgedoc_username(self):
        return f"{self.username}@ctfpad.localdomain"

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        url = 'https://www.gravatar.com/avatar/{}?d={}'.format(
            hashlib.md5(self.email.encode()).hexdigest(),
            quote(f'https://eu.ui-avatars.com/api/{self.username}/64/random/', safe='')
        )
        return url

    def save(self):
        if not self.hedgedoc_password:
            # create the hedgedoc user
            self.hedgedoc_password = get_random_string(64)
            if not register_new_hedgedoc_user(self.hedgedoc_username, self.hedgedoc_password):
                # password empty == anonymous mode under HedgeDoc
                self.hedgedoc_password = ""

        super(Member, self).save()
        return

    @property
    def country_flag_url(self):
        if not self.country:
            return f"{STATIC_URL}images/blank-country.png"
        return f"{STATIC_URL}images/flags/{slugify(self.country)}.png"

    @property
    def is_guest(self):
        return self.status == "guest"

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.id}"

    @cached_property
    def private_ctfs(self):
        if self.is_guest:
            return Ctf.objects.none()
        return Ctf.objects.filter(visibility="private", created_by=self)

    @cached_property
    def public_ctfs(self):
        if self.is_guest:
            return Ctf.objects.filter(id=self.selected_ctf.id)
        return Ctf.objects.filter(visibility="public")

    @cached_property
    def ctfs(self):
        return self.private_ctfs | self.public_ctfs

    def get_absolute_url(self):
        return reverse('ctfpad:users-detail', args=[str(self.id), ])

    def best_category(self, year=None):
        qs = self.solved_public_challenges.values(
            "category__name"
        ).annotate(
            Sum("points")
        ).order_by(
            "-points__sum"
        )

        if year:
            qs = qs.filter(
                solved_time__year=year
            )

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
    STATUS = Choices('unsolved', 'solved', )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=256)
    points = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    category = models.ForeignKey(ChallengeCategory, on_delete=models.DO_NOTHING, null=True)
    note_id = models.CharField(default=create_new_note, max_length=38, blank=True)
    excalidraw_room_id = models.CharField(default=generate_excalidraw_room_id, validators=[
        RegexValidator(regex=EXCALIDRAW_ROOM_ID_PATTERN,
                       message=f'Please follow regex format {EXCALIDRAW_ROOM_ID_PATTERN}', code='nomatch')])
    excalidraw_room_key = models.CharField(default=generate_excalidraw_room_key, validators=[
        RegexValidator(regex=EXCALIDRAW_ROOM_KEY_PATTERN,
                       message=f'Please follow regex format {EXCALIDRAW_ROOM_KEY_PATTERN}', code='nomatch')])
    ctf = models.ForeignKey(Ctf, on_delete=models.CASCADE)
    last_update_by = models.ForeignKey(Member, on_delete=models.DO_NOTHING, null=True, related_name='last_updater')
    flag = models.CharField(max_length=128, blank=True)
    flag_tracker = FieldTracker(fields=['flag', ])
    status = StatusField()
    solved_time = MonitorField(monitor='status', when=['solved', ])
    solvers = models.ManyToManyField("ctfpad.Member", blank=True, related_name="solved_challenges")
    tags = models.ManyToManyField("ctfpad.Tag", blank=True, related_name="challenges")

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
        # Ensure presence of a trailing slash at the end
        url = os.path.join(EXCALIDRAW_URL, "")
        url += f"#room={self.excalidraw_room_id},{self.excalidraw_room_key}"
        return url

    @cached_property
    def files(self):
        return self.challengefile_set.all()

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.ctf.id}--{self.id}"

    def save(self):
        if self.flag_tracker.has_changed("flag"):
            self.status = "solved" if self.flag else "unsolved"
            self.solvers.add(self.last_update_by)

        super(Challenge, self).save()
        return

    def get_absolute_url(self):
        return reverse('ctfpad:challenges-detail', args=[str(self.id), ])


class ChallengeFile(TimeStampedModel):
    """
    CTF file model, for a file associated with a challenge
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(null=True, upload_to=CTF_CHALLENGE_FILE_PATH,
                            validators=[challenge_file_max_size_validator, ])
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

    def save(self):
        # save() to commit files to proper location
        super(ChallengeFile, self).save()

        # update missing properties
        p = Path(CTF_CHALLENGE_FILE_ROOT) / self.name
        if p.exists():
            abs_path = str(p.absolute())
            if not self.mime: self.mime = get_file_mime(p)
            if not self.type: self.type = get_file_magic(p)
            if not self.hash: self.hash = hashlib.sha256(open(abs_path, "rb").read()).hexdigest()
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
        return Member.objects.select_related(
            'user'
        ).filter(
            creation_time__year__lte=self.year
        )

    def player_activity(self) -> dict:
        """Return the number of ctfs played per member
        """
        return Member.objects.select_related(
            'user'
        ).filter(
            solved_challenges__isnull=False,
            solved_challenges__ctf__start_date__year=self.year
        ).annotate(
            play_count=Count('solved_challenges__ctf', distinct=True)
        )

    def category_stats(self) -> dict:
        """Return the total number of challenges solved per category
        """
        return Challenge.objects.filter(
            solvers__isnull=False,
            ctf__start_date__year=self.year
        ).values("category__name").annotate(
            Count("category")
        )

    def ctf_stats(self) -> dict:
        """Return a monthly count of public CTFs played
        """
        ctfs = Ctf.objects.filter(
            challenge__isnull=False,
            start_date__year=self.year,
        ).annotate(
            month=TruncMonth('start_date')
        ).order_by(
            'start_date'
        ).distinct()

        monthly_counts = [(k.strftime('%Y/%m'), v) for k, v in sorted(
            Counter(ctf.month for ctf in ctfs).items())]

        return {'monthly_counts': monthly_counts}

    def year_stats(self) -> list:
        """Return a yearly count of public CTFs played
        """
        return Ctf.objects.filter(
            start_date__isnull=False,
            visibility='public'
        ).values_list(
            'start_date__year'
        ).annotate(
            Count('start_date__year')
        )

    def ranking_stats(self) -> dict:
        """Return the all time and last CTFs rankings
        """
        qs = Ctf.objects.prefetch_related(
            'challenge_set',
            'challenge_set__solvers',
            'challenge_set__solvers__user',
        ).filter(
            visibility='public',
            rating__gt=0,
            end_date__lt=datetime.now(),  # finished ctfs only
            start_date__year=self.year,
            challenge__solvers__isnull=False,
            challenge__status='solved'
        ).order_by(
            'start_date'
        ).distinct()

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

            first_points = max(ctf.member_points.values())
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
            ctf.ranking = sorted(ctf.member_percents.items(), key=lambda x: x[1], reverse=True)

        return {'alltime': alltime_ranking, 'last_ctfs': ctfs[::-1]}


SearchResult = namedtuple("SearchResult", "category name description link")


class SearchEngine:
    """A very basic^Mbad search engine
    """

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
        """ search in ctf name & description

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in Ctf.objects.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
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
                    reverse("ctfpad:ctfs-detail", kwargs={"pk": entry.id})
                )
            )
        return results

    @classmethod
    def search_in_challenges(cls, query: str) -> list:
        """ search in challenge name & description

        Args:
            query (str): [description]

        Returns:
            list: [description]
        """
        results = []
        for entry in Challenge.objects.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
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
                    reverse("ctfpad:challenges-detail", kwargs={"pk": entry.id})
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
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query) |
                Q(description__icontains=query)
        ):
            results.append(
                SearchResult(
                    "member",
                    entry.username,
                    entry.description,
                    reverse("ctfpad:users-detail", kwargs={"pk": entry.id})
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
        for entry in ChallengeCategory.objects.filter(
                Q(name__icontains=query)
        ):
            for challenge in entry.challenge_set.all():
                results.append(
                    SearchResult(
                        "category",
                        challenge.name,
                        f"{challenge.name} - ({challenge.ctf})",
                        reverse("ctfpad:challenges-detail", kwargs={"pk": challenge.id})
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
        for entry in Tag.objects.filter(
                Q(name__icontains=query)
        ):
            for challenge in entry.challenges.all():
                results.append(
                    SearchResult(
                        "tag",
                        challenge.name,
                        f"{challenge.name} - ({challenge.ctf})",
                        reverse("ctfpad:challenges-detail", kwargs={"pk": challenge.id})
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
                        reverse("ctfpad:ctfs-import") + f"?ctftime_id={entry['id']}"
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
