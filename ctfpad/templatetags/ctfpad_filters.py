from datetime import datetime, timedelta
from django import template
from django.contrib import messages
from collections import namedtuple

register = template.Library()

@register.filter
def as_local_datetime_for_member(utc_timezone, member):
    return utc_timezone +  member.timezone_offset


@register.filter
def as_time_accumulator_graph(items):
    Point = namedtuple("Point", "time accu")
    accu = 0
    res = []
    for x in items:
        accu += x.points
        res.append( Point(x.solved_time, accu) )
    return res


@register.simple_tag(takes_context = True)
def theme_cookie(context):
    request = context['request']
    value = request.COOKIES.get('theme', 'light')
    if value not in ('light', 'dark'):
        value = 'light'
    return value
