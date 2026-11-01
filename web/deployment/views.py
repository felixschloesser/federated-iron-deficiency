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
from web.deployment import services
from web.deployment.domain import deployed_model, screening_models
from web.deployment.models import Deployment


class LaboratoryDirectorRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_DIRECTOR


class ModelsView(LaboratoryDirectorRequiredMixin, TemplateView):
    template_name = "deployment/models.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        deployed, no_usable_model = deployed_model(settings.FINAL_MODELS_DIR)
        history = Deployment.objects.select_related("screening_model").order_by(
            "-deployed_at", "-pk"
        )
        return {
            **super().get_context_data(**kwargs),
            "screening_models": screening_models(settings.FINAL_MODELS_DIR),
            "deployed": deployed if no_usable_model is None else None,
            "no_usable_model": no_usable_model,
            "history": history,
        }


class DeployView(LaboratoryDirectorRequiredMixin, View):
    def post(self, request: HttpRequest, run_id: str) -> HttpResponse:
        try:
            deployment = services.deploy(
                run_id=run_id, directory=settings.FINAL_MODELS_DIR, now=timezone.now()
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"{deployment.screening_model.name} deployed.")
        return redirect("deployment:models")
