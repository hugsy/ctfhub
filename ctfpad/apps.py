from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class CtfpadConfig(AppConfig):
    name = 'ctfpad'
    verbose_name = _('ctfpad')

    def ready(self):
        import ctfpad.signals
