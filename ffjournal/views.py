from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from django.core.management import call_command
from .models import League, LeagueMemberEmail, Article, Newsletter
from accounts.models import CustomUser  # This is your custom user model
from .sleeper_api import fetch_league_data, fetch_team_data, fetch_all_matchup_data, fetch_roster_data, fetch_all_transactions_data
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from .forms import LeagueMemberEmailForm, CustomizeWriterForm, SupportForm  # Add this import
from django.template.loader import render_to_string
from django.conf import settings
from django.core.mail import send_mail
from accounts.models import Profile
from django.contrib import messages
from django.http import HttpResponseRedirect, HttpResponse
from django import forms
from django.http import HttpResponseForbidden
from django.http import FileResponse, Http404
from .decorators import user_is_league_owner
from datetime import timedelta
from django.http import HttpRequest
from django.utils import timezone
import time
from .forms import ScheduleForm
import os
import logging
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def fetch_players(request):
    try:
        call_command('fetch_players')
        messages.success(request, 'Player data fetched successfully.')
    except Exception as e:
        messages.error(request, f'Error fetching player data: {str(e)}')
    return HttpResponseRedirect(reverse('admin:index'))

def home(request):
    if request.method == 'POST':
        league_id = request.POST.get('league_id')
        fetch_league_data(league_id)  # Removed the db argument
        return redirect('home')
    return render(request, 'ffjournal/home.html')

def leagues(request):
    leagues = League.objects.all()  # Use Django's ORM to fetch all League instances
    return render(request, 'ffjournal/leagues.html', {'leagues': leagues})

