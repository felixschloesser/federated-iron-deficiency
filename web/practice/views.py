from functools import cached_property
from typing import Any

import grpc
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F, Prefetch, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import capfirst, pluralize
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, View

from web.accounts.mixins import RoleRequiredMixin
from web.accounts.roles import Role
from web.practice import messaging, services
from web.practice.forms import OrderForm
from web.practice.models import (
    GeneralPractitioner,
    Order,
    OrderQuerySet,
    Patient,
    Sample,
)
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
        samples = patient.samples.prefetch_related(
            Prefetch(
                "orders",
                queryset=Order.objects.select_related("lab_report").order_by(
                    "ordered_at", "pk"
                ),
            )
        ).order_by("-collected_at", "-pk")
        # Blood is collected first; tests are ordered on a sample afterwards (R26).
        collect = reverse("practice:collect_sample", kwargs={"patient": patient.pk})
        # Each sample with the tests on it, in the order they were placed, so a
        # ferritin ordered beside a suggestion shows right under it (R9, R11).
        # Only the newest opens; the others summarise their tests and whether a
        # lab report in them suggests ferritin.
        return {
            **super().get_context_data(**kwargs),
            "actions": [],
            "post_actions": [{"url": collect, "label": "Collect sample"}],
            "samples": [
                {
                    "sample": sample,
                    "entries": (
                        entries := [self.entry(o) for o in sample.orders.all()]
                    ),
                    "actions": self.sample_actions(sample, entries),
                    "open": number == 0,
                    "tests": ", ".join(
                        order.get_test_display() for order in sample.orders.all()
                    ),
                    "suggested": any(
                        getattr(order, "lab_report", None) is not None
                        and order.lab_report.ferritin_suggested
                        for order in sample.orders.all()
                    ),
                }
                for number, sample in enumerate(samples)
            ],
        }

    def sample_actions(
        self, sample: Sample, entries: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """The tests a sample does not have yet; ferritin not while it is offered
        beside a suggestion, where it matters (R11)."""
        ordered = {entry["order"].test for entry in entries}
        beside = any(entry["order_ferritin_url"] for entry in entries)
        return [
            {"url": self.order_url(sample, test), "label": f"Order {test.label}"}
            for test in Test
            if test not in ordered and not (test == Test.FERRITIN and beside)
        ]

    def order_url(self, sample: Sample, test: Test) -> str:
        return reverse(
            "practice:new_order",
            kwargs={"patient": self.object.pk, "sample": sample.pk, "test": test},
        )

    def entry(self, order: Order) -> dict[str, Any]:
        """An order with its lab report, if fetched, and Order ferritin beside a
        suggestion."""
        lab_report = getattr(order, "lab_report", None)
        offered = lab_report is not None and ferritin_order_offered(lab_report)
        return {
            "order": order,
            "lab_report": lab_report,
            "order_ferritin_url": self.order_url(order.sample, Test.FERRITIN)
            if offered
            else None,
        }


class OrderIndexView(GeneralPractitionerRequiredMixin, ListView[Order]):
    template_name = "practice/orders.html"
    context_object_name = "orders"

    def get_queryset(self) -> OrderQuerySet:
        orders = (
            Order.objects.of_general_practitioner(self.general_practitioner)
            .select_related("sample__patient")
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
            messages.success(
                request,
                f"{fetched or 'No'} new lab report{pluralize(fetched)}.",
            )
        return redirect("practice:orders")


class CollectSampleView(GeneralPractitionerRequiredMixin, View):
    """Records a sample collected from one of the general practitioner's patients."""

    def post(self, request: HttpRequest, patient: int) -> HttpResponse:
        record = get_object_or_404(self.general_practitioner.patients, pk=patient)
        sample = services.collect_sample(
            general_practitioner=self.general_practitioner,
            patient=record,
            now=timezone.now(),
        )
        messages.success(request, f"Sample {sample.sample_id} collected.")
        return redirect("practice:patient", pk=record.pk)


class NewOrderView(GeneralPractitionerRequiredMixin, FormView[OrderForm]):
    """Orders one test on one of a patient's samples: both chosen before the form."""

    template_name = "practice/new_order.html"
    form_class = OrderForm

    @cached_property
    def patient(self) -> Patient:
        return get_object_or_404(
            self.general_practitioner.patients, pk=self.kwargs["patient"]
        )

    @cached_property
    def sample(self) -> Sample:
        return get_object_or_404(self.patient.samples, pk=self.kwargs["sample"])

    def get_form_kwargs(self) -> dict[str, Any]:
        return {**super().get_form_kwargs(), "test": self.kwargs["test"]}

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        return {
            **context,
            "patient": self.patient,
            "sample": self.sample,
            "test": self.kwargs["test"],
        }

    def get_success_url(self) -> str:
        return reverse("practice:patient", kwargs={"pk": self.patient.pk})

    def form_valid(self, form: OrderForm) -> HttpResponse:
        try:
            placed = services.place_order(
                general_practitioner=self.general_practitioner,
                sample=self.sample,
                test=self.kwargs["test"],
                indication=form.cleaned_data.get("indication"),
                now=timezone.now(),
            )
        except ValidationError as error:
            for field, errors in error.error_dict.items():
                # An error on a field this form does not show goes to the summary.
                form.add_error(field if field in form.fields else None, errors)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"{capfirst(placed.get_test_display())} ordered on sample"
            f" {placed.sample.sample_id}.",
        )
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
