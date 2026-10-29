from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, ListView

from web.practice import services
from web.practice.forms import OrderForm
from web.practice.models import GP, Order, OrderQuerySet


class GPRequiredMixin(LoginRequiredMixin):
    """Lets in only a logged-in GP, available to the view as `self.gp`."""

    gp: GP

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        gp = GP.objects.filter(user=user).first()
        if gp is None:
            raise PermissionDenied
        self.gp = gp
        return super().dispatch(request, *args, **kwargs)


class OrderIndexView(GPRequiredMixin, ListView[Order]):
    template_name = "practice/index.html"
    context_object_name = "orders"

    def get_queryset(self) -> OrderQuerySet:
        orders = Order.objects.of_gp(self.gp).select_related("patient")
        return orders.order_by("-ordered_at", "-pk")


class NewOrderView(GPRequiredMixin, FormView[OrderForm]):
    template_name = "practice/new_order.html"
    form_class = OrderForm
    success_url = reverse_lazy("practice:index")

    def get_form_kwargs(self) -> dict[str, Any]:
        return {**super().get_form_kwargs(), "gp": self.gp}

    def form_valid(self, form: OrderForm) -> HttpResponse:
        try:
            services.place_order(
                gp=self.gp,
                patient=form.cleaned_data["patient"],
                test=form.cleaned_data["test"],
                indication=form.cleaned_data["indication"],
                now=timezone.now(),
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Order placed.")
        return super().form_valid(form)
