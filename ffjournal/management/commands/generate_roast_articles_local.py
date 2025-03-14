import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from openai import OpenAI
from ffjournal.models import League, Roster, Player, Article, Team
from django.db.models import Q
import json

# Configure logging
logging.basicConfig(level=logging.INFO)

# OpenAI setup
client = OpenAI(api_key=settings.OPENAI_API_KEY)

def generate_roast_article(league):
    print(f"Generating roast article for League: {league.name}")
    logging.info(f"Fetching rosters for League: {league.name}")
    
    rosters = Roster.objects.filter(sleeper_league_id=league.sleeper_league_id)
    
    print(f"Found {len(rosters)} rosters for League: {league.name}")
    
    if not rosters:
        logging.error(f"No rosters found for League: {league.name}.")
        return None

    roster_data = []
    for roster in rosters:
        team = Team.objects.filter(sleeper_league_id=league.sleeper_league_id, sleeper_user_id=roster.owner_id).first()
        team_name = team.team_name if team else f"Team {roster.owner_id}"
        
        starters = []
        bench = []
        for player_id in roster.players:
            player = Player.objects.filter(player_id=player_id).first()
            if player and 'fantasy_positions' in player.data:
                player_data = {
                    "name": player.full_name,
                    "position": player.data['fantasy_positions'][0] if isinstance(player.data['fantasy_positions'], list) else player.data['fantasy_positions'],
                    "team": player.team if hasattr(player, 'team') else None,
                    "rank_ave": player.rank_ave
                }
                if player_id in roster.starters:
                    starters.append(player_data)
                else:
                    bench.append(player_data)
        
        if starters or bench:
            roster_data.append({
                "team_name": team_name,
                "starters": starters,
                "bench": bench
            })

    if not roster_data:
        logging.error(f"No valid roster data found for League: {league.name}.")
        return None
    
    system_message = """
    You are a savage fantasy football analyst tasked with roasting each team's roster in a league. For each team, analyze their roster and mercilessly mock their player selections, pointing out weaknesses, bad draft picks, and questionable decisions. Pay special attention to the difference between starters and bench players. The roast should be humorous, insulting, and pull no punches. Feel free to use trash talk, sarcasm, and hyperbole to exaggerate the shortcomings of each team. The goal is to entertain the reader by creatively and ruthlessly criticizing each roster.

    The rank_ave field represents the average ranking of a player across all players in fantasy football. A player with a rank_ave of 1 is considered the best player in fantasy football. A rank_ave of None indicates that the player wasn't ranked. Use this information to mock teams with low-ranked or unranked players.

    Do not use any Markdown or other markup languages. Provide the response in plain text, suitable for direct insertion into a PDF.
    """

    # Check if the league has a custom system prompt and append it
    if league.custom_system_prompt:
        system_message += f"\n\n{league.custom_system_prompt}"

    prompt = f"""
    Generate a humorous and insulting roast of each team's roster in the fantasy football league based on the following roster data. Make sure to roast EVERY team in the league. For each team, analyze their starters and bench players, mercilessly mocking their weaknesses, bad draft picks, and questionable decisions. The roast should be savage, pulling no punches and using trash talk, sarcasm, and hyperbole to exaggerate each roster's shortcomings. Pay special attention to any discrepancies between the quality of starters and bench players. The goal is to entertain the reader by creatively and ruthlessly criticizing each team. Open your roast with a short paragraph, roasting the entire league.

    League Name: {league.name}
    Roster Data: {json.dumps(roster_data, indent=2)}
    """

    print(f"\nFull prompt being sent to OpenAI for League: {league.name}:\n{prompt}\n")

    logging.info(f"Sending prompt to OpenAI for League: {league.name}")
    
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=7000
        )

        roast_content = completion.choices[0].message.content
        print(f"\nOpenAI response:\n{roast_content}\n")

        return roast_content

    except Exception as e:
        print(f"\nError generating roast article for League: {league.name}: {e}\n")
        return None

class Command(BaseCommand):
    help = "Generates roast articles for all leagues."

    def handle(self, *args, **kwargs):
        current_week = fetch_current_nfl_week()
        if not current_week:
            print("Failed to fetch the current NFL week.")
            return

        leagues = League.objects.filter(Q(status='in_season') | Q(status='pre_draft'))
        for league in leagues:
            try:
                print(f"\nGenerating roast article for League: {league.name}")
                content = generate_roast_article(league)
                print(f"Content returned: {content}")
                
                if content:
                    article, created = Article.objects.update_or_create(
                        sleeper_league_id=league,
                        week=current_week,  
                        label='roster_roast',
                        defaults={
                            'content': content,
                        }
                    )
                    if created:
                        print(f"Roast article for League: {league.name} created successfully.")
                    else:
                        print(f"Roast article for League: {league.name} updated successfully.")
                else:
                    print(f"Failed to generate roast article for League: {league.name}. Content was None.")
            except Exception as e:
                print(f"Error in generate_roast_article for League: {league.name}")
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