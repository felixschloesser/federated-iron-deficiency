from functools import cached_property
from typing import Any

import grpc
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, View

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.roles import Role
from web.practice import messaging, services
from web.practice.forms import OrderForm
from web.practice.models import GeneralPractitioner, Order, OrderQuerySet, Patient
from web.practice.queries import ferritin_order_offered
from web.vocabulary import Test


class GeneralPractitionerRequiredMixin(RoleRequiredMixin):
    """Lets in only general practitioners, as `self.general_practitioner`."""

    role = Role.GENERAL_PRACTITIONER
    request: HttpRequest

    @cached_property
    def general_practitioner(self) -> GeneralPractitioner:
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied
        practitioner: GeneralPractitioner = user.general_practitioner
        return practitioner


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
        orders = list(
            patient.orders.select_related("lab_report").order_by("-ordered_at", "-pk")
        )
        ordered = {order.test for order in orders}
        # One sample per patient, each test at most once (R26): offer only the others.
        actions = [
            {
                "url": reverse(
                    "practice:new_order", kwargs={"patient": patient.pk, "test": test}
                ),
                "label": f"Order {test.label}",
            }
            for test in Test
            if test not in ordered
        ]
        # Each order with its lab report, if fetched, and Order ferritin beside a
        # suggestion (R9, R11).
        entries = [
            {
                "order": order,
                "lab_report": lab_report,
                "order_ferritin_url": reverse(
                    "practice:new_order",
                    kwargs={"patient": patient.pk, "test": Test.FERRITIN},
                )
                if lab_report is not None and ferritin_order_offered(lab_report)
                else None,
            }
            for order in orders
            for lab_report in [getattr(order, "lab_report", None)]
        ]
        return {
            **super().get_context_data(**kwargs),
            "actions": actions,
            "entries": entries,
        }


class OrderIndexView(GeneralPractitionerRequiredMixin, ListView[Order]):
    template_name = "practice/orders.html"
    context_object_name = "orders"

    def get_queryset(self) -> OrderQuerySet:
        orders = (
            Order.objects.of_general_practitioner(self.general_practitioner)
            .select_related("patient")
            .annotate(lab_report_released_at=F("lab_report__released_at"))
        )
        return orders.order_by("-ordered_at", "-pk")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        # Only an app with a hospital to ask can check for reports (R23).
        post_actions = (
            [
                {
                    "url": reverse("practice:check_for_reports"),
                    "label": "Check for reports",
                }
            ]
            if settings.MESSAGING_ADDRESS
            else []
        )
        return {**super().get_context_data(**kwargs), "post_actions": post_actions}


class CheckForReportsView(GeneralPractitionerRequiredMixin, View):
    """Sends pending lab orders and fetches new lab reports now (R23)."""

    def post(self, request: HttpRequest) -> HttpResponse:
        connection = messaging.configured_connection()
        if connection is None:
            raise Http404
        try:
            fetched = messaging.check_for_lab_reports(connection, now=timezone.now())
        except grpc.RpcError:
            messages.error(
                request, "The hospital could not be reached. Try again later."
            )
        else:
            messages.success(request, f"{fetched} new lab report{pluralize(fetched)}.")
        return redirect("practice:orders")


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
            for field, errors in error.error_dict.items():
                # An error on a field this form does not show goes to the summary.
                form.add_error(field if field in form.fields else None, errors)
            return self.form_invalid(form)
        messages.success(self.request, "Order placed.")
        if (connection := messaging.configured_connection()) is not None:
            try:
                messaging.send_pending_lab_orders(connection, now=timezone.now())
            except grpc.RpcError:
                messages.warning(
                    self.request,
                    "The hospital could not be reached; the lab order is"
                    " sent with the next check for reports.",
                )
        return super().form_valid(form)
