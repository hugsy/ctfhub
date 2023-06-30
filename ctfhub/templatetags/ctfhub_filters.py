from collections import namedtuple
from django import template
from django.utils.safestring import mark_safe
import bleach

register = template.Library()


@register.simple_tag
def best_category(member, year=None):
    return member.best_category(year)


@register.filter
def as_time_accumulator_graph(items):
    Point = namedtuple("Point", "time accu")
    accu = 0
    res = []
    for x in items:
        accu += x.points
        res.append(Point(x.solved_time, accu))
    return res


@register.simple_tag(takes_context=True)
def theme_cookie(context):
    request = context["request"]
    value = request.COOKIES.get("theme", "light")
    if value not in ("light", "dark"):
        value = "light"
    return value


@register.filter
def html_sanitize(html: str) -> str:
    """Only authorize links (a tags) html. Escape the rest

    Args:
        html ([type]): [description]

    Returns:
        [type]: [description]
    """
    return bleach.linkify(
        bleach.clean(
            html,
            tags=["a", "br", "hr"],
            protocols=["http", "https"],
            strip=True,
        )
    )


@register.filter(is_safe=True, needs_autoescape=False)
def as_tick_or_cross(b: bool):
    if b:
        return mark_safe(
            """<strong><i class="fas fa-check" style="color: green;"></i><strong>"""
        )
    else:
        return mark_safe(
            """<strong><i class="fas fa-times" style="color: red;"></i><strong>"""
        )
