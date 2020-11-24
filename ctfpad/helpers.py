from datetime import datetime
from time import time
from django.utils.crypto import get_random_string
import magic
import os
import pathlib
import requests
import smtplib

from functools import lru_cache
from uuid import uuid4

from ctftools.settings import (
    CTFPAD_ACCEPTED_IMAGE_EXTENSIONS,
    CTFPAD_DEFAULT_CTF_LOGO,
    HEDGEDOC_URL,
    STATIC_URL,
    CTFTIME_API_EVENTS_URL,
    CTFTIME_USER_AGENT,
    EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD,
)


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
        f'{HEDGEDOC_URL}/register',
        data={'email': username, 'password': password},
        allow_redirects = False
    )

    if res.status_code != requests.codes.found:
        return False

    return True


def create_new_note() -> str:
    """"Returns a unique note ID so that the note will be automatically created when accessed for the first time

    Returns:
        str: the string ID of the new note
    """
    return f"/{uuid4()}"


def check_note_id(id: str) -> bool:
    """"Checks if a specific note exists from its ID.

    Args:
        id (str): the identifier to check

    Returns:
        bool: returns True if it exists
    """
    res = requests.head( f"{HEDGEDOC_URL}/{id}" )
    return res.status_code == requests.codes.found


def get_file_magic(fpath: pathlib.Path) -> str:
    """Returns the file description from its magic number (ex. 'PE32+ executable (console) x86-64, for MS Windows' )

    Args:
        fpath (pathlib.Path): path object to the file

    Returns:
        str: the file description, or "" if the file doesn't exist on FS
    """
    abspath = str(fpath.absolute())
    return magic.from_file(abspath) if fpath.exists() else "Data"


def get_file_mime(fpath: pathlib.Path) -> str:
    """Returns the mime type associated to the file (ex. 'appication/pdf')

    Args:
        fpath (pathlib.Path): path object to the file

    Returns:
        str: the file mime type, or "application/octet-stream" if the file doesn't exist on FS
    """
    abspath = str(fpath.absolute())
    return magic.from_file(abspath, mime=True) if fpath.exists() else "application/octet-stream"


def ctftime_parse_date(date: str) -> datetime:
    """Parse a CTFTime date

    Args:
        date (str): the date to parse
    Returns:
        datetime: the date object or "" if there was a parsing error
    """
    try:
        return datetime.strptime(date[:19], "%Y-%m-%dT%H:%M:%S")
    except:
        return ""


@lru_cache(maxsize=128)
def ctftime_fetch_running_ctf_data(limit=100) -> list:
    """Retrieve the currently running CTFs from CTFTime API. I couldn't do this by only using the CTFTime API.

    Returns:
        list: JSON output from CTFTime
    """
    try:
        res = requests.get(f"{CTFTIME_API_EVENTS_URL}?limit={limit}&start={time()-(3600*24*7):.0f}&finish={time()+(3600*24*7):.0f}",
            headers={"user-agent": CTFTIME_USER_AGENT})
        if res.status_code != requests.codes.ok:
            raise RuntimeError(f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}")
        result = []
        for ctf in res.json():
            start, finish, now = ctftime_parse_date(ctf["start"]), ctftime_parse_date(ctf["finish"]), now
            if start < now and finish > now:
                result.append(ctf)
    except Exception:
        result = []
    return result



@lru_cache(maxsize=128)
def ctftime_fetch_next_ctf_data() -> list:
    """Retrieve upcoming CTFs from CTFTime API

    Returns:
        list: JSON output from CTFTime
    """
    try:
        res = requests.get(CTFTIME_API_EVENTS_URL, headers={"user-agent": CTFTIME_USER_AGENT})
        if res.status_code != requests.codes.ok:
            raise RuntimeError(f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}")
        result = res.json()
    except Exception:
        result = []
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
    res = requests.get(url, headers={"user-agent": CTFTIME_USER_AGENT})
    if res.status_code != requests.codes.ok:
        raise RuntimeError(f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}")
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
    default_logo = f"{STATIC_URL}/images/{CTFPAD_DEFAULT_CTF_LOGO}"
    try:
        ctf_info = ctftime_get_ctf_info(ctftime_id)
        logo = ctf_info.setdefault("logo", default_logo)
        _, ext = os.path.splitext(logo)
        if ext.lower() not in CTFPAD_ACCEPTED_IMAGE_EXTENSIONS:
            return default_logo
    except:
        logo = default_logo
    return logo



def send_mail(recipients: list, subject: str, body: str) -> bool:
    """[summary]

    Args:
        recipients (list): [description]
        subject (str): [description]
        body (str): [description]

    Returns:
        bool: [description]
    """
    if EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
        try:
            send_mail(
                subject,
                body,
                EMAIL_HOST_USER,
                recipients,
                fail_silently = False
            )
            return True
        except smtplib.SMTPException:
            pass
    return False



def get_random_string_64() -> str:
    return get_random_string(64)


def get_random_string_128() -> str:
    return get_random_string(128)
