from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Profile



class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False

class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)

    # This method will list the league IDs associated with the user
    def get_leagues(self, obj):
        return ", ".join([league.league_id for league in obj.profile.leagues.all()])
    get_leagues.short_description = 'Leagues'

    list_display = ['username', 'email', 'get_leagues']

