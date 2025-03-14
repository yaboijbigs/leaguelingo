import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from openai import OpenAI
from ffjournal.models import League, Matchup, Roster, Player, Article, Team
from pydantic import BaseModel, ValidationError
from typing import Optional, List
from django.db.models import Q
import json

# Configure logging
logging.basicConfig(level=logging.INFO)

# OpenAI setup
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Define the Pydantic models to structure the API responses
class LeagueData(BaseModel):
    name: str
    latest_league_winner_team_name: Optional[str] = None  # Change this field
    waiver_budget: Optional[int] = None
    playoff_teams: Optional[int] = None
    veto_votes_needed: Optional[int] = None
    num_teams: Optional[int] = None
    playoff_week_start: Optional[int] = None
    trade_deadline: Optional[int] = None
    pick_trading: Optional[bool] = None
    max_keepers: Optional[int] = None
    roster_positions: List[str]

def parse_league_data(league: League) -> LeagueData:
    """Parses the JSON data field and relevant columns from the League model."""
    data = league.data if isinstance(league.data, dict) else json.loads(league.data) if league.data else {}
    roster_positions = data.get('roster_positions', [])

    latest_league_winner_team_name = None
    if league.latest_league_winner_roster_id:
        try:
            roster = Roster.objects.get(
                sleeper_league_id=league.sleeper_league_id,
                roster_id=league.latest_league_winner_roster_id
            )
            team = Team.objects.get(
                sleeper_league_id=league.sleeper_league_id,
                sleeper_user_id=roster.owner_id
            )
            latest_league_winner_team_name = team.team_name
        except (Roster.DoesNotExist, Team.DoesNotExist):
            pass

    return LeagueData(
        name=league.name,
        latest_league_winner_team_name=latest_league_winner_team_name,  # Update this field
        waiver_budget=league.waiver_budget,
        playoff_teams=league.playoff_teams,
        veto_votes_needed=league.veto_votes_needed,
        num_teams=league.num_teams,
        playoff_week_start=league.playoff_week_start,
        trade_deadline=league.trade_deadline,
        pick_trading=league.pick_trading,
        max_keepers=league.max_keepers,
        roster_positions=roster_positions
    )

def generate_league_overview(league):
    print(f"Generating league overview for League: {league.name}")
    logging.info(f"Fetching data for League: {league.name}")
    
    league_data = parse_league_data(league)

    # Default system message
    system_message = """
    You are a seasoned fantasy football analyst tasked with summarizing a fantasy football league's structure and key characteristics. The summary should highlight the league's key settings, roster positions, and any notable rules. Be sure to mention the previous league winner if available. This article is meant to provide an overview that captures the essence of the league's structure and uniqueness.
    """

    # Check if the league has a custom system prompt and append it
    if league.custom_system_prompt:
        system_message += f"\n\n{league.custom_system_prompt}"

    prompt = f"""
    Generate a detailed overview of the fantasy football league based on the following data:
    Name: {league_data.name}
    Latest League Winner Team Name: {league_data.latest_league_winner_team_name}
    Waiver Budget: {league_data.waiver_budget}
    Playoff Teams: {league_data.playoff_teams}
    Veto Votes Needed: {league_data.veto_votes_needed}
    Number of Teams: {league_data.num_teams}
    Playoff Week Start: {league_data.playoff_week_start}
    Trade Deadline: {league_data.trade_deadline}
    Pick Trading: {league_data.pick_trading}
    Max Keepers: {league_data.max_keepers}
    Roster Positions: {", ".join(league_data.roster_positions)}

    Do not use any Markdown or other markup languages. Provide the response in plain text, suitable for direct insertion into a PDF.
    """

    print(f"\nFull prompt being sent to OpenAI for League: {league.name}:\n{prompt}\n")

    logging.info(f"Sending prompt to OpenAI for League: {league.name}")
    
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            functions=[
                {
                    "name": "generate_article",
                    "description": "Generates a league overview article",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "article": {
                                "type": "string",
                                "description": "The generated article content"
                            }
                        },
                        "required": ["article"]
                    }
                }
            ],
            function_call={"name": "generate_article"},
            max_tokens=7000
        )

        response_content = completion.choices[0].message.function_call.arguments
        print(f"\nOpenAI response:\n{response_content}\n")

        try:
            article_content = json.loads(response_content)["article"]
            return article_content
        except (json.JSONDecodeError, KeyError) as e:
            print(f"\nError parsing JSON response: {e}\nResponse content: {response_content}\n")
            return None

    except Exception as e:
        print(f"\nError generating league overview for League: {league.name}: {e}\n")
        return None


class Command(BaseCommand):
    help = "Generates league overviews for all leagues."

    def handle(self, *args, **kwargs):
        current_week = fetch_current_nfl_week()
        if not current_week:
            print("Failed to fetch the current NFL week.")
            return

        leagues = League.objects.filter(Q(status='in_season') | Q(status='pre_draft'))
        for league in leagues:
            print(f"\nGenerating league overview for League: {league.name}")
            try:
                content = generate_league_overview(league)
                print(f"Content returned: {content}")
                
                if content:
                    # Check if an article already exists for the league overview
                    article, created = Article.objects.update_or_create(
                        sleeper_league_id=league,
                        week=current_week,  # Use the current_week instead of hardcoding 0
                        label='league_overview',
                        defaults={
                            'content': content,
                        }
                    )
                    if created:
                        print(f"League overview for League: {league.name} created successfully.")
                    else:
                        print(f"League overview for League: {league.name} updated successfully.")
                else:
                    print(f"Failed to generate league overview for League: {league.name}. Content was None.")
            except Exception as e:
                print(f"Error in generate_league_overview for League: {league.name}")
                print(f"Error details: {str(e)}")
                print("Traceback:")
                import traceback
                traceback.print_exc()


def fetch_current_nfl_week():
    """Fetches the current NFL week from the Sleeper API."""
    url = "https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    if response.status_code == 200:
        nfl_state = response.json()
        return nfl_state['week']
    logging.error(f"Failed to fetch NFL state. Status code: {response.status_code}")
    return None
