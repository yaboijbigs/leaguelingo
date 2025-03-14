import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from openai import OpenAI
from ffjournal.models import League, Matchup, Roster, Player, Article, Team, PlayerProjection, TrendingUpPlayer, TrendingDownPlayer
from pydantic import BaseModel, ValidationError
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
class TrendingPlayerData(BaseModel):
    name: str
    count: int
    position: Optional[str] = None
    team: Optional[str] = None

def fetch_current_nfl_week():
    """Fetches the current NFL week from the Sleeper API."""
    url = "https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    if response.status_code == 200:
        nfl_state = response.json()
        return nfl_state['week']
    logging.error(f"Failed to fetch NFL state. Status code: {response.status_code}")
    return None

def generate_waiver_watch_article(league, week):
    print(f"Entering generate_waiver_watch_article for League: {league.name}, Week: {week}")
    logging.info(f"Fetching trending players for League: {league.name}, Week: {week}")

    # Fetch trending players
    trending_up_players = get_trending_up_players(league)
    trending_down_players = get_trending_down_players(league)

    logging.info(f"Trending up players: {trending_up_players}")
    logging.info(f"Trending down players: {trending_down_players}")

    if not trending_up_players and not trending_down_players:
        logging.error(f"No trending players found for League: {league.name}, Week: {week}.")
        return None, None

    # Default system message
    system_message = """
    You are a seasoned fantasy football analyst specializing in waiver wire trends. Your task is to provide insightful analysis on trending players, both those gaining popularity and those losing favor among fantasy managers. Your analysis should be thorough, detailed, and help readers understand the potential impact of these trends on their fantasy teams.
    """

    # Check if the league has a custom system prompt and append it
    if league.custom_system_prompt:
        system_message += f"\n\n{league.custom_system_prompt}"

    prompt = f"""
    Generate a detailed fantasy football waiver watch article for Week {week} based on the following trending player data. The article should have the following structure:

    1. Title: Create a catchy and informative title that summarizes the key trends for Week {week}.

    2. Introduction: A brief paragraph introducing the waiver watch for Week {week}.

    3. Trending Up Players:
    Discuss the following players who are trending up but not rostered in this league. The count you will receive is the number of teams worldwide that have added the player to their roster in the past 24 hours. Discuss each of these players:
    {trending_up_players}

    4. Trending Down Players:
    Discuss the following players who are trending down but still rostered in this league. The count you will receive is the number of teams worldwide that have dropped the player from their roster in the past 24 hours. Be sure to talk trash about the fantasy football team that currently has the player. Discuss each of these players:
    {trending_down_players}

    5. Conclusion: Brief closing statements summarizing the key takeaways and encouraging managers to make moves.

    Provide your response in plain text that is markdown2 friendly. If you do include markdown, ensure it is properly spaced out, so that it can be detected by our markdown to display converter.

    """

    print(f"\nFull prompt being sent to OpenAI for League: {league.name}, Week: {week}:\n{prompt}\n")

    logging.info(f"Sending prompt to OpenAI for League: {league.name}, Week: {week}")
    
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            functions=[{
                "name": "generate_article",
                "description": "Generate a fantasy football waiver watch article with a title and content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "A catchy and informative title for the article"
                        },
                        "content": {
                            "type": "string",
                            "description": "The main content of the article, in plain text with no markdown"
                        }
                    },
                    "required": ["title", "content"]
                }
            }],
            function_call={"name": "generate_article"}
        )

        response_content = completion.choices[0].message.function_call.arguments
        
        # Add more robust JSON parsing
        try:
            article_data = json.loads(response_content)
        except json.JSONDecodeError as json_error:
            print(f"JSON Decode Error: {json_error}")
            print(f"Raw response content: {response_content}")
            
            # Attempt to clean the response content
            cleaned_content = ''.join(char for char in response_content if ord(char) >= 32)
            try:
                article_data = json.loads(cleaned_content)
            except json.JSONDecodeError:
                print("Failed to parse JSON even after cleaning.")
                return None, None

        title = article_data.get('title', 'No Title Generated')
        content = article_data.get('content', 'No Content Generated')

        print(f"\nGenerated Title: {title}")
        print(f"\nGenerated Content: {content[:100]}...")  # Print first 100 characters of content

        return title, content

    except Exception as e:
        print(f"\nError generating waiver watch article for league {league.name}, week {week}: {e}\n")
        return None, None

