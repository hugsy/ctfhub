from datetime import datetime, timedelta
from django import template
from django.contrib import messages

register = template.Library()

@register.filter
def as_local_datetime_for_member(utc_timezone, member):
    return utc_timezone +  member.timezone_offset


@register.simple_tag(takes_context = True)
def theme_cookie(context):
    request = context['request']
    value = request.COOKIES.get('theme', 'light')
    return value
