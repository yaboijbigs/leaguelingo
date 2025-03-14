from django.contrib import admin, messages
from django.urls import path, reverse
from django.shortcuts import redirect, HttpResponseRedirect
from django.core.management import call_command
from .models import League, Roster, Team, Matchup, Player, Event, Article
from .sleeper_api import fetch_league_data, fetch_roster_data, fetch_team_data, fetch_all_matchup_data, fetch_all_transactions_data
from django.db import transaction
from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group, User
from accounts.models import CustomUser, Profile
from django.contrib.auth.admin import UserAdmin


# Admin action to refresh all league data
@admin.action(description='Refresh all league data')
def refresh_all_leagues(modeladmin, request, queryset):
    leagues = League.objects.all()
    for league in leagues:
        try:
            with transaction.atomic():
                fetch_league_data(league.sleeper_league_id)
                if league.status != 'complete':
                    fetch_roster_data(league.sleeper_league_id)
                    fetch_team_data(league.sleeper_league_id)
                    fetch_all_matchup_data(league.sleeper_league_id)
                    fetch_all_transactions_data(league.sleeper_league_id)
        except Exception as e:
            modeladmin.message_user(request, f"Error refreshing league {league.name}: {str(e)}", level='error')
        else:
            modeladmin.message_user(request, f"Successfully refreshed league {league.name}", level='success')

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'sleeper_league_id', 'status')
    search_fields = ('name', 'sleeper_league_id')
    actions = [refresh_all_leagues]

@admin.register(Roster)
class RosterAdmin(admin.ModelAdmin):
    list_display = ('sleeper_league_id', 'roster_id', 'owner_id')
    search_fields = ('sleeper_league_id__sleeper_league_id', 'owner_id')

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('sleeper_user_id', 'team_name', 'is_owner')
    search_fields = ('sleeper_user_id', 'team_name')

@admin.register(Matchup)
class MatchupAdmin(admin.ModelAdmin):
    list_display = ('sleeper_league_id', 'matchup_id', 'week', 'points')
    search_fields = ('sleeper_league_id__sleeper_league_id', 'week')

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('player_id', 'full_name', 'team', 'position', 'rank_ave')
    search_fields = ('player_id', 'full_name', 'team')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'type', 'status')
    search_fields = ('transaction_id', 'sleeper_league_id__sleeper_league_id')

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('sleeper_league_id', 'week')
    search_fields = ('sleeper_league_id__sleeper_league_id', 'week')

# Custom Admin Site
class MyAdminSite(admin.AdminSite):
    site_header = 'League Lingo Admin'
    site_title = 'League Lingo Admin Portal'
    index_title = 'Welcome to the League Lingo Admin Portal'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('fetch-players/', self.admin_view(self.fetch_players), name='fetch_players'),
        ]
        return custom_urls + urls

    def fetch_players(self, request):
        try:
            call_command('fetch_players')
            self.message_user(request, "Player data has been updated successfully!", messages.SUCCESS)
            print("Fetch Players Command Executed")  # Add this line for debugging
        except Exception as e:
            self.message_user(request, f"Error: {str(e)}", messages.ERROR)
            print(f"Error: {str(e)}")  # Add this line for debugging
        return HttpResponseRedirect(reverse('admin:index'))

    def index(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context['fetch_players_url'] = reverse('admin:fetch_players')
        return super().index(request, extra_context)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False

class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)

    # This method will list the league IDs associated with the user
    def get_leagues(self, obj):
        return ", ".join([league.sleeper_league_id for league in obj.profile.leagues.all()])
    get_leagues.short_description = 'Leagues'

    list_display = ['username', 'email', 'get_leagues']

# Register the custom admin site
admin_site = MyAdminSite(name='myadmin')

admin_site.register(League, LeagueAdmin)
admin_site.register(Roster, RosterAdmin)
admin_site.register(Team, TeamAdmin)
admin_site.register(Matchup, MatchupAdmin)
admin_site.register(Player, PlayerAdmin)
admin_site.register(Event, EventAdmin)
admin_site.register(Article, ArticleAdmin)
admin_site.register(Group)
admin_site.register(User)
admin_site.register(EmailAddress)
admin_site.register(CustomUser, CustomUserAdmin)
admin_site.register(Profile)
