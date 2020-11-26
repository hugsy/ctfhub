import uuid
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import namedtuple

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum, Count, Q
from django.urls.base import reverse
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property

from model_utils.fields import MonitorField, StatusField
from model_utils import Choices, FieldTracker


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
    def solved_challenges_for_graph(self):
        res = []
        Point = namedtuple("Point", "time accu")
        accu = 0
        for solved in self.solved_challenges:
            accu += solved.points
            res.append( Point(solved.solved_time, accu) )
        return res

    @cached_property
    def jitsi_url(self):
        return f"{JITSI_URL}/{self.id}"




class Member(TimeStampedModel):
    """
    CTF team member model
    """
    COUNTRIES= Choices("Andorra", "United Arab Emirates", "Afghanistan", "Antigua and Barbuda", "Anguilla", "Albania", "Armenia", "Angola", "Antarctica", "Argentina", "American Samoa", "Austria", "Australia", "Aruba", "Åland Islands", "Azerbaijan", "Bosnia and Herzegovina", "Barbados", "Bangladesh", "Belgium", "Burkina Faso", "Bulgaria", "Bahrain", "Burundi", "Benin", "Saint Barthélemy", "Bermuda", "Brunei", "Bolivia", "Caribbean Netherlands", "Brazil", "Bahamas", "Bhutan", "Bouvet Island", "Botswana", "Belarus", "Belize", "Canada", "Cocos (Keeling) Islands", "DR Congo", "Central African Republic", "Republic of the Congo", "Switzerland", "Côte d'Ivoire (Ivory Coast)", "Cook Islands", "Chile", "Cameroon", "China", "Colombia", "Costa Rica", "Cuba", "Cape Verde", "Curaçao", "Christmas Island", "Cyprus", "Czechia", "Germany", "Djibouti", "Denmark", "Dominica", "Dominican Republic", "Algeria", "Ecuador", "Estonia", "Egypt", "Western Sahara", "Eritrea", "Spain", "Ethiopia", "European Union", "Finland", "Fiji", "Falkland Islands", "Micronesia", "Faroe Islands", "France", "Gabon", "United Kingdom", "England", "Northern Ireland", "Scotland", "Wales", "Grenada", "Georgia", "French Guiana", "Guernsey", "Ghana", "Gibraltar", "Greenland", "Gambia", "Guinea", "Guadeloupe", "Equatorial Guinea", "Greece", "South Georgia", "Guatemala", "Guam", "Guinea-Bissau", "Guyana", "Hong Kong", "Heard Island and McDonald Islands", "Honduras", "Croatia", "Haiti", "Hungary", "Indonesia", "Ireland", "Israel", "Isle of Man", "India", "British Indian Ocean Territory", "Iraq", "Iran", "Iceland", "Italy", "Jersey", "Jamaica", "Jordan", "Japan", "Kenya", "Kyrgyzstan", "Cambodia", "Kiribati", "Comoros", "Saint Kitts and Nevis", "North Korea", "South Korea", "Kuwait", "Cayman Islands", "Kazakhstan", "Laos", "Lebanon", "Saint Lucia", "Liechtenstein", "Sri Lanka", "Liberia", "Lesotho", "Lithuania", "Luxembourg", "Latvia", "Libya", "Morocco", "Monaco", "Moldova", "Montenegro", "Saint Martin", "Madagascar", "Marshall Islands", "North Macedonia", "Mali", "Myanmar", "Mongolia", "Macau", "Northern Mariana Islands", "Martinique", "Mauritania", "Montserrat", "Malta", "Mauritius", "Maldives", "Malawi", "Mexico", "Malaysia", "Mozambique", "Namibia", "New Caledonia", "Niger", "Norfolk Island", "Nigeria", "Nicaragua", "Netherlands", "Norway", "Nepal", "Nauru", "Niue", "New Zealand", "Oman", "Panama", "Peru", "French Polynesia", "Papua New Guinea", "Philippines", "Pakistan", "Poland", "Saint Pierre and Miquelon", "Pitcairn Islands", "Puerto Rico", "Palestine", "Portugal", "Palau", "Paraguay", "Qatar", "Réunion", "Romania", "Serbia", "Russia", "Rwanda", "Saudi Arabia", "Solomon Islands", "Seychelles", "Sudan", "Sweden", "Singapore", "Saint Helena, Ascension and Tristan da Cunha", "Slovenia", "Svalbard and Jan Mayen", "Slovakia", "Sierra Leone", "San Marino", "Senegal", "Somalia", "Suriname", "South Sudan", "São Tomé and Príncipe", "El Salvador", "Sint Maarten", "Syria", "Eswatini (Swaziland)", "Turks and Caicos Islands", "Chad", "French Southern and Antarctic Lands", "Togo", "Thailand", "Tajikistan", "Tokelau", "Timor-Leste", "Turkmenistan", "Tunisia", "Tonga", "Turkey", "Trinidad and Tobago", "Tuvalu", "Taiwan", "Tanzania", "Ukraine", "Uganda", "United States Minor Outlying Islands", "United Nations", "United States", "Alaska", "Alabama", "Arkansas", "Arizona", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Iowa", "Idaho", "Illinois", "Indiana", "Kansas", "Kentucky", "Louisiana", "Massachusetts", "Maryland", "Maine", "Michigan", "Minnesota", "Missouri", "Mississippi", "Montana", "North Carolina", "North Dakota", "Nebraska", "New Hampshire", "New Jersey", "New Mexico", "Nevada", "New York", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Virginia", "Vermont", "Washington", "Wisconsin", "West Virginia", "Wyoming", "Uruguay", "Uzbekistan", "Vatican City (Holy See)", "Saint Vincent and the Grenadines", "Venezuela", "British Virgin Islands", "United States Virgin Islands", "Vietnam", "Vanuatu", "Wallis and Futuna", "Samoa", "Kosovo", "Yemen", "Mayotte", "South Africa", "Zambia", "Zimbabwe")
    TIMEZONES = Choices("UTC", "UTC-12", "UTC-11", "UTC-10", "UTC-9", "UTC-8", "UTC-7", "UTC-6", "UTC-5", "UTC-4", "UTC-3", "UTC-2", "UTC-1", "UTC+1", "UTC+2", "UTC+3", "UTC+4", "UTC+5", "UTC+6", "UTC+7", "UTC+8", "UTC+9", "UTC+10", "UTC+11", "UTC+12")

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
    def best_category(self) -> str:
        best_categories_by_point = self.solved_challenges.filter(
            ctf__visibility = "public"
        ).values("category__name").annotate(
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
    """[summary]
    """
    VALID_SEARCH_CATEGORIES = (
        "ctf",
        "challenge",
        "member",
        "ctftime",
        "category",
        "file",
    )

    def __init__(self, query, *args, **kwargs):
        query = query.lower()
        patterns = query.split()
        self.selected_category = None

        # if a specific category was selected, use it
        for p in patterns:
            if p.startswith("cat:"):
                p = p.replace("cat:", "")
                if p in SearchEngine.VALID_SEARCH_CATEGORIES:
                    self.selected_category = p
                    query = query.replace(f"cat:{p}", "")
                    break

        self.results = []

        # search in ctf name & description
        if self.selected_category in (None, "ctf"):
            for entry in Ctf.objects.filter(
                    Q(name__icontains = query) |
                    Q(description__icontains = query)
                ):
                if query.lower() in entry.name:
                    description = entry.name
                else:
                    description = entry.description[50:]

                self.results.append(
                    SearchResult(
                        "ctf",
                        entry.name,
                        description,
                        reverse("ctfpad:ctfs-detail", kwargs={"pk": entry.id})
                    )
                )

        # search members
        if self.selected_category in (None, "member"):
            for entry in Member.objects.filter(
                    Q(user__username__icontains = query) |
                    Q(user__email__icontains = query) |
                    Q(description__icontains = query)
                ):

                self.results.append(
                    SearchResult(
                        "member",
                        entry.username,
                        entry.description,
                        reverse("ctfpad:users-detail", kwargs={"pk": entry.id})
                    )
                )