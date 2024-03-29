import io
import os
import pathlib
import smtplib
import time
import uuid
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional, Union
import warnings

import django.core.mail
import django.utils.crypto
import magic
import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import get_storage_class

import ctfhub.models


if TYPE_CHECKING:
    from ctfhub.models import ChallengeFile


class HedgeDoc:
    email: str
    password: str
    session: Optional[requests.Session]
    __url: Optional[str]

    def __init__(
        self, credentials: Union["ctfhub.models.Member", tuple[str, str]]
    ) -> None:
        if isinstance(credentials, ctfhub.models.Member):
            self.email = credentials.hedgedoc_username
            if not credentials.hedgedoc_password:
                raise AttributeError(
                    "Member is not registered on the hedgedoc instance"
                )
            self.password = credentials.hedgedoc_password
        elif isinstance(credentials, tuple):
            self.email, self.password = credentials
        else:
            raise TypeError("Invalid type for credentials")

        self.session = None
        self.__url = None
        return

    def __del__(self) -> None:
        if self.logged_in:
            self.logout()
        return

    @property
    def username(self) -> str:
        return self.email[: self.email.find("@")]

    @property
    def logged_in(self) -> bool:
        if not self.session:
            return False

        response = self.session.get(
            f"{self.url}/me",
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )

        if response.status_code != requests.codes["ok"]:
            return False

        data = response.json()
        return data["status"] == "ok"

    @property
    def url(self) -> str:
        """Get the URL base to hedgedoc. This is the URL as it must be used for CTFHub to reach HedgeDoc.
        To get the URL as must be used by web browsers, use `public_url`

        Raises:
            ValidationError: if the url is invalid (bad pattern OR unreachable)

        Returns:
            str: _description_
        """
        if not self.__url:
            #
            # lazy fetching, cache it, raises ValidationError on failure
            #
            url = settings.HEDGEDOC_URL.rstrip("/").lower()
            if not url.startswith("http://") and not url.startswith("https://"):
                raise ValidationError(f"Invalid URL protocol for {url}")
            if not self.ping(url):  # TODO add timeout
                raise ValidationError(f"Failed to reach {url}")
            self.__url = url

        return self.__url

    @property
    def public_url(self) -> str:
        """Get the URL to HedgeDoc as it must be used by web browsers.

        Raises:
            ValidationError: if the url is invalid (bad pattern OR unreachable)

        Returns:
            str: _description_
        """
        return self.url

    @staticmethod
    def Url() -> str:  # pylint: disable=invalid-name
        """Static method to always return the public URL

        Returns:
            str: _description_
        """
        cli = HedgeDoc(("anonymous", ""))
        return cli.public_url

    def ping(self, url: Optional[str] = None) -> bool:
        """Sends a simple ping to the server

        Args:
            url (Optional[str], optional): the url to ping, if not given default to the instance `__url` attribute

        Returns:
            bool: true if the server responded correctly, false on timeout
        """
        if not url:
            url = self.__url
        assert url
        try:
            requests.head(
                url,
                timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            return False
        except requests.exceptions.ConnectionError:
            return False
        return True

    def register(self) -> bool:
        """Register the member in hedgedoc. If fail, the member will be seen as anonymous. Anonymous user can read but
        not write to notes.

        Returns:
            bool: if the register action succeeded, returns True; False in any other cases
        """

        res = requests.post(
            f"{self.url}/register",
            data={"email": self.email, "password": self.password},
            allow_redirects=True,
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )

        #
        # HedgeDoc successful user registration can be fingerprint by an HTTP/302 to the root
        # and a Cookie `connect.sid`
        #
        if res.status_code != requests.codes["ok"]:
            print(f"bad response code {res.status_code}")
            return False

        cookie = res.headers.get("Set-Cookie", "").lower()
        if not cookie.startswith("connect.sid"):
            print(f"missing cookie {res.status_code}")
            return False

        #
        # The registration is ok, the session is valid
        # Affect it to the instance
        #
        return self.login()

    def delete(self) -> bool:
        """Delete the current user, invalidate the session

        Returns:
            bool: true on success, false otherwise
        """
        if not self.logged_in:
            return False

        def get_nonce() -> str:
            """Retrieve the delete `nonce` hidden in <a> tag"""
            assert self.session
            response = self.session.get(
                f"{self.url}/",
                allow_redirects=False,
                timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
            )
            if response.status_code != requests.codes["ok"]:
                return ""

            text = response.text
            text = text[text.find("/me/delete/") + 11 :]
            return text[: text.find('"')]

        assert self.session
        nonce = get_nonce()

        response = self.session.get(
            f"{self.url}/me/delete/{nonce}",
            allow_redirects=False,
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )

        #
        # On successful user delete, expect HTTP/302 + a new `connect.sid` cookie
        #
        if response.status_code != requests.codes["found"]:
            return False

        if "set-cookie" not in response.headers:
            return False

        if not response.headers["set-cookie"].lower().startswith("connect.sid"):
            return False

        self.session.close()
        self.session = None
        return True

    def login(self) -> bool:
        """Logs the current user in using the credentials of the instance. If the users is already logged in, just
        return successfully immediately.

        Returns:
            bool: true if logged in, false otherwise
        """
        if self.logged_in:
            return True

        sess = requests.Session()
        response = sess.post(
            f"{self.url}/login",
            data={
                "email": self.email,
                "password": self.password,
            },
            allow_redirects=True,
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )

        #
        # On success, expect HTTP/200 after redirect + new auth cookie
        #
        if response.status_code != requests.codes["ok"]:
            sess.close()
            return False

        #
        # Affect the session, and run a sanity check, get the user id
        #
        self.session = sess
        data = self.info()
        if not data or data.get("status", "") != "ok":
            print(f"login(): failed to get status: {data}")
            self.session.close()
            self.session = None
            return False

        username = data.get("name", "")
        if username != self.username:
            self.session.close()
            self.session = None
            print(
                f"login(): username mismatch: got {username}, expected {self.username}"
            )
            return False

        return True

    def logout(self) -> bool:
        """Logout the current user, invalidate the session

        Returns:
            bool: true if logged out, false otherwise
        """
        if not self.logged_in:
            return True

        assert self.session

        response = self.session.get(
            f"{self.url}/logout",
            allow_redirects=True,
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )

        #
        # Successful logout means HTTP OK
        #
        if response.status_code != requests.codes["ok"]:
            return False

        self.session.close()
        self.session = None
        return True

    def info(self) -> dict:
        """Returns the HedgeDoc info of the current user

        Returns:
            dict: _description_
        """
        if self.session:
            response = self.session.get(
                f"{self.url}/me",
                timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
            )
        else:
            response = requests.get(
                f"{self.url}/me",
                timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
            )

        if response.status_code != requests.codes["ok"]:
            return {}

        data = response.json()
        return data

    def create_note(self) -> str:
        """ "Returns a unique note ID so that the note will be automatically created when accessed for the first time

        Returns:
            str: a string of the GUID for the new note
        """
        return f"/{uuid.uuid4()}"

    def note_exists(self, note_id) -> str:
        """ "Checks if a specific note exists from its ID.

        Args:
            id (str): the identifier to check

        Returns:
            bool: returns True if it exists
        """
        if not self.logged_in:
            self.login()
            assert self.logged_in

        assert self.session
        res = self.session.head(
            f"{self.url}/{note_id}",
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )
        return res.status_code == requests.codes["found"]

    def export_note(self, note_id: uuid.UUID) -> str:
        """Export a challenge note as string

        Args:
            note_id (uuid.UUID): the note id to export, usually the string of a GUID

        Raises:
            AttributeError: if not authenticated
            KeyError: if the note_id doesn't exist

        Returns:
            str: The body of the note if successful; an empty string otherwise
        """
        if not self.logged_in:
            if not self.login():
                raise AttributeError

        assert self.session
        response = self.session.get(
            f"{self.url}/{note_id}/download",
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )
        if response.status_code != requests.codes["ok"]:
            raise KeyError(f"Note {note_id} doesn't exist")

        return response.text


class CtfTime:
    url = "https://ctftime.org"
    api_events_url = f"{url}/api/v1/events"
    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:12.0) Gecko/20100101 Firefox/12.0"

    @staticmethod
    def team_url(team_id: int):
        if team_id < 0:
            return "#"
        return f"{CtfTime.url}/team/{team_id}"

    @staticmethod
    def event_url(event_id: int):
        return f"{CtfTime.url}/event/{event_id}"

    @lru_cache(maxsize=128)
    @staticmethod
    def event_logo_url(event_id: int):
        """_summary_

        Args:
            event_id (int): _description_

        Returns:
            _type_: _description_
        """
        default_logo = f"{settings.IMAGE_URL}/{settings.CTFHUB_DEFAULT_CTF_LOGO}"
        if not event_id:
            return default_logo

        try:
            ctf_info = CtfTime.fetch_ctf_info(event_id)
            logo: str = ctf_info.setdefault("logo", default_logo)
            _, ext = os.path.splitext(logo)
            if ext.lower() not in settings.CTFHUB_ACCEPTED_IMAGE_EXTENSIONS:
                return default_logo
        except (ValueError, RuntimeError):
            logo = default_logo
        return logo

    @lru_cache(maxsize=128)
    @staticmethod
    def fetch_ctf_info(ctf_id: int) -> dict[str, Any]:
        """Retrieve all the information for a specific CTF from CTFTime.

        Args:
            ctftime_id (int): CTFTime event ID

        Returns:
            dict: JSON output from CTFTime
        """
        response = requests.get(
            f"{CtfTime.api_events_url}/{ctf_id}/",
            headers={"user-agent": CtfTime.user_agent},
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )
        if response.status_code != requests.codes["ok"]:
            raise RuntimeError(
                f"CTFTime returned HTTP code {response.status_code} on {response.url} (expected {requests.codes['ok']}):"
                f"{response.reason}"
            )
        return response.json()

    @staticmethod
    def parse_date(date: str) -> datetime:
        """Parse a CTFTime date

        Args:
            date (str): the date to parse
        Returns:
            datetime: the date object or "" if there was a parsing error
        """
        return datetime.strptime(date[:19], "%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def ctfs(running=True, future=True) -> list:
        """Return CTFs that are currently running and starting in the next 6 months.

        Returns:
            list: current and future CTFs
        """
        ctfs = CtfTime.fetch_ctfs()
        now = datetime.now()

        result = []
        for ctf in ctfs:
            start = ctf["start"]
            finish = ctf["finish"]

            assert isinstance(start, datetime) and isinstance(finish, datetime)
            if running and start < now < finish:
                result.append(ctf)
            if future and now < start < finish:
                result.append(ctf)

        return result

    @staticmethod
    def fetch_ctfs(limit=100) -> list[dict[str, str | int | datetime]]:
        """Retrieve CTFs from CTFTime API with a wide start/finish window (-1/+26 weeks) so we can later run our own filters
        on the cached results for better performance and accuracy.

        Returns:
            list: JSON output from CTFTime
        """
        start = time.time() - (3600 * 24 * 60)
        end = time.time() + (3600 * 24 * 7 * 26)
        res = requests.get(
            f"{CtfTime.api_events_url}/?limit={limit}&start={start:.0f}&finish={end:.0f}",
            headers={"user-agent": CtfTime.user_agent},
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )
        if res.status_code != requests.codes["ok"]:
            raise RuntimeError(
                f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes['ok']}): {res.reason}"
            )

        result: list[dict[str, Union[str, int, datetime]]] = []
        for ctf in res.json():
            ctf["start"] = CtfTime.parse_date(ctf["start"])
            ctf["finish"] = CtfTime.parse_date(ctf["finish"])
            ctf["duration"] = ctf["finish"] - ctf["start"]
            result.append(ctf)

        return result


