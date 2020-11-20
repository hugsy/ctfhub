import pathlib
import magic
import requests
import os

from functools import lru_cache
from uuid import uuid4

from ctftools.settings import (
    CTPAD_ACCEPTED_IMAGE_EXTENSIONS,
    HEDGEDOC_URL,
    CTFTIME_API_EVENTS_URL,
    CTFPAD_DEFAULT_CTF_LOGO, STATIC_URL,
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


@lru_cache(maxsize=128)
def ctftime_fetch_next_ctf_data() -> list:
    """Retrieve the next CTFs from CTFTime API

    Returns:
        list: JSON output of the upcoming CTFs of the output from CTFTime
    """
    try:
        res = requests.get(CTFTIME_API_EVENTS_URL, headers={"user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:12.0) Gecko/20100101 Firefox/12.0"})
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
        ctftime_id (int): [description]

    Returns:
        str: [description]
    """
    if ctftime_id == 0:
        return []
    try:
        url = f"{CTFTIME_API_EVENTS_URL}{ctftime_id}/"
        res = requests.get(url, headers={"user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:12.0) Gecko/20100101 Firefox/12.0"})
        if res.status_code != requests.codes.ok:
            raise RuntimeError(f"CTFTime service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}")
        result = res.json()
    except Exception:
        result = []
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
    ctf_info = ctftime_get_ctf_info(ctftime_id)
    logo = ctf_info.setdefault("logo", default_logo)
    _, ext = os.path.splitext(logo)
    if ext.lower() not in CTPAD_ACCEPTED_IMAGE_EXTENSIONS:
        return default_logo
    return logo
    return default_logo