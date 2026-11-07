from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from ml.cohort import CBC_VARS
from web.hospital.cohort.models import LabRecord, TrainingCohort
from web.hospital.deployment.views import LaboratoryDirectorRequiredMixin
from web.shared.accounts.models import User

NO_FOLDER = "This web app has no folder for the training cohort (TRAINING_COHORT_DIR)."


def director(request: HttpRequest) -> User:
    """The laboratory director LaboratoryDirectorRequiredMixin let in."""
    if not isinstance(request.user, User):
        raise PermissionDenied
    return request.user


class TrainingCohortView(LaboratoryDirectorRequiredMixin, TemplateView):
    template_name = "cohort/training_cohort.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "provided": TrainingCohort.objects.provided(),
            "summary": LabRecord.objects.summary(),
            "cbc_values": len(CBC_VARS),
            "provide_url": reverse("cohort:provide"),
            "withdraw_url": reverse("cohort:withdraw"),
            "decisions": TrainingCohort.objects.select_related(
                "provided_by", "withdrawn_by"
            ),
        }


class ProvideView(LaboratoryDirectorRequiredMixin, View):
    def post(self, request: HttpRequest) -> HttpResponse:
        if settings.TRAINING_COHORT_DIR is None:
            messages.error(request, NO_FOLDER)
            return redirect("cohort:training_cohort")
        try:
            cohort = TrainingCohort.objects.provide(
                directory=settings.TRAINING_COHORT_DIR,
                by=director(request),
                now=timezone.now(),
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request,
                f"Training cohort provided: {cohort.past_patients} past patients.",
            )
        return redirect("cohort:training_cohort")


class WithdrawView(LaboratoryDirectorRequiredMixin, View):
    def post(self, request: HttpRequest) -> HttpResponse:
        if settings.TRAINING_COHORT_DIR is None:
            messages.error(request, NO_FOLDER)
            return redirect("cohort:training_cohort")
        try:
            TrainingCohort.objects.withdraw(
                directory=settings.TRAINING_COHORT_DIR,
                by=director(request),
                now=timezone.now(),
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Training cohort withdrawn.")
        return redirect("cohort:training_cohort")