def refresh_data(request):
    if request.method == 'POST':
        try:
            leagues = League.objects.all()  # Use Django ORM to fetch all League instances
            for league in leagues:
                fetch_league_data(league.sleeper_league_id)  # Removed the db argument
                if league.status != 'complete':
                    fetch_roster_data(league.sleeper_league_id)  # Removed the db argument
                    fetch_team_data(league.sleeper_league_id)  # Removed the db argument
                    fetch_all_matchup_data(league.sleeper_league_id)  # Removed the db argument
                    fetch_all_transactions_data(league.sleeper_league_id)  # Removed the db argument
            return JsonResponse({"message": "Data refreshed successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

@login_required
def my_leagues_view(request):
    # Placeholder context; you can add data later
    context = {}
    return render(request, 'my_leagues.html', context)

@login_required
@user_is_league_owner
def manage_league_emails_view(request, league_id):
    league = get_object_or_404(League, id=league_id, profiles__user=request.user)
    emails = league.member_emails.all()

    if request.method == 'POST':
        if 'add_email' in request.POST:
            form = LeagueMemberEmailForm(request.POST)
            if form.is_valid():
                if emails.count() < 32:  # Check if they have less than 32 emails
                    email_instance = form.save(commit=False)
                    email_instance.league = league
                    
                    # Automatically confirm if the email belongs to the logged-in user
                    if email_instance.email == request.user.email:
                        email_instance.confirmed = True
                    email_instance.save()

                    if not email_instance.confirmed:
                        send_confirmation_email(request, email_instance)  # Send confirmation email

                    return redirect('manage_league_emails', league_id=league_id)
                else:
                    form.add_error(None, 'You cannot add more than 32 emails.')
        elif 'remove_email' in request.POST:
            email_id = request.POST.get('remove_email')
            email_to_remove = get_object_or_404(LeagueMemberEmail, id=email_id, league=league)
            email_to_remove.delete()
            return redirect('manage_league_emails', league_id=league_id)
        elif 'resend_confirmation' in request.POST:
            email_id = request.POST.get('resend_confirmation')
            email_instance = get_object_or_404(LeagueMemberEmail, id=email_id, league=league)

            # Check if 15 minutes have passed since the last confirmation was sent
            if email_instance.last_confirmation_sent and timezone.now() < email_instance.last_confirmation_sent + timedelta(minutes=15):
                messages.error(request, "You can only resend the confirmation email once every 15 minutes.")
            else:
                send_confirmation_email(request, email_instance)
                email_instance.last_confirmation_sent = timezone.now()
                email_instance.save()
                messages.success(request, "Confirmation email resent successfully.")

            return redirect('manage_league_emails', league_id=league_id)
    else:
        form = LeagueMemberEmailForm()

    return render(request, 'ffjournal/manage_league_emails.html', {
        'league': league,
        'emails': emails,
        'form': form,
    })


def send_confirmation_email(request, email_instance):
    league = email_instance.league
    confirmation_url = f"http://{request.get_host()}/ffjournal/confirm-email/{email_instance.id}/"
    
    subject = f"Confirm Your Subscription to {league.name}"
    message = render_to_string('ffjournal/email_confirmation.html', {
        'league': league,
        'confirmation_url': confirmation_url,
    })
    send_mail(subject, '', 'noreply@lol.com', [email_instance.email], html_message=message, fail_silently=False)
    
def confirm_email(request, email_id):
    email_instance = get_object_or_404(LeagueMemberEmail, id=email_id)
    if not email_instance.confirmed:
        email_instance.confirmed = True
        email_instance.save()
    
    messages.success(request, 'Your email has been confirmed.')
    
    return redirect('confirmation_success')

def confirmation_success(request):
    return render(request, 'ffjournal/confirmation_success.html')

def send_newsletter(league, week):
    # Fetch articles for the given league and week
    articles = Article.objects.filter(sleeper_league_id=league, week=week)
    
    if not articles.exists():
        return  # No articles, no email

    # Render the email content
    subject = f"Weekly Newsletter - Week {week}"
    message = render_to_string('emails/newsletter_email.html', {
        'week': week,
        'league_name': league.name,
        'articles': articles
    })
    
    # Fetch league member emails (assuming league.members is a list of emails)
    recipient_list = [member.email for member in league.members.all()]

    # Send the email
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
        fail_silently=False,
    )

@staff_member_required
def admin_dashboard_view(request):
    # Fetch data for the overview
    total_users = Profile.objects.count()
    total_leagues = League.objects.count()
    paid_leagues = Profile.objects.filter(has_paid=True).count()
    unpaid_leagues = total_leagues - paid_leagues
    newsletters_sent = Article.objects.filter(status='sent').count()
    newsletters_pending = Article.objects.filter(status='pending').count()

    context = {
        'total_users': total_users,
        'total_leagues': total_leagues,
        'paid_leagues': paid_leagues,
        'unpaid_leagues': unpaid_leagues,
        'newsletters_sent': newsletters_sent,
        'newsletters_pending': newsletters_pending,
        'fetch_players_url': reverse('fetch_players'),
    }

    return render(request, 'admin/dashboard.html', context)

@login_required
@user_is_league_owner
class SystemPromptForm(forms.ModelForm):
    class Meta:
        model = League
        fields = ['custom_system_prompt']
        widgets = {
            'custom_system_prompt': forms.Textarea(attrs={'maxlength': 500}),
        }

@login_required
@user_is_league_owner
def customize_sports_writer(request, league_id):
    league = get_object_or_404(League, id=league_id)  # Change league_id to id
    if request.method == 'POST':
        form = CustomizeWriterForm(request.POST, instance=league)  # Pass instance
        if form.is_valid():
            form.save()  # Save the form directly
            return redirect('my_leagues')
    else:
        form = CustomizeWriterForm(instance=league)  # Pass instance
    return render(request, 'ffjournal/customize_sports_writer.html', {'form': form, 'league': league})


@login_required
@user_is_league_owner
def view_newsletters(request, league_id):
    league = get_object_or_404(League, id=league_id, profiles__user=request.user)
    
    # Get the latest newsletter for each week
    newsletters = (
        Newsletter.objects.filter(league=league)
        .order_by('week', '-created_at')
        .distinct('week')
    )
    
    # Generate PDF URLs for each newsletter
    newsletters_with_urls = []
    for newsletter in newsletters:
        if newsletter.pdf_file:
            pdf_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{newsletter.pdf_file}"
            newsletters_with_urls.append((newsletter, pdf_url))
        else:
            newsletters_with_urls.append((newsletter, None))
    
    return render(request, 'ffjournal/view_newsletters.html', {
        'league': league, 
        'newsletters': newsletters_with_urls
    })


@login_required
@user_is_league_owner
def view_newsletter(request, league_id, newsletter_id):
    league = get_object_or_404(League, id=league_id, profiles__user=request.user)
    newsletter = get_object_or_404(Newsletter, id=newsletter_id, league=league)

    pdf_file_name = f"newsletters/league_{league.id}_week_{newsletter.week}.pdf"

    # Check if the file exists in your storage
    if default_storage.exists(pdf_file_name):
        # Generate a URL for the PDF file and redirect to it
        pdf_url = default_storage.url(pdf_file_name)
        return redirect(pdf_url)
    else:
        raise Http404("The requested newsletter PDF is not available.")

@login_required
@user_is_league_owner
def customize_sports_writer_view(request, league_id):
    league = get_object_or_404(League, id=league_id, profiles__user=request.user)
    # Add your logic for customizing the sports writer here
    return render(request, 'ffjournal/customize_sports_writer.html', {'league': league})

@login_required
def support_view(request):
    if request.method == 'POST':
        form = SupportForm(request.POST)
        if form.is_valid():
            # Gather form data
            email = form.cleaned_data['email']
            phone = form.cleaned_data['phone']
            league_id = form.cleaned_data['league_id']
            complaint = form.cleaned_data['complaint']
            
            # Compose email content
            subject = 'Support Request'
            message = f"Email: {email}\nPhone: {phone}\nLeague ID: {league_id}\n\nComplaint:\n{complaint}"
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [settings.SUPPORT_EMAIL]  # Define this in your settings.py

            # Send the email
            send_mail(subject, message, from_email, recipient_list)

            # Show a thank you message
            return render(request, 'ffjournal/support_thankyou.html')

    else:
        form = SupportForm()

    return render(request, 'ffjournal/support.html', {'form': form})

def unsubscribe_view(request, email_id):
    email_instance = get_object_or_404(LeagueMemberEmail, id=email_id)
    
    if request.method == 'POST':
        email_instance.unsubscribed = True
        email_instance.unsubscribed_at = timezone.now()
        email_instance.save()
        return redirect('confirmation_success')
    
    return render(request, 'ffjournal/unsubscribe_confirm.html', {'email_instance': email_instance})

@login_required
def configure_sending(request, league_id):
    league = League.objects.get(id=league_id)

    # Pre-populate the form with the current settings
    initial_data = {
        'day': league.scheduled_day,
        'time': league.scheduled_time,
    }
    form = ScheduleForm(initial=initial_data)

    if request.method == 'POST':
        if not league.can_update_schedule():
            messages.error(request, 'You can only update your schedule once a week.')
        else:
            form = ScheduleForm(request.POST)
            if form.is_valid():
                league.scheduled_day = form.cleaned_data['day']
                league.scheduled_time = form.cleaned_data['time']
                league.last_updated = timezone.now()  # Update the last_updated time
                league.save()
                messages.success(request, 'Schedule updated successfully.')
                return redirect('my_leagues')
    else:
        # Still allow them to see the form with current values
        form = ScheduleForm(initial=initial_data)

    return render(request, 'ffjournal/configure_sending.html', {'form': form, 'league': league})
