# Generated by Django 4.2.2 on 2023-06-30 21:06

import ctfhub.helpers
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ctfhub", "0019_alter_challenge_note_id_alter_ctf_note_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="hedgedoc_password",
            field=models.CharField(
                default=ctfhub.helpers.get_random_string_64,
                editable=False,
                max_length=64,
            ),
        ),
    ]
