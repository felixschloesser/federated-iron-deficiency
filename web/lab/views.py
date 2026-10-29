from typing import Any

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
from web.lab.models import Sample
from web.practice.models import Order


class LaboratoryStaffRequiredMixin(RoleRequiredMixin):
    role = Role.LABORATORY_STAFF


class SamplesView(LaboratoryStaffRequiredMixin, TemplateView):
    template_name = "lab/samples.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "orders_to_receive": queries.orders_to_receive(),
            "samples_to_analyse": queries.samples_to_analyse(),
            "samples_analysed": queries.samples_analysed(),
        }


class ReceiveView(LaboratoryStaffRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        try:
            sample = services.receive(order=order, now=timezone.now())
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Sample {sample.sample_id} received.")
        return redirect("lab:samples")


class RunAnalyserView(LaboratoryStaffRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        sample = get_object_or_404(Sample.objects.select_related("order"), pk=pk)
        try:
            services.run_analyser(sample=sample, now=timezone.now())
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Sample {sample.sample_id} analysed.")
        return redirect("lab:samples")
