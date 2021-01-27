from django.db.models.signals import post_save
from django.dispatch import receiver

from ctfpad.models import Ctf
from ctfpad.helpers import discord_send_message, get_current_site
from ctftools.settings import (
    DISCORD_BOT_NAME
)


@receiver(post_save, sender=Ctf, dispatch_uid="ctf_create_notify_discord")
def discord_notify_ctf_creation(sender, instance: Ctf, created: bool, **kwargs: dict) -> bool:
    if not created:
        return False

    root = get_current_site()
    url = f"{root}{instance.get_absolute_url()}"
    defaults = {
        "username": DISCORD_BOT_NAME,
        "content": f"New CTF added",
        "embeds": [{
            "url": url,
            "description": f"""
`{instance.created_by.username}` added the team for `{instance.name}`!
Date: {instance.start_date} - {instance.end_date}
Link: [{url}]({url})
""",
    }]}
    data = kwargs.setdefault("json", defaults)
    return discord_send_message(data)
