from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.roles import Role
from web.lab.models import LabOrder, NotScreened


class LaboratoryStaffRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_STAFF


class ToAnalyseView(LaboratoryStaffRequiredMixin, TemplateView):
    template_name = "lab/to_analyse.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        lab_orders = LabOrder.objects.to_analyse()
        return {**super().get_context_data(**kwargs), "lab_orders": lab_orders}


class AnalysedView(LaboratoryStaffRequiredMixin, TemplateView):
    template_name = "lab/analysed.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        lab_orders = LabOrder.objects.analysed()
        return {**super().get_context_data(**kwargs), "lab_orders": lab_orders}


class RunAnalyserView(LaboratoryStaffRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        lab_order = get_object_or_404(LabOrder.objects.select_related("sample"), pk=pk)
        try:
            lab_order.run_analyser(
                directory=settings.FINAL_MODELS_DIR,
                now=timezone.now(),
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            # Every analysis releases its lab report at once (features/screening.feature).
            released = (
                f"Sample {lab_order.sample.sample_id}:"
                f" {lab_order.get_test_display()} analysed, lab report released"
            )
            reason = lab_order.not_screened_reason
            if reason is not None and NotScreened(reason).is_model_problem():
                messages.warning(
                    request,
                    f"{released} without screening: {NotScreened(reason).label}."
                    " Tell the laboratory director.",
                )
            else:
                messages.success(request, f"{released}.")
        return redirect("lab:to_analyse")
