import requests
from .models import League, Roster, Team, Matchup, Event, generate_default_owner_id
import json
import logging

# Configure logging
logging.basicConfig(filename='detailed_comparison.log', level=logging.INFO, format='%(asctime)s - %(message)s')

def fetch_league_data(league_id: str, owner=None):
    url = f"https://api.sleeper.app/v1/league/{league_id}"
    response = requests.get(url)
    
    if response.status_code != 200:
        logging.error(f"Failed to fetch league data. Status code: {response.status_code}, Response: {response.text}")
        return None

    league_data = response.json()
    
    if not league_data:
        logging.error(f"Received empty response for league_id: {league_id}")
        return None

    # Try to get existing league
    existing_league = League.objects.filter(sleeper_league_id=league_id).first()

    league_info = {
        'sleeper_league_id': league_id,
        'name': league_data.get('name'),
        'status': league_data.get('status'),
        'waiver_budget': league_data.get('settings', {}).get('waiver_budget', 0),
        'playoff_teams': league_data.get('settings', {}).get('playoff_teams', 0),
        'veto_votes_needed': league_data.get('settings', {}).get('veto_votes_needed'),
        'num_teams': league_data.get('total_rosters', 0),
        'playoff_week_start': league_data.get('settings', {}).get('playoff_week_start', 0),
        'trade_deadline': league_data.get('settings', {}).get('trade_deadline', 0),
        'pick_trading': league_data.get('settings', {}).get('pick_trading'),
        'max_keepers': league_data.get('settings', {}).get('max_keepers'),
        'draft_id': league_data.get('draft_id', ''),
        'previous_league_id': league_data.get('previous_league_id', ''),
        'total_rosters': league_data.get('total_rosters', 0),
        'data': league_data,
    }

    # Safely check for latest_league_winner_roster_id
    metadata = league_data.get('metadata')
    if metadata is not None and 'latest_league_winner_roster_id' in metadata:
        league_info['latest_league_winner_roster_id'] = metadata['latest_league_winner_roster_id']

    if existing_league:
        # Update existing league
        for key, value in league_info.items():
            setattr(existing_league, key, value)
        # Only set owner if it's a new league and owner is provided
        if owner and not existing_league.owner:
            existing_league.owner = owner
        existing_league.save()
    else:
        # Create new league
        league_info['owner'] = owner
        existing_league = League.objects.create(**league_info)
    
    if league_info['status'] == 'complete':
        logging.info(f"League {league_id} is complete. Skipping updates to Roster, Team, and Matchup tables.")
    
    # Ensure the object is retrieved fresh from the database to prevent any weird instance issues
    league_instance = League.objects.get(sleeper_league_id=league_id)
    return league_instance


def fetch_roster_data(league_id: str):
    url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
    response = requests.get(url)
    
    if response.status_code == 200:
        rosters_data = response.json()
        
        for roster in rosters_data:
            roster_dict = {
                'sleeper_league_id_id': league_id,  # Use '_id' suffix because it's a ForeignKey field
                'roster_id': roster.get('roster_id'),
                'owner_id': roster.get('owner_id') or generate_default_owner_id(),
                'co_owners': roster.get('co_owners'),
                'keepers': roster.get('keepers'),
                'players': roster.get('players'),
                'starters': roster.get('starters')
            }
            
            existing_roster = Roster.objects.filter(
                sleeper_league_id=league_id,
                roster_id=roster_dict['roster_id']
            ).first()
            
            if existing_roster:
                for key, value in roster_dict.items():
                    setattr(existing_roster, key, value)
                existing_roster.save()
            else:
                Roster.objects.create(**roster_dict)

