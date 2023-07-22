from typing import TYPE_CHECKING
from django.core.exceptions import ValidationError

from ctfhub_project.settings import CHALLENGE_FILE_MAX_SIZE

if TYPE_CHECKING:
    from django.core import files


def challenge_file_max_size_validator(value: "files.File"):
    if value.size > CHALLENGE_FILE_MAX_SIZE:
        raise ValidationError(
            f"File too large. Size should not exceed {CHALLENGE_FILE_MAX_SIZE}B."
        )
