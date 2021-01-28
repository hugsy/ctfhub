import random, datetime

from django.db.models.signals import post_save
from django.dispatch import receiver

from ctfpad.models import Challenge, Ctf
from ctfpad.helpers import discord_send_message, get_current_site
from ctftools.settings import (
    DISCORD_BOT_NAME
)


NEW_CTF_MESSAGES = [
    f"New CTF added ! 💻 ",
    f"New CTF 🏳  ! Warm your keyboards ⌨ ",
    f"Yay another CTF ! Book your weekends, stock up beers and junk food... Let's do this 🤓",
]



@receiver(post_save, sender=Ctf, dispatch_uid="ctf_create_notify_discord")
def discord_notify_ctf_creation(sender, instance: Ctf, created: bool, **kwargs: dict) -> bool:
    if not created:
        return False

    root = get_current_site()
    url = f"{root}{instance.get_absolute_url()}"
    defaults = {
        "username": DISCORD_BOT_NAME,
        "content": random.choice(NEW_CTF_MESSAGES),
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



SCORED_FLAG_MESSAGES = [
    "Flag scored! 🎺",
    "Jackpot! Another flag 🏳",
    "You get a flag, you get a flag, everybody gets a flag !",
]

@receiver(post_save, sender=Challenge, dispatch_uid="discord_notify_scored_challenge")
def discord_notify_scored_challenge(sender, instance: Challenge, created: bool, **kwargs: dict) -> bool:
    if created:
        return False

    if not instance.flag:
        return False

    if not instance.flag_tracker.has_changed("flag"):
        return False

    # HACK check if the flag was scored "recently"
    if datetime.datetime.now() - instance.solved_time >= datetime.timedelta(seconds=1):
        return False

    root = get_current_site()
    ctf_url = f"{root}{instance.ctf.get_absolute_url()}"
    challenge_url = f"{root}{instance.get_absolute_url()}"
    points = f"{instance.points} "
    points += "points" if instance.points > 1 else "point"
    js = {
        "username": DISCORD_BOT_NAME,
        "content": random.choice(SCORED_FLAG_MESSAGES),
        "embeds": [{
            "url": challenge_url,
            "description": f"""
`{instance.last_update_by.username}` scored {points} with `{instance.name}` (ctf:[`{instance.ctf.name}`]({ctf_url}), category:`{instance.category.name}`)!

Flag: `{instance.flag}`
""",
    }]}
    return discord_send_message(js)