def get_rostered_player_ids(league):
    rostered_player_ids = set()
    rosters = Roster.objects.filter(sleeper_league_id=league)
    for roster in rosters:
        rostered_player_ids.update(str(player_id) for player_id in roster.players)
    logging.info(f"Rostered player IDs for league {league.name}: {rostered_player_ids}")
    return rostered_player_ids

def get_trending_up_players(league):
    rostered_player_ids = get_rostered_player_ids(league)
    all_trending_up = TrendingUpPlayer.objects.order_by('-count')
    
    trending_up_data = []
    for trend in all_trending_up:
        logging.info(f"Checking trending up player: {trend.player_id}, rostered: {trend.player_id in rostered_player_ids}")
        if trend.player_id not in rostered_player_ids:
            player = Player.objects.filter(player_id=trend.player_id).first()
            if player:
                trending_up_data.append({
                    'name': player.full_name,
                    'count': trend.count,
                    'position': player.position,
                    'team': player.team
                })
                if len(trending_up_data) == 3:
                    break

    logging.info(f"Trending up players for league {league.name}: {trending_up_data}")
    return trending_up_data

def get_trending_down_players(league):
    rostered_player_ids = get_rostered_player_ids(league)
    all_trending_down = TrendingDownPlayer.objects.order_by('-count')
    
    trending_down_data = []
    for trend in all_trending_down:
        logging.info(f"Checking trending down player: {trend.player_id}, rostered: {trend.player_id in rostered_player_ids}")
        if trend.player_id in rostered_player_ids:
            player = Player.objects.filter(player_id=trend.player_id).first()
            if player:
                # Find the roster for this player in the league
                roster = Roster.objects.filter(sleeper_league_id=league, players__contains=[trend.player_id]).first()
                team_name = "Unknown"
                if roster:
                    # Use the owner_id from the roster and the league to find the team
                    team = Team.objects.filter(sleeper_user_id=roster.owner_id, sleeper_league_id=league).first()
                    if team:
                        team_name = team.team_name

                trending_down_data.append({
                    'name': player.full_name,
                    'count': trend.count,
                    'position': player.position,
                    'team': player.team,
                    'fantasy_team': team_name
                })
                if len(trending_down_data) == 3:
                    break

    logging.info(f"Trending down players for league {league.name}: {trending_down_data}")
    return trending_down_data

class Command(BaseCommand):
    help = "Generates waiver watch articles for all leagues for the current NFL week."

    def handle(self, *args, **kwargs):
        current_week = fetch_current_nfl_week()
        if not current_week:
            print("Failed to fetch the current NFL week.")
            return

        current_time = timezone.now()
        leagues = League.objects.filter(status='in_season')
        
        for league in leagues:
            if self.should_run_task(league, current_time):
                print(f"\nGenerating waiver watch article for League: {league.name}, Week: {current_week}")
                try:
                    title, content = generate_waiver_watch_article(league, current_week)
                    print(f"Title: {title}")
                    print(f"Content returned: {content}")
                    
                    if title and content:
                        article, created = Article.objects.update_or_create(
                            sleeper_league_id=league,
                            week=current_week,
                            label='waiver_watch',
                            defaults={'title': title, 'content': content}
                        )
                        if created:
                            print(f"Waiver watch article for League: {league.name}, Week: {current_week} created successfully.")
                        else:
                            print(f"Waiver watch article for League: {league.name}, Week: {current_week} updated successfully.")
                    else:
                        print(f"Failed to generate waiver watch article for League: {league.name}, Week: {current_week}. Content or title was None.")
                except Exception as e:
                    print(f"Error in generate_waiver_watch_article for League: {league.name}, Week: {current_week}")
                    print(f"Error details: {str(e)}")
                    print("Traceback:")
                    import traceback
                    traceback.print_exc()

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