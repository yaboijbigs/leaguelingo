import stripe
from django.shortcuts import render, redirect, get_object_or_404
from .forms import SleeperLeagueIDForm, CustomSignupForm, AddLeagueForm
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
import requests
from django.db import transaction
from django.conf import settings
from django.urls import reverse
from allauth.account.views import SignupView
from django import forms
from django.contrib.auth.decorators import login_required
from ffjournal.models import League, Article, LeagueMemberEmail
from ffjournal.sleeper_api import (
    fetch_league_data,
    fetch_roster_data,
    fetch_team_data,
    fetch_all_matchup_data,
    fetch_all_transactions_data,
)
from ffjournal.decorators import user_is_league_owner

def error_view(request):
    return render(request, 'accounts/error.html')

stripe.api_ = settings.STRIPE_SECRET_KEY

def league_id_check_view(request):
    if request.method == 'POST':
        form = SleeperLeagueIDForm(request.POST)
        if form.is_valid():
            league_id = form.cleaned_data['league_id']

            # Check the league status via the Sleeper API
            url = f"https://api.sleeper.app/v1/league/{league_id}"
            response = requests.get(url)

            if response.status_code == 200:
                league_data = response.json()
                league_status = league_data.get('status')

                # Reject if the league is complete
                if league_status == 'complete':
                    form.add_error('league_id', 'This league is already completed and cannot be used.')
                    return render(request, 'account/league_id_check.html', {'form': form})

                # Check if the league already exists in the database
                if League.objects.filter(sleeper_league_id=league_id).exists():
                    form.add_error('league_id', 'This league is already registered with us. Please contact the league manager.')
                    return render(request, 'account/league_id_check.html', {'form': form})

                # Store the league_id in the session and proceed to sign-up
                request.session['league_id'] = league_id
                return redirect('account_signup')
            else:
                form.add_error('league_id', 'Failed to retrieve league information. Please check the ID and try again.')
                return render(request, 'account/league_id_check.html', {'form': form})
    else:
        form = SleeperLeagueIDForm()

    return render(request, 'account/league_id_check.html', {'form': form})

def test_view(request):
    return render(request, 'account/test.html')

def privacy_policy(request):
    return render(request, 'account/privacy_policy.html')

def terms_of_service(request):
    return render(request, 'account/terms_of_service.html')

class CustomSignupView(SignupView):
    form_class = CustomSignupForm

    def form_valid(self, form):
        # Store form data in the session, do NOT create the user
        self.request.session['signup_data'] = {
            'email': form.cleaned_data.get('email'),
            'password': form.cleaned_data.get('password1'),
        }
        # Redirect to the payment page
        return redirect('payment')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = None  # Ensure no user context is passed
        return context

def payment_view(request):
    if request.method == 'POST':
        # Create a Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'League Lingo Subscription',
                    },
                    'unit_amount': 25000,  # Amount in cents ($250.00)
                },
                'quantity': 1,
            }],
            mode='payment',
            allow_promotion_codes=True,
            success_url=request.build_absolute_uri(reverse('payment_success')),
            cancel_url=request.build_absolute_uri(reverse('payment')),
        )
        return redirect(session.url, code=303)
    return render(request, 'account/payment.html')

@login_required
def payment_success_view(request):
    #signup_data = request.session.get('signup_data')
    league_id = request.session.get('league_id')
    profile = request.user.profile

    # Mark user's profile as paid
    profile.has_paid = True
    profile.save()

    if league_id:
        try:
            with transaction.atomic():
                # Pass the current user as the owner
                league = fetch_league_data(league_id, owner=request.user)
                
                if league.status != 'complete':
                    fetch_roster_data(league_id)
                    fetch_team_data(league_id)
                    fetch_all_matchup_data(league_id)
                    fetch_all_transactions_data(league_id)

                # Ensure the object is retrieved fresh from the database
                league = League.objects.get(sleeper_league_id=league_id)

                profile.leagues.add(league)  # Attempt to add the league
                profile.save()

                LeagueMemberEmail.objects.create(
                    league=league,
                    email=request.user.email
                )

                user_email = request.user.email
                email_instance = LeagueMemberEmail.objects.filter(email=user_email, league=league).first()
                email_instance.confirmed = True
                email_instance.save()

                request.session.pop('league_id', None)
                return redirect('my_leagues')

        except Exception as e:
            # Handle any exceptions that occur during league creation
            print(f"Error creating league: {str(e)}")
            return redirect('error')
    else:
        return redirect('my_leagues')

