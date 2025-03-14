import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from ffjournal.models import TrendingUpPlayer, TrendingDownPlayer
from django.db import transaction

class Command(BaseCommand):
    help = 'Fetch trending up and down players from Sleeper API and update database'

    def process_trending_players(self, url, model):
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        updated_count = 0
        created_count = 0
        for item in data:
            player_id = item['player_id']
            count = item['count']
            
            obj, created = model.objects.update_or_create(
                player_id=player_id,
                defaults={
                    'count': count,
                    'created_at': timezone.now()
                }
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1

            self.stdout.write(f"Processed {model.__name__}: player_id={player_id}, count={count}, created={created}")

        # Remove old entries not in the current data
        current_player_ids = [item['player_id'] for item in data]
        deleted_count = model.objects.exclude(player_id__in=current_player_ids).delete()[0]

        return updated_count, created_count, deleted_count

    def handle(self, *args, **options):
        trending_up_url = "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=24&limit=50"
        trending_down_url = "https://api.sleeper.app/v1/players/nfl/trending/drop?lookback_hours=24&limit=50"
        
        try:
            with transaction.atomic():
                # Process trending up players
                up_updated, up_created, up_deleted = self.process_trending_players(trending_up_url, TrendingUpPlayer)
                
                # Process trending down players
                down_updated, down_created, down_deleted = self.process_trending_players(trending_down_url, TrendingDownPlayer)

            self.stdout.write(self.style.SUCCESS(
                f'Successfully processed trending players:\n'
                f'Trending Up - Updated: {up_updated}, Created: {up_created}, Deleted: {up_deleted}\n'
                f'Trending Down - Updated: {down_updated}, Created: {down_created}, Deleted: {down_deleted}'
            ))

            # Verify the data in the database
            self.stdout.write("Top 5 Trending Up Players:")
            for player in TrendingUpPlayer.objects.order_by('-count')[:5]:
                self.stdout.write(f"Player in DB: player_id={player.player_id}, count={player.count}")

            self.stdout.write("Top 5 Trending Down Players:")
            for player in TrendingDownPlayer.objects.order_by('-count')[:5]:
                self.stdout.write(f"Player in DB: player_id={player.player_id}, count={player.count}")

        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching data from Sleeper API: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred: {e}'))
