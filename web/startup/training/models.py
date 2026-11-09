"""The final models the startup's data scientist released, the recipient
hospitals the startup registered, and which of them fetched which final model
(features/startup/release.feature)."""

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction
from django.utils.text import slugify

if TYPE_CHECKING:
    from web.shared.accounts.models import User


class RecipientManager(models.Manager["Recipient"]):
    @transaction.atomic
    def add(self, *, name: str) -> "Recipient":
        """Register a recipient hospital by name; the same name again returns the
        existing one. A name whose slug another recipient already has is
        refused."""
        recipient = self.filter(name=name).first()
        if recipient is None:
            recipient = Recipient(name=name, slug=slugify(name))
            recipient.full_clean()
            recipient.save()
        return recipient


class Recipient(models.Model):
    """A hospital the startup registered by its name, which never changes. The
    hospital calls as the name's slug and may fetch every released final model,
    whether or not it took part in training."""

    name = models.CharField(max_length=100, unique=True)
    # The name the hospital's web app calls as; derived from the name.
    slug = models.SlugField(max_length=100, editable=False)

    objects = RecipientManager()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["slug"],
                name="one_recipient_per_slug",
                violation_error_code="slug_taken",
                violation_error_message="Another hospital's name has this slug.",
            ),
        )

    def __str__(self) -> str:
        return self.name


class ReleaseQuerySet(models.QuerySet["Release"]):
    def not_held(self, held_run_ids: list[str]) -> "ReleaseQuerySet":
        """The releases whose run ID is not among those the recipient says it
        holds; oldest release first."""
        return self.exclude(final_model_run_id__in=held_run_ids).order_by(
            "released_at", "pk"
        )

    def with_fetches(self) -> "ReleaseQuerySet":
        """Prefetch the recipients that fetched each release, for the final models
        page."""
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
    def record_fetched(
        self, *, recipient: Recipient, run_ids: list[str], now: datetime
    ) -> None:
        """Record that `recipient` was sent the released final models with these
        run IDs; only the first fetch of each is recorded."""
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
        """The recipient hospitals that fetched this release, sorted by name."""
        return sorted(
            (fetch.recipient for fetch in self.fetches.all()),
            key=lambda each: each.name,
        )


class Fetch(models.Model):
    """A record that the startup sent a released final model to a recipient
    hospital that was still waiting for the reply, whether or not the hospital
    then stored it."""

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
