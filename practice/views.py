from functools import cached_property
from typing import Any

import grpc
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F, Prefetch, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import capfirst, pluralize
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, View

from practice import messaging
from practice.forms import CollectSampleForm, OrderForm
from practice.models import (
    Laboratory,
    Order,
    Patient,
    Sample,
)
from shared.accounts.mixins import RoleRequiredMixin
from shared.accounts.roles import Role
from shared.vocabulary import Test


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
        # Blood is collected first; tests are ordered on a sample afterwards (features/practice/ordering.feature).
        collect = reverse("practice:collect_sample", kwargs={"patient": patient.pk})
        laboratories = Laboratory.objects.count()
        # Several laboratories: the choice comes first, on its own page (features/practice/messaging.feature).
        collect_action = {"url": collect, "label": "Collect sample"}
        # Where a doctor waits for a lab report, so they need not go to Orders.
        check_action = {
            "url": reverse(
                "practice:patient_check_for_reports", kwargs={"patient": patient.pk}
            ),
            "label": "Check for reports",
        }
        # Each sample with the tests on it, in the order they were placed, so a
        # ferritin ordered beside a suggestion shows right under it (features/practice/reports.feature, features/practice/ordering.feature).
        # Only the newest opens; the others summarise their tests and whether a
        # lab report in them suggests ferritin.
        return {
            **super().get_context_data(**kwargs),
            "subtitle": f"{patient.get_registered_sex_display()}, aged {patient.age}",
            "actions": [collect_action] if laboratories > 1 else [],
            "post_actions": ([] if laboratories > 1 else [collect_action])
            + ([check_action] if laboratories > 0 else []),
            # Only an app with a laboratory to ask fetches lab reports (features/practice/messaging.feature).
            "fetches_reports": laboratories > 0,
            "samples": samples,
        }


class OrderIndexView(GeneralPractitionerRequiredMixin, ListView[Order]):
    template_name = "practice/orders.html"
    context_object_name = "orders"

    def get_queryset(self) -> QuerySet[Order]:
        orders = Order.objects.select_related("sample__patient").annotate(
            lab_report_released_at=F("lab_report__released_at")
        )
        return orders.order_by("-ordered_at", "-pk")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        # Only an app with a laboratory to ask can check for reports (features/practice/messaging.feature).
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
    now (features/practice/messaging.feature)."""

    def post(self, request: HttpRequest, patient: int | None = None) -> HttpResponse:
        # From a patient's page, back to it; from Orders, back there.
        back = reverse("practice:orders")
        if patient is not None:
            record = get_object_or_404(Patient, pk=patient)
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
    laboratory chosen; a practice with one laboratory skips the choice (features/practice/messaging.feature, features/practice/ordering.feature)."""

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
        laboratory = form.cleaned_data["laboratory"]
        if laboratory is None and Laboratory.objects.count() == 1:
            laboratory = Laboratory.objects.get()
        try:
            sample = self.patient.collect_sample(
                laboratory=laboratory, now=timezone.now()
            )
        except ValidationError as error:
            for field, errors in error.error_dict.items():
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
        if laboratory is not None:
            try:
                messaging.send_pending_lab_orders(
                    laboratory,
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
