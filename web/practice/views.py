from functools import cached_property
from typing import Any

import grpc
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F, Prefetch, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import capfirst, pluralize
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, View

from web.practice import messaging
from web.practice.forms import CollectSampleForm, OrderForm
from web.practice.models import (
    Laboratory,
    Order,
    Patient,
    Sample,
)
from web.shared.accounts.mixins import RoleRequiredMixin
from web.shared.accounts.roles import Role
from web.shared.vocabulary import Test


class GeneralPractitionerRequiredMixin(RoleRequiredMixin):
    role = Role.GENERAL_PRACTITIONER


class PatientIndexView(GeneralPractitionerRequiredMixin, ListView[Patient]):
    template_name = "practice/patients.html"
    context_object_name = "patients"

    def get_queryset(self) -> QuerySet[Patient]:
        patients = Patient.objects.with_ferritin_suggested()
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
    """One of the practice's patients."""

    template_name = "practice/patient.html"
    context_object_name = "patient"

    def get_queryset(self) -> QuerySet[Patient]:
        return Patient.objects.all()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        patient = self.object
        samples = (
            patient.samples.select_related("laboratory", "sample_id")
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
        # Blood is collected first; tests are ordered on a sample afterwards.
        collect = reverse("practice:collect_sample", kwargs={"patient": patient.pk})
        laboratories = Laboratory.objects.count()
        # Several laboratories: the choice comes first, on its own page.
        collect_action = {"url": collect, "label": "Collect sample"}
        # Where a doctor waits for a lab report, so they need not go to Orders.
        check_action = {
            "url": reverse(
                "practice:patient_check_for_reports", kwargs={"patient": patient.pk}
            ),
            "label": "Check for reports",
        }
        # Each sample with the tests on it, in the order they were placed, so a
        # ferritin ordered beside a suggestion shows right under it.
        # Only the newest opens; the others summarise their tests and whether a
        # lab report in them suggests ferritin.
        return {
            **super().get_context_data(**kwargs),
            "subtitle": f"{patient.get_registered_sex_display()}, aged {patient.age}",
            "actions": [collect_action] if laboratories > 1 else [],
            "post_actions": ([] if laboratories > 1 else [collect_action])
            + [check_action],
            "samples": samples,
        }


class OrderIndexView(GeneralPractitionerRequiredMixin, ListView[Order]):
    template_name = "practice/orders.html"
    context_object_name = "orders"

    def get_queryset(self) -> QuerySet[Order]:
        orders = Order.objects.select_related(
            "sample__patient", "sample__sample_id"
        ).annotate(lab_report_released_at=F("lab_report__released_at"))
        return orders.order_by("-ordered_at", "-pk")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        post_actions = [
            {"url": reverse("practice:check_for_reports"), "label": "Check for reports"}
        ]
        return {**super().get_context_data(**kwargs), "post_actions": post_actions}


class CheckForReportsView(GeneralPractitionerRequiredMixin, View):
    """Sends pending lab orders and fetches new lab reports from every laboratory
    now (tests/practice/test_messaging.py)."""

    def post(self, request: HttpRequest, patient: int | None = None) -> HttpResponse:
        # From a patient's page, back to it; from Orders, back there.
        back = reverse("practice:orders")
        if patient is not None:
            record = get_object_or_404(Patient, pk=patient)
            back = reverse("practice:patient", kwargs={"pk": record.pk})
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
    laboratory chosen; a practice with one laboratory skips the choice (features/practice/ordering.feature)."""

    template_name = "practice/collect_sample.html"
    form_class = CollectSampleForm

    @cached_property
    def patient(self) -> Patient:
        return get_object_or_404(Patient, pk=self.kwargs["patient"])

    def get_initial(self) -> dict[str, Any]:
        # The primary laboratory preselected; the general practitioner may pick another.
        return {"laboratory": Laboratory.objects.primary()}

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), "patient": self.patient}

    def form_valid(self, form: CollectSampleForm) -> HttpResponse:
        try:
            sample = self.patient.collect_sample(
                laboratory=form.cleaned_data["laboratory"], now=timezone.now()
            )
        except ValidationError as error:
            for field, errors in error.error_dict.items():
                # The stock of sample IDs is no field of the form: the summary says it.
                form.add_error(field if field in form.fields else None, errors)
            return self.form_invalid(form)
        messages.success(self.request, f"Sample {sample.sample_id} collected.")
        # Straight to the routine first test; any other is ordered from the sample.
        return redirect(
            "practice:order",
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
        return get_object_or_404(Patient, pk=self.kwargs["patient"])

    @cached_property
    def sample(self) -> Sample:
        return get_object_or_404(
            self.patient.samples.select_related("sample_id"), pk=self.kwargs["sample"]
        )

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

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return self.refused() or super().get(request, *args, **kwargs)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return self.refused() or super().post(request, *args, **kwargs)

    def refused(self) -> HttpResponse | None:
        """An order refused whatever its indication (a typed or stale URL): back to
        the patient, with why. place_order checks again, for two tabs at once."""
        refusal = self.sample.order_refusal(
            test=self.kwargs["test"], now=timezone.now()
        )
        if refusal is None:
            return None
        for message in refusal.messages:
            messages.error(self.request, message)
        return redirect("practice:patient", pk=self.patient.pk)

    def get_success_url(self) -> str:
        return reverse("practice:patient", kwargs={"pk": self.patient.pk})

    def form_valid(self, form: OrderForm) -> HttpResponse:
        try:
            placed = self.sample.place_order(
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
        try:
            messaging.send_pending_lab_orders(
                laboratory,
                now=timezone.now(),
                timeout=messaging.IN_REQUEST_TIMEOUT_SECONDS,
            )
        except grpc.RpcError as error:
            messages.warning(
                self.request,
                f"{laboratory} could not be reached, so the lab order is not sent yet."
                if messaging.unreachable(error)
                else f"{laboratory} refused the lab order. Tell the administrator.",
            )
        placed.refresh_from_db(fields=["reason_for_rejection"])
        if placed.reason_for_rejection is not None:
            messages.error(
                self.request,
                f"{laboratory} rejected the lab order: {placed.reason_for_rejection}",
            )
        return super().form_valid(form)