def fetch_team_data(league_id: str):
    logging.info(f"==== Starting fetch_team_data for league ID {league_id} ====")
    
    url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    response = requests.get(url)
    
    if response.status_code == 200:
        users_data = response.json()
        
        # Fetch existing teams for the league
        existing_teams = Team.objects.filter(sleeper_league_id=league_id)
        existing_team_dict = {team.sleeper_user_id: team for team in existing_teams}
        
        # Fetch all rosters for the league
        rosters = Roster.objects.filter(sleeper_league_id=league_id)
        roster_dict = {roster.owner_id: roster for roster in rosters}
        
        # Create a set of all sleeper_user_ids for comparison
        all_user_ids = set(existing_team_dict.keys())
        
        # Process each user returned by the API
        for user in users_data:
            team_dict = {
                'sleeper_user_id': user.get('user_id'),
                'display_name': user.get('display_name'),
                'avatar': user.get('metadata', {}).get('avatar'),
                'team_name': user.get('metadata', {}).get('team_name'),
                'is_owner': user.get('is_owner', False),
                'sleeper_league_id_id': league_id,  # ForeignKey requires _id
                'is_team_owner': False,
                'is_co_owner': False
            }
            
            # Determine if the user is a team owner or co-owner
            roster = roster_dict.get(team_dict['sleeper_user_id'])
            if roster:
                team_dict['is_team_owner'] = True
                co_owners = roster.co_owners or []
                if isinstance(co_owners, str):
                    co_owners = json.loads(co_owners)  # Parse the JSON string into a Python list
                
                # Debugging logs for co-owner check
                logging.info(f"Checking co-owners for team: {team_dict['sleeper_user_id']}, co_owners: {co_owners}")

                for co_owner in co_owners:
                    if str(co_owner) in all_user_ids:
                        team_dict['is_co_owner'] = True
                        logging.info(f"User {team_dict['sleeper_user_id']} is a co-owner.")
                        break  # Exit loop once a match is found
                else:
                    logging.info(f"User {team_dict['sleeper_user_id']} is NOT a co-owner.")
            
            # Update existing team or create a new one
            existing_team = existing_team_dict.get(team_dict['sleeper_user_id'])
            if existing_team:
                for key, value in team_dict.items():
                    setattr(existing_team, key, value)
                existing_team.save()
                logging.info(f"Updated existing team: {team_dict['sleeper_user_id']} in league {league_id}")
            else:
                Team.objects.create(**team_dict)
                logging.info(f"Created new team: {team_dict['sleeper_user_id']} in league {league_id}")
        
        # Update team names for teams with null names and who are team owners
        teams_to_update = Team.objects.filter(
            sleeper_league_id=league_id,
            team_name__isnull=True,
            is_team_owner=True
        )
        
        for team in teams_to_update:
            team.team_name = f"Team {team.display_name}"
            team.save()
            logging.info(f"Updated team name: user_id={team.sleeper_user_id}, new_name='{team.team_name}'")
        
        logging.info(f"Updated team names for {len(teams_to_update)} teams in league ID {league_id}")
        
        # Verify the updates
        verified_teams = Team.objects.filter(sleeper_league_id=league_id)
        for team in verified_teams:
            logging.info(f"Verified team: user_id={team.sleeper_user_id}, name='{team.team_name}', is_owner={team.is_team_owner}")

        logging.info(f"==== Completed fetch_team_data for league ID {league_id} ====")

        # Log any remaining teams with null names
        null_name_teams = Team.objects.filter(
            sleeper_league_id=league_id,
            team_name__isnull=True,
            is_team_owner=True
        )
        
        if null_name_teams.exists():
            logging.warning(f"Found {null_name_teams.count()} teams still with null names in league ID {league_id}")
            for team in null_name_teams:
                logging.warning(f"Null name team: user_id={team.sleeper_user_id}, display_name='{team.display_name}', is_owner={team.is_team_owner}")
        else:
            logging.info(f"No teams with null names remaining in league ID {league_id}")


def fetch_matchup_data(league_id: str, week: int):
    url = f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}"
    response = requests.get(url)
    
    if response.status_code == 200:
        matchups_data = response.json()
        
        grouped_matchups = {}
        for matchup in matchups_data:
            matchup_id = matchup.get('matchup_id')
            if matchup_id not in grouped_matchups:
                grouped_matchups[matchup_id] = []
            grouped_matchups[matchup_id].append(matchup)
        
        for matchup_id, matchups in grouped_matchups.items():
            for matchup in matchups:
                matchup_dict = {
                    'sleeper_league_id_id': league_id,
                    'matchup_id': matchup_id,
                    'roster_id': matchup.get('roster_id'),
                    'points': matchup.get('points'),
                    'custom_points': matchup.get('custom_points'),
                    'week': week,
                    'players': matchup.get('players'),
                    'starters': matchup.get('starters'),
                    'starters_points': matchup.get('starters_points'),
                    'players_points': matchup.get('players_points')
                }
                
                existing_matchup = Matchup.objects.filter(
                    sleeper_league_id=league_id,
                    matchup_id=matchup_id,
                    roster_id=matchup_dict['roster_id'],
                    week=week
                ).first()
                
                if existing_matchup:
                    for key, value in matchup_dict.items():
                        setattr(existing_matchup, key, value)
                    existing_matchup.save()
                else:
                    Matchup.objects.create(**matchup_dict)

def fetch_all_matchup_data(league_id: str):
    url = "https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    
    if response.status_code == 200:
        nfl_state = response.json()
        current_week = nfl_state['week']
        
        for week in range(1, current_week + 1):
            fetch_matchup_data(league_id, week)

def fetch_transactions_data_for_week(league_id: str, week: int):
    url = f"https://api.sleeper.app/v1/league/{league_id}/transactions/{week}"
    response = requests.get(url)
    
    if response.status_code == 200:
        transactions_data = response.json()
        
        for transaction in transactions_data:
            event_dict = {
                'sleeper_league_id_id': league_id,  # Use '_id' suffix because it's a ForeignKey field
                'transaction_id': transaction['transaction_id'],
                'type': transaction['type'],
                'status': transaction['status'],
                'settings': transaction.get('settings'),
                'event_metadata': transaction.get('metadata'),
                'created': transaction['created'],
                'leg': transaction['leg'],
                'draft_picks': transaction.get('draft_picks', []),
                'creator': transaction['creator'],
                'consenter_ids': transaction['consenter_ids'],
                'roster_ids': transaction['roster_ids'],
                'adds': transaction.get('adds'),
                'drops': transaction.get('drops'),
                'waiver_budget': transaction.get('waiver_budget', []),
                'status_updated': transaction['status_updated']
            }
            
            existing_event = Event.objects.filter(transaction_id=transaction['transaction_id']).first()
            
            if existing_event:
                for key, value in event_dict.items():
                    setattr(existing_event, key, value)
                existing_event.save()
                logging.info(f"Updated existing event: {transaction['transaction_id']}")
            else:
                Event.objects.create(**event_dict)
                logging.info(f"Created new event: {transaction['transaction_id']}")

def fetch_all_transactions_data(league_id: str):
    url = "https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    
    if response.status_code == 200:
        nfl_state = response.json()
        current_week = nfl_state['week']
        
        for week in range(1, current_week + 1):
            fetch_transactions_data_for_week(league_id, week)
    else:
        logging.error(f"Failed to fetch NFL state. Status code: {response.status_code}")