@lru_cache(maxsize=1)
def get_current_site() -> str:
    warnings.warn("get_current_site() is obsolete, use `settings.CTFHUB_URL`")
    return settings.CTFHUB_URL


@lru_cache(maxsize=1)
def which_hedgedoc() -> str:
    """OBSOLETE FUNCTION
    Returns the docker container hostname if the default URL from the config is not accessible.
    This is so that ctfhub works out of the box with `docker-compose up` as most people wanting to
    trial it out won't bother changing the default values with public FQDN/IPs.

    Returns:
        str: the base HedgeDoc URL
    """
    warnings.warn("which_hedgedoc() is obsolete, use `helpers.HedgeDoc`")
    raise NotImplementedError


def create_new_note() -> str:
    """OBSOLETE FUNCTION: use the HedgeDoc() class"""
    warnings.warn("Obsolete function, do not use it")
    return f"/{uuid.uuid4()}"


def check_note_id(_: str) -> bool:
    """OBSOLETE FUNCTION
    Checks if a specific note exists from its ID.

    Args:
        id (str): the identifier to check

    Returns:
        bool: returns True if it exists
    """
    warnings.warn("check_note_id() is obsolete, use `helpers.HedgeDoc`")
    raise NotImplementedError


def get_file_magic(
    challenge_file: Union[io.BufferedReader, pathlib.Path], use_mime: bool = False
) -> str:
    """
    Returns the file description from its magic number (ex. 'PE32+ executable (console) x86-64, for MS Windows' ), or a
    MIME type if `use_mime` is True

    Args:
        challenge_file: File-like object or a pathlib.Path
        use_mime: specifies whether to get the output string as a MIME type

    Raises:
        TypeError if `challenge_file` has an invalid type

    Returns:
        str: the file description, or "" if the file doesn't exist on FS
    """

    if isinstance(challenge_file, io.BufferedReader):
        challenge_file.seek(0)
        challenge_file_data = challenge_file.read()
    elif isinstance(challenge_file, pathlib.Path):
        challenge_file_data = challenge_file.open("rb").read()
    else:
        raise TypeError("Invalid type for `challenge_file`")

    try:
        return magic.from_buffer(challenge_file_data, mime=use_mime)
    except (ValueError, magic.MagicException):
        return "Data" if not use_mime else "application/octet-stream"


