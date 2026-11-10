from typing import Any

import grpc
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from ml.cohort import FERRITIN_CUTOFF, INFLAMED_FERRITIN_CUTOFF, INFLAMMATION_CRP
from ml.training_cohort import TrainingCohortUnavailable
from web.hospital.deployment.forms import TargetSensitivityForm
from web.hospital.deployment.grpc_client import fetch_screening_models, unreachable
from web.hospital.deployment.model_files import screening_models
from web.hospital.deployment.models import (
    Deployment,
    NoUsableModel,
    TargetSensitivity,
)
from web.shared.accounts.mixins import RoleRequiredMixin
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role


class LaboratoryDirectorRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_DIRECTOR


# The cutoffs cohort/iron_deficient.html shows, as the training label uses them.
IRON_DEFICIENCY = {
    "ferritin": FERRITIN_CUTOFF,
    "inflamed_ferritin": INFLAMED_FERRITIN_CUTOFF,
    "crp": INFLAMMATION_CRP,
}


def director(request: HttpRequest) -> User:
    """The logged-in user, whom LaboratoryDirectorRequiredMixin has already checked
    is a laboratory director."""
    if not isinstance(request.user, User):
        raise PermissionDenied
    return request.user


def history() -> list[dict[str, Any]]:
    """Every target sensitivity set and every deployment, newest first."""
    targets = [
        {
            "at": target.set_at,
            "by": target.set_by.username,
            "decision": f"Target sensitivity set to {target}",
        }
        for target in TargetSensitivity.objects.select_related("set_by")
    ]
    deployments = [
        {
            "at": deployment.deployed_at,
            "by": deployment.deployed_by.username,
            "decision": f"{deployment.deployed_screening_model.name} deployed at"
            f" threshold {deployment.deployed_screening_model.threshold:.2f}"
            f" (target {deployment.target_sensitivity}%)",
        }
        for deployment in Deployment.objects.select_related(
            "deployed_screening_model", "deployed_by"
        )
    ]
    return sorted(targets + deployments, key=lambda entry: entry["at"], reverse=True)


class ScreeningModelsView(LaboratoryDirectorRequiredMixin, TemplateView):
    """The screening models and the target sensitivity they are deployed at. A
    POST sets the target sensitivity; an invalid one shows the page again with
    the error beside the field. The same radios, sent by GET (`?percent=`),
    show what a target would cost and change nothing; the page then offers to
    set it."""

    template_name = "deployment/models.html"
    # The target sensitivity being previewed; None shows the one in force.
    preview: int | None = None

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if "percent" in request.GET:
            form = TargetSensitivityForm(request.GET)
            if not form.is_valid():
                raise Http404("No such target sensitivity.")
            self.preview = form.cleaned_data["percent"]
        return super().get(request, *args, **kwargs)

    def post(self, request: HttpRequest) -> HttpResponse:
        form = TargetSensitivityForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(target_form=form))
        target = TargetSensitivity.objects.set(
            percent=form.cleaned_data["percent"],
            by=director(request),
            directory=settings.SCREENING_MODELS_DIR,
            now=timezone.now(),
        )
        messages.success(request, f"Target sensitivity set to {target}.")
        return redirect("deployment:screening_models")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        deployed = Deployment.objects.screener(settings.SCREENING_MODELS_DIR)
        target = TargetSensitivity.objects.current()
        current = None if target is None else target.percent
        # Showing the target in force previews nothing.
        preview = None if self.preview == current else self.preview
        shown = preview or current
        return {
            **super().get_context_data(**kwargs),
            "target": target,
            "preview": preview,
            "shown": shown,
            "target_form": kwargs.get("target_form")
            or TargetSensitivityForm(
                initial=None if shown is None else {"percent": shown}
            ),
            # Each screening model with its local validation at the target.
            "cards": [
                {
                    "model": model,
                    "at_target": None if shown is None else model.at_target(shown),
                }
                for model in screening_models(settings.SCREENING_MODELS_DIR)
            ],
            "iron_deficiency": IRON_DEFICIENCY,
            "deployed": None
            if isinstance(deployed, NoUsableModel)
            else deployed.deployed_screening_model,
            "no_usable_model": deployed
            if isinstance(deployed, NoUsableModel)
            else None,
            "history": history(),
            # Only a hospital that knows the startup's endpoint can fetch.
            "post_actions": [
                {
                    "url": reverse("deployment:fetch_screening_models"),
                    "label": "Fetch new screening models",
                }
            ]
            if settings.STARTUP_ADDRESS
            else [],
        }


class FetchScreeningModelsView(LaboratoryDirectorRequiredMixin, View):
    """Fetch the startup's new screening models, validate them on this hospital's
    own past patients, and go back to the Screening models page."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not settings.STARTUP_ADDRESS:
            raise Http404("This hospital knows no startup to fetch from.")
        try:
            stored = fetch_screening_models(now=timezone.now())
        except TrainingCohortUnavailable:
            messages.error(
                request,
                "Provide the training cohort first: screening models are validated on it.",
            )
        except grpc.RpcError as error:
            messages.error(
                request,
                "The startup could not be reached. Try again later."
                if unreachable(error)
                else "The startup refused the request. Tell the administrator.",
            )
        else:
            messages.success(
                request,
                f"{len(stored) or 'No'} new screening model{'' if len(stored) == 1 else 's'}.",
            )
        return redirect("deployment:screening_models")


class DeployView(LaboratoryDirectorRequiredMixin, View):
    def post(self, request: HttpRequest, run_id: str) -> HttpResponse:
        try:
            deployment = Deployment.objects.deploy(
                run_id=run_id,
                by=director(request),
                directory=settings.SCREENING_MODELS_DIR,
                now=timezone.now(),
            )
        except ValidationError as error:
            # Deploying is offered only once a target is set, so what is left is
            # a file that changed or vanished since the page showed: page-wide.
            messages.error(request, " ".join(error.messages))
        else:
            deployed = deployment.deployed_screening_model
            messages.success(
                request,
                f"{deployed.name} deployed at threshold {deployed.threshold:.2f}"
                f" (target {deployment.target_sensitivity}%).",
            )
        return redirect("deployment:screening_models")
