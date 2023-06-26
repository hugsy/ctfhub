from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CtfhubConfig(AppConfig):
    name = "ctfhub"
    verbose_name = _("ctfhub")

    def ready(self):
        pass
