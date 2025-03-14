from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from allauth.account.forms import SignupForm
from .models import CustomUser
from ffjournal.models import League


class SleeperLeagueIDForm(forms.Form):
    league_id = forms.CharField(max_length=255, label='Sleeper League ID')

    def clean_league_id(self):
        league_id = self.cleaned_data['league_id']
        if League.objects.filter(sleeper_league_id=league_id).exists():
            raise forms.ValidationError("This league is already registered with us. Please contact the league manager.")
        return league_id

class AddLeagueForm(forms.Form):
    league_id = forms.CharField(max_length=255, label='Sleeper League ID')

    def clean_league_id(self):
        league_id = self.cleaned_data.get('league_id')
        if League.objects.filter(sleeper_league_id=league_id).exists():
            raise forms.ValidationError("This league has already been added.")
        return league_id


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('email', 'username',)

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'username',)

class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super(CustomSignupForm, self).__init__(*args, **kwargs)
        self.fields['email'].label = "Your Email Address"

    def save(self, request):
        # Override save to do nothing (prevent user creation here)
        # Instead, we'll store the data in the session and create the user after payment
        return None

