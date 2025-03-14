import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from openai import OpenAI
from ffjournal.models import League, Matchup, Roster, Player, Article, Team
from pydantic import BaseModel, ValidationError
from typing import Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO)

# OpenAI setup
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Define the Pydantic models to structure the API responses
class PlayerData(BaseModel):
    name: str
    position: str
    team: Optional[str] = None  # Add the team field
    rank_ave: Optional[float] = None

class MatchupData(BaseModel):
    team_name: str
    starters: List[PlayerData]
    points: float

def fetch_current_nfl_week():
    """Fetches the current NFL week from the Sleeper API."""
    url = "https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    if response.status_code == 200:
        nfl_state = response.json()
        return nfl_state['week']
    logging.error(f"Failed to fetch NFL state. Status code: {response.status_code}")
    return None

def generate_matchup_article(league, week):
    print(f"Entering generate_matchup_article for League: {league.name}, Week: {week}")
    logging.info(f"Fetching matchups for League: {league.name}, Week: {week}")
    matchups = Matchup.objects.filter(sleeper_league_id=league.sleeper_league_id, week=week)
    
    if not matchups:
        logging.error(f"No matchups found for League: {league.name}, Week: {week}.")
        return None

    matchup_data = []
    for matchup in matchups:
        roster = Roster.objects.filter(sleeper_league_id=league.sleeper_league_id, roster_id=matchup.roster_id).first()
        
        if roster:
            team = Team.objects.filter(sleeper_league_id=league.sleeper_league_id, sleeper_user_id=roster.owner_id).first()
            team_name = team.team_name if team else f"Team {roster.owner_id}"
            
            # Add previous league winner information
            previous_league_winner = False
            if league.latest_league_winner_roster_id == roster.roster_id:
                previous_league_winner_team = Team.objects.filter(
                    sleeper_league_id=league.sleeper_league_id, 
                    sleeper_user_id=roster.owner_id
                ).first()
                if previous_league_winner_team:
                    previous_league_winner = previous_league_winner_team.team_name
                else:
                    previous_league_winner = f"Team {roster.owner_id}"
            
            starters = roster.starters or []
            
            starter_data = []
            for starter in starters:
                player = Player.objects.filter(player_id=starter).first()
                if player and 'fantasy_positions' in player.data:
                    starter_data.append(PlayerData(
                        name=player.full_name,
                        position=player.data['fantasy_positions'][0] if isinstance(player.data['fantasy_positions'], list) else player.data['fantasy_positions'],
                        team=player.team if hasattr(player, 'team') else None,  # Include the team if available
                        rank_ave=player.rank_ave
                    ))
            
            if starter_data:
                matchup_data.append(MatchupData(
                    team_name=team_name,
                    starters=starter_data,
                    points=matchup.points,
                    previous_league_winner=previous_league_winner
                ))

    print(f"Matchup data: {matchup_data}")

    if not matchup_data:
        logging.error(f"No valid matchup data found for League: {league.name}, Week: {week}.")
        return None
    
    # Default system message
    system_message = """
    You are a seasoned fantasy football analyst tasked with reviewing weekly matchups. For each matchup, compare the two teams, discuss their strengths, analyze the performance of key players, and predict who will win and whether it will be a close contest or a blowout. The analysis should be thorough and detailed, covering all aspects of the matchups, including player rankings and potential game impact. Do not be afraid to trash talk or point out team's weaknesses, the article shouldn't be just upshots.

    The rank_ave field represents the average ranking of a player across all players in fantasy football. A player with a rank_ave of 1 is considered the best player in fantasy football. A rank_ave of None indicates that the player wasn't ranked. Use this information to infer the relative strength of each team without explicitly mentioning the rank_ave values.

    Provide the response as a single string containing the detailed analysis of the week's matchups.
    """

    # Check if the league has a custom system prompt and append it
    if league.custom_system_prompt:
        system_message += f"\n\n{league.custom_system_prompt}"

    prompt = f"""
    Generate a detailed fantasy football article for Week {week} based on the following matchup data. For each matchup, compare the two teams, mention their strengths, analyze the performance of key players, and predict who will win and whether it will be a close contest or a blowout. The analysis should be insightful and comprehensive, helping readers understand the potential outcomes of each game. Be sure to mention which team was the previous league winner by referencing the 'previous_league_winner' field if it is not False.

    {matchup_data}
    """

    print(f"\nFull prompt being sent to OpenAI for League: {league.name}, Week: {week}:\n{prompt}\n")

    logging.info(f"Sending prompt to OpenAI for League: {league.name}, Week: {week}")
    
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=7000
        )

        response_content = completion.choices[0].message.content
        print(f"\nOpenAI response:\n{response_content}\n")

        return response_content

    except Exception as e:
        print(f"\nError generating article for league {league.name}, week {week}: {e}\n")
        return None


class Command(BaseCommand):
    help = "Generates articles for all leagues for the current NFL week."

    def handle(self, *args, **kwargs):
        current_week = fetch_current_nfl_week()
        if not current_week:
            print("Failed to fetch the current NFL week.")
            return

        leagues = League.objects.filter(status='in_season')
        for league in leagues:
            print(f"\nGenerating article for League: {league.name}, Week: {current_week}")
            try:
                content = generate_matchup_article(league, current_week)
                print(f"Content returned: {content}")
                
                if content:
                    # Check if an article already exists for the current week and league
                    article, created = Article.objects.update_or_create(
                        sleeper_league_id=league,
                        week=current_week,
                        label='this_weeks_matchups',
                        defaults={
                            'content': content,
                        }
                    )
                    if created:
                        print(f"Article for League: {league.name}, Week: {current_week} created successfully.")
                    else:
                        print(f"Article for League: {league.name}, Week: {current_week} updated successfully.")
                else:
                    print(f"Failed to generate article for League: {league.name}, Week: {current_week}. Content was None.")
            except Exception as e:
                print(f"Error in generate_matchup_article for League: {league.name}, Week: {current_week}")
                print(f"Error details: {str(e)}")
                print("Traceback:")
                import traceback
                traceback.print_exc()