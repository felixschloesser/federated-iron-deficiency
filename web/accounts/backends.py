from typing import Any

from django.contrib.auth.backends import ModelBackend

from web.accounts.models import User


class RoleBackend(ModelBackend):
    """Django's backend, loading each request's user with their role record."""

    def get_user(self, user_id: Any) -> User | None:
        user = (
            User.objects.select_related(
                "general_practitioner", "laboratory_staff_member", "laboratory_director"
            )
            .filter(pk=user_id)
            .first()
        )
        return user if self.user_can_authenticate(user) else None
