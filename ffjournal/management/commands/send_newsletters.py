import os
import django
from django.core.management.base import BaseCommand
import base64
from django.contrib.staticfiles import finders
from leaguelingo.storage_backends import CustomS3Boto3Storage

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leaguelingo.settings')
django.setup()

from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe
from ffjournal.models import League, Article, Newsletter
import requests
import os
from xhtml2pdf import pisa
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from io import BytesIO
from django.db import IntegrityError
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    resources
    """
    # use short variable names
    sUrl = settings.STATIC_URL      # Typically /static/
    sRoot = settings.STATIC_ROOT    # Typically /home/userX/project_static/
    mUrl = settings.MEDIA_URL       # Typically /media/
    mRoot = settings.MEDIA_ROOT     # Typically /home/userX/project_static/media/

    # convert URIs to absolute system paths
    if uri.startswith(mUrl):
        path = os.path.join(mRoot, uri.replace(mUrl, ""))
    elif uri.startswith(sUrl):
        path = os.path.join(sRoot, uri.replace(sUrl, ""))
    else:
        return uri  # handle absolute uri (ie: http://some.tld/foo.png)

    # make sure that file exists
    if not os.path.isfile(path):
        raise Exception(
            'media URI must start with %s or %s' % (sUrl, mUrl)
        )
    return path

class Command(BaseCommand):
    help = 'Send weekly newsletters to a specific league'

    def add_arguments(self, parser):
        parser.add_argument('league_id', type=int, help='The ID of the league to send the newsletter to.')

    def handle(self, *args, **kwargs):
        league_id = kwargs['league_id']
        current_week = self.get_current_week()

        try:
            league = League.objects.get(id=league_id)
            self.send_newsletter(league, current_week)
            self.stdout.write(self.style.SUCCESS(f'Successfully sent newsletter for league {league.name}'))
        except League.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'League with ID {league_id} does not exist'))
    
    def get_current_week(self):
        try:
            response = requests.get("https://api.sleeper.app/v1/state/nfl")
            if response.status_code == 200:
                nfl_state = response.json()
                return nfl_state['week']
            else:
                self.stdout.write(self.style.WARNING(f"Failed to fetch NFL state. Status code: {response.status_code}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching NFL state: {str(e)}"))

        start_date = timezone.datetime(2024, 9, 4)
        now = timezone.now()
        week_number = (now - start_date).days // 7 + 1
        return week_number

    def send_newsletter(self, league, current_week):
        # Fetch all articles for this league and week, excluding individual matchup write-ups
        league_articles = Article.objects.filter(
            sleeper_league_id=league.sleeper_league_id,
            week=current_week
        ).exclude(
            label__startswith='matchup_'
        ).exclude(
            label__startswith='matchup_recap_'
        )

        if not league_articles.exists():
            self.stdout.write(f"No articles found for league {league.name} in week {current_week}")
            return

        # Organize articles by their labels
        articles_content = {}
        for article in league_articles:
            articles_content[article.label] = {
                'title': article.title,
                'content': article.content
            }

        context = {
            'league': league,
            'articles': articles_content,
            'logo_url': f"{settings.SITE_URL}/static/images/logo.png"
        }

        # Generate the PDF file from the HTML content only once
        pdf_result = self.generate_pdf(league, current_week, context)
        if pdf_result:
            pdf_file_name, pdf_url = pdf_result
            if pdf_file_name and pdf_url:
                try:
                    # Create or update a single newsletter for this league and week
                    newsletter, created = Newsletter.objects.update_or_create(
                        league=league,
                        week=current_week,
                        defaults={'pdf_file': pdf_file_name}
                    )

                    # Add all articles to the newsletter
                    newsletter.articles.set(league_articles)

                    # Add the PDF URL to the email context
                    context['pdf_url'] = pdf_url

                    # Send emails to all members
                    for member_email in league.member_emails.filter(unsubscribed=False, confirmed=True):
                        # Update unsubscribe_url for each member
                        context['unsubscribe_url'] = f"{settings.SITE_URL}/ffjournal/unsubscribe/{member_email.id}/"

                        # Re-render the email body with the PDF URL and member-specific unsubscribe URL
                        email_body = render_to_string('ffjournal/newsletter_template.html', context)

                        # Send the email without PDF attachment
                        send_mail(
                            subject=f"Your Weekly Newsletter - {league.name}",
                            message="Your weekly newsletter is now ready.",
                            from_email='sportswriter@lol.com',
                            recipient_list=[member_email.email],
                            fail_silently=False,
                            html_message=email_body
                        )

                        self.stdout.write(self.style.SUCCESS(f"Newsletter sent to {member_email.email} for league {league.name}"))

                except IntegrityError:
                    self.stdout.write(self.style.ERROR(f"Failed to create or update newsletter for league {league.name}"))
            else:
                self.stdout.write(self.style.ERROR(f"PDF generation failed for league {league.name}. Newsletter not sent."))
        else:
            self.stdout.write(self.style.ERROR(f"PDF generation failed for league {league.name}. Newsletter not sent."))

    def generate_pdf(self, league, current_week, context):
        template_path = 'ffjournal/newsletter_template.html'
        html = render_to_string(template_path, context)

        pdf_file_name = f"media/newsletters/league_{league.id}_week_{current_week}.pdf"
        
        pdf_content = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_content, link_callback=link_callback)
        
        if pisa_status.err:
            self.stdout.write(self.style.ERROR(f"Failed to generate PDF for league {league.name}"))
            return None
        else:
            pdf_content.seek(0)
            try:
                # Use the custom S3 storage
                s3_storage = CustomS3Boto3Storage()
                path = s3_storage.save(pdf_file_name, ContentFile(pdf_content.getvalue()))
                logger.info(f"PDF saved successfully: {path}")
                logger.info(f"Storage backend used: {default_storage.__class__.__name__}")
                
                # Generate a public URL for the file
                url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{path}"
                logger.info(f"Generated public URL: {url}")

                return path, url
            except Exception as e:
                logger.error(f"Error saving PDF: {str(e)}")
                logger.error(f"Storage backend used: {default_storage.__class__.__name__}")
                return None
