from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, TemplateView

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.models import User
from web.accounts.roles import Role
from web.startup.training.final_models import (
    final_models,
    for_sale,
    transmission_statuses,
)
from web.startup.training.forms import SubmitRunForm
from web.startup.training.models import Transmission
from web.startup.training.runs import TrainingRun, stop_run, submit_run, training_runs


class DataScientistRequiredMixin(RoleRequiredMixin):
    role = Role.DATA_SCIENTIST


def listed_runs() -> tuple[list[TrainingRun] | None, str | None]:
    """The SuperLink's runs, or None and why their statuses are unknown."""
    try:
        return training_runs(), None
    except ValidationError as error:
        return None, error.messages[0]


class TrainingRunsView(DataScientistRequiredMixin, FormView[SubmitRunForm]):
    """Every run the SuperLink knows, and the form that submits the next one."""

    template_name = "training/training_runs.html"
    form_class = SubmitRunForm
    success_url = reverse_lazy("training:runs")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        runs, runs_unknown = listed_runs()
        by_run = {
            transmission.run_id: transmission
            for transmission in Transmission.objects.all()
        }
        return {
            **super().get_context_data(**kwargs),
            # Each run with the final model it transmits, if it is a transmission.
            "training_runs": [(run, by_run.get(str(run.run_id))) for run in runs or []],
            "runs_unknown": runs_unknown,
            # A SuperLink that does not list runs would not take one, nor a stop.
            "submits": runs_unknown is None,
            "checked_at": timezone.now(),
        }

    def get_initial(self) -> dict[str, Any]:
        return SubmitRunForm.defaults()

    def form_valid(self, form: SubmitRunForm) -> HttpResponse:
        try:
            run_id = submit_run(form.run_configuration())
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Training run {run_id} submitted. Its final model appears on Final"
            " models when the run finishes.",
        )
        return super().form_valid(form)


class FinalModelsView(DataScientistRequiredMixin, TemplateView):
    """The startup's final models, each with whether it reached the hospitals."""

    template_name = "training/final_models.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        runs, runs_unknown = listed_runs()
        kept = final_models(settings.FINAL_MODELS_DIR)
        statuses = transmission_statuses(kept, runs, list(Transmission.objects.all()))
        return {
            **super().get_context_data(**kwargs),
            "final_models": [(model, statuses[model.run_id]) for model in kept],
            "runs_unknown": runs_unknown,
            # A SuperLink that does not list runs would not take a transmission.
            "transmits": runs_unknown is None,
        }


class StopRunView(DataScientistRequiredMixin, View):
    """Stops a training run in progress, then back to the training runs."""

    def post(self, request: HttpRequest, run_id: int) -> HttpResponse:
        try:
            stop_run(run_id)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f"Training run {run_id} stopped.")
        return redirect("training:runs")


class TransmitView(DataScientistRequiredMixin, View):
    """Transmits a final model to every connected hospital, then back."""

    def post(self, request: HttpRequest, run_id: str) -> HttpResponse:
        user = request.user
        if not isinstance(user, User):  # The mixin let in only a data scientist.
            raise PermissionDenied
        try:
            transmission = Transmission.objects.transmit(
                final_model=run_id, transmitted_by=user, now=timezone.now()
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(
                request,
                f"Run {transmission.run_id} transmits final model of run {run_id}"
                " to every hospital connected now.",
            )
        return redirect("training:models")


class ForSaleView(DataScientistRequiredMixin, View):
    """A final model's weights as a file: the model sale (P5)."""

    def get(self, request: HttpRequest, run_id: str) -> HttpResponse:
        data = for_sale(settings.FINAL_MODELS_DIR, run_id)
        if data is None:
            raise Http404(f"No final model of run {run_id}.")
        response = HttpResponse(data, content_type="application/octet-stream")
        response["Content-Disposition"] = (
            f'attachment; filename="final-model-run-{run_id}.pt"'
        )
        return response
