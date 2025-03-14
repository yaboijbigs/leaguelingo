from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

class CustomUser(AbstractUser):
    pass

    def __str__(self):
        return self.email


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    has_paid = models.BooleanField(default=False)
    leagues = models.ManyToManyField('ffjournal.League', related_name='profiles')  # Ensure correct reference to the League model

    def __str__(self):
        return f"{self.user.username}"



@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    # Check if the profile exists, create if it doesn't
    Profile.objects.get_or_create(user=instance)
    instance.profile.save()
