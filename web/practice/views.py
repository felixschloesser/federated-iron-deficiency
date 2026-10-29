from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from web.practice import services
from web.practice.forms import OrderForm
from web.practice.models import GP, Order


def gp_of(request: HttpRequest) -> GP:
    """Return the GP who is logged in; anyone else may not use these pages."""
    user = request.user
    gp = GP.objects.filter(user=user).first() if user.is_authenticated else None
    if gp is None:
        raise PermissionDenied
    return gp


@login_required
@require_GET
def index(request: HttpRequest) -> HttpResponse:
    gp = gp_of(request)
    orders = Order.objects.filter(patient__gp=gp).select_related("patient")
    return render(
        request,
        "practice/index.html",
        {"orders": orders.order_by("-ordered_at", "-pk")},
    )


@login_required
@require_http_methods(["GET", "POST"])
def new_order(request: HttpRequest) -> HttpResponse:
    gp = gp_of(request)
    form = OrderForm(request.POST or None, gp=gp)
    if request.method == "POST" and form.is_valid():
        try:
            services.place_order(gp=gp, **form.cleaned_data, now=timezone.now())
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("practice:index")
    return render(request, "practice/new_order.html", {"form": form})
