# Generated by Django 5.0.3 on 2024-09-10 07:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ffjournal', '0014_remove_trendingdownplayer_player_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trendingupplayer',
            name='player',
        ),
        migrations.AddField(
            model_name='trendingupplayer',
            name='player_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
