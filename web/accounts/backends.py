from typing import Any

from django.contrib.auth.backends import ModelBackend

from web.accounts.models import User


class RoleBackend(ModelBackend):
    """Django's backend, loading each request's user with their role record."""

    def get_user(self, user_id: Any) -> User | None:
        # The role records of the apps this party installs (web.party).
        roles = [
            relation.name
            for relation in User._meta.related_objects
            if relation.one_to_one
        ]
        user = User.objects.select_related(*roles).filter(pk=user_id).first()
        return user if self.user_can_authenticate(user) else None
