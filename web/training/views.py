from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.roles import Role
from web.training.final_models import final_models, for_sale
from web.training.forms import SubmitRunForm
from web.training.runs import submit_run


class DataScientistRequiredMixin(RoleRequiredMixin):
    role = Role.DATA_SCIENTIST


class FinalModelsView(DataScientistRequiredMixin, FormView[SubmitRunForm]):
    """The startup's final models, and the form that submits the next run."""

    template_name = "training/final_models.html"
    form_class = SubmitRunForm
    success_url = reverse_lazy("training:final_models")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "final_models": final_models(settings.FINAL_MODELS_DIR),
        }

    def form_valid(self, form: SubmitRunForm) -> HttpResponse:
        try:
            run_id = submit_run(threshold=form.cleaned_data["threshold"])
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Training run {run_id} submitted. Its final model appears here when"
            " the run finishes.",
        )
        return super().form_valid(form)


class ForSaleView(DataScientistRequiredMixin, View):
    """A final model's weights and threshold as a file: the model sale (P5)."""

    def get(self, request: HttpRequest, run_id: str) -> HttpResponse:
        data = for_sale(settings.FINAL_MODELS_DIR, run_id)
        if data is None:
            raise Http404(f"No final model of run {run_id}.")
        response = HttpResponse(data, content_type="application/octet-stream")
        response["Content-Disposition"] = (
            f'attachment; filename="final-model-run-{run_id}.pt"'
        )
        return response
