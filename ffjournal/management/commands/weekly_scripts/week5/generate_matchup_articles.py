import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from openai import OpenAI
from ffjournal.models import League, Matchup, Roster, Player, Article, Team, PlayerProjection
from pydantic import BaseModel
from typing import Optional, List
from django.utils import timezone
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
    team: Optional[str] = None
    rank_ave: Optional[float] = None
    projected_points: Optional[float] = None
    injury_status: Optional[str] = None
    injury_body_part: Optional[str] = None

class MatchupData(BaseModel):
    team_name: str
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

def generate_matchup_writeup(matchups_list, league, week):
    matchup_data = []
    for matchup in matchups_list:
        roster = Roster.objects.filter(
            sleeper_league_id=league.sleeper_league_id,
            roster_id=matchup.roster_id
        ).first()
        if roster:
            team = Team.objects.filter(
                sleeper_league_id=league.sleeper_league_id,
                sleeper_user_id=roster.owner_id
            ).first()
            team_name = team.team_name if team else f"Team {roster.owner_id}"

            starters = roster.starters or []
            starter_data = []
            for starter in starters:
                player = Player.objects.filter(player_id=starter).first()
                if player and player.full_name:
                    # Fetch player projection
                    projection = PlayerProjection.objects.filter(
                        player__player_id=starter, week=week
                    ).first()
                    projected_points = projection.pts_ppr if projection else None

                    player_data = PlayerData(
                        name=player.full_name,
                        position=player.data['fantasy_positions'][0]
                        if isinstance(player.data['fantasy_positions'], list)
                        else player.data['fantasy_positions'],
                        team=player.team if hasattr(player, 'team') else None,
                        rank_ave=player.rank_ave,
                        projected_points=projected_points
                    )

                    # Add injury information only if it's not null
                    if player.injury_status:
                        player_data.injury_status = player.injury_status
                    if player.injury_body_part:
                        player_data.injury_body_part = player.injury_body_part

                    starter_data.append(player_data)
                else:
                    logging.warning(f"Skipping player with ID {starter} due to missing data")

            matchup_data.append(MatchupData(team_name=team_name, starters=starter_data))

    if len(matchup_data) != 2:
        logging.error("Expected 2 teams in matchup_data")
        return None

    # Default system message
    system_message = """
    You are a seasoned fantasy football analyst tasked with reviewing a weekly matchup. Compare the two teams, discuss their strengths, analyze the performance of key players, and predict who will win and whether it will be a close contest or a blowout. The analysis should be thorough and detailed, covering all aspects of the matchup, including player rankings and potential game impact. Do not be afraid to trash talk or point out team's weaknesses; the article shouldn't be just upshots. Do not use the --- markdown in your generation. Keep it maximum 500 words.

    The rank_ave field represents the average ranking of a player across all players in fantasy football. A player with a rank_ave of 1 is considered the best player in fantasy football. A rank_ave of None indicates that the player wasn't ranked. Use this information to infer the relative strength of each team without explicitly mentioning the rank_ave values. Keep it maximum 500 words.
    """

    # Check if the league has a custom system prompt and append it
    if league.custom_system_prompt:
        system_message += f"\n\n{league.custom_system_prompt}"

    prompt = f"""
    Generate a detailed fantasy football analysis for the following matchup in Week {week}. Compare the two teams, mention their strengths, analyze the performance of key players, and predict who will win and whether it will be a close contest or a blowout. The analysis should be insightful and comprehensive, helping readers understand the potential outcomes of this game.

    For each player, we provide the following key information:
    1. projected_points: This represents the expected fantasy points for the player in PPR scoring for this week. Use this to assess each player's potential impact on the matchup.
    2. injury_status: If present, this indicates the player's current injury status (e.g., Questionable, Doubtful, Out).
    3. injury_body_part: If present, this specifies the body part affected by the injury.

    When analyzing the matchup, consider these factors:
    - Use the projected_points to compare the expected performance of players and teams.
    - If a player has injury information, discuss how it might affect their performance or availability, and the potential impact on their team's chances.
    - Look for mismatches between opposing players based on their projections and injury status.

    Provide a balanced analysis that takes into account both the projected points and any injury concerns. Highlight any significant disparities in projected team scores or key player matchups that could influence the outcome.

    {matchup_data}
    """

    logging.info(f"Sending prompt to OpenAI for matchup {matchups_list[0].matchup_id} in League: {league.name}, Week: {week}")

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            functions=[{
                "name": "generate_writeup",
                "description": "Generate a matchup write-up",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The write-up for the matchup"
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
            label=f'matchup_{matchups_list[0].matchup_id}',
            defaults={'title': f'Matchup {matchups_list[0].matchup_id}', 'content': content}
        )

        if created:
            print(f"Matchup write-up for Matchup ID {matchups_list[0].matchup_id} created successfully.")
        else:
            print(f"Matchup write-up for Matchup ID {matchups_list[0].matchup_id} updated successfully.")

        return content

    except Exception as e:
        print(f"Error generating write-up for matchup {matchups_list[0].matchup_id} in league {league.name}, week {week}: {e}")
        return None

def combine_matchup_writeups(matchup_writeups, league, week):
    # Combine the write-ups into one article
    combined_content = "\n\n---\n\n".join(matchup_writeups)
    title = f"Week {week} Matchup Previews"

    return title, combined_content

def generate_matchup_article(league, week):
    print(f"Entering generate_matchup_article for League: {league.name}, Week: {week}")
    logging.info(f"Fetching matchups for League: {league.name}, Week: {week}")
    matchups = Matchup.objects.filter(sleeper_league_id=league.sleeper_league_id, week=week)
    
    if not matchups:
        logging.error(f"No matchups found for League: {league.name}, Week: {week}.")
        return None, None

    # Group matchups by matchup_id
    matchup_dict = {}
    for matchup in matchups:
        matchup_dict.setdefault(matchup.matchup_id, []).append(matchup)
    
    matchup_writeups = []
    for matchup_id, matchups_list in matchup_dict.items():
        writeup = generate_matchup_writeup(matchups_list, league, week)
        if writeup:
            matchup_writeups.append(writeup)

    # Now combine the write-ups into one article
    combined_title, combined_content = combine_matchup_writeups(matchup_writeups, league, week)

    return combined_title, combined_content

class Command(BaseCommand):
    help = "Generates matchup articles for a specific league for the current NFL week."

    def add_arguments(self, parser):
        parser.add_argument('league_id', type=int, help='The ID of the league to process.')

    def handle(self, *args, **kwargs):
        league_id = kwargs['league_id']
        current_week = fetch_current_nfl_week()
        if not current_week:
            print("Failed to fetch the current NFL week.")
            return

        try:
            league = League.objects.get(id=league_id)
            print(f"\nGenerating article for League: {league.name}, Week: {current_week}")
            title, content = generate_matchup_article(league, current_week)
            print(f"Title: {title}")
            print(f"Content returned: {content}")
            
            if title and content:
                article, created = Article.objects.update_or_create(
                    sleeper_league_id=league,
                    week=current_week,
                    label='this_weeks_matchups',
                    defaults={'title': title, 'content': content}
                )
                if created:
                    print(f"Article for League: {league.name}, Week: {current_week} created successfully.")
                else:
                    print(f"Article for League: {league.name}, Week: {current_week} updated successfully.")
            else:
                print(f"Failed to generate article for League: {league.name}, Week: {current_week}. Content or title was None.")
        except League.DoesNotExist:
            print(f"League with ID {league_id} does not exist.")
