from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Django's user, swappable from the start; a role is a record linked to it
    (general practitioner)."""
