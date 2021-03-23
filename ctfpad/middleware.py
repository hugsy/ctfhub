
from django.utils import timezone
from datetime import timedelta, timezone as tz

# https://docs.djangoproject.com/en/3.1/topics/i18n/timezones/#selecting-the-current-time-zone
class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            timezone.activate(tz(request.user.member.timezone_offset))
        else:
            timezone.deactivate()
        return self.get_response(request)