def get_file_mime(challenge_file: Union[io.BufferedReader, pathlib.Path]) -> str:
    """
    Returns the mime type associated to the file (ex. 'appication/pdf')

    Args:
        challenge_file: File-like object

    Returns:
        str: the file mime type, or "application/octet-stream" if the file doesn't exist on FS
    """
    return get_file_magic(challenge_file, True)


def send_mail(recipients: list[str], subject: str, body: str) -> bool:
    """Wrapper to easily send an email

    Args:
        recipients (list): [description]
        subject (str): [description]
        body (str): [description]

    Returns:
        bool: [description]
    """
    if (
        settings.EMAIL_HOST
        and settings.EMAIL_HOST_USER
        and settings.EMAIL_HOST_PASSWORD
    ):
        try:
            django.core.mail.send_mail(
                subject, body, settings.EMAIL_HOST_USER, recipients, fail_silently=False
            )
            return True
        except smtplib.SMTPException:
            pass
    return False


def get_random_string_64() -> str:
    """Convenience wrapper to generate 64 char string

    Returns:
        str: [description]
    """
    return django.utils.crypto.get_random_string(64)


def get_random_string_128() -> str:
    """Convenience wrapper to generate 128 char string

    Returns:
        str: [description]
    """
    return django.utils.crypto.get_random_string(128)


