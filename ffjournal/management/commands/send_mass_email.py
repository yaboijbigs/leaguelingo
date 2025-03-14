from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from ffjournal.models import LeagueMemberEmail

class Command(BaseCommand):
    help = 'Sends an email to all confirmed email addresses'

    def handle(self, *args, **options):
        # Get all confirmed email addresses
        confirmed_emails = LeagueMemberEmail.objects.filter(confirmed=True)

        # Render the email template without any context
        email_html = render_to_string('ffjournal/mass_email_template.html')

        # Send the email to each confirmed address
        for email_obj in confirmed_emails:
            send_mail(
                'Well fuck. Sorry about that.',
                '',  # leave empty to skip text content
                'sportswriter@lol.com',
                [email_obj.email],
                html_message=email_html,
            )

        self.stdout.write(self.style.SUCCESS(f"Sent emails to {confirmed_emails.count()} confirmed addresses"))