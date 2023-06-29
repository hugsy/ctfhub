import io
import os
import pathlib
import smtplib
import time
import uuid
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Union

import django.core.mail
import django.utils.crypto
import magic
import requests
from django.conf import settings
from django.core.files.storage import get_storage_class

from ctfhub_project.settings import (
    CTFHUB_ACCEPTED_IMAGE_EXTENSIONS,
    CTFHUB_DEFAULT_CTF_LOGO,
    CTFHUB_DOMAIN,
    CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
    CTFHUB_PORT,
    CTFHUB_USE_SSL,
    CTFTIME_API_EVENTS_URL,
    CTFTIME_USER_AGENT,
    DISCORD_WEBHOOK_URL,
    EMAIL_HOST,
    EMAIL_HOST_PASSWORD,
    EMAIL_HOST_USER,
    EXCALIDRAW_ROOM_ID_CHARSET,
    EXCALIDRAW_ROOM_ID_LENGTH,
    EXCALIDRAW_ROOM_KEY_CHARSET,
    EXCALIDRAW_ROOM_KEY_LENGTH,
    HEDGEDOC_URL,
    IMAGE_URL,
    USE_INTERNAL_HEDGEDOC,
)

if TYPE_CHECKING:
    from ctfhub.models import ChallengeFile


@lru_cache(maxsize=1)
def get_current_site() -> str:
    r = "https://" if CTFHUB_USE_SSL else "http://"
    r += f"{CTFHUB_DOMAIN}:{CTFHUB_PORT}"
    return r


@lru_cache(maxsize=1)
def which_hedgedoc() -> str:
    """Returns the docker container hostname if the default URL from the config is not accessible.
    This is so that ctfhub works out of the box with `docker-compose up` as most people wanting to
    trial it out won't bother changing the default values with public FQDN/IPs.

    Returns:
        str: the base HedgeDoc URL
    """
    if USE_INTERNAL_HEDGEDOC:
        return "http://hedgedoc:3000"

    requests.get(HEDGEDOC_URL, timeout=CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT)
    return HEDGEDOC_URL


def register_new_hedgedoc_user(username: str, password: str) -> bool:
    """Register the member in hedgedoc. If fail, the member will be
    seen as anonymous.

    Args:
        username (str): member HedgeDoc username
        password (str): member HedgeDoc password

    Returns:
        bool: if the register action succeeded, returns True; False in any other cases
    """
    res = requests.post(
        which_hedgedoc() + "/register",
        data={"email": username, "password": password},
        allow_redirects=False,
    )

    if res.status_code != requests.codes.found:
        return False

    return True


def create_new_note() -> str:
    """ "Returns a unique note ID so that the note will be automatically created when accessed for the first time

    Returns:
        str: the string ID of the new note
    """
    return f"/{uuid.uuid4()}"


def check_note_id(id: str) -> bool:
    """ "Checks if a specific note exists from its ID.

    Args:
        id (str): the identifier to check

    Returns:
        bool: returns True if it exists
    """
    res = requests.head(f"{HEDGEDOC_URL}/{id}")
    return res.status_code == requests.codes.found


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
    except Exception:
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


def ctftime_parse_date(date: str) -> datetime:
    """Parse a CTFTime date

    Args:
        date (str): the date to parse
    Returns:
        datetime: the date object or "" if there was a parsing error
    """
    return datetime.strptime(date[:19], "%Y-%m-%dT%H:%M:%S")


def ctftime_ctfs(running=True, future=True) -> list:
    """Return CTFs that are currently running and starting in the next 6 months.

    Returns:
        list: current and future CTFs
    """
    ctfs = ctftime_fetch_ctfs()
    now = datetime.now()

    result = []
    for ctf in ctfs:
        start = ctf["start"]
        finish = ctf["finish"]

        if running and start < now < finish:
            result.append(ctf)
        if future and now < start < finish:
            result.append(ctf)

    return result


