import uuid
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import namedtuple
import zipfile
import requests
import tempfile

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum, Count, Q
from django.urls.base import reverse
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property

from model_utils.fields import MonitorField, StatusField
from model_utils import Choices, FieldTracker

from ctfpad.helpers import ctftime_fetch_next_ctf_data


from ctftools.settings import (
    HEDGEDOC_URL,
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
        return self.member_set.all()




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
    weight = models.IntegerField(default=1)

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
        return self.challenge_set.filter(status = "solved")

    @property
    def unsolved_challenges(self):
        return self.challenge_set.filter(status = "unsolved")

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
            t = session.post(f"{HEDGEDOC_URL}/login", data={"email": member.hedgedoc_username, "password": member.hedgedoc_password})

        for challenge in self.challenges:
            fname = slugify( f"{self.name}-{challenge.name}.md" )
            with tempfile.TemporaryFile() as fp:
                result = session.get(f"{HEDGEDOC_URL}{challenge.note_id}/download")
                if result.status_code != requests.codes.ok:
                    continue
                zinfo = zipfile.ZipInfo(filename=fname, date_time=ts)
                zip_file.writestr(zinfo, result.text)

        if member:
            session.post(f"{HEDGEDOC_URL}/logout")

        return f"{slugify(self.name)}-notes.zip"




class Member(TimeStampedModel):
    """
    CTF team member model
    """
    COUNTRIES= Choices("Afghanistan", "Alabama", "Alaska", "Albania", "Algeria", "American Samoa", "Andorra", "Angola", "Anguilla", "Antarctica", "Antigua and Barbuda", "Argentina", "Arizona", "Arkansas", "Armenia", "Aruba", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bermuda", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Bouvet Island", "Brazil", "British Indian Ocean Territory", "British Virgin Islands", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "California", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Caribbean Netherlands", "Cayman Islands", "Central African Republic", "Chad", "Chile", "China", "Christmas Island", "Cocos (Keeling) Islands", "Colombia", "Colorado", "Comoros", "Connecticut", "Cook Islands", "Costa Rica", "Croatia", "Cuba", "Curaçao", "Cyprus", "Czechia", "Côte d\'Ivoire (Ivory Coast)", "DR Congo", "Delaware", "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "England", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini (Swaziland)", "Ethiopia", "European Union", "Falkland Islands", "Faroe Islands", "Fiji", "Finland", "Florida", "France", "French Guiana", "French Polynesia", "French Southern and Antarctic Lands", "Gabon", "Gambia", "Georgia", "Georgia", "Germany", "Ghana", "Gibraltar", "Greece", "Greenland", "Grenada", "Guadeloupe", "Guam", "Guatemala", "Guernsey", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Hawaii", "Heard Island and McDonald Islands", "Honduras", "Hong Kong", "Hungary", "Iceland", "Idaho", "Illinois", "India", "Indiana", "Indonesia", "Iowa", "Iran", "Iraq", "Ireland", "Isle of Man", "Israel", "Italy", "Jamaica", "Japan", "Jersey", "Jordan", "Kansas", "Kazakhstan", "Kentucky", "Kenya", "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Louisiana", "Luxembourg", "Macau", "Madagascar", "Maine", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Martinique", "Maryland", "Massachusetts", "Mauritania", "Mauritius", "Mayotte", "Mexico", "Michigan", "Micronesia", "Minnesota", "Mississippi", "Missouri", "Moldova", "Monaco", "Mongolia", "Montana", "Montenegro", "Montserrat", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nebraska", "Nepal", "Netherlands", "Nevada", "New Caledonia", "New Hampshire", "New Jersey", "New Mexico", "New York", "New Zealand", "Nicaragua", "Niger", "Nigeria", "Niue", "Norfolk Island", "North Carolina", "North Dakota", "North Korea", "North Macedonia", "Northern Ireland", "Northern Mariana Islands", "Norway", "Ohio", "Oklahoma", "Oman", "Oregon", "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Pennsylvania", "Peru", "Philippines", "Pitcairn Islands", "Poland", "Portugal", "Puerto Rico", "Qatar", "Republic of the Congo", "Rhode Island", "Romania", "Russia", "Rwanda", "Réunion", "Saint Barthélemy", "Saint Helena, Ascension and Tristan da Cunha", "Saint Kitts and Nevis", "Saint Lucia", "Saint Martin", "Saint Pierre and Miquelon", "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Saudi Arabia", "Scotland", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Sint Maarten", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Carolina", "South Dakota", "South Georgia", "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Svalbard and Jan Mayen", "Sweden", "Switzerland", "Syria", "São Tomé and Príncipe", "Taiwan", "Tajikistan", "Tanzania", "Tennessee", "Texas", "Thailand", "Timor-Leste", "Togo", "Tokelau", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Turks and Caicos Islands", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United Nations", "United States", "United States Minor Outlying Islands", "United States Virgin Islands", "Uruguay", "Utah", "Uzbekistan", "Vanuatu", "Vatican City (Holy See)", "Venezuela", "Vermont", "Vietnam", "Virginia", "Wales", "Wallis and Futuna", "Washington", "West Virginia", "Western Sahara", "Wisconsin", "Wyoming", "Yemen", "Zambia", "Zimbabwe")
    TIMEZONES = Choices("UTC+0", "UTC-12", "UTC-11", "UTC-10", "UTC-9", "UTC-8", "UTC-7", "UTC-6", "UTC-5", "UTC-4", "UTC-3", "UTC-2", "UTC-1", "UTC+1", "UTC+2", "UTC+3", "UTC+4", "UTC+5", "UTC+6", "UTC+7", "UTC+8", "UTC+9", "UTC+10", "UTC+11", "UTC+12")

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
    selected_ctf = models.ForeignKey(Ctf, on_delete=models.SET_NULL, null=True, blank=True)

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

    @cached_property
    def solved_public_challenges(self):
        return  self.solved_challenges.filter(
            ctf__visibility = "public"
        ).order_by("solved_time")

    @cached_property
    def best_category(self) -> str:
        best_categories_by_point = self.solved_public_challenges.values(
            "category__name"
        ).annotate(
            dcount=Sum("points")
        ).order_by(
            "-points"
        )
        if best_categories_by_point.count() == 0:
            return ""

        return best_categories_by_point.first()["category__name"]


    @property
    def total_points_scored(self):
        challenges = self.solved_challenges.filter(
            ctf__visibility = "public"
        )
        return challenges.aggregate(Sum("points"))["points__sum"] or 0


    @property
    def last_logged_in(self):
        return self.user.last_login

    @property
    def hedgedoc_username(self):
        return f"{self.username}@ctfpad.localdomain"

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
            return f"{STATIC_URL}/images/blank-country.png"
        return f"{STATIC_URL}/images/flags/{slugify(self.country)}.png"

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.id}"

    @cached_property
    def private_ctfs(self):
        return Ctf.objects.filter(visibility = "private", created_by = self)

    @cached_property
    def public_ctfs(self):
        return Ctf.objects.filter(visibility = "public")

    @cached_property
    def ctfs(self):
        return self.private_ctfs | self.public_ctfs

    @property
    def timezone_offset(self):
        if not self.timezone:
            return 0
        return timedelta(hours = int(self.timezone.replace("UTC", ""), 10))

    def to_local_date(self, utc_date):
        return utc_date + self.timezone_offset



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
    note_id = models.CharField(max_length=80, blank=True)
    ctf = models.ForeignKey(Ctf, on_delete=models.CASCADE)
    last_update_by = models.ForeignKey(Member, on_delete=models.DO_NOTHING, null=True, related_name='last_updater')
    flag = models.CharField(max_length=128, blank=True)
    flag_tracker = FieldTracker(fields=['flag',])
    status = StatusField()
    solved_time = MonitorField(monitor='status', when=['solved',])
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

    @cached_property
    def files(self):
        return self.challengefile_set.all()

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.ctf.id}--{self.id}"

    def save(self):
        if not self.note_id:
            self.note_id = create_new_note()

        if self.flag_tracker.has_changed("flag"):
            self.status = "solved"
            self.solvers.add( self.last_update_by )
            self.solved_time = datetime.now()

        super(Challenge, self).save()
        return



