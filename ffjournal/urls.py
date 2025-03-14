from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings
from .views import manage_league_emails_view, admin_dashboard_view, fetch_players, customize_sports_writer, view_newsletters, support_view, view_newsletter, unsubscribe_view, confirm_email   # Add the missing imports

urlpatterns = [
    path('', views.home, name='home'),
    path('leagues/', views.leagues, name='leagues'),
    path('refresh/', views.refresh_data, name='refresh_data'),
    path('ffjournal/manage-league-emails/<int:league_id>/', manage_league_emails_view, name='manage_league_emails'),
    path('ffjournal/admin/dashboard/', admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/', admin_dashboard_view, name='admin_dashboard'),
    path('fetch-players/', fetch_players, name='fetch_players'),
    path('ffjournal/leagues/<int:league_id>/customize/', customize_sports_writer, name='customize_sports_writer'),
    path('customize-sports-writer/<int:league_id>/', customize_sports_writer, name='customize_sports_writer'),
    path('support/', support_view, name='support'),
    path('view-newsletters/<int:league_id>/', view_newsletters, name='view_newsletters'),
    path('view-newsletter/<int:league_id>/<int:newsletter_id>/', views.view_newsletter, name='view_newsletter'),
    path('unsubscribe/<int:email_id>/', unsubscribe_view, name='unsubscribe'),
    path('confirm-email/<int:email_id>/', confirm_email, name='confirm_email'),
    path('confirmation-success/', views.confirmation_success, name='confirmation_success'),
    path('configure_sending/<int:league_id>/', views.configure_sending, name='configure_sending'),




] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