def ctftime_fetch_ctfs(limit=100) -> list:
    """Retrieve CTFs from CTFTime API with a wide start/finish window (-1/+26 weeks) so we can later run our own filters
    on the cached results for better performance and accuracy.

    Returns:
        list: JSON output from CTFTime
    """
    start = time.time() - (3600 * 24 * 60)
    end = time.time() + (3600 * 24 * 7 * 26)
    res = requests.get(
        f"{CTFTIME_API_EVENTS_URL}?limit={limit}&start={start:.0f}&finish={end:.0f}",
        headers={"user-agent": CTFTIME_USER_AGENT},
        timeout=CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
    )
    if res.status_code != requests.codes.ok:
        raise RuntimeError(
            f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}"
        )

    result = []
    for ctf in res.json():
        ctf["start"] = ctftime_parse_date(ctf["start"])
        ctf["finish"] = ctftime_parse_date(ctf["finish"])
        ctf["duration"] = ctf["finish"] - ctf["start"]
        result.append(ctf)

    return result


@lru_cache(maxsize=128)
def ctftime_get_ctf_info(ctftime_id: int) -> dict:
    """Retrieve all the information for a specific CTF from CTFTime.

    Args:
        ctftime_id (int): CTFTime event ID

    Returns:
        dict: JSON output from CTFTime
    """
    url = f"{CTFTIME_API_EVENTS_URL}{ctftime_id}/"
    res = requests.get(
        url,
        headers={"user-agent": CTFTIME_USER_AGENT},
        timeout=CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT,
    )
    if res.status_code != requests.codes.ok:
        raise RuntimeError(
            f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}"
        )
    result = res.json()
    return result


@lru_cache(maxsize=128)
def ctftime_get_ctf_logo_url(ctftime_id: int) -> str:
    """[summary]

    Args:
        ctftime_id (int): [description]

    Returns:
        str: [description]
    """
    default_logo = f"{IMAGE_URL}/{CTFHUB_DEFAULT_CTF_LOGO}"
    if ctftime_id != 0:
        try:
            ctf_info = ctftime_get_ctf_info(ctftime_id)
            logo = ctf_info.setdefault("logo", default_logo)
            _, ext = os.path.splitext(logo)
            if ext.lower() not in CTFHUB_ACCEPTED_IMAGE_EXTENSIONS:
                return default_logo
        except ValueError:
            logo = default_logo
        return logo
    return default_logo


def send_mail(recipients: list[str], subject: str, body: str) -> bool:
    """Wrapper to easily send an email

    Args:
        recipients (list): [description]
        subject (str): [description]
        body (str): [description]

    Returns:
        bool: [description]
    """
    if EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
        try:
            django.core.mail.send_mail(
                subject, body, EMAIL_HOST_USER, recipients, fail_silently=False
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
        EXCALIDRAW_ROOM_ID_LENGTH, allowed_chars=EXCALIDRAW_ROOM_ID_CHARSET
    )


def generate_excalidraw_room_key() -> str:
    """Convenience wrapper to generate an excalidraw room id

    Returns:
        str: [description]
    """
    return django.utils.crypto.get_random_string(
        EXCALIDRAW_ROOM_KEY_LENGTH, allowed_chars=EXCALIDRAW_ROOM_KEY_CHARSET
    )


def discord_send_message(js: dict) -> bool:
    """Send a notification on a Discord channel

    Args:
        js (dict): The JSON data to pass to the webhook. See https://discord.com/developers/docs/resources/channel for
        details

    Raises:
        Exception: [description]

    Returns:
        bool: True if a message was successfully sent, False in any other cases
    """
    if not DISCORD_WEBHOOK_URL:
        return False

    try:
        h = requests.post(DISCORD_WEBHOOK_URL, json=js)
        if h.status_code not in (200, 204):
            raise Exception(f"Incorrect response, got {h.status_code}")

    except Exception:
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


def export_challenge_note(member, note_id: uuid.UUID) -> str:
    """Export a challenge note. `member` is required for privilege requirements

    Args:
        member (Member): [description]
        note_id (uuid.UUID): [description]

    Returns:
        str: The body of the note if successful; an empty string otherwise
    """
    result = ""
    url = which_hedgedoc()
    print(url)
    with requests.Session() as session:
        h = session.post(
            f"{url}/login",
            data={
                "email": member.hedgedoc_username,
                "password": member.hedgedoc_password,
            },
            allow_redirects=False,
        )
        if h.status_code == requests.codes.ok:
            h2 = session.get(f"{url}{note_id}/download")
            if h2.status_code == requests.codes.ok:
                result = h2.text
            session.post(f"{url}/logout")
    return result


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
