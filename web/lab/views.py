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
from web.lab import queries, services
from web.lab.models import LabOrder, Sample


class LaboratoryStaffRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_STAFF


class SamplesView(LaboratoryStaffRequiredMixin, TemplateView):
    template_name = "lab/samples.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "samples_to_receive": queries.samples_to_receive(),
            "lab_orders_to_analyse": queries.lab_orders_to_analyse(),
            "lab_orders_analysed": queries.lab_orders_analysed(),
        }


class ReceiveView(LaboratoryStaffRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        sample = get_object_or_404(Sample, pk=pk)
        try:
            services.receive(sample=sample, now=timezone.now())
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Sample {sample.sample_id} received.")
        return redirect("lab:samples")


class RunAnalyserView(LaboratoryStaffRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        lab_order = get_object_or_404(LabOrder.objects.select_related("sample"), pk=pk)
        try:
            services.run_analyser(
                lab_order=lab_order,
                directory=settings.FINAL_MODELS_DIR,
                now=timezone.now(),
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request,
                f"Sample {lab_order.sample.sample_id}:"
                f" {lab_order.get_test_display()} analysed.",
            )
        return redirect("lab:samples")
