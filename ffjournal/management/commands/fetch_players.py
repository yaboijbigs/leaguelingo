import requests
import logging
from django.core.management.base import BaseCommand
from ffjournal.models import Player, Roster, PlayerProjection, PlayerStats
from fantasy_rankings_scraper import scrape
from django.db.models import F

# Configure logging
logging.basicConfig(filename='fetch_players.log', level=logging.INFO, format='%(asctime)s - %(message)s')

class Command(BaseCommand):
    help = 'Fetch player data, update the database, and fetch player projections'

    def handle(self, *args, **kwargs):
        self.fetch_player_data()
        self.update_player_rankings()
        self.fetch_player_stats()
        self.fetch_player_projections()

    def fetch_player_data(self):
        url = "https://api.sleeper.app/v1/players/nfl"
        response = requests.get(url)
        
        if response.status_code == 200:
            players_data = response.json()
            
            players_to_create = []
            players_to_update = []

            for player_id, player_info in players_data.items():
                player_dict = {
                    'player_id': str(player_id),
                    'first_name': player_info.get('first_name'),
                    'last_name': player_info.get('last_name'),
                    'full_name': player_info.get('full_name'),
                    'position': player_info.get('position'),
                    'team': player_info.get('team'),
                    'age': player_info.get('age'),
                    'college': player_info.get('college'),
                    'status': player_info.get('status'),
                    'height': player_info.get('height'),
                    'weight': player_info.get('weight'),
                    'injury_status': player_info.get('injury_status'),
                    'injury_body_part': player_info.get('injury_body_part'),
                    'injury_start_date': player_info.get('injury_start_date'),
                    'injury_notes': player_info.get('injury_notes'),
                    'practice_participation': player_info.get('practice_participation'),
                    'practice_description': player_info.get('practice_description'),
                    'birth_date': player_info.get('birth_date'),
                    'birth_city': player_info.get('birth_city'),
                    'birth_state': player_info.get('birth_state'),
                    'birth_country': player_info.get('birth_country'),
                    'years_exp': player_info.get('years_exp'),
                    'high_school': player_info.get('high_school'),
                    'data': player_info
                }
                
                existing_player = Player.objects.filter(player_id=str(player_id)).first()

                if existing_player:
                    for key, value in player_dict.items():
                        setattr(existing_player, key, value)
                    players_to_update.append(existing_player)
                else:
                    players_to_create.append(Player(**player_dict))
            
            # Bulk create and update
            if players_to_create:
                Player.objects.bulk_create(players_to_create)
                logging.info(f"Created {len(players_to_create)} new players.")

            if players_to_update:
                Player.objects.bulk_update(players_to_update, [
                    'first_name', 'last_name', 'full_name', 'position', 'team', 'age', 'college', 'status',
                    'height', 'weight', 'injury_status', 'injury_body_part', 'injury_start_date', 'injury_notes',
                    'practice_participation', 'practice_description', 'birth_date', 'birth_city', 'birth_state',
                    'birth_country', 'years_exp', 'high_school', 'data'
                ])
                logging.info(f"Updated {len(players_to_update)} players.")
            
            # Update full_name for players where it is null
            players_to_update_fullname = Player.objects.filter(full_name__isnull=True)
            logging.info(f"Found {players_to_update_fullname.count()} players with null full_name")

            for player in players_to_update_fullname:
                if player.first_name or player.last_name:
                    player.full_name = f"{player.first_name or ''} {player.last_name or ''}".strip()
                    player.save()
                    logging.info(f"Updated full_name for player: {player.player_id} to '{player.full_name}'")
                else:
                    logging.warning(f"Unable to update full_name for player: {player.player_id}. Both first_name and last_name are missing.")

            # Double-check if any players still have null full_name
            remaining_null_fullname = Player.objects.filter(full_name__isnull=True).count()
            logging.info(f"After update, {remaining_null_fullname} players still have null full_name")

            logging.info("Player data has been updated in the database.")
        else:
            logging.error(f"Failed to fetch player data. Status code: {response.status_code}")

    def update_player_rankings(self):
        data = scrape('fantasypros.com')
        player_rankings = data.get_format(1)

        players_to_update = []
        total_players = len(player_rankings)
        players_found = 0
        players_not_found = 0

        for player_data in player_rankings:
            player_name = player_data['player_name']
            player_team_id = player_data['player_team_id']
            player_position_id = player_data['player_position_id']
            rank_ave = player_data['rank_ave']

            player = Player.objects.filter(
                full_name__iexact=player_name,
                team__iexact=player_team_id,
                position__iexact=player_position_id
            ).first()

            if player:
                player.rank_ave = float(rank_ave)
                players_to_update.append(player)
                players_found += 1
                logging.info(f"Found player: {player_name}, {player_team_id}, {player_position_id}, rank_ave: {rank_ave}")
            else:
                players_not_found += 1
                logging.warning(f"Player not found: {player_name}, {player_team_id}, {player_position_id}")

        if players_to_update:
            Player.objects.bulk_update(players_to_update, ['rank_ave'])
            logging.info(f"Updated rankings for {len(players_to_update)} players.")
        else:
            logging.warning("No players were updated with new rankings.")

        logging.info(f"Total players processed: {total_players}")
        logging.info(f"Players found and updated: {players_found}")
        logging.info(f"Players not found: {players_not_found}")
        logging.info("Player rankings update process completed.")

    def fetch_player_projections(self):
        # Get unique player IDs from all rosters
        player_ids = set()
        for roster in Roster.objects.all():
            player_ids.update(roster.players)

        # Remove team defenses (usually represented by team abbreviations)
        player_ids = {pid for pid in player_ids if not pid.isalpha()}

        # Get the current NFL week (you may need to implement this logic)
        current_nfl_week = self.get_current_nfl_week()
        projection_week = current_nfl_week + 1

        base_url = "https://api.sleeper.com/projections/nfl/player"
        
        for player_id in player_ids:
            url = f"{base_url}/{player_id}?season_type=regular&season=2024&week={projection_week}"
            response = requests.get(url)
            
            if response.status_code == 200:
                projection_data = response.json()
                
                # Extract relevant data from the projection, defaulting to None if not found
                pts_ppr = None
                opponent = None
                
                if projection_data:
                    stats = projection_data.get('stats', {})
                    if isinstance(stats, dict):
                        pts_ppr = stats.get('pts_ppr')
                    opponent = projection_data.get('opponent')
                
                player = Player.objects.filter(player_id=player_id).first()
                if player:
                    PlayerProjection.objects.update_or_create(
                        player=player,
                        week=projection_week,
                        defaults={
                            'pts_ppr': pts_ppr,
                            'opponent': opponent
                        }
                    )
                    logging.info(f"Updated projection for player {player_id} for week {projection_week}")
                else:
                    logging.warning(f"Player with ID {player_id} not found in the database")
            else:
                logging.error(f"Failed to fetch projection for player {player_id}. Status code: {response.status_code}")

        logging.info("Player projections have been updated in the database.")

    def fetch_player_stats(self):
            # Get unique player IDs from all rosters
            player_ids = set()
            for roster in Roster.objects.all():
                player_ids.update(roster.players)

            # Remove team defenses (usually represented by team abbreviations)
            player_ids = {pid for pid in player_ids if not pid.isalpha()}

            # Get the current NFL week (you may need to implement this logic)
            current_nfl_week = self.get_current_nfl_week()
            stat_week = current_nfl_week

            base_url = "https://api.sleeper.com/stats/nfl/player"
            
            for player_id in player_ids:
                url = f"{base_url}/{player_id}?season_type=regular&season=2024&week={stat_week}"
                response = requests.get(url)
                
                if response.status_code == 200:
                    stat_data = response.json()
                    
                    # Extract relevant data from the projection, defaulting to None if not found
                    pts_ppr = None
                    opponent = None
                    
                    if stat_data:
                        stats = stat_data.get('stats', {})
                        if isinstance(stats, dict):
                            pts_ppr = stats.get('pts_ppr')
                        opponent = stat_data.get('opponent')
                    
                    player = Player.objects.filter(player_id=player_id).first()
                    if player:
                        PlayerStats.objects.update_or_create(
                            player=player,
                            week=stat_week,
                            defaults={
                                'pts_ppr': pts_ppr,
                                'opponent': opponent
                            }
                        )
                        logging.info(f"Updated stats for player {player_id} for week {stat_week}")
                    else:
                        logging.warning(f"Player with ID {player_id} not found in the database")
                else:
                    logging.error(f"Failed to fetch stats for player {player_id}. Status code: {response.status_code}")

            logging.info("Player stats have been updated in the database.")

    def get_current_nfl_week(self):
        url = "https://api.sleeper.app/v1/state/nfl"
        response = requests.get(url)
        if response.status_code == 200:
            nfl_state = response.json()
            return nfl_state['week']
        logging.error(f"Failed to fetch NFL state. Status code: {response.status_code}")
        return None

