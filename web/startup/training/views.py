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

from web.shared.accounts.mixins import RoleRequiredMixin
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role
from web.startup.training.final_models import final_models
from web.startup.training.forms import SubmitRunForm
from web.startup.training.models import Release
from web.startup.training.runs import TrainingRun, stop_run, submit_run, training_runs


class DataScientistRequiredMixin(RoleRequiredMixin):
    role = Role.DATA_SCIENTIST


def listed_runs() -> tuple[list[TrainingRun] | None, str | None]:
    """The SuperLink's runs, or None and the reason their statuses are unknown."""
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
        return {
            **super().get_context_data(**kwargs),
            "training_runs": runs or [],
            "runs_unknown": runs_unknown,
            # A SuperLink that cannot list runs cannot take a new run or a stop
            # either, so the page hides both.
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
    """The startup's final models, whether each is released, and which
    recipient hospitals fetched it."""

    template_name = "training/final_models.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        releases = {
            release.final_model_run_id: release
            for release in Release.objects.with_fetches()
        }
        return {
            **super().get_context_data(**kwargs),
            # Each final model paired with its release, or None if unreleased (the
            # page then offers Release).
            "final_models": [
                (model, releases.get(model.run_id))
                for model in final_models(settings.FINAL_MODELS_DIR)
            ],
        }


class StopRunView(DataScientistRequiredMixin, View):
    """Stop a training run in progress, then return to the training runs."""

    def post(self, request: HttpRequest, run_id: int) -> HttpResponse:
        try:
            stop_run(run_id)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f"Training run {run_id} stopped.")
        return redirect("training:runs")


class ReleaseView(DataScientistRequiredMixin, View):
    """Release a final model so recipient hospitals may fetch it, then return to
    the final models."""

    def post(self, request: HttpRequest, run_id: str) -> HttpResponse:
        user = request.user
        if not isinstance(
            user, User
        ):  # Narrows the type: the mixin let in only a data scientist.
            raise PermissionDenied
        if run_id not in {
            model.run_id for model in final_models(settings.FINAL_MODELS_DIR)
        }:
            raise Http404(f"No final model of run {run_id}.")
        Release.objects.release(
            final_model_run_id=run_id, released_by=user, now=timezone.now()
        )
        messages.success(
            request,
            f"Final model of run {run_id} released: recipient hospitals may fetch it.",
        )
        return redirect("training:models")
