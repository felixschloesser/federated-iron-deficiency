"""The final models the startup's data scientist released, the recipient
hospitals the startup registered, and which of them fetched which final model
(features/startup/release.feature)."""

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction

if TYPE_CHECKING:
    from shared.accounts.models import User


class RecipientManager(models.Manager["Recipient"]):
    @transaction.atomic
    def add(self, *, certificate_name: str, name: str) -> "Recipient":
        """Register a recipient hospital, or change its name."""
        recipient, _ = self.update_or_create(
            certificate_name=certificate_name, defaults={"name": name}
        )
        return recipient


class Recipient(models.Model):
    """A hospital the startup registered by the certificate name it issued; it
    may fetch every released final model, whether or not it trained."""

    certificate_name = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=100)

    objects = RecipientManager()

    def __str__(self) -> str:
        return self.name


class ReleaseQuerySet(models.QuerySet["Release"]):
    def new_for(self, recipient: Recipient) -> "ReleaseQuerySet":
        """The released final models this recipient has not stored yet, oldest
        release first."""
        return self.exclude(fetches__recipient=recipient).order_by("released_at", "pk")

    def with_fetches(self) -> "ReleaseQuerySet":
        """Each release with the recipients that fetched it, for the final models page."""
        return self.prefetch_related("fetches__recipient")

    @transaction.atomic
    def release(
        self, *, final_model_run_id: str, released_by: "User", now: datetime
    ) -> "Release":
        """Release a final model; releasing it again changes nothing."""
        release, _ = self.get_or_create(
            final_model_run_id=final_model_run_id,
            defaults={"released_by": released_by, "released_at": now},
        )
        return release

    @transaction.atomic
    def acknowledge(
        self, *, recipient: Recipient, run_ids: list[str], now: datetime
    ) -> None:
        """`recipient` stored these released final models: offer them no more."""
        for release in self.filter(final_model_run_id__in=run_ids):
            Fetch.objects.get_or_create(
                release=release, recipient=recipient, defaults={"fetched_at": now}
            )


class Release(models.Model):
    # The training run whose final model it releases.
    final_model_run_id = models.CharField(max_length=64, unique=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    released_at = models.DateTimeField()

    objects = ReleaseQuerySet.as_manager()

    def __str__(self) -> str:
        return f"Final model {self.final_model_run_id}, released"

    def fetched_by(self) -> list[Recipient]:
        """The recipient hospitals that stored it, by name."""
        return sorted(
            (fetch.recipient for fetch in self.fetches.all()),
            key=lambda each: each.name,
        )


class Fetch(models.Model):
    """A recipient hospital stored a released final model: its acknowledgement."""

    release = models.ForeignKey(
        Release, on_delete=models.PROTECT, related_name="fetches"
    )
    recipient = models.ForeignKey(
        Recipient, on_delete=models.PROTECT, related_name="fetches"
    )
    fetched_at = models.DateTimeField()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["release", "recipient"], name="one_fetch_per_recipient"
            ),
        )

    def __str__(self) -> str:
        return f"{self.recipient} fetched {self.release}"
