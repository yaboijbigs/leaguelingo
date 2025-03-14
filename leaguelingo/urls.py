from django.conf import settings
from django.urls import path, include
from ffjournal.admin import admin_site  # Use custom admin site
from accounts.views import (
    league_id_check_view, 
    payment_view, 
    payment_success_view, 
    error_view, 
    CustomSignupView, 
    my_leagues_view, 
    additional_league_payment_view, 
    additional_league_payment_success_view,
    privacy_policy,
    terms_of_service
)

urlpatterns = [
    path('admin/', admin_site.urls),  # Use the custom admin site
    path('ffjournal/', include('ffjournal.urls')),
    path("accounts/", include("allauth.urls")),
    path('accounts/league-id-check/', league_id_check_view, name='league_id_check'),
    path('accounts/payment/', payment_view, name='payment'),
    path('accounts/payment-success/', payment_success_view, name='payment_success'),
    path("", include("pages.urls")),
    path('accounts/dashboard/', my_leagues_view, name='dashboard'),
    path('accounts/error/', error_view, name='error_page'),
    path('accounts/signup/', CustomSignupView.as_view(), name='account_signup'),
    path('accounts/my_leagues/', my_leagues_view, name='my_leagues'),
    path('accounts/additional-league/', additional_league_payment_view, name='additional_league_payment'),
    path('accounts/additional-league/success/', additional_league_payment_success_view, name='additional_league_payment_success'),
    path('accounts/privacy-policy/', privacy_policy, name='privacy_policy'),
    path('accounts/terms-of-service/', terms_of_service, name='terms_of_service'),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
