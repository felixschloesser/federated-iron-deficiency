from functools import cached_property
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView

from web.accounts.roles import Role, role_of
from web.practice import services
from web.practice.forms import OrderForm
from web.practice.models import GeneralPractitioner, Order, OrderQuerySet, Patient, Test


class GeneralPractitionerRequiredMixin(LoginRequiredMixin):
    """Lets in only a logged-in general practitioner, as `self.general_practitioner`."""

    general_practitioner: GeneralPractitioner

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        if role_of(user) is not Role.GENERAL_PRACTITIONER:
            raise PermissionDenied
        self.general_practitioner = user.general_practitioner
        return super().dispatch(request, *args, **kwargs)


class PatientIndexView(GeneralPractitionerRequiredMixin, ListView[Patient]):
    template_name = "practice/patients.html"
    context_object_name = "patients"

    def get_queryset(self) -> QuerySet[Patient]:
        return self.general_practitioner.patients.order_by("name", "pk")


class PatientDetailView(GeneralPractitionerRequiredMixin, DetailView[Patient]):
    """One of the general practitioner's patients; anyone else's is 404 (R13)."""

    template_name = "practice/patient.html"
    context_object_name = "patient"

    def get_queryset(self) -> QuerySet[Patient]:
        return self.general_practitioner.patients.all()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        patient = self.object
        actions = [
            {
                "url": reverse(
                    "practice:new_order", kwargs={"patient": patient.pk, "test": test}
                ),
                "label": f"Order {test.label}",
            }
            for test in Test
        ]
        orders = patient.orders.order_by("-ordered_at", "-pk")
        return {
            **super().get_context_data(**kwargs),
            "actions": actions,
            "orders": orders,
        }


class OrderIndexView(GeneralPractitionerRequiredMixin, ListView[Order]):
    template_name = "practice/orders.html"
    context_object_name = "orders"

    def get_queryset(self) -> OrderQuerySet:
        orders = Order.objects.of_general_practitioner(
            self.general_practitioner
        ).select_related("patient")
        return orders.order_by("-ordered_at", "-pk")


class NewOrderView(GeneralPractitionerRequiredMixin, FormView[OrderForm]):
    """Orders one test for one patient: both chosen before the form."""

    template_name = "practice/new_order.html"
    form_class = OrderForm

    @cached_property
    def patient(self) -> Patient:
        return get_object_or_404(
            self.general_practitioner.patients, pk=self.kwargs["patient"]
        )

    def get_form_kwargs(self) -> dict[str, Any]:
        return {**super().get_form_kwargs(), "test": self.kwargs["test"]}

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        return {**context, "patient": self.patient, "test": self.kwargs["test"]}

    def get_success_url(self) -> str:
        return reverse("practice:patient", kwargs={"pk": self.patient.pk})

    def form_valid(self, form: OrderForm) -> HttpResponse:
        try:
            services.place_order(
                general_practitioner=self.general_practitioner,
                patient=self.patient,
                test=self.kwargs["test"],
                indication=form.cleaned_data.get("indication"),
                now=timezone.now(),
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Order placed.")
        return super().form_valid(form)
