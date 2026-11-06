"""The hospital's URLs follow one scheme: /<app>/<things>/ for an index,
/<app>/<things>/<id>/ for one thing, /<app>/<things>/<id>/<verb>/ for an action;
and its web app serves no other party's pages."""

import pytest
from django.urls import Resolver404, resolve, reverse


@pytest.mark.parametrize(
    ("name", "kwargs", "path"),
    [
        ("deployment:screening_models", {}, "/deployment/screening-models/"),
        (
            "deployment:deploy",
            {"run_id": "7"},
            "/deployment/screening-models/7/deploy/",
        ),
        ("lab:test_requests", {}, "/lab/test-requests/"),
        ("lab:analysed", {}, "/lab/test-requests/analysed/"),
        ("lab:analyse", {"pk": 3}, "/lab/test-requests/3/analyse/"),
    ],
)
def test_each_url_follows_the_scheme(
    name: str, kwargs: dict[str, object], path: str
) -> None:
    assert reverse(name, kwargs=kwargs) == path


@pytest.mark.parametrize("prefix", ["practice/", "training/"])
def test_another_partys_pages_are_not_served_here(prefix: str) -> None:
    with pytest.raises(Resolver404):
        resolve(f"/{prefix}")
