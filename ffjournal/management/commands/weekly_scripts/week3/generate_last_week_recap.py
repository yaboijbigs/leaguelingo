import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from openai import OpenAI
from ffjournal.models import League, Matchup, Roster, Player, Article, Team, PlayerStats
from pydantic import BaseModel
from typing import Optional, List
from django.utils import timezone
from django.conf import settings
import pytz
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)

# OpenAI setup
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Define the Pydantic models to structure the API responses
class PlayerData(BaseModel):
    name: str
    position: str
    team: Optional[str] = None  # Add the team field
    points: Optional[float] = None  # Points scored in the matchup

class TeamData(BaseModel):
    team_name: str
    points: float
    starters: List[PlayerData]

def fetch_current_nfl_week():
    """Fetches the current NFL week from the Sleeper API."""
    url = "https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    if response.status_code == 200:
        nfl_state = response.json()
        return nfl_state['week']
    logging.error(f"Failed to fetch NFL state. Status code: {response.status_code}")
    return None

def generate_matchup_recap(matchup_teams, league, week):
    if len(matchup_teams) != 2:
        logging.error("Expected 2 teams in matchup_teams")
        return None

    team_data_list = []
    for team_info in matchup_teams:
        team_name = team_info['team_name']
        team_points = team_info['points']
        starters_data = []
        for player_info in team_info['starters']:
            player_data = PlayerData(
                name=player_info['name'],
                position=player_info['position'],
                team=player_info.get('team'),
                points=player_info['points']
            )
            starters_data.append(player_data)
        team_data = TeamData(
            team_name=team_name,
            points=team_points,
            starters=starters_data
        )
        team_data_list.append(team_data)

    # Default system message
    system_message = """
    You are a seasoned fantasy football analyst tasked with reviewing a weekly matchup. Discuss who won and highlight big performances. The analysis should be thorough and detailed, covering all aspects of the matchup, including team scores and individual player performances. Do not be afraid to trash talk or point out team's weaknesses; the article shouldn't be just upshots. Do not use the --- markdown in your generation. Keep it a maximum of 500 words.
    """

    # Check if the league has a custom system prompt and append it
    if league.custom_system_prompt:
        system_message += f"\n\n{league.custom_system_prompt}"

    prompt = f"""
    Generate a detailed fantasy football recap for the following matchup in Week {week}. Discuss who won and highlight big performances. The analysis should be insightful and comprehensive, helping readers understand what happened in the game.

    Provide a balanced analysis that takes into account both the team scores and individual player performances. Highlight any significant disparities in team scores or standout player performances that influenced the outcome.

    {team_data_list}
    """

    logging.info(f"Sending prompt to OpenAI for matchup in League: {league.name}, Week: {week}")

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            functions=[{
                "name": "generate_writeup",
                "description": "Generate a matchup recap write-up",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The write-up for the matchup recap"
                        }
                    },
                    "required": ["content"]
                }
            }],
            function_call={"name": "generate_writeup"}
        )

        response_content = completion.choices[0].message.function_call.arguments
        writeup_data = json.loads(response_content)

        content = writeup_data['content']

        # Store the write-up in the database
        article, created = Article.objects.update_or_create(
            sleeper_league_id=league,
            week=week,
            label=f'matchup_recap_{matchup_teams[0]["matchup_id"]}',
            defaults={'title': f'Matchup Recap {matchup_teams[0]["matchup_id"]}', 'content': content}
        )

        if created:
            print(f"Matchup recap for Matchup ID {matchup_teams[0]['matchup_id']} created successfully.")
        else:
            print(f"Matchup recap for Matchup ID {matchup_teams[0]['matchup_id']} updated successfully.")

        return content

    except Exception as e:
        print(f"Error generating recap for matchup {matchup_teams[0]['matchup_id']} in league {league.name}, week {week}: {e}")
        return None

def combine_matchup_recaps(matchup_recaps, league, week):
    # Combine the recaps into one article
    combined_content = "\n\n---\n\n".join(matchup_recaps)
    title = f"Week {week} Matchup Recaps"

    return title, combined_content

