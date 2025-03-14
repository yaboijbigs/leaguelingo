from django.core.management.base import BaseCommand
from ffjournal.models import League
from ffjournal.sleeper_api import (
    fetch_league_data,
    fetch_roster_data,
    fetch_team_data,
    fetch_all_matchup_data,
    fetch_all_transactions_data,
)
from django.db import transaction

class Command(BaseCommand):
    help = 'Refresh all league data'

    def handle(self, *args, **kwargs):
        leagues = League.objects.all()
        for league in leagues:
            try:
                with transaction.atomic():
                    fetch_league_data(league.sleeper_league_id)
                    if league.status != 'complete':
                        fetch_roster_data(league.sleeper_league_id)
                        fetch_team_data(league.sleeper_league_id)
                        fetch_all_matchup_data(league.sleeper_league_id)
                        fetch_all_transactions_data(league.sleeper_league_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully refreshed league {league.name}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error refreshing league {league.name}: {str(e)}"))
