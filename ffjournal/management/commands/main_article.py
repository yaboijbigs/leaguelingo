import os
import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from openai import OpenAI
from ffjournal.models import League, Matchup, Roster, Player, Article, Team
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure OpenAI
api_key = settings.OPENAI_API_KEY
client = OpenAI(api_key=api_key)

# Configure logging
logging.basicConfig(filename='detailed_comparison.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Pydantic model for validating the article content
class ArticleContent(BaseModel):
    content: str

def generate_main_article(league_id, week):
    # Query week 1 matchups, starters, and projected points
    matchups = Matchup.objects.filter(sleeper_league_id=league_id, week=week)
    
    matchup_data = []
    for matchup in matchups:
        roster = Roster.objects.filter(sleeper_league_id=league_id, roster_id=matchup.roster_id).first()
        
        # Fetch the team name
        team = Team.objects.filter(sleeper_league_id=league_id, sleeper_user_id=roster.owner_id).first()
        team_name = team.team_name if team else f"Team {roster.owner_id}"
        
        starters = roster.starters
        
        starter_data = []
        for starter in starters:
            player = Player.objects.filter(player_id=starter).first()
            if player is not None and 'fantasy_positions' in player.data:
                starter_data.append(f"{player.full_name} - {player.data['fantasy_positions']} - {player.rank_ave}")
            else:
                logging.warning(f"Skipping player with ID {starter} due to missing data")
        
        if starter_data:
            matchup_data.append(f"Team: {team_name}, Starters: {', '.join(starter_data)}, Points: {matchup.points}")
        else:
            logging.warning(f"No valid starters found for team {team_name}")
    
    # Generate the article using OpenAI
    matchup_data_str = "\n".join(matchup_data)
    prompt = f"Generate a fantasy football article for Week {week} based on the following matchup data:\n\n{matchup_data_str}"

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",  # or whichever model you're using
            messages=[
                {"role": "system", "content": "You are a fantasy football analyst writing weekly articles. Provide your response in JSON format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=3000
        )
        
        # Print the raw response from OpenAI
        print("OpenAI API Response:")
        print(completion)
        print("\nResponse Content:")
        print(completion.choices[0].message.content)
        
        article_content = ArticleContent.parse_raw(completion.choices[0].message.content)
        
        # Save the generated article to the database
        Article.objects.create(
            sleeper_league_id=League.objects.get(sleeper_league_id=league_id),
            week=week,
            content=article_content.content
        )
        
        return article_content.content
    
    except Exception as e:
        logging.error(f"Error generating article: {e}", exc_info=True)
        raise


# Django management command to run the script
class Command(BaseCommand):
    help = "Generate and store a fantasy football article for a specific league and week."

    def add_arguments(self, parser):
        parser.add_argument('league_id', type=str, help="Sleeper league ID")
        parser.add_argument('week', type=int, help="Week number")

    def handle(self, *args, **kwargs):
        league_id = kwargs['league_id']
        week = kwargs['week']
        
        article_content = generate_main_article(league_id, week)
        self.stdout.write(self.style.SUCCESS(f"Article for Week {week} generated and saved successfully."))
