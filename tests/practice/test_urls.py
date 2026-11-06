"""The practice's URLs follow one scheme: /<app>/<things>/ for an index,
/<app>/<things>/<id>/ for one thing, /<app>/<things>/<id>/<verb>/ for an action;
and its web app serves no other party's pages."""

import pytest
from django.urls import Resolver404, resolve, reverse


@pytest.mark.parametrize(
    ("name", "kwargs", "path"),
    [
        ("practice:patients", {}, "/practice/patients/"),
        ("practice:patient", {"pk": 3}, "/practice/patients/3/"),
        (
            "practice:collect_sample",
            {"patient": 3},
            "/practice/patients/3/collect-sample/",
        ),
        (
            "practice:order",
            {"patient": 3, "sample": 4, "test": "cbc"},
            "/practice/patients/3/samples/4/orders/cbc/",
        ),
        (
            "practice:patient_check_for_reports",
            {"patient": 3},
            "/practice/patients/3/check-for-reports/",
        ),
        ("practice:orders", {}, "/practice/orders/"),
        ("practice:check_for_reports", {}, "/practice/orders/check-for-reports/"),
    ],
)
def test_each_url_follows_the_scheme(
    name: str, kwargs: dict[str, object], path: str
) -> None:
    assert reverse(name, kwargs=kwargs) == path


@pytest.mark.parametrize("prefix", ["cohort/", "deployment/", "lab/", "training/"])
def test_another_partys_pages_are_not_served_here(prefix: str) -> None:
    with pytest.raises(Resolver404):
        resolve(f"/{prefix}")
