# Generated by Django 3.1.4 on 2021-01-02 11:39

import model_utils.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ctfhub", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ctf",
            name="weight",
            field=models.FloatField(default=1),
        ),
        migrations.AlterField(
            model_name="member",
            name="country",
            field=model_utils.fields.StatusField(
                choices=[(0, "dummy")],
                default="Afghanistan",
                max_length=100,
                no_check_for_status=True,
            ),
        ),
    ]
