# Generated by Django 5.0.3 on 2024-09-10 08:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ffjournal', '0015_remove_trendingupplayer_player_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='consenter_ids',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