def generate_excalidraw_room_id() -> str:
    """Convenience wrapper to generate an excalidraw room id

    Returns:
        str: [description]
    """
    return django.utils.crypto.get_random_string(
        settings.EXCALIDRAW_ROOM_ID_LENGTH,
        allowed_chars=settings.EXCALIDRAW_ROOM_ID_CHARSET,
    )


def generate_excalidraw_room_key() -> str:
    """Convenience wrapper to generate an excalidraw room id

    Returns:
        str: [description]
    """
    return django.utils.crypto.get_random_string(
        settings.EXCALIDRAW_ROOM_KEY_LENGTH,
        allowed_chars=settings.EXCALIDRAW_ROOM_KEY_CHARSET,
    )


def discord_send_message(json_data: dict) -> bool:
    """Send a notification on a Discord channel

    Args:
        js (dict): The JSON data to pass to the webhook. See https://discord.com/developers/docs/resources/channel for
        details

    Raises:
        Exception: [description]

    Returns:
        bool: True if a message was successfully sent, False in any other cases
    """
    if not settings.DISCORD_WEBHOOK_URL:
        return False

    try:
        response = requests.post(
            settings.DISCORD_WEBHOOK_URL,
            json=json_data,
            timeout=settings.CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
        )
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Incorrect response, got {response.status_code}")

    except (RuntimeError, requests.exceptions.Timeout):
        return False

    return True


def generate_github_page_header(**kwargs) -> str:
    """Create a default GithubPages header.

    Args:
        kwargs (dict): [description]

    Returns:
        str: A default header to be used in GithubPages
    """
    title = kwargs.setdefault("title", "Exported note")
    author = kwargs.setdefault("author", "Anonymous")
    tags = kwargs.setdefault("tags", "[]")
    date = kwargs.setdefault("date", datetime.now()).strftime("%Y-%m-%d %H:%M %Z")
    content = f"""---
layout: post
title: {title}
author: {author}
tags: {tags}
date: {date}
---

"""
    return content


def get_named_storage(name: str) -> Any:
    config = settings.STORAGES[name]
    storage_class = get_storage_class(config["BACKEND"])
    return storage_class(**config["OPTIONS"])


def get_challenge_upload_path(instance: "ChallengeFile", filename: str) -> str:
    """Custom helper to retrieve the upload path for a given challenge file.

    Args:
        instance (ChallengeFile): _description_
        filename (str): _description_

    Returns:
        str: _description_
    """
    return f"files/{instance.challenge.id}/{filename}"
