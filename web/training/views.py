from typing import Any

from django.conf import settings
from django.views.generic import TemplateView

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.roles import Role
from web.training.final_models import final_models


class DataScientistRequiredMixin(RoleRequiredMixin):
    role = Role.DATA_SCIENTIST


class FinalModelsView(DataScientistRequiredMixin, TemplateView):
    template_name = "training/final_models.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "final_models": final_models(settings.FINAL_MODELS_DIR),
        }
