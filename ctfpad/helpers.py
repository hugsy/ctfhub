import pathlib
import magic
import requests

from ctftools.settings import (
    CODIMD_URL,
    CTFTIME_API_EVENTS_URL,
)


def create_new_note() -> str:
    """"Connects to CodiMD to create a new note, and returns its ID

    Returns:
        str: the string ID of the new note
    """
    s = requests.Session()
    res = s.get(f"{CODIMD_URL}/new", allow_redirects=False)
    if res.status_code != requests.codes.found:
        raise RuntimeError(f"CodiMD service returned HTTP code {res.status_code} (expected {requests.codes.found}): {res.reason}")
    location = res.headers["location"]
    res = s.get(f"{CODIMD_URL}{location}")
    if res.status_code != requests.codes.ok:
        raise RuntimeError(f"CodiMD service returned HTTP code {res.status_code} (expected {requests.codes.ok}): {res.reason}")
    return  location


def check_note_id(id: str) -> bool:
    """"Checks if a specific note exists from its ID.

    Args:
        id (str): the identifier to check

    Returns:
        bool: returns True if it exists
    """
    res = requests.head( f"{CODIMD_URL}/{id}" )
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
