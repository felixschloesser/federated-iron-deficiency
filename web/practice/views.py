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

from web.practice import grpc_client
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
        # Blood is collected first; tests are then ordered on the sample.
        collect = reverse("practice:collect_sample", kwargs={"patient": patient.pk})
        laboratories = Laboratory.objects.count()
        # With several laboratories, Collect sample links to a page to choose one;
        # with one, it posts straight away.
        collect_action = {"url": collect, "label": "Collect sample"}
        # Also offered here, so a doctor waiting for a lab report need not go to
        # Orders.
        check_action = {
            "url": reverse(
                "practice:patient_check_for_reports", kwargs={"patient": patient.pk}
            ),
            "label": "Check for reports",
        }
        # Samples come newest first, each with its tests in the order placed, so
        # a ferritin ordered beside a suggestion shows right below it. The page
        # opens only the newest sample; the others show a summary of their tests
        # and whether a lab report suggests ferritin.
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
    """Send pending lab orders to every laboratory and fetch new lab reports now."""

    def post(self, request: HttpRequest, patient: int | None = None) -> HttpResponse:
        # Redirect back to where the request came from: the patient's page or
        # Orders.
        back = reverse("practice:orders")
        if patient is not None:
            record = get_object_or_404(Patient, pk=patient)
            back = reverse("practice:patient", kwargs={"pk": record.pk})
        check = grpc_client.check_every_laboratory(now=timezone.now())
        for laboratory, error in check.failures:
            messages.error(
                request,
                f"{laboratory} could not be reached. Try again later."
                if grpc_client.unreachable(error)
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
    """Record a sample collected from a patient for the chosen laboratory, then
    go to ordering its CBC. A practice with one laboratory skips the choice."""

    template_name = "practice/collect_sample.html"
    form_class = CollectSampleForm

    @cached_property
    def patient(self) -> Patient:
        return get_object_or_404(Patient, pk=self.kwargs["patient"])

    def get_initial(self) -> dict[str, Any]:
        # Preselect the primary laboratory; the general practitioner may pick another.
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
                # Running out of sample IDs is not about a form field, so it goes
                # to the error summary.
                form.add_error(field if field in form.fields else None, errors)
            return self.form_invalid(form)
        messages.success(self.request, f"Sample {sample.sample_id} collected.")
        # Go straight to ordering the routine CBC; other tests are ordered from
        # the sample later.
        return redirect(
            "practice:order",
            patient=self.patient.pk,
            sample=sample.pk,
            test=Test.CBC,
        )


class NewOrderView(GeneralPractitionerRequiredMixin, FormView[OrderForm]):
    """Order one test on one of a patient's samples; the URL names both."""

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
        """If this test cannot be ordered on this sample at all (say, from a typed
        or stale URL), redirect back to the patient with the reason. place_order
        checks again, in case two tabs order at once."""
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
            grpc_client.send_pending_lab_orders(
                laboratory,
                now=timezone.now(),
                timeout=grpc_client.IN_REQUEST_TIMEOUT_SECONDS,
            )
        except grpc.RpcError as error:
            messages.warning(
                self.request,
                f"{laboratory} could not be reached, so the lab order is not sent yet."
                if grpc_client.unreachable(error)
                else f"{laboratory} refused the lab order. Tell the administrator.",
            )
        placed.refresh_from_db(fields=["reason_for_rejection"])
        if placed.reason_for_rejection is not None:
            messages.error(
                self.request,
                f"{laboratory} rejected the lab order: {placed.reason_for_rejection}",
            )
        return super().form_valid(form)
