from typing import Any

import grpc
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from ml.training_cohort import TrainingCohortUnavailable
from web.hospital.deployment.forms import DeployForm
from web.hospital.deployment.grpc_client import fetch_final_models, unreachable
from web.hospital.deployment.model_files import screening_models
from web.hospital.deployment.models import Deployment, NoUsableModel
from web.shared.accounts.mixins import RoleRequiredMixin
from web.shared.accounts.roles import Role


class LaboratoryDirectorRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_DIRECTOR


class ScreeningModelsView(LaboratoryDirectorRequiredMixin, TemplateView):
    template_name = "deployment/models.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        deployed = Deployment.objects.screener(settings.SCREENING_MODELS_DIR)
        history = Deployment.objects.select_related(
            "deployed_screening_model"
        ).order_by("-deployed_at", "-pk")
        return {
            **super().get_context_data(**kwargs),
            "screening_models": screening_models(settings.SCREENING_MODELS_DIR),
            "deployed": None
            if isinstance(deployed, NoUsableModel)
            else deployed.deployed_screening_model,
            "no_usable_model": deployed
            if isinstance(deployed, NoUsableModel)
            else None,
            "history": history,
            # Only a hospital that knows the startup's endpoint can fetch.
            "post_actions": [
                {
                    "url": reverse("deployment:fetch_final_models"),
                    "label": "Fetch new final models",
                }
            ]
            if settings.STARTUP_ADDRESS
            else [],
        }


class FetchFinalModelsView(LaboratoryDirectorRequiredMixin, View):
    """Fetches the startup's new final models, validated on this hospital's own
    past patients, then back (features/hospital/fetch.feature)."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not settings.STARTUP_ADDRESS:
            raise Http404("This hospital knows no startup to fetch from.")
        try:
            stored = fetch_final_models(now=timezone.now())
        except TrainingCohortUnavailable:
            messages.error(
                request,
                "Provide the training cohort first: final models are validated on it.",
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
                f"{len(stored) or 'No'} new final model{'' if len(stored) == 1 else 's'}.",
            )
        return redirect("deployment:screening_models")


class DeployView(LaboratoryDirectorRequiredMixin, View):
    def post(self, request: HttpRequest, run_id: str) -> HttpResponse:
        form = DeployForm(request.POST)
        if not form.is_valid():
            # The page shows every model, so its errors go in a message.
            messages.error(
                request, " ".join(str(error) for error in form.errors["threshold"])
            )
            return redirect("deployment:screening_models")
        try:
            deployment = Deployment.objects.deploy(
                run_id=run_id,
                threshold=form.cleaned_data["threshold"],
                directory=settings.SCREENING_MODELS_DIR,
                now=timezone.now(),
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            deployed = deployment.deployed_screening_model
            messages.success(
                request,
                f"{deployed.name} deployed at threshold {deployed.threshold:.2f}.",
            )
        return redirect("deployment:screening_models")
