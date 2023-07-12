from collections import namedtuple
from typing import TYPE_CHECKING, Any

import bleach
from django import template
from django.utils.safestring import mark_safe

if TYPE_CHECKING:
    from ctfhub.models import Challenge

register = template.Library()


@register.simple_tag
def best_category(member, year=None):
    return member.best_category(year)


@register.filter
def as_time_accumulator_graph(items: list["Challenge"]):
    Point = namedtuple("Point", "time accu")
    accu = 0
    res: list[Point] = []
    for item in items:
        accu += item.points
        res.append(Point(item.solved_time, accu))
    return res


@register.simple_tag(takes_context=True)
def theme_cookie(context: dict[str, Any]):
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
def as_tick_or_cross(is_on: bool):
    if is_on:
        return mark_safe(
            """<strong><i class="fas fa-check" style="color: green;"></i><strong>"""
        )

    return mark_safe(
        """<strong><i class="fas fa-times" style="color: red;"></i><strong>"""
    )
