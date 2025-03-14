from django.template.loader import render_to_string
from .models import Article, League
from django.core.mail import EmailMultiAlternatives


def compile_newsletter(league, week):
    # Fetch all articles for this league and week
    articles = Article.objects.filter(league=league, week=week)
    
    # Prepare the context for the template
    context = {
        'league_name': league.name,
        'matchup_previews': articles.filter(label='matchup_previews').first().content if articles.filter(label='matchup_previews').exists() else "",
        'league_overview': articles.filter(label='league_overview').first().content if articles.filter(label='league_overview').exists() else "",
        'top_performers': articles.filter(label='top_performers').first().content if articles.filter(label='top_performers').exists() else ""
    }
    
    # Render the newsletter HTML
    newsletter_html = render_to_string('emails/newsletter_email.html', context)
    
    return newsletter_html

def send_newsletter(league, week, email_content, subject='League Lingo Weekly Newsletter'):
    subject = f"League Lingo Weekly Newsletter - Week {week}"
    from_email = 'sportswriter@lol.com'
    recipient_list = [member.email for member in league.members.all()]  # Assuming you have a `members` field

    # Create email
    email = EmailMultiAlternatives(
        subject=subject,
        body='',
        from_email=from_email,
        to=recipient_list
    )
    email.attach_alternative(email_content, "text/html")
    email.send()