class ChallengeFile(TimeStampedModel):
    """
    CTF file model, for a file associated with a challenge
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(null=True, upload_to=CTF_CHALLENGE_FILE_PATH, validators=[challenge_file_max_size_validator,])
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    mime = models.CharField(max_length=128)
    type = models.CharField(max_length=512)
    hash = models.CharField(max_length=64) # sha256 -> 32*2

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
            if not self.hash: self.hash = hashlib.sha256( open(abs_path, "rb").read() ).hexdigest()
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

    def players_activity(self) -> dict:
        """
        Retrieve all the players activity (i.e. number of CTFs with at least
        one solved challenge)
        """
        res = {}
        active_players = Member.objects.filter(solved_challenges__isnull=False)
        for player in active_players:
            res[ player.username ] = Challenge.objects.filter(solvers__in = [player,]).distinct("ctf").count()
        return res


    def solved_categories(self) -> dict:
        """[summary]

        Returns:
            dict: [description]
        """
        count_solved_challenges = Challenge.objects.filter(
            solvers__isnull=False
        ).values("category__name").annotate(
            dcount=Count("category")
        )
        return count_solved_challenges


    def last_year_stats(self) -> dict:
        """[summary]

        Returns:
            dict: [description]
        """
        res = {}
        now = datetime.now()
        cur_month = now
        for _ in range(12):
            start_cur_month = cur_month.replace(day=1)
            ctf_by_month = Ctf.objects.filter(
                start_date__month = start_cur_month.month
            ).count()
            res[start_cur_month.strftime("%Y/%m")] = ctf_by_month
            cur_month = start_cur_month - timedelta(days=1)
        return res


SearchResult = namedtuple("SearchResult", "category name description link" )

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
                p = p.replace("cat:", "")
                if p in VALID_SEARCH_CATEGORIES:
                    self.selected_category = p
                    query = query.replace(f"cat:{p}", "")
                    break

        self.results = []

        if self.selected_category is None:
            for cat in VALID_SEARCH_CATEGORIES:
                handle = VALID_SEARCH_CATEGORIES[cat]
                self.results.extend( handle(query) )
        else:
            handle = VALID_SEARCH_CATEGORIES[self.selected_category]
            self.results.extend( handle(query) )
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
                Q(name__icontains = query) |
                Q(description__icontains = query)
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
                Q(name__icontains = query) |
                Q(description__icontains = query)
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
                    Q(user__username__icontains = query) |
                    Q(user__email__icontains = query) |
                    Q(description__icontains = query)
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
                Q(name__icontains = query)
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
                Q(name__icontains = query)
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
        for entry in ctftime_fetch_next_ctf_data():
            if query in entry["title"].lower() or query in entry["description"].lower():
                results.append(
                    SearchResult(
                        "ctftime",
                        entry["title"][:15] + "...",
                        entry["description"][:100] + "...",
                        reverse("ctfpad:ctfs-import") + f"?ctftime_id={entry['id']}"
                    )
                )
        return results


VALID_SEARCH_CATEGORIES = {
    "ctf" :        SearchEngine.search_in_ctfs,
    "challenge" :  SearchEngine.search_in_challenges,
    "member" :     SearchEngine.search_in_members,
    "category" :   SearchEngine.search_in_categories,
    "tag" :        SearchEngine.search_in_tags,
    "ctftime" :    SearchEngine.search_in_ctftime,
}