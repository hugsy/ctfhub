from django.core.exceptions import ValidationError

from ctfhub_project.settings import CHALLENGE_FILE_MAX_SIZE


def challenge_file_max_size_validator(value):
    if value.size > CHALLENGE_FILE_MAX_SIZE:
        raise ValidationError(
            f"File too large. Size should not exceed {CHALLENGE_FILE_MAX_SIZE}B."
        )
