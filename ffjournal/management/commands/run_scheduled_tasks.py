import os
from datetime import datetime, timedelta
import pytz
from django.core.management.base import BaseCommand
from ffjournal.models import League, Article
from django.utils import timezone
from django.conf import settings
import requests
from importlib import import_module
from ffjournal.management.commands.send_newsletters import Command as SendNewslettersCommand
from django.utils.dateparse import parse_date

class Command(BaseCommand):
    help = 'Check league schedules and run tasks if scheduled time is reached.'

    def handle(self, *args, **kwargs):
        current_time = timezone.now()
        current_week = self.fetch_current_nfl_week()

        if not current_week:
            self.stdout.write(self.style.ERROR("Failed to fetch the current NFL week."))
            return

        leagues = League.objects.filter(status='in_season')
        self.stdout.write(f"Found {leagues.count()} leagues in season.")

        eligible_leagues = []
        for league in leagues:
            if self.should_run_task(league, current_time):
                eligible_leagues.append(league)

        if eligible_leagues:
            self.run_league_tasks(eligible_leagues, current_week)
        else:
            self.stdout.write("No tasks were scheduled to run for any leagues.")

    def should_run_task(self, league, current_time):
        if not league.scheduled_day or not league.scheduled_time:
            self.stdout.write(f"League {league.name} has no scheduled day or time.")
            return False
        
        league_timezone = pytz.timezone(settings.TIME_ZONE)
        current_time_local = current_time.astimezone(league_timezone)
        
        # Create a datetime for the scheduled time today
        scheduled_time_today = datetime.combine(current_time_local.date(), league.scheduled_time)
        scheduled_time_today = league_timezone.localize(scheduled_time_today)
        
        self.stdout.write(f"League {league.name} scheduled for {league.scheduled_day} at {league.scheduled_time}")
        self.stdout.write(f"Current time: {current_time_local}, Scheduled time today: {scheduled_time_today}")
        
        # Check if it's the scheduled day and past the scheduled time
        if current_time_local.strftime('%A') == league.scheduled_day and current_time_local >= scheduled_time_today:
            last_run_time = league.last_run_time
            if not last_run_time or last_run_time < scheduled_time_today:
                self.stdout.write(f"Task should run for league {league.name}")
                return True
            else:
                self.stdout.write(f"Task already ran this week for league {league.name}")
        else:
            self.stdout.write(f"Not the scheduled day or time for league {league.name}")
        
        return False

    def run_league_tasks(self, leagues, current_week):
        weekly_scripts_dir = f"ffjournal.management.commands.weekly_scripts.week{current_week}"
        self.stdout.write(f"Looking for scripts in {weekly_scripts_dir}")

        try:
            script_files = [f for f in os.listdir(os.path.join(settings.BASE_DIR, weekly_scripts_dir.replace(".", "/"))) if f.endswith(".py") and f != "__init__.py"]
            self.stdout.write(f"Found script files: {script_files}")
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Weekly scripts directory not found for week {current_week}."))
            return

        for script_file in script_files:
            script_module = f"{weekly_scripts_dir}.{script_file[:-3]}"
            self.stdout.write(f"Running {script_module} for all eligible leagues...")

            module = import_module(script_module)
            script_instance = module.Command()

            for league in leagues:
                # Determine the week the script will create articles for
                if 'generate_last_week_recap' in script_module:
                    week_to_check = current_week - 1
                else:
                    week_to_check = current_week

                try:
                    # Run the script for the league
                    script_instance.handle(league_id=league.id)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"{script_module} failed for league {league.name}. Error: {e}"))
                    continue  # Continue with the next league

        for league in leagues:
            send_newsletters_instance = SendNewslettersCommand()
            self.stdout.write(f"Sending newsletters for league {league.name}...")
            send_newsletters_instance.handle(league_id=league.id)
            league.last_run_time = timezone.now()
            league.save()


    def fetch_current_nfl_week(self):
        """Fetches the current NFL week from the Sleeper API."""
        url = "https://api.sleeper.app/v1/state/nfl"
        response = requests.get(url)
        if response.status_code == 200:
            nfl_state = response.json()
            return nfl_state['week']
        self.stdout.write(self.style.ERROR(f"Failed to fetch NFL state. Status code: {response.status_code}"))
        return None

    def verify_article_creation(self, league, week, script_module):
        """Verify that at least one article was created by the script."""
        # Instead of mapping script modules to specific labels, we'll check if any new article was created for the league and week after running the script.

        # Get the count of articles before running the script
        articles_before = Article.objects.filter(
            sleeper_league_id=league.sleeper_league_id,
            week=week
        ).count()

        # Run the script (this would be handled elsewhere in the code)

        # Get the count of articles after running the script
        articles_after = Article.objects.filter(
            sleeper_league_id=league.sleeper_league_id,
            week=week
        ).count()

        # Verify that new articles were created
        if articles_after > articles_before:
            return True
        else:
            self.stdout.write(self.style.ERROR(f"No new articles were created by {script_module} for league {league.name}."))
            return False