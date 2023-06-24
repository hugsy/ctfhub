import random, datetime

from django.db.models.signals import post_save
from django.dispatch import receiver

from ctfpad.models import Challenge, Ctf
from ctfpad.helpers import discord_send_message, get_current_site
from ctftools.settings import DISCORD_BOT_NAME

# formatted with the ctf name
NEW_CTF_MESSAGES = [
    "New CTF added ! `{}` 💻 ",
    "CTF `{}` added 🏳  ! Warm your keyboards ⌨ ",
    "Yay another CTF ! `{}` is on ! Book your weekends, stock up beers and junk food... Let's do this 🤓",
    "Alright stop, collaborate on `{}` and listen... 🎶",
    "99 CTF on the wall, 99 CTF. Take `{}` down, pass it around, 98 CTF on the wall... 🍺",
    "Brace yourselves, `{}` is coming... 🐺",
    "`$ sudo apt-get install '{}'` 💻",
]

# formatted with the challenge name
SCORED_FLAG_MESSAGES = [
    "Flag scored for `{}`! 🎺",
    "Jackpot on `{}`! Another flag 🏳",
    "You get a flag, you get a flag, everybody gets a flag ! `{}` was just scored...",
    "RIP `{}` 🎃, we own you!",
]


@receiver(post_save, sender=Ctf, dispatch_uid="ctf_create_notify_discord")
def discord_notify_ctf_creation(
    sender, instance: Ctf, created: bool, **kwargs: dict
) -> bool:
    if not created:
        return False

    if instance.visibility != "public":
        return False

    root = get_current_site()
    url = f"{root}{instance.get_absolute_url()}"
    msg = random.choice(NEW_CTF_MESSAGES).format(instance.name)
    date_and_time = (
        f"Permanent CTF"
        if instance.is_permanent
        else f"Date: {instance.start_date} - {instance.end_date}"
    )
    defaults = {
        "username": DISCORD_BOT_NAME,
        "content": msg,
        "embeds": [
            {
                "url": url,
                "description": f"""
`{instance.created_by.username}` added the team for `{instance.name}`!
{date_and_time}
Link: [{url}]({url})
""",
            }
        ],
    }
    data = kwargs.setdefault("json", defaults)
    return discord_send_message(data)


@receiver(post_save, sender=Challenge, dispatch_uid="discord_notify_scored_challenge")
def discord_notify_scored_challenge(
    sender, instance: Challenge, created: bool, **kwargs: dict
) -> bool:
    if created:
        return False

    if instance.ctf.visibility != "public":
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
    msg = random.choice(SCORED_FLAG_MESSAGES).format(instance.name)
    points = f"{instance.points} "
    points += "points" if instance.points > 1 else "point"
    js = {
        "username": DISCORD_BOT_NAME,
        "content": msg,
        "embeds": [
            {
                "url": challenge_url,
                "description": f"""
`{instance.last_update_by.username}` scored {points} with `{instance.name}` (ctf:[`{instance.ctf.name}`]({ctf_url}), category:`{instance.category.name}`)!

Flag: `{instance.flag}`
""",
            }
        ],
    }
    return discord_send_message(js)