def generate_last_week_recap(league, week):
    print(f"Generating recap for League: {league.name}, Week: {week}")
    logging.info(f"Fetching matchups for League: {league.name}, Week: {week}")

    matchups = Matchup.objects.filter(sleeper_league_id=league.sleeper_league_id, week=week)

    if not matchups:
        logging.error(f"No matchups found for League: {league.name}, Week: {week}.")
        return None, None

    # Organize matchups by matchup_id
    matchup_data = {}
    for matchup in matchups:
        roster = Roster.objects.filter(sleeper_league_id=league.sleeper_league_id, roster_id=matchup.roster_id).first()
        if matchup.matchup_id not in matchup_data:
            matchup_data[matchup.matchup_id] = []

        if roster:
            team = Team.objects.filter(sleeper_league_id=league.sleeper_league_id, sleeper_user_id=roster.owner_id).first()
            team_name = team.team_name if team else f"Team {roster.owner_id}"
        else:
            team_name = f"Team {matchup.roster_id}"

        starters_data = []
        for player_id, points in zip(matchup.starters, matchup.starters_points):
            player = Player.objects.filter(player_id=player_id).first()
            if player and player.full_name:
                starters_data.append({
                    'name': player.full_name,
                    'points': points,
                    'position': player.data['fantasy_positions'][0]
                    if isinstance(player.data['fantasy_positions'], list)
                    else player.data['fantasy_positions'],
                    'team': player.team if hasattr(player, 'team') else None,
                })

        matchup_data[matchup.matchup_id].append({
            'matchup_id': matchup.matchup_id,
            'team_name': team_name,
            'points': matchup.points,
            'starters': starters_data,
        })

    matchup_recaps = []
    for matchup_id, matchup_teams in matchup_data.items():
        recap = generate_matchup_recap(matchup_teams, league, week)
        if recap:
            matchup_recaps.append(recap)

    # Now combine the recaps into one article
    combined_title, combined_content = combine_matchup_recaps(matchup_recaps, league, week)

    return combined_title, combined_content

class Command(BaseCommand):
    help = "Generates recap articles for a specific league for the previous NFL week."

    def add_arguments(self, parser):
        parser.add_argument('league_id', type=int, help='The ID of the league to process.')

    def handle(self, *args, **kwargs):
        league_id = kwargs['league_id']
        current_week = fetch_current_nfl_week()
        if not current_week:
            print("Failed to fetch the current NFL week.")
            return

        last_week = current_week - 1
        if last_week < 1:
            print("It's too early in the season for a recap.")
            return

        try:
            league = League.objects.get(id=league_id)
            print(f"\nGenerating recap for League: {league.name}, Week: {last_week}")
            title, content = generate_last_week_recap(league, last_week)
            
            if title and content:
                article, created = Article.objects.update_or_create(
                    sleeper_league_id=league,
                    week=current_week,
                    label='last_week_recap',
                    defaults={'title': title, 'content': content}
                )
                if created:
                    print(f"Recap article for League: {league.name}, Week: {last_week} created successfully.")
                else:
                    print(f"Recap article for League: {league.name}, Week: {last_week} updated successfully.")
            else:
                print(f"Failed to generate recap article for League: {league.name}, Week: {last_week}. Content or title was None.")

        except League.DoesNotExist:
            print(f"League with ID {league_id} does not exist.")


    def should_run_task(self, league, current_time):
        if not league.scheduled_day or not league.scheduled_time:
            print(f"League {league.name} has no scheduled day or time.")
            return False

        league_timezone = pytz.timezone(settings.TIME_ZONE)
        current_time_local = current_time.astimezone(league_timezone)

        scheduled_time_today = datetime.combine(current_time_local.date(), league.scheduled_time)
        scheduled_time_today = league_timezone.localize(scheduled_time_today)

        print(f"League {league.name} scheduled for {league.scheduled_day} at {league.scheduled_time}")
        print(f"Current time: {current_time_local}, Scheduled time today: {scheduled_time_today}")

        if current_time_local.strftime('%A') == league.scheduled_day and current_time_local >= scheduled_time_today:
            last_run_time = league.last_run_time
            if not last_run_time or last_run_time < scheduled_time_today:
                print(f"Task should run for league {league.name}")
                return True
            else:
                print(f"Task already ran this week for league {league.name}")
        else:
            print(f"Not the scheduled day or time for league {league.name}")

        return False