@login_required
def my_leagues_view(request):
    profile = request.user.profile
    leagues = profile.leagues.all()
    add_league_form = AddLeagueForm()

    if request.method == 'POST':
        add_league_form = AddLeagueForm(request.POST)
        if add_league_form.is_valid():
            league_id = add_league_form.cleaned_data['league_id']

            # Check the league status via the Sleeper API
            url = f"https://api.sleeper.app/v1/league/{league_id}"
            response = requests.get(url)

            if response.status_code == 200:
                league_data = response.json()
                league_status = league_data.get('status')

                # Reject if the league is complete
                if league_status == 'complete':
                    add_league_form.add_error('league_id', 'This league is already completed and cannot be added.')
                    return render(request, 'account/my_leagues.html', {'leagues': leagues, 'add_league_form': add_league_form})

                # Check if the league already exists in the database
                if League.objects.filter(sleeper_league_id=league_id).exists():
                    add_league_form.add_error('league_id', 'This league is already registered with us. Please contact the league manager.')
                    return render(request, 'account/my_leagues.html', {'leagues': leagues, 'add_league_form': add_league_form})

                # Store league_id in the session for use after payment
                request.session['additional_league_id'] = league_id

                # Redirect to the payment page
                return redirect('additional_league_payment')  # Redirect to the payment view

            else:
                add_league_form.add_error('league_id', 'Failed to retrieve league information. Please check the ID and try again.')
                return render(request, 'account/my_leagues.html', {'leagues': leagues, 'add_league_form': add_league_form})

    return render(request, 'account/my_leagues.html', {'leagues': leagues, 'add_league_form': add_league_form})



@login_required
def additional_league_payment_view(request):
    league_id = request.session.get('additional_league_id')
    if not league_id:
        return redirect('my_leagues')  # If no league ID, redirect back to the My Leagues page

    # Create a Stripe Checkout session for the additional league payment
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Additional League',
                },
                'unit_amount': 25000,  # $250.00 in cents
            },
            'quantity': 1,
        }],
        mode='payment',
        allow_promotion_codes=True,
        success_url=request.build_absolute_uri(reverse('additional_league_payment_success')),
        cancel_url=request.build_absolute_uri(reverse('my_leagues')),
    )

    # Redirect to the Stripe Checkout session
    return redirect(session.url, code=303)

@login_required
def additional_league_payment_success_view(request):
    league_id = request.session.get('additional_league_id')
    profile = request.user.profile

    # Mark user's profile as paid
    profile.has_paid = True
    profile.save()

    if league_id:
        try:
            with transaction.atomic():
                # Pass the current user as the owner
                league = fetch_league_data(league_id, owner=request.user)
                
                if league.status != 'complete':
                    fetch_roster_data(league_id)
                    fetch_team_data(league_id)
                    fetch_all_matchup_data(league_id)
                    fetch_all_transactions_data(league_id)

                # Ensure the object is retrieved fresh from the database
                league = League.objects.get(sleeper_league_id=league_id)

                profile.leagues.add(league)  # Attempt to add the league
                profile.save()

                LeagueMemberEmail.objects.create(
                    league=league,
                    email=request.user.email
                )

                user_email = request.user.email
                email_instance = LeagueMemberEmail.objects.filter(email=user_email, league=league).first()
                email_instance.confirmed = True
                email_instance.save()

                request.session.pop('additional_league_id', None)
                return redirect('my_leagues')

        except Exception as e:
            # Handle any exceptions that occur during league creation
            print(f"Error creating league: {str(e)}")
            return redirect('error')
    else:
        return redirect('my_leagues')


