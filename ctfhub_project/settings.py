import os
from pathlib import Path


def get_boolean(key: str) -> bool:
    return os.getenv(key) in ("1", "True", "true", True)


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = (
    os.getenv("CTFHUB_SECRET_KEY")
    or "ow#8y081ih3nunjqh)u^ug)ln_$xri3-upt^e)7h)&l$05-7tf"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_boolean("CTFHUB_DEBUG") or False
PROJECT_VERSION: float = 0.1
PROJECT_URL = "https://github.com/hugsy/ctfhub"

CTFHUB_PROTOCOL = os.getenv("CTFHUB_PROTOCOL") or "http"
CTFHUB_DOMAIN = os.getenv("CTFHUB_DOMAIN") or "localhost"
CTFHUB_PORT = os.getenv("CTFHUB_PORT") or "8000"
CTFHUB_USE_SSL = CTFHUB_PROTOCOL == "https" or False
CTFHUB_URL = (
    os.getenv("CTFHUB_URL") or f"{CTFHUB_PROTOCOL}://{CTFHUB_DOMAIN}:{CTFHUB_PORT}"
)

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

ALLOWED_HOSTS = [
    CTFHUB_DOMAIN,
] + os.getenv(
    "CTFHUB_ALLOWED_HOSTS", ""
).split(";")
CSRF_TRUSTED_ORIGINS = [
    CTFHUB_URL,
] + os.getenv(
    "CTFHUB_TRUSTED_ORIGINS", ""
).split(";")

CSRF_COOKIE_NAME = "ctfhub-csrf"
SESSION_COOKIE_NAME = "ctfhub-session"

# Application definition

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sites",
    "model_utils",
    "django_sendfile",
    "ctfhub",
]

SITE_ID = 1


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ctfhub_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "ctfhub.context_processors.add_debug_context",
                "ctfhub.context_processors.add_timezone_context",
            ],
        },
    },
]

WSGI_APPLICATION = "ctfhub_project.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': BASE_DIR / 'db.sqlite3',
    # }
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.getenv("CTFHUB_DB_NAME") or "ctfhub",
        "USER": os.getenv("CTFHUB_DB_USER") or "ctfhub",
        "PASSWORD": os.getenv("CTFHUB_DB_PASSWORD") or "ctfhub",
        "HOST": os.getenv("CTFHUB_DB_HOST") or "localhost",
        "PORT": os.getenv("CTFHUB_DB_PORT") or "5432",
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = False

STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/uploads/"
MEDIA_ROOT = BASE_DIR / "uploads/"

IMAGE_URL = f"{STATIC_URL}images/"
IMAGE_ROOT = BASE_DIR / "static/images"

CTF_CHALLENGE_FILE_URL = "/uploads/files/"
CTF_CHALLENGE_FILE_PATH = "files/"
CTF_CHALLENGE_FILE_ROOT = MEDIA_ROOT / CTF_CHALLENGE_FILE_PATH

USERS_FILE_URL = "/uploads/media/"
USERS_FILE_PATH = "media/"
USERS_FILE_ROOT = MEDIA_ROOT / USERS_FILE_PATH

STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        "OPTIONS": {
            "location": str(BASE_DIR / "static"),
            "base_url": "/static/",
        },
    },
    "MEDIA": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": str(BASE_DIR / "uploads"),
            "base_url": "/uploads/",
        },
    },
    "CHALLENGE_FILES": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": str(BASE_DIR / "uploads" / "files"),
            "base_url": "/uploads/files/",
        },
    },
    "USER_FILES": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": str(BASE_DIR / "uploads" / "media"),
            "base_url": "/uploads/media/",
        },
    },
}

SENDFILE_BACKEND = "django_sendfile.backends.simple"
SENDFILE_ROOT = str(BASE_DIR / "uploads/files")

HEDGEDOC_URL = os.getenv("CTFHUB_HEDGEDOC_URL", "")

LOGIN_URL = "ctfhub:user-login"
LOGIN_REDIRECT_URL = "ctfhub:dashboard"
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
CHALLENGE_FILE_MAX_SIZE = FILE_UPLOAD_MAX_MEMORY_SIZE

FIRST_DAY_OF_WEEK = 1
SHORT_DATE_FORMAT = "Y-m-d"
SHORT_DATETIME_FORMAT = "Y-m-d P"

CTFHUB_DEFAULT_CTF_LOGO = "blank-ctf.png"
CTFHUB_ACCEPTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".gif", ".bmp")

CTFHUB_DEFAULT_COUNTRY_LOGO = "blank.png"

# EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
# EMAIL_FILE_PATH = MEDIA_ROOT / "email_sent"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("CTFHUB_EMAIL_SERVER_HOST") or None
EMAIL_PORT = os.getenv("CTFHUB_EMAIL_SERVER_PORT") or 587
EMAIL_USE_TLS = os.getenv("CTFHUB_EMAIL_SERVER_USE_TLS") or True
EMAIL_HOST_USER = os.getenv("CTFHUB_EMAIL_USERNAME") or None
EMAIL_HOST_PASSWORD = os.getenv("CTFHUB_EMAIL_PASSWORD") or None
EMAIL_SUBJECT_PREFIX = "[CTFHub] "


# Jistsi integration

JITSI_URL = os.getenv("CTFHUB_JITSI_URL") or "https://meet.jit.si"


# Discord integration

DISCORD_WEBHOOK_URL = os.getenv("CTFHUB_DISCORD_WEBHOOK_URL") or None
DISCORD_BOT_NAME = os.getenv("CTFHUB_DISCORD_BOT_NAME") or "SpiderBot"

CHARSET_HEXA_LOWER = "abcdef0123456789"
CHARSET_HEXA_UPPER = "ABCDEF0123456789"
CHARSET_HEXA_MIXED = "abcdefABCDEF0123456789"
CHARSET_ALNUM_LOWER = "abcdefghijklmnopqrstuvwxyz0123456789"
CHARSET_ALNUM_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CHARSET_ALNUM_MIXED = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Excalidraw integration
EXCALIDRAW_URL = os.getenv("CTFHUB_EXCALIDRAW_URL") or "https://excalidraw.com"
EXCALIDRAW_ROOM_ID_REGEX = "[0-9a-f]{20}"
EXCALIDRAW_ROOM_KEY_REGEX = "[a-zA-Z0-9_-]{22}"
EXCALIDRAW_ROOM_ID_CHARSET = CHARSET_HEXA_LOWER
EXCALIDRAW_ROOM_ID_LENGTH = 20
EXCALIDRAW_ROOM_KEY_CHARSET = CHARSET_ALNUM_MIXED + "_-"
EXCALIDRAW_ROOM_KEY_LENGTH = 22

CTFHUB_HTTP_REQUEST_DEFAULT_TIMEOUT = 10
