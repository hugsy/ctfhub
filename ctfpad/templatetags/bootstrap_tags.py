from django import template
from django.contrib import messages
from django.template.defaultfilters import stringfilter

from collections import namedtuple

register = template.Library()



@register.filter
def as_bootstrap_alert(msg):
    return msg


