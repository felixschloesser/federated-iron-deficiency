"""Every app's URLs follow one scheme: /<app>/<things>/ for an index,
/<app>/<things>/<id>/ for one thing, /<app>/<things>/<id>/<verb>/ for an action."""

import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    ("name", "kwargs", "path"),
    [
        ("training:runs", {}, "/training/runs/"),
        ("training:stop", {"run_id": 7}, "/training/runs/7/stop/"),
        ("training:models", {}, "/training/models/"),
        ("training:release", {"run_id": "7"}, "/training/models/7/release/"),
        ("deployment:screening_models", {}, "/deployment/screening-models/"),
        ("deployment:fetch_final_models", {}, "/deployment/screening-models/fetch/"),
        (
            "deployment:deploy",
            {"run_id": "7"},
            "/deployment/screening-models/7/deploy/",
        ),
        ("lab:test_requests", {}, "/lab/test-requests/"),
        ("lab:analysed", {}, "/lab/test-requests/analysed/"),
        ("lab:analyse", {"pk": 3}, "/lab/test-requests/3/analyse/"),
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
