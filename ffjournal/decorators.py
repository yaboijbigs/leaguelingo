from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from .models import League
from accounts.models import CustomUser  # This is your custom user model


def user_is_league_owner(view_func):
    def wrap(request, league_id, *args, **kwargs):
        league = get_object_or_404(League, id=league_id)
        if request.user != league.owner:
            raise PermissionDenied
        return view_func(request, league_id, *args, **kwargs)
    return wrap
