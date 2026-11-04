from functools import cached_property
from typing import Any

import grpc
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
from web.practice import messaging
from web.practice.forms import CollectSampleForm, OrderForm
from web.practice.models import (
    GeneralPractitioner,
    Laboratory,
    Order,
    OrderQuerySet,
    Patient,
    Sample,
)
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
        patients = self.general_practitioner.patients.with_ferritin_suggested()
        patients = patients.order_by("name", "pk")
        if query := self.request.GET.get("q", "").strip():
            patients = patients.filter(name__icontains=query)
        return patients

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "query": self.request.GET.get("q", "").strip(),
        }


class PatientDetailView(GeneralPractitionerRequiredMixin, DetailView[Patient]):
    """One of the general practitioner's patients; anyone else's is 404 (R13)."""

    template_name = "practice/patient.html"
    context_object_name = "patient"

    def get_queryset(self) -> QuerySet[Patient]:
        return self.general_practitioner.patients.all()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        patient = self.object
        samples = (
            patient.samples.select_related("laboratory")
            .prefetch_related(
                Prefetch(
                    "orders",
                    queryset=Order.objects.select_related("lab_report").order_by(
                        "ordered_at", "pk"
                    ),
                )
            )
            .order_by("-collected_at", "-pk")
        )
        # Blood is collected first; tests are ordered on a sample afterwards (R26).
        collect = reverse("practice:collect_sample", kwargs={"patient": patient.pk})
        laboratories = Laboratory.objects.count()
        # Several laboratories: the choice comes first, on its own page (R22).
        collect_action = {"url": collect, "label": "Collect sample"}
        # Where a doctor waits for a lab report, so they need not go to Orders.
        check_action = {
            "url": reverse(
                "practice:patient_check_for_reports", kwargs={"patient": patient.pk}
            ),
            "label": "Check for reports",
        }
        # Each sample with the tests on it, in the order they were placed, so a
        # ferritin ordered beside a suggestion shows right under it (R9, R11).
        # Only the newest opens; the others summarise their tests and whether a
        # lab report in them suggests ferritin.
        return {
            **super().get_context_data(**kwargs),
            "subtitle": f"{patient.get_registered_sex_display()}, aged {patient.age}",
            "actions": [collect_action] if laboratories > 1 else [],
            "post_actions": ([] if laboratories > 1 else [collect_action])
            + ([check_action] if laboratories > 0 else []),
            # Only an app with a laboratory to ask fetches lab reports (R23).
            "fetches_reports": laboratories > 0,
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
        offered = lab_report is not None and lab_report.ferritin_order_offered()
        return {
            "order": order,
            # Until the hospital has the lab order, no report is on its way (R22).
            "sent": order.sent_at is not None,
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
        # Only an app with a laboratory to ask can check for reports (R23).
        post_actions = (
            [
                {
                    "url": reverse("practice:check_for_reports"),
                    "label": "Check for reports",
                }
            ]
            if Laboratory.objects.exists()
            else []
        )
        return {**super().get_context_data(**kwargs), "post_actions": post_actions}


class CheckForReportsView(GeneralPractitionerRequiredMixin, View):
    """Sends pending lab orders and fetches new lab reports from every laboratory
    now (R23)."""

    def post(self, request: HttpRequest, patient: int | None = None) -> HttpResponse:
        # From a patient's page, back to it; from Orders, back there.
        back = reverse("practice:orders")
        if patient is not None:
            record = get_object_or_404(self.general_practitioner.patients, pk=patient)
            back = reverse("practice:patient", kwargs={"pk": record.pk})
        if not Laboratory.objects.exists():
            raise Http404
        check = messaging.check_every_laboratory(now=timezone.now())
        for laboratory, error in check.failures:
            messages.error(
                request,
                f"{laboratory} could not be reached. Try again later."
                if messaging.unreachable(error)
                else f"{laboratory} refused a message. Tell the administrator.",
            )
        if len(check.failures) < check.asked:
            fetched = check.fetched
            messages.success(
                request,
                f"{fetched or 'No'} new lab report{pluralize(fetched)}.",
            )
        return redirect(back)


class CollectSampleView(GeneralPractitionerRequiredMixin, FormView[CollectSampleForm]):
    """Records a sample collected from one of the practice's patients, for the
    laboratory chosen; a practice with one laboratory skips the choice (R22, R26)."""

    template_name = "practice/collect_sample.html"
    form_class = CollectSampleForm

    @cached_property
    def patient(self) -> Patient:
        return get_object_or_404(
            self.general_practitioner.patients, pk=self.kwargs["patient"]
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), "patient": self.patient}

    def form_valid(self, form: CollectSampleForm) -> HttpResponse:
        laboratory = form.cleaned_data["laboratory"]
        if laboratory is None and Laboratory.objects.count() == 1:
            laboratory = Laboratory.objects.get()
        try:
            sample = self.general_practitioner.collect_sample(
                patient=self.patient, laboratory=laboratory, now=timezone.now()
            )
        except ValidationError as error:
            for field, errors in error.error_dict.items():
                form.add_error(field if field in form.fields else None, errors)
            return self.form_invalid(form)
        messages.success(self.request, f"Sample {sample.sample_id} collected.")
        # Straight to the routine first test; any other is ordered from the sample.
        return redirect(
            "practice:new_order",
            patient=self.patient.pk,
            sample=sample.pk,
            test=Test.CBC,
        )


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
            placed = self.general_practitioner.place_order(
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
        laboratory = self.sample.laboratory
        connection = None if laboratory is None else messaging.connection_to(laboratory)
        if laboratory is not None and connection is not None:
            try:
                messaging.send_pending_lab_orders(
                    laboratory,
                    connection,
                    now=timezone.now(),
                    timeout=messaging.IN_REQUEST_TIMEOUT_SECONDS,
                )
            except grpc.RpcError as error:
                messages.warning(
                    self.request,
                    f"{laboratory} could not be reached, so the lab order is not"
                    " sent yet."
                    if messaging.unreachable(error)
                    else f"{laboratory} refused the lab order. Tell the administrator.",
                )
        return super().form_valid(form)
