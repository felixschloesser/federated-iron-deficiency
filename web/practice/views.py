from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, ListView

from web.practice import services
from web.practice.forms import OrderForm
from web.practice.models import GeneralPractitioner, Order, OrderQuerySet, Test


class GeneralPractitionerRequiredMixin(LoginRequiredMixin):
    """Lets in only a logged-in general practitioner, as `self.general_practitioner`."""

    general_practitioner: GeneralPractitioner

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        general_practitioner = GeneralPractitioner.objects.filter(user=user).first()
        if general_practitioner is None:
            raise PermissionDenied
        self.general_practitioner = general_practitioner
        return super().dispatch(request, *args, **kwargs)


class OrderIndexView(GeneralPractitionerRequiredMixin, ListView[Order]):
    template_name = "practice/index.html"
    context_object_name = "orders"

    def get_queryset(self) -> OrderQuerySet:
        orders = Order.objects.of_general_practitioner(
            self.general_practitioner
        ).select_related("patient")
        return orders.order_by("-ordered_at", "-pk")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        actions = [
            {
                "url": reverse("practice:new_order", kwargs={"test": test}),
                "label": f"Order {test.label}",
            }
            for test in Test
        ]
        return {**super().get_context_data(**kwargs), "actions": actions}


class NewOrderView(GeneralPractitionerRequiredMixin, FormView[OrderForm]):
    template_name = "practice/new_order.html"
    form_class = OrderForm
    success_url = reverse_lazy("practice:index")

    def get_form_kwargs(self) -> dict[str, Any]:
        return {
            **super().get_form_kwargs(),
            "general_practitioner": self.general_practitioner,
            "test": self.kwargs["test"],
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), "test": self.kwargs["test"]}

    def form_valid(self, form: OrderForm) -> HttpResponse:
        try:
            services.place_order(
                general_practitioner=self.general_practitioner,
                patient=form.cleaned_data["patient"],
                test=self.kwargs["test"],
                indication=form.cleaned_data.get("indication"),
                now=timezone.now(),
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Order placed.")
        return super().form_valid(form)
