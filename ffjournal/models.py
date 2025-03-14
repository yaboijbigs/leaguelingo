from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.core.validators import EmailValidator
from django.utils import timezone
import datetime
import uuid
from django.db.models import JSONField
from django.contrib.postgres.fields import ArrayField

def generate_default_owner_id():
    return f"CPU_{uuid.uuid4().hex[:8]}"

class League(models.Model):
    sleeper_league_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leagues_owned', null=True, blank=True)
    latest_league_winner_roster_id = models.CharField(max_length=255, null=True, blank=True)
    waiver_budget = models.IntegerField(null=True, blank=True)
    playoff_teams = models.IntegerField()
    veto_votes_needed = models.IntegerField(null=True, blank=True)
    num_teams = models.IntegerField()
    playoff_week_start = models.IntegerField()
    trade_deadline = models.IntegerField(null=True, blank=True)
    pick_trading = models.IntegerField(null=True, blank=True)
    max_keepers = models.IntegerField(null=True, blank=True)
    draft_id = models.CharField(max_length=255, null=True, blank=True)
    previous_league_id = models.CharField(max_length=255, null=True, blank=True)
    total_rosters = models.IntegerField()
    data = models.JSONField()  # Django uses JSONField instead of JSONB
    custom_system_prompt = models.CharField(max_length=500, blank=True, null=True)
    weekly_newsletter_pdf = models.CharField(max_length=255, null=True, blank=True)
    scheduled_day = models.CharField(max_length=10, null=True, blank=True, default='Thursday')
    scheduled_time = models.TimeField(null=True, blank=True, default=datetime.time(12, 0))  # 12:00 PM
    last_updated = models.DateTimeField(null=True, blank=True)
    last_run_time = models.DateTimeField(null=True, blank=True)

    def can_update_schedule(self):
        if not self.last_updated:
            return True
        # Allow update only if a week has passed since the last update
        return timezone.now() >= self.last_updated + timezone.timedelta(weeks=1)

    def __str__(self):
        return self.name

class LeagueMemberEmail(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='member_emails')
    email = models.EmailField(validators=[EmailValidator()])
    unsubscribed = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)
    subscribed_at = models.DateTimeField(default=timezone.now)
    last_confirmation_sent = models.DateTimeField(null=True, blank=True)  # To track when confirmation was last sent

    def __str__(self):
        return f"{self.email} - {self.league.name}"

class Roster(models.Model):
    sleeper_league_id = models.ForeignKey(League, on_delete=models.CASCADE, to_field='sleeper_league_id')
    roster_id = models.IntegerField()
    owner_id = models.CharField(max_length=255, default=generate_default_owner_id)
    co_owners = models.JSONField(null=True, blank=True)
    keepers = models.JSONField(null=True, blank=True)
    players = models.JSONField()
    starters = models.JSONField()

class Team(models.Model):
    sleeper_user_id = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    avatar = models.CharField(max_length=255, null=True, blank=True)
    team_name = models.CharField(max_length=255, null=True, blank=True)
    is_owner = models.BooleanField(null=True, blank=True)
    sleeper_league_id = models.ForeignKey(League, on_delete=models.CASCADE, to_field='sleeper_league_id')
    is_team_owner = models.BooleanField(null=True, blank=True)
    is_co_owner = models.BooleanField()

class Matchup(models.Model):
    sleeper_league_id = models.ForeignKey(League, on_delete=models.CASCADE, to_field='sleeper_league_id')
    matchup_id = models.IntegerField(null=True, blank=True)
    roster_id = models.IntegerField(null=True, blank=True)
    points = models.FloatField(null=True, blank=True)
    custom_points = models.FloatField(null=True, blank=True)
    week = models.IntegerField()
    players = ArrayField(models.CharField(max_length=20), blank=True, null=True)
    starters = ArrayField(models.CharField(max_length=20), blank=True, null=True)
    starters_points = ArrayField(models.FloatField(), blank=True, null=True)
    players_points = JSONField(null=True, blank=True)  # This should now use the built-in JSONField

class Player(models.Model):
    player_id = models.CharField(max_length=255, unique=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    position = models.CharField(max_length=255, null=True, blank=True)
    team = models.CharField(max_length=255, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    college = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
    height = models.CharField(max_length=255, null=True, blank=True)
    weight = models.CharField(max_length=255, null=True, blank=True)
    injury_status = models.CharField(max_length=255, null=True, blank=True)
    injury_body_part = models.CharField(max_length=255, null=True, blank=True)
    injury_start_date = models.CharField(max_length=255, null=True, blank=True)
    injury_notes = models.CharField(max_length=255, null=True, blank=True)
    practice_participation = models.CharField(max_length=255, null=True, blank=True)
    practice_description = models.CharField(max_length=255, null=True, blank=True)
    birth_date = models.CharField(max_length=255, null=True, blank=True)
    birth_city = models.CharField(max_length=255, null=True, blank=True)
    birth_state = models.CharField(max_length=255, null=True, blank=True)
    birth_country = models.CharField(max_length=255, null=True, blank=True)
    years_exp = models.IntegerField(null=True, blank=True)
    high_school = models.CharField(max_length=255, null=True, blank=True)
    data = models.JSONField()
    rank_ave = models.FloatField(null=True, blank=True)

class Event(models.Model):
    sleeper_league_id = models.ForeignKey(League, on_delete=models.CASCADE, to_field='sleeper_league_id')
    transaction_id = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    settings = models.JSONField(null=True, blank=True)
    event_metadata = models.JSONField(null=True, blank=True)
    leg = models.IntegerField()
    draft_picks = models.JSONField(null=True, blank=True)
    creator = models.CharField(max_length=255)
    created = models.BigIntegerField()
    consenter_ids = models.JSONField(null=True, blank=True)
    roster_ids = models.JSONField()
    adds = models.JSONField(null=True, blank=True)
    drops = models.JSONField(null=True, blank=True)
    waiver_budget = models.JSONField(null=True, blank=True)
    status_updated = models.BigIntegerField()

class Article(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('sent', 'Sent'),
    ]

    sleeper_league_id = models.ForeignKey(League, on_delete=models.CASCADE, to_field='sleeper_league_id')
    week = models.IntegerField()
    label = models.CharField(max_length=255)
    title = models.CharField(max_length=255, default="Placeholder Title")  # New field for the article title
    content = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')

    def __str__(self):
        return f"{self.title} - Week {self.week} - League {self.sleeper_league_id.name}"

class Newsletter(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    week = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to='newsletters/', null=True, blank=True)
    articles = models.ManyToManyField(Article)

    class Meta:
        unique_together = ('league', 'week')

    def __str__(self):
        return f"Week {self.week} - {self.league.name}"

class PlayerProjection(models.Model):
    week = models.IntegerField()
    pts_ppr = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, to_field='player_id')
    opponent = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ('week', 'player')

    def __str__(self):
        return f"{self.player.full_name} - Week {self.week}"
    

class PlayerStats(models.Model):
    week = models.IntegerField()
    pts_ppr = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, to_field='player_id')
    opponent = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ('week', 'player')

    def __str__(self):
        return f"{self.player.full_name} - Week {self.week}"
    
class TrendingUpPlayer(models.Model):
    player_id = models.CharField(max_length=255, null=True, blank=True)  # Changed from ForeignKey to CharField
    count = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.player.full_name} - Up {self.count}"

class TrendingDownPlayer(models.Model):
    player_id = models.CharField(max_length=255, null=True, blank=True)  # Changed from ForeignKey to CharField
    count = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.player_id} - Down {self.count}"