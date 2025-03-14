from django.urls import path
from .views import HomePageView, AboutPageView

urlpatterns = [
    path('', HomePageView.as_view(), name='home'),  # Root URL points to the landing page
    path('home/', HomePageView.as_view(), name='home'),  # /home/ URL
    path('about/', AboutPageView.as_view(), name='about'),  # /about/ URL
]
