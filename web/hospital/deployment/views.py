from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.roles import Role
from web.hospital.deployment.forms import DeployForm
from web.hospital.deployment.model_files import screening_models
from web.hospital.deployment.models import Deployment, NoUsableModel


class LaboratoryDirectorRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_DIRECTOR


class ScreeningModelsView(LaboratoryDirectorRequiredMixin, TemplateView):
    template_name = "deployment/models.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        deployed = Deployment.objects.screener(settings.SCREENING_MODELS_DIR)
        history = Deployment.objects.select_related("screening_model").order_by(
            "-deployed_at", "-pk"
        )
        return {
            **super().get_context_data(**kwargs),
            "screening_models": screening_models(settings.SCREENING_MODELS_DIR),
            "deployed": None
            if isinstance(deployed, NoUsableModel)
            else deployed.screening_model,
            "no_usable_model": deployed
            if isinstance(deployed, NoUsableModel)
            else None,
            "history": history,
        }


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
            deployed = deployment.screening_model
            messages.success(
                request,
                f"{deployed.name} deployed at threshold {deployed.threshold:.2f}.",
            )
        return redirect("deployment:screening_models")
